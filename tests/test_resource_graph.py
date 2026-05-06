from __future__ import annotations

import asyncio
from typing import Any

import pytest

from azure_cost_mcp.resource_graph import ResourceGraphClient

from .helpers import make_settings


class RecordingResourceGraphClient(ResourceGraphClient):
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


def test_default_subscriptions_derive_from_scope() -> None:
    client = ResourceGraphClient(make_settings(azure_cost_management_scope="/subscriptions/sub-123"))

    assert client.default_subscriptions() == ["sub-123"]
    assert (
        ResourceGraphClient(make_settings(azure_cost_management_scope="/providers/Microsoft.Management/managementGroups/root"))
        .default_subscriptions()
        is None
    )


def test_query_resources_uses_default_subscriptions_and_top() -> None:
    client = RecordingResourceGraphClient(responses=[{"data": [{"id": "1"}]}])

    result = asyncio.run(client.query_resources("Resources | take 1", top=5))

    assert result == {"data": [{"id": "1"}]}
    assert client.calls[0]["url"] == "/providers/Microsoft.ResourceGraph/resources"
    assert client.calls[0]["json_body"] == {
        "query": "Resources | take 1",
        "subscriptions": ["sub-default"],
        "options": {"$top": 5},
    }


def test_find_resources_missing_tags_builds_query(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ResourceGraphClient(make_settings())
    captured = {}

    async def fake_query_resources(query: str, *, subscriptions=None, top=None) -> dict[str, Any]:
        captured["query"] = query
        captured["subscriptions"] = subscriptions
        captured["top"] = top
        return {"data": [{"id": "resource-1"}]}

    monkeypatch.setattr(client, "query_resources", fake_query_resources)

    result = asyncio.run(
        client.find_resources_missing_tags(
            required_tag_keys=["Department", "Owner"],
            subscriptions=["sub-a"],
            resource_ids=["/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"],
            max_results=10,
        )
    )

    assert result == [{"id": "resource-1"}]
    assert "isempty(tostring(tags['Department']))" in captured["query"]
    assert "isempty(tostring(tags['Owner']))" in captured["query"]
    assert "id in~ (" in captured["query"]
    assert captured["subscriptions"] == ["sub-a"]
    assert captured["top"] == 10


def test_find_resources_missing_tags_requires_tags() -> None:
    client = ResourceGraphClient(make_settings())

    with pytest.raises(ValueError, match="至少需要一個 tag key"):
        asyncio.run(
            client.find_resources_missing_tags(
                required_tag_keys=[],
                max_results=5,
            )
        )


def test_escape_kql_literal_escapes_quotes_and_backslashes() -> None:
    assert ResourceGraphClient._escape_kql_literal(r"Dept\A'B") == r"Dept\\A''B"
    assert ResourceGraphClient._missing_tag_condition("Owner's Team") == "isempty(tostring(tags['Owner''s Team']))"


def test_m365_subscriptions_derive_from_scope() -> None:
    client = ResourceGraphClient(
        make_settings(m365_cost_management_scope="/subscriptions/m365-sub-abc")
    )
    assert client.m365_subscriptions() == ["m365-sub-abc"]
    assert (
        ResourceGraphClient(make_settings(m365_cost_management_scope=None))
        .m365_subscriptions()
        is None
    )


def test_m365_or_default_subscriptions_prefers_m365() -> None:
    client = ResourceGraphClient(
        make_settings(
            azure_cost_management_scope="/subscriptions/azure-sub",
            m365_cost_management_scope="/subscriptions/m365-sub",
        )
    )
    assert client.m365_or_default_subscriptions() == ["m365-sub"]


def test_m365_or_default_subscriptions_falls_back_to_azure() -> None:
    client = ResourceGraphClient(
        make_settings(
            azure_cost_management_scope="/subscriptions/azure-sub",
            m365_cost_management_scope=None,
        )
    )
    assert client.m365_or_default_subscriptions() == ["azure-sub"]


def test_query_resources_includes_skip_token() -> None:
    client = RecordingResourceGraphClient(responses=[{"data": []}])

    asyncio.run(
        client.query_resources("Resources | take 1", top=5, skip_token="tok-abc")
    )

    assert client.calls[0]["json_body"]["options"] == {"$top": 5, "$skipToken": "tok-abc"}


def test_get_all_resources_with_tags_paginates() -> None:
    page1 = {
        "data": [{"id": f"r{i}", "subscriptionId": "sub-1"} for i in range(3)],
        "$skipToken": "tok-next",
    }
    page2 = {
        "data": [{"id": "r3", "subscriptionId": "sub-1"}],
    }
    client = RecordingResourceGraphClient(responses=[page1, page2])

    result = asyncio.run(
        client.get_all_resources_with_tags(subscriptions=["sub-1"], max_results=100)
    )

    assert len(result) == 4
    assert result[0]["id"] == "r0"
    assert result[3]["id"] == "r3"
    assert len(client.calls) == 2
    assert client.calls[1]["json_body"]["options"]["$skipToken"] == "tok-next"


def test_get_all_resources_with_tags_respects_max_results() -> None:
    page1 = {
        "data": [{"id": f"r{i}"} for i in range(3)],
        "$skipToken": "tok-next",
    }
    client = RecordingResourceGraphClient(responses=[page1])

    result = asyncio.run(
        client.get_all_resources_with_tags(subscriptions=["sub-1"], max_results=2)
    )

    assert len(result) == 2


def test_get_all_resources_with_tags_filters_by_type_and_rg() -> None:
    client = RecordingResourceGraphClient(responses=[{"data": []}])

    asyncio.run(
        client.get_all_resources_with_tags(
            subscriptions=["sub-1"],
            resource_types=["Microsoft.Compute/virtualMachines"],
            resource_groups=["rg-prod"],
        )
    )

    kql = client.calls[0]["json_body"]["query"]
    assert "type in~" in kql
    assert "Microsoft.Compute/virtualMachines" in kql
    assert "resourceGroup in~" in kql
    assert "rg-prod" in kql
