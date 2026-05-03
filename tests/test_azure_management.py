from __future__ import annotations

import asyncio

import httpx
import pytest

from azure_cost_mcp.azure_management import (
    MANAGEMENT_SCOPE,
    AzureManagementApiClient,
    AzureManagementApiError,
)

from .helpers import make_settings


class DummyCredential:
    def __init__(self) -> None:
        self.closed = False

    async def get_token(self, scope: str):
        assert scope == MANAGEMENT_SCOPE
        return type("Token", (), {"token": "access-token"})()

    async def close(self) -> None:
        self.closed = True


class DummyAsyncClient:
    def __init__(self, response: httpx.Response, **kwargs) -> None:
        self.response = response
        self.kwargs = kwargs
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> "DummyAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def request(self, method: str, url: str, *, params=None, json=None) -> httpx.Response:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
            }
        )
        return self.response


def test_request_returns_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    credential = DummyCredential()
    response = httpx.Response(
        200,
        json={"value": 1},
        request=httpx.Request("GET", "https://management.azure.com/test"),
    )
    instances: list[DummyAsyncClient] = []

    def fake_async_client(**kwargs) -> DummyAsyncClient:
        client = DummyAsyncClient(response, **kwargs)
        instances.append(client)
        return client

    monkeypatch.setattr("azure_cost_mcp.azure_management.create_azure_credential", lambda _: credential)
    monkeypatch.setattr("azure_cost_mcp.azure_management.httpx.AsyncClient", fake_async_client)

    client = AzureManagementApiClient(make_settings())
    result = asyncio.run(
        client._request(
            "GET",
            "/test",
            params={"api-version": "2025-03-01"},
            json_body={"query": "value"},
        )
    )

    assert result == {"value": 1}
    assert credential.closed is True
    assert instances[0].kwargs["base_url"] == "https://management.azure.com"
    assert instances[0].kwargs["headers"]["Authorization"] == "Bearer access-token"
    assert instances[0].calls == [
        {
            "method": "GET",
            "url": "/test",
            "params": {"api-version": "2025-03-01"},
            "json": {"query": "value"},
        }
    ]


def test_request_returns_none_for_no_content(monkeypatch: pytest.MonkeyPatch) -> None:
    credential = DummyCredential()
    response = httpx.Response(
        204,
        request=httpx.Request("DELETE", "https://management.azure.com/test"),
    )

    monkeypatch.setattr("azure_cost_mcp.azure_management.create_azure_credential", lambda _: credential)
    monkeypatch.setattr(
        "azure_cost_mcp.azure_management.httpx.AsyncClient",
        lambda **kwargs: DummyAsyncClient(response, **kwargs),
    )

    client = AzureManagementApiClient(make_settings())
    result = asyncio.run(client._request("DELETE", "/test"))

    assert result is None
    assert credential.closed is True


def test_request_raises_formatted_error(monkeypatch: pytest.MonkeyPatch) -> None:
    credential = DummyCredential()
    response = httpx.Response(
        400,
        json={"error": {"code": "BadRequest", "message": "boom"}},
        request=httpx.Request("POST", "https://management.azure.com/test"),
    )

    monkeypatch.setattr("azure_cost_mcp.azure_management.create_azure_credential", lambda _: credential)
    monkeypatch.setattr(
        "azure_cost_mcp.azure_management.httpx.AsyncClient",
        lambda **kwargs: DummyAsyncClient(response, **kwargs),
    )

    client = AzureManagementApiClient(make_settings())
    with pytest.raises(AzureManagementApiError, match="BadRequest: boom"):
        asyncio.run(client._request("POST", "/test"))


def test_format_error_falls_back_to_message_field() -> None:
    response = httpx.Response(
        500,
        json={"message": "server exploded"},
        request=httpx.Request("GET", "https://management.azure.com/test"),
    )

    message = AzureManagementApiClient._format_error(response)

    assert "server exploded" in message
    assert "status 500" in message
