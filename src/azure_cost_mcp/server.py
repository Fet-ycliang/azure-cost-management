"""Azure Cost MCP server 建立與工具註冊。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import httpx
from azure.core.exceptions import AzureError
from mcp.server.fastmcp import FastMCP

from .auth import create_m365_credential
from .azure_management import AzureManagementApiClient, AzureManagementApiError
from .config import Settings, get_settings
from .cost_management import CostManagementClient
from .databricks_mcp import DatabricksMcpClient, DatabricksMcpClientError
from .embedding import DatabricksEmbeddingClient
from .formatting import to_response
from .lakebase import LakebaseClient
from .learn import LearnSearchClient, LearnSearchError
from .models import (
    ConnectionValidationParams,
    CostTrendParams,
    DatabricksQueryParams,
    DatabricksQuerySource,
    DepartmentCostParams,
    LearnSearchParams,
    ResponseOptions,
    SavingsRecommendationParams,
    StorageExportsParams,
    TagApplyParams,
    TagDiffParams,
    TagEmbedParams,
    TagInventoryParams,
    TagSuggestParams,
    TrendGranularity,
    UntaggedResourcesParams,
)
from .resource_graph import ResourceGraphClient
from .storage import StorageClientError, StorageExportClient

PROJECT_PRIORITIES = [
    "Azure Databricks",
    "Storage",
    "VM",
    "Network egress",
]

USE_CASES = [
    "查詢部門費用",
    "查詢節費方向與優化建議",
    "查詢費用趨勢",
    "找出未打標記的服務或資源",
    "透過 Databricks MCP server 做成本查詢與 SQL 分析",
]

IMPLEMENTED_TOOLS = [
    "azure_cost_get_bootstrap_status",
    "azure_cost_validate_connections",
    "azure_cost_get_planned_capabilities",
    "azure_cost_department_cost",
    "azure_cost_cost_trend",
    "azure_cost_cost_saving_opportunities",
    "azure_cost_databricks_query",
    "azure_cost_untagged_resources",
    "azure_cost_list_storage_exports",
    "azure_cost_tag_inventory",
    "azure_cost_tag_diff",
    "azure_cost_tag_apply",
    "azure_cost_embed_tags",
    "azure_cost_tag_suggest",
    "azure_cost_learn_search",
]

def _to_float(value: Any) -> float:
    """將 cost 欄位轉為 float。"""
    if isinstance(value, dict):
        value = value.get("value", 0)
    if value in (None, ""):
        return 0.0
    return float(value)


def _round_cost(value: Any) -> float:
    """統一 cost 精度。"""
    return round(_to_float(value), 4)


def _detect_cost_field(records: list[dict[str, Any]]) -> str:
    """找出成本欄位。"""
    if not records:
        return "PreTaxCost"
    for candidate in ("PreTaxCost", "Cost", "totalCost"):
        if candidate in records[0]:
            return candidate
    for key, value in records[0].items():
        if isinstance(value, (int, float)):
            return key
    return "PreTaxCost"


def _detect_group_field(records: list[dict[str, Any]], preferred: str | None = None) -> str:
    """找出分組欄位。"""
    if not records:
        return preferred or "group"
    reserved = {"PreTaxCost", "Cost", "totalCost", "Currency", "UsageDate"}
    if preferred and preferred in records[0]:
        return preferred
    for key in records[0]:
        if key not in reserved:
            return key
    return preferred or "group"


def _detect_currency(records: list[dict[str, Any]]) -> str | None:
    """找出幣別欄位。"""
    for record in records:
        currency = record.get("Currency")
        if currency:
            return str(currency)
    return None


def _normalize_group_value(value: Any) -> str:
    """正規化分組值。"""
    if value in (None, "", "null"):
        return "(untagged)"
    return str(value)


def _normalize_trend_date(value: Any, granularity: TrendGranularity) -> str:
    """將 Cost Management 回傳日期轉成 ISO-like 顯示格式。"""
    if value in (None, ""):
        return "-"
    text = str(value)
    if text.isdigit() and len(text) == 8:
        parsed = datetime.strptime(text, "%Y%m%d")
        return parsed.date().isoformat()
    if text.isdigit() and len(text) == 6 and granularity == TrendGranularity.MONTHLY:
        return f"{text[:4]}-{text[4:6]}"
    return text


def _service_hypothesis(service_name: str) -> str:
    normalized = service_name.lower()
    if "databricks" in normalized:
        return (
            "檢查 job cluster / all-purpose cluster 比例、auto-stop、warehouse idle timeout、"
            "Photon 與 DBU 版本設定。"
        )
    if any(keyword in normalized for keyword in ("virtual machines", "virtual machine", "vm")):
        return "檢查 Reservation / Savings Plan、rightsizing、排程關機與 Azure Hybrid Benefit。"
    if "storage" in normalized or "blob" in normalized or "disk" in normalized:
        return "檢查 Hot/Cool/Cold 分層、LRS/ZRS 搭配、snapshot/version 清理與 lifecycle policy。"
    if any(keyword in normalized for keyword in ("bandwidth", "data transfer", "egress", "network")):
        return "檢查跨區流量、NAT / outbound 流量與 Databricks、Storage 是否同區。"
    if "app service" in normalized or "web app" in normalized:
        return "檢查 App Service Plan 利用率、autoscale、是否適合改為 ACA 或以 Savings Plan 吃掉穩定 compute。"
    return "建議依 meter、region、resource group 與使用模式進一步拆分，再決定是否適用 Reservation 或架構優化。"


def _build_optimization_hypotheses(service_costs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """根據主要成本服務產出對應假說。"""
    hypotheses = []
    for service in service_costs:
        service_name = service["service_name"]
        hypotheses.append(
            {
                "service_name": service_name,
                "cost": service["cost"],
                "focus": _service_hypothesis(service_name),
            }
        )
    return hypotheses


def _annotate_missing_tags(
    resources: list[dict[str, Any]],
    required_tag_keys: list[str],
) -> list[dict[str, Any]]:
    """補上缺漏的 tag keys。"""
    annotated = []
    for resource in resources:
        tags = resource.get("tags") or {}
        missing_tags = [
            tag_key for tag_key in required_tag_keys if not str(tags.get(tag_key, "")).strip()
        ]
        annotated.append(
            {
                "id": resource.get("id"),
                "name": resource.get("name"),
                "type": resource.get("type"),
                "resource_group": resource.get("resourceGroup"),
                "location": resource.get("location"),
                "subscription_id": resource.get("subscriptionId"),
                "missing_tags": missing_tags,
                "tags": tags,
            }
        )
    return annotated


def _summarize_missing_tags(resources: list[dict[str, Any]]) -> dict[str, Any]:
    """彙整未標記資源摘要。"""
    by_type = Counter(resource["type"] for resource in resources)
    by_tag = Counter(
        missing_tag
        for resource in resources
        for missing_tag in resource.get("missing_tags", [])
    )
    return {
        "resource_count": len(resources),
        "counts_by_type": dict(by_type.most_common()),
        "counts_by_missing_tag": dict(by_tag.most_common()),
    }


def _load_desired_files(
    desired_dir: Path,
    rg_filter: list[str] | None = None,
    subscription_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    """讀取 desired tags JSON 目錄，回傳扁平化條目清單。"""
    if not desired_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    rg_lower = {r.lower() for r in rg_filter} if rg_filter else None
    for json_file in sorted(desired_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            if rg_lower and (entry.get("resource_group") or "").lower() not in rg_lower:
                continue
            if subscription_filter and entry.get("subscription_id") not in subscription_filter:
                continue
            entries.append(entry)
    return entries


def _compute_tag_diff(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """計算 desired vs current 的 tag diff（merge 語意：只計算新增與修改）。"""
    result: list[dict[str, Any]] = []
    for entry in entries:
        current: dict[str, str] = {k: str(v or "") for k, v in (entry.get("current_tags") or {}).items()}
        desired: dict[str, str] = {k: str(v or "") for k, v in (entry.get("desired_tags") or {}).items()}

        added: dict[str, str] = {}
        modified: dict[str, dict[str, str]] = {}
        unchanged: dict[str, str] = {}

        for key, dval in desired.items():
            dval = dval.strip()
            cval = current.get(key, "").strip()
            if not dval:
                continue
            if not cval:
                added[key] = dval
            elif cval != dval:
                modified[key] = {"from": cval, "to": dval}
            else:
                unchanged[key] = dval

        if added or modified:
            result.append(
                {
                    "resource_id": entry.get("resource_id", ""),
                    "name": entry.get("name", ""),
                    "type": entry.get("type", ""),
                    "resource_group": entry.get("resource_group", ""),
                    "subscription_id": entry.get("subscription_id", ""),
                    "added": added,
                    "modified": modified,
                    "unchanged": unchanged,
                }
            )
    return result


def _format_diff_table(diff_entries: list[dict[str, Any]]) -> str:
    """把 diff 條目轉成 Markdown 表格字串。"""
    if not diff_entries:
        return "（無需更新的資源）"

    lines = [
        "| 資源名稱 | RG | 訂閱 | Tag Key | 動作 | 目前值 | 期望值 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in diff_entries:
        name = entry["name"]
        rg = entry["resource_group"]
        sub = entry["subscription_id"]
        for key, val in entry["added"].items():
            lines.append(f"| {name} | {rg} | {sub} | `{key}` | 新增 | （空） | {val} |")
        for key, change in entry["modified"].items():
            lines.append(f"| {name} | {rg} | {sub} | `{key}` | 修改 | {change['from']} | {change['to']} |")
    return "\n".join(lines)


def _write_json_cache(path: Path, payload: dict[str, Any]) -> None:
    """同步寫入 JSON 快取檔案（供 asyncio.to_thread 使用）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _build_tag_coverage_summary(
    resources: list[dict[str, Any]],
    required_keys: list[str],
) -> dict[str, Any]:
    """計算 tag 覆蓋率，按 resource group 彙整。"""
    by_rg: dict[str, dict[str, Any]] = {}
    tagged_total = 0

    for r in resources:
        tags = r.get("tags") or {}
        rg = r.get("resourceGroup") or "(unknown)"
        missing = [k for k in required_keys if not str(tags.get(k, "")).strip()]
        is_fully_tagged = not missing

        if is_fully_tagged:
            tagged_total += 1

        entry = by_rg.setdefault(
            rg, {"total": 0, "tagged": 0, "missing_key_counts": Counter()}
        )
        entry["total"] += 1
        if is_fully_tagged:
            entry["tagged"] += 1
        else:
            for k in missing:
                entry["missing_key_counts"][k] += 1

    total = len(resources)
    coverage_pct = round(tagged_total / total * 100, 1) if total > 0 else 0.0

    rg_summary = sorted(
        [
            {
                "resource_group": rg,
                "total": data["total"],
                "tagged": data["tagged"],
                "untagged": data["total"] - data["tagged"],
                "coverage_pct": round(data["tagged"] / data["total"] * 100, 1),
                "top_missing_keys": dict(data["missing_key_counts"].most_common(5)),
            }
            for rg, data in by_rg.items()
        ],
        key=lambda x: x["coverage_pct"],
    )

    return {
        "tagged_count": tagged_total,
        "untagged_count": total - tagged_total,
        "coverage_pct": coverage_pct,
        "by_resource_group": rg_summary,
    }


