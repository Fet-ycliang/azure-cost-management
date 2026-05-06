from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from azure_cost_mcp.azure_management import AzureManagementApiError
from azure_cost_mcp.cost_management import CostManagementClient as RealCostManagementClient
from azure_cost_mcp.storage import StorageClientError
from azure_cost_mcp import server as server_module
from mcp.server.fastmcp.exceptions import ToolError

from .helpers import make_settings


class FakeCostClient:
    rows_to_records = staticmethod(RealCostManagementClient.rows_to_records)

    def __init__(
        self,
        *,
        query_results: list[dict[str, Any]] | None = None,
        benefit_result: list[dict[str, Any]] | Exception | None = None,
        reservation_result: list[dict[str, Any]] | Exception | None = None,
    ) -> None:
        self.query_results = list(query_results or [])
        self.benefit_result = benefit_result if benefit_result is not None else []
        self.reservation_result = reservation_result if reservation_result is not None else []
        self.query_calls: list[dict[str, Any]] = []

    async def query_usage(self, **kwargs) -> dict[str, Any]:
        self.query_calls.append(kwargs)
        if not self.query_results:
            return {"properties": {"columns": [], "rows": []}}
        return self.query_results.pop(0)

    async def list_benefit_recommendations(self, **kwargs) -> list[dict[str, Any]]:
        if isinstance(self.benefit_result, Exception):
            raise self.benefit_result
        return self.benefit_result

    async def list_reservation_recommendations(self, **kwargs) -> list[dict[str, Any]]:
        if isinstance(self.reservation_result, Exception):
            raise self.reservation_result
        return self.reservation_result


class FakeResourceGraphClient:
    def __init__(
        self,
        *,
        resources: list[dict[str, Any]] | None = None,
        default_subscriptions: list[str] | None = None,
        m365_subscriptions: list[str] | None = None,
    ) -> None:
        self.resources = resources or []
        self._default_subscriptions = default_subscriptions or ["sub-default"]
        self._m365_subscriptions = m365_subscriptions or ["m365-sub-default"]
        self.query_calls: list[dict[str, Any]] = []
        self.find_calls: list[dict[str, Any]] = []
        self.inventory_calls: list[dict[str, Any]] = []

    async def query_resources(self, query: str, *, subscriptions=None, top=None, skip_token=None) -> dict[str, Any]:
        self.query_calls.append(
            {
                "query": query,
                "subscriptions": subscriptions,
                "top": top,
                "skip_token": skip_token,
            }
        )
        return {"data": self.resources[:top] if top else self.resources}

    async def find_resources_missing_tags(
        self,
        *,
        required_tag_keys: list[str],
        subscriptions: list[str] | None = None,
        resource_ids: list[str] | None = None,
        max_results: int,
    ) -> list[dict[str, Any]]:
        self.find_calls.append(
            {
                "required_tag_keys": required_tag_keys,
                "subscriptions": subscriptions,
                "resource_ids": resource_ids,
                "max_results": max_results,
            }
        )
        return self.resources[:max_results]

    async def get_all_resources_with_tags(
        self,
        *,
        subscriptions=None,
        resource_types=None,
        resource_groups=None,
        max_results=5000,
    ) -> list[dict[str, Any]]:
        self.inventory_calls.append(
            {
                "subscriptions": subscriptions,
                "resource_types": resource_types,
                "resource_groups": resource_groups,
                "max_results": max_results,
            }
        )
        return self.resources[:max_results]

    def default_subscriptions(self) -> list[str] | None:
        return self._default_subscriptions

    def m365_subscriptions(self) -> list[str] | None:
        return self._m365_subscriptions

    def m365_or_default_subscriptions(self) -> list[str] | None:
        return self._m365_subscriptions or self._default_subscriptions


