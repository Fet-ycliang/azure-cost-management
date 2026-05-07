"""Databricks AI Gateway embedding client。"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Settings

logger = logging.getLogger(__name__)


class DatabricksEmbeddingClient:
    """呼叫 Databricks AI Gateway /embeddings endpoint。

    端點格式：https://<workspace>/ai-gateway/mlflow/v1/embeddings
    模型：databricks-bge-large-en（1024 dim）或其他已部署模型。
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def is_configured(self) -> bool:
        return bool(
            self._settings.databricks_embedding_url
            and self._settings.databricks_token
        )

    async def get_embedding(self, text: str) -> list[float]:
        """取得單一文字的 embedding 向量。"""
        return (await self.get_embeddings_batch([text]))[0]

    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """批次取得 embedding 向量（單次 HTTP 請求）。"""
        if not self.is_configured():
            raise RuntimeError(
                "Embedding 未設定：需要 DATABRICKS_EMBEDDING_URL 與 DATABRICKS_TOKEN。"
            )

        try:
            import httpx
        except ImportError as exc:
            raise ImportError("httpx 未安裝，請執行：uv sync") from exc

        url = self._settings.databricks_embedding_url
        token = self._settings.databricks_token
        model = self._settings.databricks_embedding_model

        payload = {"model": model, "input": texts}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # OpenAI 相容格式：data[].embedding
        items: list[dict] = data["data"]
        items.sort(key=lambda x: x["index"])
        return [item["embedding"] for item in items]


def _resource_to_text(resource: dict) -> str:
    """將資源 tag snapshot 轉換為可嵌入的文字摘要。"""
    tags = resource.get("tags") or {}
    tag_str = ", ".join(f"{k}={v}" for k, v in sorted(tags.items()) if v)
    return (
        f"Type: {resource.get('type', '')}\n"
        f"Name: {resource.get('name', '')}\n"
        f"ResourceGroup: {resource.get('resource_group', '')}\n"
        f"Tags: {tag_str or '(none)'}"
    )
