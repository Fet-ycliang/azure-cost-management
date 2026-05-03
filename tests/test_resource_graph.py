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