class FakeDatabricksClient:
    def __init__(
        self,
        *,
        configured: bool = True,
        tools: list[dict[str, Any]] | None = None,
        configured_tool_result: dict[str, Any] | Exception | None = None,
    ) -> None:
        self.configured = configured
        self.tools = tools if tools is not None else [{"name": "query_tool"}]
        self.configured_tool_result = (
            configured_tool_result
            if configured_tool_result is not None
            else {
                "tool_name": "query_tool",
                "is_error": False,
                "structured_content": {"rows": 1},
                "content": [{"type": "text", "text": "ok"}],
                "available_tools": ["query_tool"],
            }
        )
        self.calls: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return self.configured

    async def list_tools(self) -> list[dict[str, Any]]:
        return self.tools

    async def call_configured_tool(
        self,
        *,
        tool_name: str | None,
        env_var_name: str,
        purpose: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "tool_name": tool_name,
                "env_var_name": env_var_name,
                "purpose": purpose,
                "arguments": arguments,
            }
        )
        if isinstance(self.configured_tool_result, Exception):
            raise self.configured_tool_result
        return self.configured_tool_result


class FakeStorageClient:
    def __init__(self, *, blobs: list[dict[str, Any]] | Exception | None = None) -> None:
        self.blobs = blobs if blobs is not None else []
        self.calls: list[dict[str, Any]] = []

    async def list_cost_blobs(self, *, prefix: str | None = None, max_results: int) -> list[dict[str, Any]]:
        self.calls.append({"prefix": prefix, "max_results": max_results})
        if isinstance(self.blobs, Exception):
            raise self.blobs
        return self.blobs[:max_results]


class FakeManagementClient:
    def __init__(self, *, patch_error: Exception | None = None) -> None:
        self.patch_calls: list[dict[str, Any]] = []
        self.patch_error = patch_error

    async def patch_resource_tags(
        self,
        resource_id: str,
        *,
        tags: dict[str, str],
        api_version: str = "2021-04-01",
    ) -> dict[str, Any] | None:
        self.patch_calls.append({"resource_id": resource_id, "tags": tags})
        if self.patch_error:
            raise self.patch_error
        return {"properties": {"tags": tags}}


