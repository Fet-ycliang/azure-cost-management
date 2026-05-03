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
    ) -> None:
        self.resources = resources or []
        self._default_subscriptions = default_subscriptions or ["sub-default"]
        self.query_calls: list[dict[str, Any]] = []
        self.find_calls: list[dict[str, Any]] = []

    async def query_resources(self, query: str, *, subscriptions=None, top=None) -> dict[str, Any]:
        self.query_calls.append(
            {
                "query": query,
                "subscriptions": subscriptions,
                "top": top,
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

    def default_subscriptions(self) -> list[str] | None:
        return self._default_subscriptions


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


def build_server(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings=None,
    cost_client: FakeCostClient | None = None,
    resource_graph_client: FakeResourceGraphClient | None = None,
    databricks_client: FakeDatabricksClient | None = None,
    storage_client: FakeStorageClient | None = None,
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
