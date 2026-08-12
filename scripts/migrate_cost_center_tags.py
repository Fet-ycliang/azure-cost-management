#!/usr/bin/env python3
"""將 Azure 資源的 legacy CostCenter tag 遷移為 cost_center。

遷移流程固定為：
1. 以相同值新增 cost_center。
2. 確認 Merge API 成功後，才刪除 CostCenter。

若兩個 key 同時存在但值不同，或 CostCenter 為空值，資源會列為衝突且不會修改。

用法：
    uv run python scripts/migrate_cost_center_tags.py
    uv run python scripts/migrate_cost_center_tags.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from azure.core.exceptions import ClientAuthenticationError

from azure_cost_mcp.auth import create_azure_credential, create_m365_credential
from azure_cost_mcp.azure_management import (
    MANAGEMENT_SCOPE,
    AzureManagementApiClient,
    AzureManagementApiError,
)
from azure_cost_mcp.config import Settings, get_settings
from azure_cost_mcp.resource_graph import ResourceGraphClient

LEGACY_TAG_KEY = "CostCenter"
STANDARD_TAG_KEY = "cost_center"
SUBSCRIPTIONS_API_VERSION = "2022-12-01"
MigrationAction = Literal["copy-and-delete", "delete-legacy", "conflict", "skip-empty"]
RETRYABLE_STATUS_CODES = {409, 412, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class MigrationPlan:
    """單一資源的 tag 遷移計畫。"""

    resource_id: str
    name: str
    resource_type: str
    resource_group: str
    subscription_id: str
    legacy_value: str
    standard_value: str
    action: MigrationAction


class TagMigrationClient:
    """在整個遷移期間重用 credential 與 HTTP 連線的 Azure tag client。"""

    def __init__(
        self,
        settings: Settings,
        credential_fn: Callable[[Settings], Any],
    ) -> None:
        self._settings = settings
        self._credential_fn = credential_fn
        self._credential: Any | None = None
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """建立可重用的 credential 與 HTTP client。"""
        self._credential = self._credential_fn(self._settings)
        self._client = httpx.AsyncClient(
            base_url=self._settings.azure_management_base_url,
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(60.0, read=120.0),
        )

    async def close(self) -> None:
        """釋放 HTTP 連線與 credential。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._credential is not None:
            await self._credential.close()
            self._credential = None

    async def patch_resource_tags(self, resource_id: str, *, tags: dict[str, str]) -> None:
        """以 Merge 語意新增或更新指定 tags。"""
        await self._patch_tags(resource_id, operation="Merge", tags=tags)

    async def delete_resource_tags(self, resource_id: str, *, tag_keys: list[str]) -> None:
        """刪除指定的 tag keys。"""
        if not tag_keys:
            raise ValueError("tag_keys 至少需要一個 tag key。")
        await self._patch_tags(
            resource_id,
            operation="Delete",
            tags={key: "" for key in tag_keys},
        )

    async def _patch_tags(
        self,
        resource_id: str,
        *,
        operation: Literal["Merge", "Delete"],
        tags: dict[str, str],
    ) -> None:
        """呼叫 Azure Tags API 套用指定操作。"""
        if self._credential is None or self._client is None:
            raise RuntimeError("TagMigrationClient 尚未啟動。")
        token = await self._credential.get_token(MANAGEMENT_SCOPE)
        response = await self._client.patch(
            f"{resource_id}/providers/Microsoft.Resources/tags/default",
            params={"api-version": "2021-04-01"},
            headers={"Authorization": f"Bearer {token.token}"},
            json={
                "operation": operation,
                "properties": {"tags": tags},
            },
        )
        if response.status_code != 200:
            raise AzureManagementApiError(AzureManagementApiClient._format_error(response))


class TagWriter(Protocol):
    """提供 tag Merge 與 Delete 操作的 client 介面。"""

    async def patch_resource_tags(self, resource_id: str, *, tags: dict[str, str]) -> None:
        """以 Merge 語意新增或更新指定 tags。"""

    async def delete_resource_tags(self, resource_id: str, *, tag_keys: list[str]) -> None:
        """刪除指定的 tag keys。"""