class FakeLakebaseClient:
    def __init__(
        self,
        *,
        configured: bool = False,
        suggestions: list[dict[str, Any]] | None = None,
    ) -> None:
        self._configured = configured
        self._ready = False
        self._suggestions = suggestions or []
        self.init_calls = 0
        self.upsert_calls: list[dict[str, Any]] = []
        self.record_calls: list[dict[str, Any]] = []
        self.suggest_calls: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return self._configured

    def is_ready(self) -> bool:
        return self._ready

    async def init(self) -> None:
        self.init_calls += 1
        self._ready = True

    async def upsert_tag_snapshots(self, resources: list, snapshot_date: str) -> int:
        self.upsert_calls.append({"resources": resources, "snapshot_date": snapshot_date})
        return len(resources)

    async def record_tag_changes(
        self, diff_entries: list, *, dry_run: bool, rationale: str, applied_by: str = ""
    ) -> int:
        self.record_calls.append(
            {"diff_entries": diff_entries, "dry_run": dry_run, "rationale": rationale}
        )
        return len(diff_entries)

    async def find_similar_tagged_resources(
        self,
        resource_type: str,
        resource_group: str,
        *,
        required_keys: list[str],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        self.suggest_calls.append(
            {
                "resource_type": resource_type,
                "resource_group": resource_group,
                "required_keys": required_keys,
                "limit": limit,
            }
        )
        return self._suggestions[:limit]


def build_server(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings=None,
    cost_client: FakeCostClient | None = None,
    resource_graph_client: FakeResourceGraphClient | None = None,
    databricks_client: FakeDatabricksClient | None = None,
    storage_client: FakeStorageClient | None = None,
    management_client: FakeManagementClient | None = None,
    lakebase_client: FakeLakebaseClient | None = None,
):
    monkeypatch.setattr(
        server_module,
        "CostManagementClient",
        lambda current_settings: cost_client or FakeCostClient(),
    )
    monkeypatch.setattr(
        server_module,
        "ResourceGraphClient",
        lambda current_settings: resource_graph_client or FakeResourceGraphClient(),
    )
    monkeypatch.setattr(
        server_module,
        "DatabricksMcpClient",
        lambda current_settings: databricks_client or FakeDatabricksClient(),
    )
    monkeypatch.setattr(
        server_module,
        "StorageExportClient",
        lambda current_settings: storage_client or FakeStorageClient(),
    )
    monkeypatch.setattr(
        server_module,
        "AzureManagementApiClient",
        lambda current_settings: management_client or FakeManagementClient(),
    )
    monkeypatch.setattr(
        server_module,
        "LakebaseClient",
        lambda current_settings: lakebase_client or FakeLakebaseClient(),
    )
    return server_module.create_mcp_server(settings or make_settings())


def run_json_tool(server, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    merged_params = {"response_format": "json"}
    if params:
        merged_params.update(params)
    result = asyncio.run(
        server._tool_manager.get_tool(name).run({"params": merged_params})
    )
    return json.loads(result)


def test_bootstrap_and_planned_capability_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    server = build_server(monkeypatch)

    bootstrap = run_json_tool(server, "azure_cost_get_bootstrap_status")
    planned = run_json_tool(server, "azure_cost_get_planned_capabilities")

    assert "azure_cost_validate_connections" in bootstrap["implemented_tools"]
    assert bootstrap["integrations"]["azure_storage_configured"] is True
    assert planned["use_cases"][0] == "查詢部門費用"
    assert "Storage LRS / ZRS 與 Hot / Cool / Cold 配置建議" in planned["remaining_focus"]


def test_validate_connections_tool_reports_all_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    server = build_server(
        monkeypatch,
        cost_client=FakeCostClient(),
        resource_graph_client=FakeResourceGraphClient(resources=[{"id": "1"}]),
        databricks_client=FakeDatabricksClient(tools=[{"name": "query_tool"}]),
        storage_client=FakeStorageClient(blobs=[{"name": "cost.csv"}]),
    )

    payload = run_json_tool(server, "azure_cost_validate_connections")

    assert payload["test_sequence"] == ["connection", "functional", "end_to_end"]
    assert payload["summary"] == {"total": 4, "ok": 4, "failed": 0, "skipped": 0}
    assert [check["name"] for check in payload["checks"]] == [
        "cost_management",
        "resource_graph",
        "storage",
        "databricks_mcp",
    ]


def test_department_cost_tool_supports_ranking_and_department_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cost_client = FakeCostClient(
        query_results=[
            {
                "properties": {
                    "columns": [
                        {"name": "Department"},
                        {"name": "PreTaxCost"},
                        {"name": "Currency"},
                    ],
                    "rows": [["IT", 10.0, "USD"], [None, 5.0, "USD"]],
                }
            },
            {
                "properties": {
                    "columns": [
                        {"name": "ServiceName"},
                        {"name": "PreTaxCost"},
                        {"name": "Currency"},
                    ],
                    "rows": [["Storage", 7.5, "USD"], ["VM", 2.5, "USD"]],
                }
            },
        ]
    )
    server = build_server(monkeypatch, cost_client=cost_client)

    ranking = run_json_tool(server, "azure_cost_department_cost", {"top": 2})
    detail = run_json_tool(
        server,
        "azure_cost_department_cost",
        {"department_name": "IT", "top": 1},
    )

    assert ranking["departments"][1]["department"] == "(untagged)"
    assert detail["department_name"] == "IT"
    assert detail["total_cost"] == 10.0
    assert detail["top_services"] == [{"service_name": "Storage", "cost": 7.5}]
    assert cost_client.query_calls[0]["grouping"] == [{"name": "Department", "type": "TagKey"}]
    assert cost_client.query_calls[1]["filters"]["tags"]["values"] == ["IT"]


def test_cost_trend_tool_builds_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    cost_client = FakeCostClient(
        query_results=[
            {
                "properties": {
                    "columns": [
                        {"name": "UsageDate"},
                        {"name": "PreTaxCost"},
                        {"name": "Currency"},
                    ],
                    "rows": [[20260101, 1.0, "USD"], [20260102, 2.34567, "USD"]],
                }
            }
        ]
    )
    server = build_server(monkeypatch, cost_client=cost_client)

    payload = run_json_tool(
        server,
        "azure_cost_cost_trend",
        {
            "service_name": "Storage",
            "department_name": "IT",
        },
    )

    assert payload["filters"]["service_name"] == "Storage"
    assert payload["filters"]["department_name"] == "IT"
    assert payload["total_cost"] == 3.3457
    assert payload["trend"][0]["period"] == "2026-01-01"
    assert len(cost_client.query_calls[0]["filters"]["and"]) == 2


def test_saving_opportunities_tool_collects_recommendations_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cost_client = FakeCostClient(
        query_results=[
            {
                "properties": {
                    "columns": [
                        {"name": "ServiceName"},
                        {"name": "PreTaxCost"},
                    ],
                    "rows": [["Azure Databricks", 100.0], ["Storage", 50.0]],
                }
            }
        ],
        benefit_result=[
            {
                "properties": {
                    "scope": "Shared",
                    "term": "P1Y",
                    "armSkuName": "dbu-plan",
                    "currencyCode": "USD",
                    "recommendationDetails": {
                        "commitmentAmount": 100,
                        "savingsAmount": 40.0,
                        "savingsPercentage": 20,
                        "coveragePercentage": 80,
                        "averageUtilizationPercentage": 70,
                        "wastageCost": 1.5,
                    },
                }
            }
        ],
        reservation_result=AzureManagementApiError("reservation unavailable"),
    )
    server = build_server(monkeypatch, cost_client=cost_client)

    payload = run_json_tool(server, "azure_cost_cost_saving_opportunities")

    assert payload["top_services"][0]["service_name"] == "Azure Databricks"
    assert "Photon" in payload["optimization_hypotheses"][0]["focus"]
    assert payload["savings_plan_recommendations"][0]["arm_sku_name"] == "dbu-plan"
    assert payload["recommendation_errors"] == ["reservation unavailable"]


def test_databricks_query_tool_uses_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    databricks_client = FakeDatabricksClient(
        configured_tool_result={
            "tool_name": "query_tool",
            "is_error": False,
            "structured_content": {"rows": 2},
            "content": [{"type": "text", "text": "done"}],
            "available_tools": ["query_tool"],
        }
    )
    server = build_server(monkeypatch, databricks_client=databricks_client)

    query_payload = run_json_tool(
        server,
        "azure_cost_databricks_query",
        {"question": "show costs"},
    )

    assert query_payload["mode"] == "databricks-proxy"
    assert query_payload["query_source"] == "amortized"
    assert query_payload["result"]["structured_content"]["rows"] == 2
    assert databricks_client.calls[0]["purpose"] == "databricks-query"
    assert databricks_client.calls[0]["arguments"] == {"question": "show costs"}


def test_databricks_query_tool_defaults_to_amortized_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    databricks_client = FakeDatabricksClient()
    server = build_server(
        monkeypatch,
        settings=make_settings(
            databricks_mcp_server_url=None,
            databricks_mcp_query_tool_name=None,
            databricks_mcp_amortized_server_url="https://example.com/amortized",
            databricks_mcp_amortized_query_tool_name="amortized_tool",
            databricks_mcp_actual_server_url="https://example.com/actual",
            databricks_mcp_actual_query_tool_name="actual_tool",
        ),
        databricks_client=databricks_client,
    )

    query_payload = run_json_tool(
        server,
        "azure_cost_databricks_query",
        {"question": "show monthly cost"},
    )

    assert databricks_client.calls[0]["tool_name"] == "amortized_tool"
    assert query_payload["query_source"] == "amortized"
    assert query_payload["remote_server"] == "https://example.com/amortized"


def test_databricks_query_tool_supports_actual_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    databricks_client = FakeDatabricksClient()
    server = build_server(
        monkeypatch,
        settings=make_settings(
            databricks_mcp_server_url=None,
            databricks_mcp_query_tool_name=None,
            databricks_mcp_amortized_server_url="https://example.com/amortized",
            databricks_mcp_amortized_query_tool_name="amortized_tool",
            databricks_mcp_actual_server_url="https://example.com/actual",
            databricks_mcp_actual_query_tool_name="actual_tool",
        ),
        databricks_client=databricks_client,
    )

    query_payload = run_json_tool(
        server,
        "azure_cost_databricks_query",
        {"question": "show monthly actual cost", "query_source": "actual"},
    )

    assert databricks_client.calls[0]["tool_name"] == "actual_tool"
    assert query_payload["query_source"] == "actual"
    assert query_payload["remote_server"] == "https://example.com/actual"


def test_databricks_query_tool_flattens_extra_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    databricks_client = FakeDatabricksClient()
    server = build_server(monkeypatch, databricks_client=databricks_client)

    run_json_tool(
        server,
        "azure_cost_databricks_query",
        {
            "sql": "select 1",
            "arguments": {"query": "SELECT 1 AS ok", "warehouse_id": "wh-1"},
        },
    )

    assert databricks_client.calls[0]["arguments"] == {
        "sql": "select 1",
        "query": "SELECT 1 AS ok",
        "warehouse_id": "wh-1",
    }


def test_untagged_resources_tool_returns_resource_graph_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resources = [
        {
            "id": "1",
            "name": "vm-1",
            "type": "Microsoft.Compute/virtualMachines",
            "resourceGroup": "rg-1",
            "location": "eastus",
            "subscriptionId": "sub-default",
            "tags": {},
        }
    ]
    resource_graph_client = FakeResourceGraphClient(resources=resources)
    server = build_server(monkeypatch, resource_graph_client=resource_graph_client)

    untagged_payload = run_json_tool(
        server,
        "azure_cost_untagged_resources",
        {"required_tag_keys": ["Department"]},
    )

    assert untagged_payload["summary"]["resource_count"] == 1
    assert untagged_payload["source"] == "Azure Resource Graph"


def test_list_storage_exports_handles_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    storage_client = FakeStorageClient(blobs=[{"name": "cost-management/file.csv"}])
    server = build_server(monkeypatch, storage_client=storage_client)

    payload = run_json_tool(
        server,
        "azure_cost_list_storage_exports",
        {"max_results": 1},
    )

    assert payload["blob_count"] == 1
    assert payload["blobs"][0]["name"] == "cost-management/file.csv"

    error_server = build_server(
        monkeypatch,
        storage_client=FakeStorageClient(blobs=StorageClientError("storage failed")),
    )
    with pytest.raises(ToolError, match="storage failed"):
        asyncio.run(
            error_server._tool_manager.get_tool("azure_cost_list_storage_exports").run(
                {"params": {"response_format": "json"}}
            )
        )


def test_tag_inventory_tool_returns_coverage_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    resources = [
        {
            "id": "r1",
            "name": "vm-1",
            "type": "Microsoft.Compute/virtualMachines",
            "resourceGroup": "rg-a",
            "subscriptionId": "m365-sub-default",
            "location": "eastasia",
            "tags": {"cost_center": "eng"},
        },
        {
            "id": "r2",
            "name": "vm-2",
            "type": "Microsoft.Compute/virtualMachines",
            "resourceGroup": "rg-a",
            "subscriptionId": "m365-sub-default",
            "location": "eastasia",
            "tags": {},
        },
    ]
    rg_client = FakeResourceGraphClient(resources=resources)
    server = build_server(
        monkeypatch,
        settings=make_settings(
            azure_cost_tag_inventory_cache_dir=str(tmp_path / "tag-inventory"),
            azure_cost_required_tag_keys="cost_center",
        ),
        resource_graph_client=rg_client,
    )

    payload = run_json_tool(server, "azure_cost_tag_inventory", {"force_refresh": True})

    assert payload["total_resources"] == 2
    assert payload["tagged_count"] == 1
    assert payload["untagged_count"] == 1
    assert payload["coverage_pct"] == 50.0
    assert payload["required_tag_keys"] == ["cost_center"]
    assert len(payload["by_resource_group"]) == 1
    assert payload["by_resource_group"][0]["resource_group"] == "rg-a"
    assert payload["by_resource_group"][0]["coverage_pct"] == 50.0
    assert len(rg_client.inventory_calls) == 1


def test_tag_inventory_tool_uses_m365_subscriptions_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    rg_client = FakeResourceGraphClient(resources=[])
    server = build_server(
        monkeypatch,
        settings=make_settings(
            azure_cost_tag_inventory_cache_dir=str(tmp_path / "tag-inventory"),
        ),
        resource_graph_client=rg_client,
    )

    payload = run_json_tool(server, "azure_cost_tag_inventory", {"force_refresh": True})

    assert payload["subscriptions"] == ["m365-sub-default"]


# ---------------------------------------------------------------------------
# azure_cost_tag_diff
# ---------------------------------------------------------------------------

_DESIRED_ENTRIES = [
    {
        "resource_id": "/subscriptions/sub-a/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1",
        "name": "vm-1",
        "type": "Microsoft.Compute/virtualMachines",
        "resource_group": "rg-1",
        "subscription_id": "sub-a",
        "current_tags": {"cost_center": "eng"},
        "desired_tags": {"cost_center": "eng", "Environment": "prod"},
    },
    {
        "resource_id": "/subscriptions/sub-a/resourceGroups/rg-1/providers/Microsoft.Storage/storageAccounts/st-1",
        "name": "st-1",
        "type": "Microsoft.Storage/storageAccounts",
        "resource_group": "rg-1",
        "subscription_id": "sub-a",
        "current_tags": {"cost_center": "old"},
        "desired_tags": {"cost_center": "eng", "Environment": ""},
    },
]


def _write_desired_json(desired_dir, entries=None) -> None:
    import json
    desired_dir.mkdir(parents=True, exist_ok=True)
    (desired_dir / "rg-1.json").write_text(
        json.dumps(entries or _DESIRED_ENTRIES), encoding="utf-8"
    )


def test_tag_diff_tool_returns_diff_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    desired_dir = tmp_path / "desired"
    _write_desired_json(desired_dir)
    server = build_server(monkeypatch)

    payload = run_json_tool(
        server,
        "azure_cost_tag_diff",
        {"desired_dir": str(desired_dir)},
    )

    assert payload["total_resources_with_changes"] == 2
    assert payload["total_tags_to_add"] == 1   # vm-1: Environment added
    assert payload["total_tags_to_modify"] == 1  # st-1: cost_center modified
    assert "Environment" in payload["diff_table"]
    assert "新增" in payload["diff_table"]
    assert "修改" in payload["diff_table"]


def test_tag_diff_tool_returns_empty_when_no_desired_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    server = build_server(monkeypatch)

    payload = run_json_tool(
        server,
        "azure_cost_tag_diff",
        {"desired_dir": str(tmp_path / "nonexistent")},
    )

    assert payload["total_resources_with_changes"] == 0
    assert payload["total_tags_to_add"] == 0


# ---------------------------------------------------------------------------
# azure_cost_tag_apply
# ---------------------------------------------------------------------------


def test_tag_apply_tool_dry_run_when_apply_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    desired_dir = tmp_path / "desired"
    _write_desired_json(desired_dir)
    mgmt_client = FakeManagementClient()
    server = build_server(monkeypatch, management_client=mgmt_client)

    payload = run_json_tool(
        server,
        "azure_cost_tag_apply",
        {"desired_dir": str(desired_dir), "apply": False},
    )

    assert payload["mode"] == "dry-run"
    assert payload["total_resources"] == 2
    assert len(mgmt_client.patch_calls) == 0
    assert all(r["status"] == "dry-run" for r in payload["results"])


def test_tag_apply_tool_dry_run_when_apply_enabled_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    desired_dir = tmp_path / "desired"
    _write_desired_json(desired_dir)
    mgmt_client = FakeManagementClient()
    server = build_server(
        monkeypatch,
        settings=make_settings(azure_cost_tag_apply_enabled=False),
        management_client=mgmt_client,
    )

    payload = run_json_tool(
        server,
        "azure_cost_tag_apply",
        {"desired_dir": str(desired_dir), "apply": True},
    )

    assert payload["mode"] == "dry-run"
    assert len(mgmt_client.patch_calls) == 0


def test_tag_apply_tool_actually_patches_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    desired_dir = tmp_path / "desired"
    _write_desired_json(desired_dir)
    mgmt_client = FakeManagementClient()
    server = build_server(
        monkeypatch,
        settings=make_settings(azure_cost_tag_apply_enabled=True),
        management_client=mgmt_client,
    )

    payload = run_json_tool(
        server,
        "azure_cost_tag_apply",
        {"desired_dir": str(desired_dir), "apply": True, "rationale": "fix missing tags"},
    )

    assert payload["mode"] == "apply"
    assert payload["ok"] == 2
    assert payload["errors"] == 0
    assert len(mgmt_client.patch_calls) == 2
    # vm-1: merged unchanged(cost_center=eng) + added(Environment=prod)
    vm1_call = next(c for c in mgmt_client.patch_calls if "vm-1" in c["resource_id"])
    assert vm1_call["tags"]["Environment"] == "prod"
    assert vm1_call["tags"]["cost_center"] == "eng"
    assert payload["rationale"] == "fix missing tags"


def test_tag_apply_tool_records_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    desired_dir = tmp_path / "desired"
    _write_desired_json(desired_dir)
    from azure_cost_mcp.azure_management import AzureManagementApiError
    mgmt_client = FakeManagementClient(patch_error=AzureManagementApiError("boom"))
    server = build_server(
        monkeypatch,
        settings=make_settings(azure_cost_tag_apply_enabled=True),
        management_client=mgmt_client,
    )

    payload = run_json_tool(
        server,
        "azure_cost_tag_apply",
        {"desired_dir": str(desired_dir), "apply": True},
    )

    assert payload["errors"] == 2
    assert all(r["status"] == "error" for r in payload["results"])


# ---------------------------------------------------------------------------
# azure_cost_tag_suggest
# ---------------------------------------------------------------------------


def test_tag_suggest_tool_returns_skipped_when_lakebase_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = build_server(monkeypatch, lakebase_client=FakeLakebaseClient(configured=False))

    payload = run_json_tool(server, "azure_cost_tag_suggest")

    assert payload["status"] == "skipped"
    assert payload["suggestions"] == []


def test_tag_suggest_tool_returns_suggestions_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_suggestions = [
        {
            "resource_id": "/subscriptions/sub-a/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-ref",
            "name": "vm-ref",
            "type": "Microsoft.Compute/virtualMachines",
            "resource_group": "rg-1",
            "tags": {"cost_center": "eng", "Environment": "prod"},
        }
    ]
    lb_client = FakeLakebaseClient(configured=True, suggestions=fake_suggestions)
    server = build_server(monkeypatch, lakebase_client=lb_client)

    payload = run_json_tool(
        server,
        "azure_cost_tag_suggest",
        {
            "resource_type": "Microsoft.Compute/virtualMachines",
            "resource_group": "rg-1",
            "limit": 3,
        },
    )

    assert payload["status"] == "ok"
    assert payload["suggestion_count"] == 1
    assert payload["suggestions"][0]["name"] == "vm-ref"
    assert lb_client.suggest_calls[0]["resource_type"] == "Microsoft.Compute/virtualMachines"
    assert lb_client.suggest_calls[0]["limit"] == 3
    assert lb_client.init_calls == 1  # was not ready, so init() called


def test_tag_suggest_tool_handles_lakebase_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ErrorLakebaseClient(FakeLakebaseClient):
        async def find_similar_tagged_resources(self, *args, **kwargs):
            raise RuntimeError("DB connection failed")

    server = build_server(
        monkeypatch, lakebase_client=ErrorLakebaseClient(configured=True)
    )

    payload = run_json_tool(server, "azure_cost_tag_suggest")

    assert payload["status"] == "error"
    assert "DB connection failed" in payload["reason"]


# ---------------------------------------------------------------------------
# Lakebase integration in inventory + apply
# ---------------------------------------------------------------------------


def test_tag_inventory_tool_upserts_to_lakebase_when_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    resources = [
        {
            "id": "r1",
            "name": "vm-1",
            "type": "Microsoft.Compute/virtualMachines",
            "resourceGroup": "rg-a",
            "subscriptionId": "m365-sub-default",
            "location": "eastasia",
            "tags": {"cost_center": "eng"},
        }
    ]
    lb_client = FakeLakebaseClient(configured=True)
    server = build_server(
        monkeypatch,
        settings=make_settings(
            azure_cost_tag_inventory_cache_dir=str(tmp_path / "tag-inventory"),
        ),
        resource_graph_client=FakeResourceGraphClient(resources=resources),
        lakebase_client=lb_client,
    )

    run_json_tool(server, "azure_cost_tag_inventory", {"force_refresh": True})

    assert len(lb_client.upsert_calls) == 1
    assert lb_client.upsert_calls[0]["resources"] == resources
    assert lb_client.init_calls == 1


def test_tag_inventory_tool_skips_lakebase_upsert_when_cache_hit(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    import json as json_module
    resources = [
        {
            "id": "r1",
            "name": "vm-1",
            "type": "Microsoft.Compute/virtualMachines",
            "resourceGroup": "rg-a",
            "subscriptionId": "m365-sub-default",
            "location": "eastasia",
            "tags": {},
        }
    ]
    today = __import__("datetime").date.today().isoformat()
    cache_dir = tmp_path / "tag-inventory" / today
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "m365-sub-default.json").write_text(
        json_module.dumps({"resources": resources, "snapshot_date": today}),
        encoding="utf-8",
    )
    lb_client = FakeLakebaseClient(configured=True)
    server = build_server(
        monkeypatch,
        settings=make_settings(
            azure_cost_tag_inventory_cache_dir=str(tmp_path / "tag-inventory"),
        ),
        resource_graph_client=FakeResourceGraphClient(resources=[]),
        lakebase_client=lb_client,
    )

    run_json_tool(server, "azure_cost_tag_inventory", {"force_refresh": False})

    assert len(lb_client.upsert_calls) == 0


def test_tag_apply_tool_records_to_lakebase(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    desired_dir = tmp_path / "desired"
    _write_desired_json(desired_dir)
    lb_client = FakeLakebaseClient(configured=True)
    server = build_server(
        monkeypatch,
        settings=make_settings(azure_cost_tag_apply_enabled=True),
        lakebase_client=lb_client,
    )

    run_json_tool(
        server,
        "azure_cost_tag_apply",
        {"desired_dir": str(desired_dir), "apply": True, "rationale": "batch fix"},
    )

    assert len(lb_client.record_calls) == 1
    assert lb_client.record_calls[0]["dry_run"] is False
    assert lb_client.record_calls[0]["rationale"] == "batch fix"


def test_tag_apply_tool_records_dry_run_to_lakebase(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    desired_dir = tmp_path / "desired"
    _write_desired_json(desired_dir)
    lb_client = FakeLakebaseClient(configured=True)
    server = build_server(monkeypatch, lakebase_client=lb_client)

    run_json_tool(
        server,
        "azure_cost_tag_apply",
        {"desired_dir": str(desired_dir), "apply": False},
    )

    assert len(lb_client.record_calls) == 1
    assert lb_client.record_calls[0]["dry_run"] is True
