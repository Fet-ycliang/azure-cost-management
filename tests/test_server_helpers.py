from __future__ import annotations

import asyncio

from azure_cost_mcp.models import TrendGranularity
from azure_cost_mcp.server import (
    _annotate_missing_tags,
    _build_connection_check,
    _build_optimization_hypotheses,
    _detect_cost_field,
    _detect_currency,
    _detect_group_field,
    _format_check_error,
    _normalize_group_value,
    _normalize_reservation_recommendations,
    _normalize_savings_plan_recommendations,
    _normalize_trend_date,
    _round_cost,
    _run_connection_checks,
    _service_hypothesis,
    _summarize_connection_checks,
    _summarize_missing_tags,
    _to_float,
)

from .helpers import make_settings


def test_numeric_helpers_and_detection_helpers() -> None:
    records = [
        {"ServiceName": "Storage", "PreTaxCost": {"value": 12.34567}, "Currency": "USD"},
        {"ServiceName": "VM", "PreTaxCost": 3, "Currency": "USD"},
    ]

    assert _to_float({"value": "2.5"}) == 2.5
    assert _to_float(None) == 0.0
    assert _round_cost({"value": 12.34567}) == 12.3457
    assert _detect_cost_field(records) == "PreTaxCost"
    assert _detect_group_field(records, preferred="ServiceName") == "ServiceName"
    assert _detect_currency(records) == "USD"
    assert _normalize_group_value(None) == "(untagged)"


def test_trend_date_and_service_hypothesis_variants() -> None:
    assert _normalize_trend_date("20260131", TrendGranularity.DAILY) == "2026-01-31"
    assert _normalize_trend_date("202601", TrendGranularity.MONTHLY) == "2026-01"
    assert "Photon" in _service_hypothesis("Azure Databricks")
    assert "Reservation / Savings Plan" in _service_hypothesis("Virtual Machines")
    assert "Hot/Cool/Cold" in _service_hypothesis("Storage")
    assert "跨區流量" in _service_hypothesis("Network egress")
    assert "App Service Plan" in _service_hypothesis("App Service")
    assert "進一步拆分" in _service_hypothesis("Unknown Service")


def test_optimization_and_missing_tag_helpers() -> None:
    top_services = [
        {"service_name": "Azure Databricks", "cost": 100.0},
        {"service_name": "Storage", "cost": 50.0},
    ]
    raw_resources = [
        {
            "id": "1",
            "name": "vm-1",
            "type": "Microsoft.Compute/virtualMachines",
            "resourceGroup": "rg-1",
            "location": "eastus",
            "subscriptionId": "sub-a",
            "tags": {"Department": ""},
        },
        {
            "id": "2",
            "name": "st-1",
            "type": "Microsoft.Storage/storageAccounts",
            "resourceGroup": "rg-1",
            "location": "eastus",
            "subscriptionId": "sub-a",
            "tags": {},
        },
    ]

    hypotheses = _build_optimization_hypotheses(top_services)
    resources = _annotate_missing_tags(raw_resources, ["Department", "Owner"])
    summary = _summarize_missing_tags(resources)

    assert hypotheses[0]["service_name"] == "Azure Databricks"
    assert "Photon" in hypotheses[0]["focus"]
    assert resources[0]["missing_tags"] == ["Department", "Owner"]
    assert resources[1]["missing_tags"] == ["Department", "Owner"]
    assert summary["resource_count"] == 2
    assert summary["counts_by_type"]["Microsoft.Compute/virtualMachines"] == 1
    assert summary["counts_by_missing_tag"]["Department"] == 2


