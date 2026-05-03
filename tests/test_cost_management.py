from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest

from azure_cost_mcp.cost_management import CostManagementClient

from .helpers import make_settings


class RecordingCostManagementClient(CostManagementClient):
    def __init__(self, responses: list[dict[str, Any]], **settings_overrides: Any) -> None:
        super().__init__(make_settings(**settings_overrides))
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params=None,
        json_body=None,
        expected_statuses=(200, 204),
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json_body": json_body,
                "expected_statuses": expected_statuses,
            }
        )
        return self.responses.pop(0)


def test_require_scope_uses_override_or_default() -> None:
    client = CostManagementClient(make_settings(azure_cost_management_scope="/subscriptions/default"))

    assert client.require_scope() == "/subscriptions/default"
    assert client.require_scope("/subscriptions/override") == "/subscriptions/override"


def test_require_scope_raises_when_missing() -> None:
    client = CostManagementClient(make_settings(azure_cost_management_scope=None))

    with pytest.raises(ValueError, match="AZURE_COST_MANAGEMENT_SCOPE 尚未設定"):
        client.require_scope()


def test_query_usage_builds_payload_and_combines_pages() -> None:
    client = RecordingCostManagementClient(
        responses=[
            {
                "properties": {
                    "columns": [{"name": "PreTaxCost"}],
                    "rows": [[12.0]],
                    "nextLink": "/next-page",
                }
            },
            {
                "properties": {
                    "columns": [{"name": "PreTaxCost"}],
                    "rows": [[8.0]],
                }
            },
        ]
    )

    result = asyncio.run(
        client.query_usage(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            granularity="Daily",
            grouping=[{"name": "ServiceName", "type": "Dimension"}],
            filters={"tags": {"name": "Department", "operator": "In", "values": ["IT"]}},
            scope="/subscriptions/sub-a",
        )
    )

    assert client.calls[0]["url"] == "/subscriptions/sub-a/providers/Microsoft.CostManagement/query"
    assert client.calls[0]["params"] == {"api-version": "2025-03-01"}
    assert client.calls[0]["json_body"]["dataset"]["grouping"] == [
        {"name": "ServiceName", "type": "Dimension"}
    ]
    assert client.calls[0]["json_body"]["dataset"]["filter"] == {
        "tags": {"name": "Department", "operator": "In", "values": ["IT"]}
    }
    assert client.calls[1]["url"] == "/next-page"
    assert client.calls[1]["params"] is None
    assert result["properties"]["rows"] == [[12.0], [8.0]]
    assert result["properties"]["nextLink"] is None


def test_list_benefit_recommendations_builds_expected_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CostManagementClient(make_settings())
    captured = {}

    async def fake_collect(url: str, *, params: dict[str, str]) -> list[dict[str, Any]]:
        captured["url"] = url
        captured["params"] = params
        return [{"name": "benefit"}]

    monkeypatch.setattr(client, "_collect_paged_values", fake_collect)

    result = asyncio.run(
        client.list_benefit_recommendations(
            look_back_period="Last30Days",
            term="P1Y",
            recommendation_scope="Shared",
            expand_usage=True,
        )
    )

    assert result == [{"name": "benefit"}]
    assert captured["url"] == (
        "/subscriptions/sub-default/providers/Microsoft.CostManagement/benefitRecommendations"
    )
    assert captured["params"]["$expand"] == "properties/usage,properties/allRecommendationDetails"
    assert "properties/term eq 'P1Y'" in captured["params"]["$filter"]


def test_list_reservation_recommendations_builds_expected_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CostManagementClient(make_settings())
    captured = {}

    async def fake_collect(url: str, *, params: dict[str, str]) -> list[dict[str, Any]]:
        captured["url"] = url
        captured["params"] = params
        return [{"name": "reservation"}]

    monkeypatch.setattr(client, "_collect_paged_values", fake_collect)

    result = asyncio.run(
        client.list_reservation_recommendations(
            look_back_period="Last7Days",
            recommendation_scope="Shared",
            resource_type="VirtualMachines",
        )
    )

    assert result == [{"name": "reservation"}]
    assert captured["url"] == (
        "/subscriptions/sub-default/providers/Microsoft.Consumption/reservationRecommendations"
    )
    assert "properties/resourceType eq 'VirtualMachines'" in captured["params"]["$filter"]


def test_collect_paged_values_follows_next_link() -> None:
    client = RecordingCostManagementClient(
        responses=[
            {"value": [{"id": 1}], "nextLink": "/page-2"},
            {"value": [{"id": 2}]},
        ]
    )

    result = asyncio.run(
        client._collect_paged_values(
            "/providers/Microsoft.Resource/items",
            params={"api-version": "1"},
        )
    )

    assert result == [{"id": 1}, {"id": 2}]
    assert client.calls[0]["params"] == {"api-version": "1"}
    assert client.calls[1]["url"] == "/page-2"
    assert client.calls[1]["params"] is None


def test_rows_to_records_and_filter_helpers() -> None:
    records = CostManagementClient.rows_to_records(
        {
            "properties": {
                "columns": [{"name": "ServiceName"}, {"name": "PreTaxCost"}],
                "rows": [["Storage", 5.5]],
            }
        }
    )

    assert records == [{"ServiceName": "Storage", "PreTaxCost": 5.5}]
    assert CostManagementClient._build_filter(("a", "", "b")) == "a AND b"
