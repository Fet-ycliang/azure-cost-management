"""Azure Storage 成本匯出資料 helper。"""

from __future__ import annotations

from typing import Any

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.storage.blob.aio import BlobServiceClient

from .auth import create_azure_credential
from .config import Settings


class StorageClientError(RuntimeError):
    """Azure Storage 查詢失敗。"""


class StorageExportClient:
    """Azure Storage blob 查詢 client。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def list_cost_blobs(
        self,
        *,
        prefix: str | None = None,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """列出成本匯出檔案。"""
        account_url = self._settings.azure_cost_storage_account_url
        container = self._settings.azure_cost_storage_container
        if not account_url or not container:
            raise StorageClientError(
                "Azure Storage 尚未完整設定。請設定 AZURE_COST_STORAGE_ACCOUNT_URL 與 "
                "AZURE_COST_STORAGE_CONTAINER。"
            )

        credential = create_azure_credential(self._settings)
        service_client: BlobServiceClient | None = None
        try:
            service_client = BlobServiceClient(account_url=account_url, credential=credential)
            container_client = service_client.get_container_client(container)
            blobs = []
            async for blob in container_client.list_blobs(
                name_starts_with=prefix or self._settings.azure_cost_storage_prefix
            ):
                blobs.append(
                    {
                        "name": blob.name,
                        "size": blob.size,
                        "last_modified": (
                            blob.last_modified.isoformat() if blob.last_modified else None
                        ),
                    }
                )
                if len(blobs) >= max_results:
                    break
            return blobs
        except ResourceNotFoundError as error:
            raise StorageClientError(
                f"Azure Storage container '{container}' 不存在，或目前登入身分沒有讀取權限。"
            ) from error
        except HttpResponseError as error:
            raise StorageClientError(f"Azure Storage 查詢失敗：{error.message}") from error
        finally:
            if service_client is not None:
                await service_client.close()
            await credential.close()