def build_migration_plan(resources: list[dict[str, Any]]) -> list[MigrationPlan]:
    """依目前 tags 建立不會覆寫衝突資料的遷移計畫。"""
    plans: list[MigrationPlan] = []
    seen_resource_ids: set[str] = set()

    for resource in resources:
        resource_id = str(resource.get("id") or "").strip()
        if not resource_id or resource_id.lower() in seen_resource_ids:
            continue
        seen_resource_ids.add(resource_id.lower())

        tags = resource.get("tags") or {}
        if LEGACY_TAG_KEY not in tags:
            continue

        legacy_value = str(tags.get(LEGACY_TAG_KEY) or "").strip()
        standard_value = str(tags.get(STANDARD_TAG_KEY) or "").strip()
        if not legacy_value:
            action: MigrationAction = "skip-empty"
        elif standard_value and standard_value != legacy_value:
            action = "conflict"
        elif standard_value:
            action = "delete-legacy"
        else:
            action = "copy-and-delete"

        plans.append(
            MigrationPlan(
                resource_id=resource_id,
                name=str(resource.get("name") or ""),
                resource_type=str(resource.get("type") or ""),
                resource_group=str(resource.get("resourceGroup") or ""),
                subscription_id=str(resource.get("subscriptionId") or ""),
                legacy_value=legacy_value,
                standard_value=standard_value,
                action=action,
            )
        )

    return sorted(plans, key=lambda plan: (plan.subscription_id, plan.resource_id.lower()))


def _load_retryable_resource_ids(report_file: str) -> set[str]:
    """從既有遷移報告找出因暫時性 Azure 錯誤失敗的資源。"""
    path = Path(report_file)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"無法讀取遷移報告：{path}；{error}") from error

    resource_ids: set[str] = set()
    for outcome in report.get("outcomes", []):
        if outcome.get("status") not in {"failed-merge", "failed-delete"}:
            continue
        match = re.search(r"status (\d+)", str(outcome.get("error") or ""))
        if match and int(match.group(1)) in RETRYABLE_STATUS_CODES:
            resource_id = str(outcome.get("resource_id") or "").strip()
            if resource_id:
                resource_ids.add(resource_id.lower())
    return resource_ids


async def _list_subscriptions(client: AzureManagementApiClient) -> dict[str, str]:
    """列出 client 可存取的訂閱 ID 與名稱。"""
    result = await client._request(
        "GET",
        "/subscriptions",
        params={"api-version": SUBSCRIPTIONS_API_VERSION},
        expected_statuses=(200,),
    )
    subscriptions: dict[str, str] = {}
    for item in (result or {}).get("value", []):
        subscription_id = str(item.get("subscriptionId") or "").strip()
        if subscription_id:
            subscriptions[subscription_id] = str(item.get("displayName") or subscription_id)
    return subscriptions


async def _get_resources(
    subscription_id: str,
    graph_clients: list[ResourceGraphClient],
) -> tuple[list[dict[str, Any]], str | None]:
    """用可用 credential 取得指定訂閱的資源與 tags。"""
    errors: list[str] = []
    for client in graph_clients:
        try:
            return (
                await client.get_all_resources_with_tags(
                    subscriptions=[subscription_id],
                    max_results=5000,
                ),
                None,
            )
        except (AzureManagementApiError, ClientAuthenticationError, httpx.HTTPError) as error:
            errors.append(str(error))
    return [], "；".join(errors)


async def _run_tag_operation(
    clients: list[TagWriter],
    operation: Callable[[TagWriter], Awaitable[Any]],
) -> str | None:
    """依序使用可用 credential 執行 tag 寫入，全部失敗才回傳錯誤。"""
    errors: list[str] = []
    for client in clients:
        try:
            await operation(client)
            return None
        except (AzureManagementApiError, ClientAuthenticationError, httpx.HTTPError) as error:
            errors.append(str(error))
    return "；".join(errors)