def _normalize_savings_plan_recommendations(
    recommendations: list[dict[str, Any]],
    *,
    top: int,
) -> list[dict[str, Any]]:
    normalized = []
    for recommendation in recommendations:
        properties = recommendation.get("properties", {})
        details = properties.get("recommendationDetails", {})
        normalized.append(
            {
                "scope": properties.get("scope"),
                "term": properties.get("term"),
                "arm_sku_name": properties.get("armSkuName"),
                "currency": properties.get("currencyCode"),
                "commitment_amount": details.get("commitmentAmount"),
                "savings_amount": _round_cost(details.get("savingsAmount")),
                "savings_percentage": details.get("savingsPercentage"),
                "coverage_percentage": details.get("coveragePercentage"),
                "average_utilization_percentage": details.get("averageUtilizationPercentage"),
                "wastage_cost": _round_cost(details.get("wastageCost")),
            }
        )
    normalized.sort(key=lambda item: item["savings_amount"], reverse=True)
    return normalized[:top]


def _normalize_reservation_recommendations(
    recommendations: list[dict[str, Any]],
    *,
    top: int,
) -> list[dict[str, Any]]:
    normalized = []
    for recommendation in recommendations:
        properties = recommendation.get("properties", {})
        net_savings = properties.get("netSavings")
        currency = None
        if isinstance(net_savings, dict):
            currency = net_savings.get("currency")
        normalized.append(
            {
                "scope": properties.get("scope"),
                "term": properties.get("term"),
                "resource_type": properties.get("resourceType"),
                "sku": recommendation.get("sku") or properties.get("skuName"),
                "location": recommendation.get("location") or properties.get("location"),
                "recommended_quantity": properties.get("recommendedQuantity"),
                "net_savings": _round_cost(net_savings),
                "currency": currency,
            }
        )
    normalized.sort(key=lambda item: item["net_savings"], reverse=True)
    return normalized[:top]


