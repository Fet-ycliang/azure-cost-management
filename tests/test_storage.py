from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from azure_cost_mcp.storage import StorageClientError, StorageExportClient

from .helpers import make_settings


class DummyCredential:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeBlob:
    def __init__(self, name: str, size: int) -> None:
        self.name = name
        self.size = size
        self.last_modified = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeContainerClient:
    def __init__(self, blobs: list[FakeBlob] | None = None, error: Exception | None = None) -> None:
        self.blobs = blobs or []
        self.error = error
        self.prefixes: list[str | None] = []

    def list_blobs(self, *, name_starts_with: str | None = None):
        self.prefixes.append(name_starts_with)

        async def iterator():
            if self.error:
                raise self.error
            for blob in self.blobs:
                yield blob

        return iterator()


class FakeBlobServiceClient:
    def __init__(self, container_client: FakeContainerClient) -> None:
        self.container_client = container_client
        self.closed = False

    def get_container_client(self, container: str) -> FakeContainerClient:
        assert container == "costs"
        return self.container_client

    async def close(self) -> None:
        self.closed = True


def test_list_cost_blobs_requires_complete_configuration() -> None:
    client = StorageExportClient(
        make_settings(
            azure_cost_storage_account_url=None,
            azure_cost_storage_container=None,
        )
    )

    with pytest.raises(StorageClientError, match="Azure Storage 尚未完整設定"):
        asyncio.run(client.list_cost_blobs(max_results=5))


def test_list_cost_blobs_returns_blob_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    credential = DummyCredential()
    container_client = FakeContainerClient([FakeBlob("cost-management/a.csv", 128)])
    service_client = FakeBlobServiceClient(container_client)

    monkeypatch.setattr("azure_cost_mcp.storage.create_azure_credential", lambda _: credential)
    monkeypatch.setattr(
        "azure_cost_mcp.storage.BlobServiceClient",
        lambda account_url, credential: service_client,
    )

    client = StorageExportClient(make_settings())
    result = asyncio.run(client.list_cost_blobs(prefix=None, max_results=5))

    assert result == [
        {
            "name": "cost-management/a.csv",
            "size": 128,
            "last_modified": "2026-01-01T00:00:00+00:00",
        }
    ]
    assert container_client.prefixes == ["cost-management"]
    assert service_client.closed is True
    assert credential.closed is True


def test_list_cost_blobs_maps_storage_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    credential = DummyCredential()
    not_found_client = FakeBlobServiceClient(
        FakeContainerClient(error=ResourceNotFoundError(message="missing"))
    )

    monkeypatch.setattr("azure_cost_mcp.storage.create_azure_credential", lambda _: credential)
    monkeypatch.setattr(
        "azure_cost_mcp.storage.BlobServiceClient",
        lambda account_url, credential: not_found_client,
    )

    client = StorageExportClient(make_settings())
    with pytest.raises(StorageClientError, match="container 'costs' 不存在"):
        asyncio.run(client.list_cost_blobs(max_results=5))

    error_client = FakeBlobServiceClient(
        FakeContainerClient(error=HttpResponseError(message="denied"))
    )
    monkeypatch.setattr(
        "azure_cost_mcp.storage.BlobServiceClient",
        lambda account_url, credential: error_client,
    )

    with pytest.raises(StorageClientError, match="Azure Storage 查詢失敗：denied"):
        asyncio.run(client.list_cost_blobs(max_results=5))