async def _apply_plan(
    plan: MigrationPlan,
    clients: list[TagWriter],
) -> tuple[str, str | None]:
    """執行單一遷移計畫，確保新增成功後才刪除 legacy key。"""
    if plan.action == "conflict":
        return "conflict", "CostCenter 與 cost_center 的值不同"
    if plan.action == "skip-empty":
        return "skipped", "CostCenter 為空值"

    if plan.action == "copy-and-delete":
        merge_error = await _run_tag_operation(
            clients,
            lambda client: client.patch_resource_tags(
                plan.resource_id,
                tags={STANDARD_TAG_KEY: plan.legacy_value},
            ),
        )
        if merge_error:
            return "failed-merge", merge_error

    delete_error = await _run_tag_operation(
        clients,
        lambda client: client.delete_resource_tags(
            plan.resource_id,
            tag_keys=[LEGACY_TAG_KEY],
        ),
    )
    if delete_error:
        return "failed-delete", delete_error
    return "migrated", None


async def _apply_plans_in_batches(
    plans: list[MigrationPlan],
    clients_by_subscription: dict[str, list[TagWriter]],
    *,
    batch_size: int,
    delay_seconds: float,
) -> list[dict[str, Any]]:
    """依既有 tag apply 設定分批執行遷移。"""
    outcomes: list[dict[str, Any]] = []
    for offset in range(0, len(plans), batch_size):
        batch = plans[offset : offset + batch_size]
        results = await asyncio.gather(
            *(
                _apply_plan(
                    plan,
                    clients_by_subscription.get(plan.subscription_id, []),
                )
                for plan in batch
            )
        )
        for plan, (status, error) in zip(batch, results, strict=True):
            record = asdict(plan)
            record["status"] = status
            record["error"] = error
            outcomes.append(record)
        if offset + batch_size < len(plans) and delay_seconds:
            await asyncio.sleep(delay_seconds)
    return outcomes


def _report_path(snapshot_date: str, report_file: str | None) -> Path:
    """解析遷移報告輸出路徑。"""
    if report_file:
        return Path(report_file)
    return Path(".cache") / "tag-review" / snapshot_date / "cost-center-migration.json"