def _build_connection_check(
    name: str,
    *,
    status: str,
    configured: bool,
    detail: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """建立單一連線檢查結果。"""
    payload: dict[str, Any] = {
        "name": name,
        "status": status,
        "configured": configured,
    }
    if detail:
        payload["detail"] = detail
    if error:
        payload["error"] = error
    return payload


def _summarize_connection_checks(results: list[dict[str, Any]]) -> dict[str, int]:
    """彙整連線檢查結果。"""
    status_counts = Counter(result["status"] for result in results)
    return {
        "total": len(results),
        "ok": status_counts.get("ok", 0),
        "failed": status_counts.get("failed", 0),
        "skipped": status_counts.get("skipped", 0),
    }


def _build_databricks_query_arguments(params: DatabricksQueryParams) -> dict[str, Any]:
    """將本地 Databricks query 參數轉成遠端 tool 輸入。"""
    arguments: dict[str, Any] = {}
    if params.question is not None:
        arguments["question"] = params.question
    if params.sql is not None:
        arguments["sql"] = params.sql
    if params.catalog is not None:
        arguments["catalog"] = params.catalog
    if params.schema_name is not None:
        arguments["schema_name"] = params.schema_name
    if params.arguments:
        arguments.update(params.arguments)
    return arguments


def _resolve_databricks_query_target(
    settings: Settings,
    source: DatabricksQuerySource,
) -> dict[str, Any]:
    """解析 Databricks query 應使用的 Genie source 設定。"""
    if source is DatabricksQuerySource.ACTUAL:
        display_name = "ActualCost"
        server_env_var_name = (
            "DATABRICKS_MCP_ACTUAL_SERVER_URL 或 DATABRICKS_MCP_SERVER_URL"
        )
        tool_env_var_name = (
            "DATABRICKS_MCP_ACTUAL_QUERY_TOOL_NAME 或 DATABRICKS_MCP_QUERY_TOOL_NAME"
        )
    else:
        display_name = "AmortizedCost"
        server_env_var_name = (
            "DATABRICKS_MCP_AMORTIZED_SERVER_URL 或 DATABRICKS_MCP_SERVER_URL"
        )
        tool_env_var_name = (
            "DATABRICKS_MCP_AMORTIZED_QUERY_TOOL_NAME 或 DATABRICKS_MCP_QUERY_TOOL_NAME"
        )

    server_url, tool_name = settings.resolve_databricks_query_target(source.value)
    return {
        "query_source": source.value,
        "display_name": display_name,
        "server_url": server_url,
        "server_env_var_name": server_env_var_name,
        "tool_name": tool_name,
        "tool_env_var_name": tool_env_var_name,
        "configured": bool(server_url and tool_name),
        "settings": settings.model_copy(
            update={
                "databricks_mcp_server_url": server_url,
                "databricks_mcp_query_tool_name": tool_name,
            }
        ),
    }


def _ensure_databricks_query_target_configured(target: dict[str, Any]) -> None:
    """確認 Databricks query target 已完整設定。"""
    missing = []
    if not target["server_url"]:
        missing.append(target["server_env_var_name"])
    if not target["tool_name"]:
        missing.append(target["tool_env_var_name"])
    if missing:
        raise ValueError(
            f"{target['display_name']} Databricks query target 尚未完整設定："
            + ", ".join(missing)
        )


def _format_check_error(error: Exception) -> str:
    """將例外轉成可讀訊息。"""
    current: BaseException = error
    seen: set[int] = set()

    while True:
        marker = id(current)
        if marker in seen:
            break
        seen.add(marker)

        if isinstance(current, BaseExceptionGroup) and current.exceptions:
            current = current.exceptions[0]
            continue

        next_error = current.__cause__
        if next_error is None and not current.__suppress_context__:
            next_error = current.__context__
        if next_error is None:
            break
        current = next_error

    return f"{type(current).__name__}: {current}"


async def _run_connection_checks(
    *,
    settings: Settings,
    cost_client: CostManagementClient,
    resource_graph_client: ResourceGraphClient,
    databricks_client: DatabricksMcpClient,
    storage_client: StorageExportClient,
    subscriptions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """依序驗證成本、治理、儲存與 Databricks 連線。"""
    results: list[dict[str, Any]] = []
    today = date.today()

    if settings.azure_cost_management_scope:
        try:
            await cost_client.query_usage(
                start_date=today,
                end_date=today,
                granularity="None",
            )
            results.append(
                _build_connection_check(
                    "cost_management",
                    status="ok",
                    configured=True,
                    detail={
                        "scope": settings.azure_cost_management_scope,
                        "api_version": settings.azure_cost_management_api_version,
                    },
                )
            )
        except (
            ValueError,
            AzureError,
            AzureManagementApiError,
            httpx.HTTPError,
            Exception,
        ) as error:
            results.append(
                _build_connection_check(
                    "cost_management",
                    status="failed",
                    configured=True,
                    detail={"scope": settings.azure_cost_management_scope},
                    error=_format_check_error(error),
                )
            )
    else:
        results.append(
            _build_connection_check(
                "cost_management",
                status="skipped",
                configured=False,
                error="AZURE_COST_MANAGEMENT_SCOPE 尚未設定。",
            )
        )

    resolved_subscriptions = subscriptions or resource_graph_client.default_subscriptions()
    if resolved_subscriptions:
        try:
            resource_graph_result = await resource_graph_client.query_resources(
                "Resources | take 1",
                subscriptions=resolved_subscriptions,
                top=1,
            )
            sample_count = len(resource_graph_result.get("data", []))
            results.append(
                _build_connection_check(
                    "resource_graph",
                    status="ok",
                    configured=True,
                    detail={
                        "subscriptions": resolved_subscriptions,
                        "sample_count": sample_count,
                    },
                )
            )
        except (
            ValueError,
            AzureError,
            AzureManagementApiError,
            httpx.HTTPError,
            Exception,
        ) as error:
            results.append(
                _build_connection_check(
                    "resource_graph",
                    status="failed",
                    configured=True,
                    detail={"subscriptions": resolved_subscriptions},
                    error=_format_check_error(error),
                )
            )
    else:
        results.append(
            _build_connection_check(
                "resource_graph",
                status="skipped",
                configured=False,
                error="缺少可用的 subscription，無法驗證 Azure Resource Graph。",
            )
        )

    if settings.azure_cost_storage_account_url and settings.azure_cost_storage_container:
        try:
            blobs = await storage_client.list_cost_blobs(max_results=1)
            results.append(
                _build_connection_check(
                    "storage",
                    status="ok",
                    configured=True,
                    detail={
                        "account_url": settings.azure_cost_storage_account_url,
                        "container": settings.azure_cost_storage_container,
                        "sample_blob_count": len(blobs),
                    },
                )
            )
        except (AzureError, StorageClientError, Exception) as error:
            results.append(
                _build_connection_check(
                    "storage",
                    status="failed",
                    configured=True,
                    detail={
                        "account_url": settings.azure_cost_storage_account_url,
                        "container": settings.azure_cost_storage_container,
                    },
                    error=_format_check_error(error),
                )
            )
    else:
        results.append(
            _build_connection_check(
                "storage",
                status="skipped",
                configured=False,
                error="Azure Storage 連線設定未完整提供。",
            )
        )

    if databricks_client.is_configured():
        try:
            tools = await databricks_client.list_tools()
            results.append(
                _build_connection_check(
                    "databricks_mcp",
                    status="ok",
                    configured=True,
                    detail={
                        "server_url": settings.databricks_mcp_server_url,
                        "tool_count": len(tools),
                    },
                )
            )
        except (DatabricksMcpClientError, httpx.HTTPError, Exception) as error:
            results.append(
                _build_connection_check(
                    "databricks_mcp",
                    status="failed",
                    configured=True,
                    detail={"server_url": settings.databricks_mcp_server_url},
                    error=_format_check_error(error),
                )
            )
    else:
        results.append(
            _build_connection_check(
                "databricks_mcp",
                status="skipped",
                configured=False,
                error="DATABRICKS_MCP_SERVER_URL 尚未設定。",
            )
        )

    return results


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """建立 Azure Cost MCP server。"""
    current_settings = settings or get_settings()
    cost_client = CostManagementClient(current_settings)
    resource_graph_client = ResourceGraphClient(current_settings, credential_fn=create_m365_credential)
    amortized_databricks_query_target = _resolve_databricks_query_target(
        current_settings,
        DatabricksQuerySource.AMORTIZED,
    )
    actual_databricks_query_target = _resolve_databricks_query_target(
        current_settings,
        DatabricksQuerySource.ACTUAL,
    )
    databricks_client = DatabricksMcpClient(
        amortized_databricks_query_target["settings"]
    )
    storage_client = StorageExportClient(current_settings)
    management_client = AzureManagementApiClient(current_settings, credential_fn=create_m365_credential)
    lakebase_client = LakebaseClient(current_settings)
    embedding_client = DatabricksEmbeddingClient(current_settings)

    mcp = FastMCP(
        name="azure_cost_mcp",
        instructions=(
            "這是一個用於 Azure FinOps 查詢、趨勢分析、節費建議與 tag 治理的 MCP 服務。"
            "第一版優先聚焦 Azure Databricks、Storage、VM 與 Network egress。"
        ),
        host=current_settings.mcp_host,
        port=current_settings.mcp_port,
        streamable_http_path=current_settings.mcp_streamable_http_path,
        log_level="INFO",
    )

    @mcp.tool(
        name="azure_cost_validate_connections",
        annotations={
            "title": "驗證資料來源連線",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def azure_cost_validate_connections(params: ConnectionValidationParams) -> str:
        """驗證 Azure Cost MCP 所需的外部連線。"""

        checks = await _run_connection_checks(
            settings=current_settings,
            cost_client=cost_client,
            resource_graph_client=resource_graph_client,
            databricks_client=databricks_client,
            storage_client=storage_client,
            subscriptions=params.subscriptions,
        )
        payload = {
            "test_sequence": [
                "connection",
                "functional",
                "end_to_end",
            ],
            "summary": _summarize_connection_checks(checks),
            "checks": checks,
        }
        return to_response("Azure 外部連線驗證", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_get_bootstrap_status",
        annotations={
            "title": "取得初始化狀態",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def azure_cost_get_bootstrap_status(params: ResponseOptions) -> str:
        """取得目前 MCP 服務骨架與整合設定狀態。"""

        payload = {
            "server_name": "azure_cost_mcp",
            "default_transport": current_settings.mcp_transport,
            "streamable_http_path": current_settings.mcp_streamable_http_path,
            "implemented_tools": IMPLEMENTED_TOOLS,
            "integrations": {
                "azure_cost_management_scope_configured": bool(
                    current_settings.azure_cost_management_scope
                ),
                "default_department_tag_key": current_settings.azure_cost_department_tag_key,
                "azure_storage_configured": bool(
                    current_settings.azure_cost_storage_account_url
                    and current_settings.azure_cost_storage_container
                ),
                "databricks_mcp_server_configured": bool(
                    amortized_databricks_query_target["server_url"]
                ),
                "databricks_mcp_query_tool_configured": bool(
                    amortized_databricks_query_target["tool_name"]
                ),
                "databricks_mcp_default_query_source": "amortized",
                "databricks_mcp_amortized_query_configured": (
                    amortized_databricks_query_target["configured"]
                ),
                "databricks_mcp_actual_query_configured": (
                    actual_databricks_query_target["configured"]
                ),
            },
            "next_focus": PROJECT_PRIORITIES,
        }
        return to_response("Azure Cost MCP 初始化狀態", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_get_planned_capabilities",
        annotations={
            "title": "取得規劃能力",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def azure_cost_get_planned_capabilities(params: ResponseOptions) -> str:
        """取得目前已確認的第一版能力規劃。"""

        payload = {
            "use_cases": USE_CASES,
            "implemented_tools": IMPLEMENTED_TOOLS,
            "data_flow": [
                "Azure Cost Management REST API / 匯出資料 / FOCUS",
                "Azure Storage",
                "Databricks MCP server",
                "對外 MCP service",
            ],
            "remaining_focus": [
                "ACA / ACI / App Service / Web App 比較與成本選型",
                "APIM 選型",
                "Lakebase / SQL Server / Cosmos DB / Azure AI Search / pgvector 評估",
                "Storage LRS / ZRS 與 Hot / Cool / Cold 配置建議",
                "multi-tenant auth 與 subscription-to-tenant 對應策略",
            ],
            "tag_strategy": {
                "status": "另案規劃",
                "current_scope": "目前只保留未標記資源偵測，不提供維護功能",
            },
        }
        return to_response("Azure Cost MCP 規劃能力", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_department_cost",
        annotations={
            "title": "查詢部門費用",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_department_cost(params: DepartmentCostParams) -> str:
        """查詢部門費用，或列出各部門成本排名。"""

        start_date, end_date = params.resolved_window()
        department_tag_key = (
            params.department_tag_key or current_settings.azure_cost_department_tag_key
        )

        filters = None
        if params.department_name:
            filters = {
                "tags": {
                    "name": department_tag_key,
                    "operator": "In",
                    "values": [params.department_name],
                }
            }

        grouping = (
            [{"name": "ServiceName", "type": "Dimension"}]
            if params.department_name
            else [{"name": department_tag_key, "type": "TagKey"}]
        )
        result = await cost_client.query_usage(
            start_date=start_date,
            end_date=end_date,
            granularity="None",
            grouping=grouping,
            filters=filters,
        )
        records = cost_client.rows_to_records(result)
        cost_field = _detect_cost_field(records)
        currency = _detect_currency(records)

        if params.department_name:
            group_field = _detect_group_field(records, preferred="ServiceName")
            top_services = sorted(
                [
                    {
                        "service_name": _normalize_group_value(record.get(group_field)),
                        "cost": _round_cost(record.get(cost_field)),
                    }
                    for record in records
                ],
                key=lambda item: item["cost"],
                reverse=True,
            )[: params.top]
            payload = {
                "department_name": params.department_name,
                "department_tag_key": department_tag_key,
                "window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                "currency": currency,
                "total_cost": round(
                    sum(_round_cost(record.get(cost_field)) for record in records),
                    4,
                ),
                "top_services": top_services,
                "source": "Azure Cost Management Query API",
            }
        else:
            group_field = _detect_group_field(records, preferred=department_tag_key)
            departments = sorted(
                [
                    {
                        "department": _normalize_group_value(record.get(group_field)),
                        "cost": _round_cost(record.get(cost_field)),
                    }
                    for record in records
                ],
                key=lambda item: item["cost"],
                reverse=True,
            )[: params.top]
            payload = {
                "department_tag_key": department_tag_key,
                "window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                "currency": currency,
                "departments": departments,
                "source": "Azure Cost Management Query API",
            }

        return to_response("Azure 部門成本分析", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_cost_trend",
        annotations={
            "title": "查詢費用趨勢",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_cost_trend(params: CostTrendParams) -> str:
        """查詢費用趨勢。"""

        start_date, end_date = params.resolved_window()
        department_tag_key = (
            params.department_tag_key or current_settings.azure_cost_department_tag_key
        )

        filters_list = []
        if params.service_name:
            filters_list.append(
                {
                    "dimensions": {
                        "name": "ServiceName",
                        "operator": "In",
                        "values": [params.service_name],
                    }
                }
            )
        if params.department_name:
            filters_list.append(
                {
                    "tags": {
                        "name": department_tag_key,
                        "operator": "In",
                        "values": [params.department_name],
                    }
                }
            )

        filters = None
        if len(filters_list) == 1:
            filters = filters_list[0]
        elif filters_list:
            filters = {"and": filters_list}

        result = await cost_client.query_usage(
            start_date=start_date,
            end_date=end_date,
            granularity=params.granularity.value,
            filters=filters,
        )
        records = cost_client.rows_to_records(result)
        cost_field = _detect_cost_field(records)
        trend = [
            {
                "period": _normalize_trend_date(
                    record.get("UsageDate"),
                    params.granularity,
                ),
                "cost": _round_cost(record.get(cost_field)),
            }
            for record in records
        ]
        payload = {
            "window": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "granularity": params.granularity.value,
            "filters": {
                "service_name": params.service_name,
                "department_name": params.department_name,
                "department_tag_key": department_tag_key if params.department_name else None,
            },
            "currency": _detect_currency(records),
            "total_cost": round(sum(item["cost"] for item in trend), 4),
            "trend": trend,
            "source": "Azure Cost Management Query API",
        }
        return to_response("Azure 費用趨勢", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_cost_saving_opportunities",
        annotations={
            "title": "節費方向與建議",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_cost_saving_opportunities(
        params: SavingsRecommendationParams,
    ) -> str:
        """整合主要費用服務、Savings Plan 與 Reservation 建議。"""

        start_date, end_date = params.resolved_window()
        department_tag_key = (
            params.department_tag_key or current_settings.azure_cost_department_tag_key
        )

        filters = None
        if params.department_name:
            filters = {
                "tags": {
                    "name": department_tag_key,
                    "operator": "In",
                    "values": [params.department_name],
                }
            }

        service_result = await cost_client.query_usage(
            start_date=start_date,
            end_date=end_date,
            granularity="None",
            grouping=[{"name": "ServiceName", "type": "Dimension"}],
            filters=filters,
        )
        service_records = cost_client.rows_to_records(service_result)
        service_cost_field = _detect_cost_field(service_records)
        service_group_field = _detect_group_field(service_records, preferred="ServiceName")
        top_services = sorted(
            [
                {
                    "service_name": _normalize_group_value(record.get(service_group_field)),
                    "cost": _round_cost(record.get(service_cost_field)),
                }
                for record in service_records
            ],
            key=lambda item: item["cost"],
            reverse=True,
        )[: params.top]

        recommendation_errors = []
        savings_plan_recommendations = []
        reservation_recommendations = []

        if params.include_savings_plan:
            try:
                savings_plan_recommendations = _normalize_savings_plan_recommendations(
                    await cost_client.list_benefit_recommendations(
                        look_back_period=params.look_back_period.value,
                        term=params.savings_plan_term.value,
                        recommendation_scope=params.savings_plan_scope.value,
                        expand_usage=params.expand_savings_plan_usage,
                    ),
                    top=params.top,
                )
            except AzureManagementApiError as error:
                recommendation_errors.append(str(error))

        if params.include_reservation:
            try:
                reservation_recommendations = _normalize_reservation_recommendations(
                    await cost_client.list_reservation_recommendations(
                        look_back_period=params.look_back_period.value,
                        recommendation_scope=params.reservation_scope.value,
                        resource_type=params.reservation_resource_type.value,
                    ),
                    top=params.top,
                )
            except AzureManagementApiError as error:
                recommendation_errors.append(str(error))

        payload = {
            "window": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "department_name": params.department_name,
            "top_services": top_services,
            "optimization_hypotheses": _build_optimization_hypotheses(top_services),
            "savings_plan_recommendations": savings_plan_recommendations,
            "reservation_recommendations": reservation_recommendations,
            "recommendation_errors": recommendation_errors,
            "sources": [
                "Azure Cost Management Query API",
                "Azure Cost Management Benefit Recommendations API",
                "Azure Consumption Reservation Recommendations API",
            ],
        }
        return to_response("Azure 節費方向與優化建議", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_databricks_query",
        annotations={
            "title": "透過 Databricks 查詢",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_databricks_query(params: DatabricksQueryParams) -> str:
        """將自然語言或 SQL 原樣代理到 Databricks MCP query tool。"""

        query_target = (
            actual_databricks_query_target
            if params.query_source is DatabricksQuerySource.ACTUAL
            else amortized_databricks_query_target
        )
        _ensure_databricks_query_target_configured(query_target)
        query_client = DatabricksMcpClient(query_target["settings"])

        remote_result = await query_client.call_configured_tool(
            tool_name=query_target["tool_name"],
            env_var_name=query_target["tool_env_var_name"],
            purpose="databricks-query",
            arguments=_build_databricks_query_arguments(params),
        )
        payload = {
            "mode": "databricks-proxy",
            "query_source": query_target["query_source"],
            "remote_server": query_target["server_url"],
            "remote_tool_name": query_target["tool_name"],
            "result": remote_result,
        }
        return to_response("Azure Databricks 查詢代理", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_untagged_resources",
        annotations={
            "title": "找出未標記資源",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_untagged_resources(params: UntaggedResourcesParams) -> str:
        """以 Azure Resource Graph 找出缺少必要 tags 的資源。"""

        raw_resources = await resource_graph_client.find_resources_missing_tags(
            required_tag_keys=params.required_tag_keys,
            subscriptions=params.subscriptions,
            max_results=params.max_results,
        )
        resources = _annotate_missing_tags(raw_resources, params.required_tag_keys)
        payload = {
            "required_tag_keys": params.required_tag_keys,
            "subscriptions": (
                params.subscriptions or resource_graph_client.default_subscriptions()
            ),
            "summary": _summarize_missing_tags(resources),
            "resources": resources,
            "source": "Azure Resource Graph",
        }
        return to_response("Azure 未標記資源", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_list_storage_exports",
        annotations={
            "title": "列出 Storage 匯出檔",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_list_storage_exports(params: StorageExportsParams) -> str:
        """列出 Azure Storage 中的成本匯出 blob。"""

        try:
            blobs = await storage_client.list_cost_blobs(
                prefix=params.prefix,
                max_results=params.max_results,
            )
        except StorageClientError as error:
            raise ValueError(str(error)) from error

        payload = {
            "storage_account_url": current_settings.azure_cost_storage_account_url,
            "container": current_settings.azure_cost_storage_container,
            "prefix": params.prefix or current_settings.azure_cost_storage_prefix,
            "blob_count": len(blobs),
            "blobs": blobs,
            "source": "Azure Blob Storage",
        }
        return to_response("Azure 成本匯出檔案", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_tag_inventory",
        annotations={
            "title": "Tag 盤點",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_tag_inventory(params: TagInventoryParams) -> str:
        """以 Azure Resource Graph 盤點所有資源的 tag 現況，輸出覆蓋率摘要並寫入快取。"""

        subscriptions = params.subscription_ids or resource_graph_client.m365_or_default_subscriptions()
        required_keys = params.required_tag_keys or current_settings.azure_cost_required_tag_keys_list

        today = date.today().isoformat()
        inventory_cache_dir = Path(current_settings.azure_cost_tag_inventory_cache_dir)

        all_resources: list[dict[str, Any]] = []
        cache_hit = False

        if not params.force_refresh and subscriptions:
            loaded: list[dict[str, Any]] = []
            all_found = True
            for sub_id in subscriptions:
                sub_slug = sub_id.strip("/").replace("/", "_")
                cache_file = inventory_cache_dir / today / f"{sub_slug}.json"
                if not cache_file.exists():
                    all_found = False
                    break
                try:
                    data = json.loads(
                        await asyncio.to_thread(cache_file.read_text, encoding="utf-8")
                    )
                    loaded.extend(data.get("resources", []))
                except (OSError, json.JSONDecodeError):
                    all_found = False
                    break
            if all_found:
                all_resources = loaded
                cache_hit = True

        if not cache_hit:
            all_resources = await resource_graph_client.get_all_resources_with_tags(
                subscriptions=subscriptions,
                resource_types=params.resource_types,
                resource_groups=params.resource_groups,
                max_results=params.max_results,
            )

            by_sub: dict[str, list[dict[str, Any]]] = {}
            for r in all_resources:
                sub_id = r.get("subscriptionId") or "unknown"
                by_sub.setdefault(sub_id, []).append(r)

            for sub_id, sub_resources in by_sub.items():
                sub_slug = sub_id.strip("/").replace("/", "_")
                cache_file = inventory_cache_dir / today / f"{sub_slug}.json"
                file_payload = {
                    "subscription_id": sub_id,
                    "snapshot_date": today,
                    "resource_count": len(sub_resources),
                    "resources": sub_resources,
                }
                await asyncio.to_thread(
                    _write_json_cache, cache_file, file_payload
                )

            if lakebase_client.is_configured():
                try:
                    if not lakebase_client.is_ready():
                        await lakebase_client.init()
                    await lakebase_client.upsert_tag_snapshots(all_resources, today)
                except Exception as exc:
                    logger.warning("Lakebase upsert_tag_snapshots failed: %s", exc)

        summary = _build_tag_coverage_summary(all_resources, required_keys)

        payload = {
            "subscriptions": subscriptions,
            "snapshot_date": today,
            "cache_hit": cache_hit,
            "required_tag_keys": required_keys,
            "total_resources": len(all_resources),
            "tagged_count": summary["tagged_count"],
            "untagged_count": summary["untagged_count"],
            "coverage_pct": summary["coverage_pct"],
            "by_resource_group": summary["by_resource_group"],
            "cache_dir": str(inventory_cache_dir / today),
            "source": "Azure Resource Graph",
        }
        return to_response("Azure Tag 盤點", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_tag_diff",
        annotations={
            "title": "Tag Diff",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )
    async def azure_cost_tag_diff(params: TagDiffParams) -> str:
        """比對 desired tags JSON 與快取快照，輸出需更新的 tag 清單（純 dry-run）。"""
        desired_dir = Path(
            params.desired_dir
            if params.desired_dir
            else Path(current_settings.azure_cost_tag_inventory_cache_dir) / "desired"
        )

        entries = await asyncio.to_thread(
            _load_desired_files,
            desired_dir,
            params.rg_filter,
            params.subscription_filter,
        )
        diff = _compute_tag_diff(entries)

        add_count = sum(len(d["added"]) for d in diff)
        mod_count = sum(len(d["modified"]) for d in diff)

        payload = {
            "desired_dir": str(desired_dir),
            "total_resources_with_changes": len(diff),
            "total_tags_to_add": add_count,
            "total_tags_to_modify": mod_count,
            "diff": diff,
            "diff_table": _format_diff_table(diff),
        }
        return to_response("Tag Diff", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_tag_apply",
        annotations={
            "title": "Tag Apply",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def azure_cost_tag_apply(params: TagApplyParams) -> str:
        """將 desired tags 批次回寫至 Azure（apply=True 且 AZURE_COST_TAG_APPLY_ENABLED=true 才實際執行）。"""
        desired_dir = Path(
            params.desired_dir
            if params.desired_dir
            else Path(current_settings.azure_cost_tag_inventory_cache_dir) / "desired"
        )

        entries = await asyncio.to_thread(
            _load_desired_files,
            desired_dir,
            params.rg_filter,
            params.subscription_filter,
        )
        diff = _compute_tag_diff(entries)

        will_apply = params.apply and current_settings.azure_cost_tag_apply_enabled
        results: list[dict[str, Any]] = []

        if will_apply and diff:
            batch_size = current_settings.azure_cost_tag_apply_batch_size
            delay_s = current_settings.azure_cost_tag_apply_delay_ms / 1000.0

            for i in range(0, len(diff), batch_size):
                batch = diff[i : i + batch_size]
                for entry in batch:
                    merged = {**entry["unchanged"], **entry["added"]}
                    for key, change in entry["modified"].items():
                        merged[key] = change["to"]
                    try:
                        await management_client.patch_resource_tags(
                            entry["resource_id"], tags=merged
                        )
                        results.append({"resource_id": entry["resource_id"], "status": "ok"})
                    except Exception as exc:
                        results.append(
                            {"resource_id": entry["resource_id"], "status": "error", "error": str(exc)}
                        )
                if delay_s > 0 and i + batch_size < len(diff):
                    await asyncio.sleep(delay_s)
        else:
            for entry in diff:
                results.append({"resource_id": entry["resource_id"], "status": "dry-run"})

        ok_count = sum(1 for r in results if r["status"] == "ok")
        error_count = sum(1 for r in results if r["status"] == "error")

        if diff and lakebase_client.is_configured():
            try:
                if not lakebase_client.is_ready():
                    await lakebase_client.init()
                await lakebase_client.record_tag_changes(
                    diff,
                    dry_run=not will_apply,
                    rationale=params.rationale or "",
                )
            except Exception as exc:
                logger.warning("Lakebase record_tag_changes failed: %s", exc)

        payload = {
            "mode": "apply" if will_apply else "dry-run",
            "apply_enabled": current_settings.azure_cost_tag_apply_enabled,
            "apply_requested": params.apply,
            "rationale": params.rationale,
            "total_resources": len(diff),
            "ok": ok_count,
            "errors": error_count,
            "dry_run_count": len(diff) - ok_count - error_count,
            "diff_table": _format_diff_table(diff),
            "results": results,
        }
        return to_response("Tag Apply", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_embed_tags",
        annotations={
            "title": "Tag Embedding 生成",
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )
    async def azure_cost_embed_tags(params: TagEmbedParams) -> str:
        """讀取 tag_snapshots 中指定日期的資源，生成 embedding 向量並寫入 tag_embeddings 表。

        需要 LAKEBASE_ENABLED=true、DATABRICKS_EMBEDDING_URL、DATABRICKS_TOKEN。
        """
        if not embedding_client.is_configured():
            payload: dict[str, Any] = {
                "status": "skipped",
                "reason": "Embedding 未設定：需要 DATABRICKS_EMBEDDING_URL 與 DATABRICKS_TOKEN。",
            }
            return to_response("Tag Embedding 生成", payload, params.response_format)

        if not lakebase_client.is_configured():
            payload = {
                "status": "skipped",
                "reason": "Lakebase 尚未設定（LAKEBASE_ENABLED=false 或缺少連線設定）。",
            }
            return to_response("Tag Embedding 生成", payload, params.response_format)

        try:
            if not lakebase_client.is_ready():
                await lakebase_client.init()

            from sqlalchemy import select
            from .lakebase_models import TagSnapshot

            # 讀取指定日期的 tag snapshots
            async with lakebase_client.session_scope() as session:
                conditions = [TagSnapshot.snapshot_date == params.snapshot_date]
                if params.resource_group:
                    conditions.append(TagSnapshot.resource_group == params.resource_group)
                if params.subscription_id:
                    conditions.append(TagSnapshot.subscription_id == params.subscription_id)
                stmt = select(TagSnapshot).where(*conditions)
                result = await session.execute(stmt)
                rows = result.scalars().all()

            resources = [
                {
                    "id": r.resource_id,
                    "name": r.name,
                    "type": r.type,
                    "resource_group": r.resource_group,
                    "tags": r.tags,
                }
                for r in rows
            ]

            if not resources:
                payload = {
                    "status": "skipped",
                    "reason": f"找不到 snapshot_date={params.snapshot_date} 的資源快照。",
                }
                return to_response("Tag Embedding 生成", payload, params.response_format)

            # 批次生成 embedding
            total = 0
            bs = params.batch_size
            for i in range(0, len(resources), bs):
                batch = resources[i : i + bs]
                written = await lakebase_client.upsert_tag_embeddings(
                    batch,
                    params.snapshot_date,
                    embedding_client.get_embeddings_batch,
                )
                total += written

        except Exception as exc:
            logger.warning("azure_cost_embed_tags failed: %s", exc)
            payload = {"status": "error", "reason": str(exc)}
            return to_response("Tag Embedding 生成", payload, params.response_format)

        payload = {
            "status": "ok",
            "snapshot_date": params.snapshot_date,
            "model": current_settings.databricks_embedding_model,
            "dim": current_settings.databricks_embedding_dim,
            "resources_embedded": total,
        }
        return to_response("Tag Embedding 生成", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_tag_suggest",
        annotations={
            "title": "Tag 相似性建議",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    )
    async def azure_cost_tag_suggest(params: TagSuggestParams) -> str:
        """依據 Lakebase tag 歷史快照，找出相似的已標記資源並建議 tag 值。

        若有設定 DATABRICKS_EMBEDDING_URL 且傳入 query_text，則使用 pgvector 向量搜尋；
        否則退回 SQL type/rg 篩選。
        """
        required_keys = params.required_tag_keys or current_settings.azure_cost_required_tag_keys_list

        if not lakebase_client.is_configured():
            payload: dict[str, Any] = {
                "status": "skipped",
                "reason": "Lakebase 尚未設定（LAKEBASE_ENABLED=false 或缺少連線設定）。",
                "suggestions": [],
            }
            return to_response("Tag 相似性建議", payload, params.response_format)

        try:
            if not lakebase_client.is_ready():
                await lakebase_client.init()

            use_vector = bool(params.query_text and embedding_client.is_configured())

            if use_vector:
                query_vec = await embedding_client.get_embedding(params.query_text)  # type: ignore[arg-type]
                suggestions = await lakebase_client.find_similar_by_vector(
                    query_vec,
                    resource_type=params.resource_type,
                    limit=params.limit,
                )
                search_mode = "vector"
            else:
                suggestions = await lakebase_client.find_similar_tagged_resources(
                    resource_type=params.resource_type or "",
                    resource_group=params.resource_group or "",
                    required_keys=required_keys,
                    limit=params.limit,
                )
                search_mode = "sql"

        except Exception as exc:
            payload = {
                "status": "error",
                "reason": str(exc),
                "suggestions": [],
            }
            return to_response("Tag 相似性建議", payload, params.response_format)

        payload = {
            "status": "ok",
            "search_mode": search_mode,
            "resource_type": params.resource_type,
            "resource_group": params.resource_group,
            "required_tag_keys": required_keys,
            "limit": params.limit,
            "suggestion_count": len(suggestions),
            "suggestions": suggestions,
        }
        return to_response("Tag 相似性建議", payload, params.response_format)

    learn_client = LearnSearchClient()

    @mcp.tool(
        name="azure_cost_learn_search",
        annotations={
            "title": "搜尋 Microsoft Learn 文件",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_learn_search(params: LearnSearchParams) -> str:
        """搜尋 Microsoft Learn 官方文件或互動課程模組。

        呼叫 learn.microsoft.com 公開 Search API（免認證）。
        適用於查詢 Azure 服務文件、Cost Management 說明、
        Databricks 操作指南、FinOps 最佳實踐等資訊。
        """
        try:
            results = await learn_client.search(
                params.query,
                top=params.top,
                locale=params.locale,
                category_filter=params.category_filter,
            )
        except LearnSearchError as exc:
            payload = {"status": "error", "reason": str(exc), "results": []}
            return to_response("Microsoft Learn 搜尋", payload, params.response_format)

        payload: dict[str, Any] = {
            "query": params.query,
            "locale": params.locale,
            "category_filter": params.category_filter or "（全部）",
            "result_count": len(results),
            "results": results,
        }
        return to_response("Microsoft Learn 搜尋", payload, params.response_format)

    return mcp