def test_normalize_recommendations_sort_and_trim() -> None:
    savings = _normalize_savings_plan_recommendations(
        [
            {
                "properties": {
                    "scope": "Shared",
                    "term": "P1Y",
                    "armSkuName": "sku-a",
                    "currencyCode": "USD",
                    "recommendationDetails": {
                        "commitmentAmount": 100,
                        "savingsAmount": 50.55555,
                        "savingsPercentage": 30,
                        "coveragePercentage": 90,
                        "averageUtilizationPercentage": 80,
                        "wastageCost": 2.2,
                    },
                }
            },
            {
                "properties": {
                    "scope": "Shared",
                    "term": "P1Y",
                    "armSkuName": "sku-b",
                    "currencyCode": "USD",
                    "recommendationDetails": {
                        "commitmentAmount": 100,
                        "savingsAmount": 10,
                        "savingsPercentage": 10,
                        "coveragePercentage": 50,
                        "averageUtilizationPercentage": 70,
                        "wastageCost": 1,
                    },
                }
            },
        ],
        top=1,
    )
    reservations = _normalize_reservation_recommendations(
        [
            {
                "sku": "sku-b",
                "location": "eastus",
                "properties": {
                    "scope": "Shared",
                    "term": "P1Y",
                    "resourceType": "VirtualMachines",
                    "recommendedQuantity": 2,
                    "netSavings": {"value": 20.1, "currency": "USD"},
                },
            },
            {
                "properties": {
                    "scope": "Shared",
                    "term": "P1Y",
                    "resourceType": "VirtualMachines",
                    "skuName": "sku-a",
                    "location": "westus",
                    "recommendedQuantity": 1,
                    "netSavings": {"value": 30.25, "currency": "USD"},
                },
            },
        ],
        top=1,
    )

    assert savings == [
        {
            "scope": "Shared",
            "term": "P1Y",
            "arm_sku_name": "sku-a",
            "currency": "USD",
            "commitment_amount": 100,
            "savings_amount": 50.5555,
            "savings_percentage": 30,
            "coverage_percentage": 90,
            "average_utilization_percentage": 80,
            "wastage_cost": 2.2,
        }
    ]
    assert reservations == [
        {
            "scope": "Shared",
            "term": "P1Y",
            "resource_type": "VirtualMachines",
            "sku": "sku-a",
            "location": "westus",
            "recommended_quantity": 1,
            "net_savings": 30.25,
            "currency": "USD",
        }
    ]


def test_connection_check_helpers() -> None:
    check = _build_connection_check(
        "storage",
        status="ok",
        configured=True,
        detail={"container": "costs"},
    )
    summary = _summarize_connection_checks(
        [
            check,
            _build_connection_check("cost_management", status="failed", configured=True),
            _build_connection_check("databricks_mcp", status="skipped", configured=False),
        ]
    )

    assert check == {
        "name": "storage",
        "status": "ok",
        "configured": True,
        "detail": {"container": "costs"},
    }
    assert summary == {"total": 3, "ok": 1, "failed": 1, "skipped": 1}


def test_format_check_error_unwraps_exception_groups_and_causes() -> None:
    try:
        try:
            raise RuntimeError("redirected to block page")
        except RuntimeError as inner_error:
            raise ValueError("databricks probe failed") from inner_error
    except ValueError as outer_error:
        error = ExceptionGroup("task group failed", [outer_error])

    assert _format_check_error(error) == "RuntimeError: redirected to block page"


def test_run_connection_checks_respects_sequence_and_statuses() -> None:
    class FakeCostClient:
        async def query_usage(self, **kwargs):
            return {"properties": {"rows": []}}

    class FakeResourceGraphClient:
        async def query_resources(self, query: str, *, subscriptions=None, top=None):
            assert query == "Resources | take 1"
            return {"data": [{"id": "1"}]}

        def default_subscriptions(self) -> list[str]:
            return ["sub-a"]

    class FakeDatabricksClient:
        def is_configured(self) -> bool:
            return True

        async def list_tools(self):
            return [{"name": "tool-a"}, {"name": "tool-b"}]

    class FakeStorageClient:
        async def list_cost_blobs(self, *, max_results: int):
            assert max_results == 1
            return [{"name": "cost.csv"}]

    checks = asyncio.run(
        _run_connection_checks(
            settings=make_settings(),
            cost_client=FakeCostClient(),
            resource_graph_client=FakeResourceGraphClient(),
            databricks_client=FakeDatabricksClient(),
            storage_client=FakeStorageClient(),
        )
    )

    assert [check["name"] for check in checks] == [
        "cost_management",
        "resource_graph",
        "storage",
        "databricks_mcp",
    ]
    assert all(check["status"] == "ok" for check in checks)