async def run(args: argparse.Namespace) -> int:
    """載入可存取訂閱、產生計畫，並依需要執行 tag 遷移。"""
    get_settings.cache_clear()
    settings = get_settings()
    if settings.azure_cost_auth_mode != "service-principal":
        print(
            "[error] AZURE_COST_AUTH_MODE 必須設為 service-principal，避免遷移誤用 Azure CLI credential。",
            file=sys.stderr,
        )
        return 2

    azure_management_client = AzureManagementApiClient(settings)
    m365_management_client = AzureManagementApiClient(
        settings,
        credential_fn=create_m365_credential,
    )
    azure_graph_client = ResourceGraphClient(settings)
    m365_graph_client = ResourceGraphClient(settings, credential_fn=create_m365_credential)

    try:
        azure_subscriptions = await _list_subscriptions(azure_management_client)
        m365_subscriptions = await _list_subscriptions(m365_management_client)
    except (AzureManagementApiError, ClientAuthenticationError, httpx.HTTPError) as error:
        print(f"[error] 無法列出 Service Principal 可存取訂閱：{error}", file=sys.stderr)
        return 1

    subscription_names = {**m365_subscriptions, **azure_subscriptions}
    if not subscription_names:
        print("[error] Service Principal 沒有可存取的訂閱。", file=sys.stderr)
        return 1

    resources: list[dict[str, Any]] = []
    fetch_failures: dict[str, str] = {}
    for subscription_id in sorted(subscription_names):
        graph_clients: list[ResourceGraphClient] = []
        if subscription_id in azure_subscriptions:
            graph_clients.append(azure_graph_client)
        if subscription_id in m365_subscriptions:
            graph_clients.append(m365_graph_client)

        subscription_resources, error = await _get_resources(subscription_id, graph_clients)
        if error:
            fetch_failures[subscription_id] = error
            continue
        resources.extend(subscription_resources)

    plans = build_migration_plan(resources)
    if args.retry_report:
        try:
            retryable_resource_ids = _load_retryable_resource_ids(args.retry_report)
        except ValueError as error:
            print(f"[error] {error}", file=sys.stderr)
            return 2
        plans = [
            plan
            for plan in plans
            if plan.resource_id.lower() in retryable_resource_ids
        ]
    if args.actions:
        requested_actions = {action.strip() for action in args.actions.split(",") if action.strip()}
        invalid_actions = requested_actions - {
            "copy-and-delete",
            "delete-legacy",
            "conflict",
            "skip-empty",
        }
        if invalid_actions:
            print(
                f"[error] 不支援的 --actions 值：{', '.join(sorted(invalid_actions))}",
                file=sys.stderr,
            )
            return 2
        plans = [plan for plan in plans if plan.action in requested_actions]
    if not args.apply:
        outcomes = [
            {
                **asdict(plan),
                "status": "planned",
                "error": None,
            }
            for plan in plans
        ]
    else:
        azure_tag_client = TagMigrationClient(settings, create_azure_credential)
        m365_tag_client = TagMigrationClient(settings, create_m365_credential)
        await asyncio.gather(azure_tag_client.start(), m365_tag_client.start())
        try:
            clients_by_subscription: dict[str, list[TagWriter]] = {}
            for subscription_id in subscription_names:
                clients: list[TagWriter] = []
                if subscription_id in azure_subscriptions:
                    clients.append(azure_tag_client)
                if subscription_id in m365_subscriptions:
                    clients.append(m365_tag_client)
                clients_by_subscription[subscription_id] = clients
            outcomes = await _apply_plans_in_batches(
                plans,
                clients_by_subscription,
                batch_size=args.batch_size or settings.azure_cost_tag_apply_batch_size,
                delay_seconds=(
                    settings.azure_cost_tag_apply_delay_ms
                    if args.delay_ms is None
                    else args.delay_ms
                )
                / 1000.0,
            )
        finally:
            await asyncio.gather(azure_tag_client.close(), m365_tag_client.close())

    summary: dict[str, int] = {}
    for outcome in outcomes:
        status = str(outcome["status"])
        summary[status] = summary.get(status, 0) + 1

    report = {
        "snapshot_date": args.date,
        "apply": args.apply,
        "legacy_tag_key": LEGACY_TAG_KEY,
        "standard_tag_key": STANDARD_TAG_KEY,
        "retry_report": args.retry_report,
        "actions": args.actions,
        "subscriptions": subscription_names,
        "resources_scanned": len(resources),
        "fetch_failures": fetch_failures,
        "summary": summary,
        "outcomes": outcomes,
    }
    output_path = _report_path(args.date, args.report_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"可存取訂閱：{len(subscription_names)}；盤點資源：{len(resources)}")
    print(f"發現 legacy {LEGACY_TAG_KEY}：{len(plans)} 筆")
    for status, count in sorted(summary.items()):
        print(f"  {status}: {count}")
    if fetch_failures:
        print(f"無法盤點訂閱：{len(fetch_failures)}", file=sys.stderr)
    print(f"遷移報告：{output_path}")

    failed = any(
        outcome["status"] in {"conflict", "failed-merge", "failed-delete"} for outcome in outcomes
    )
    return 1 if failed or fetch_failures else 0


def main() -> int:
    """解析命令列參數並執行遷移。"""
    parser = argparse.ArgumentParser(
        description="將 Azure 資源的 CostCenter tag 遷移為 cost_center。"
    )
    parser.add_argument("--apply", action="store_true", help="實際執行遷移；未指定時只產生計畫。")
    parser.add_argument("--date", default=str(date.today()), help="報告日期，格式為 YYYY-MM-DD。")
    parser.add_argument("--report-file", help="遷移報告 JSON 路徑。")
    parser.add_argument(
        "--retry-report",
        help="只重試此報告中因 409、412、429 或 5xx 暫時性錯誤失敗的資源。",
    )
    parser.add_argument(
        "--actions",
        help="只處理指定動作，逗號分隔：copy-and-delete、delete-legacy、conflict、skip-empty。",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="覆寫每批資源數；未指定時使用 AZURE_COST_TAG_APPLY_BATCH_SIZE。",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=None,
        help="覆寫批次間等待毫秒；未指定時使用 AZURE_COST_TAG_APPLY_DELAY_MS。",
    )
    args = parser.parse_args()
    if args.batch_size is not None and args.batch_size < 1:
        parser.error("--batch-size 必須至少為 1。")
    if args.delay_ms is not None and args.delay_ms < 0:
        parser.error("--delay-ms 不可小於 0。")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
