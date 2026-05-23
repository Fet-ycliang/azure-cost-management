"""Microsoft Learn 文件搜尋用戶端。

使用 learn.microsoft.com 公開 Search API，不需認證。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_LEARN_SEARCH_URL = "https://learn.microsoft.com/api/search/"
_DEFAULT_TIMEOUT = 10.0


class LearnSearchError(Exception):
    """Microsoft Learn API 呼叫失敗。"""


class LearnSearchClient:
    """封裝 Microsoft Learn Search API。"""

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    async def search(
        self,
        query: str,
        *,
        top: int = 5,
        locale: str = "zh-tw",
        category_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """搜尋 Microsoft Learn 文件或課程模組。

        Args:
            query: 搜尋關鍵字。
            top: 回傳筆數上限（1–20）。
            locale: 語系，預設繁體中文（zh-tw）；無繁中內容時自動退回英文。
            category_filter: 限定 category，例如 'Documentation' 或 'Learn'；
                             省略時同時回傳所有類型。

        Returns:
            結果清單，每筆含 title / url / description / category / last_updated。

        Raises:
            LearnSearchError: API 呼叫失敗時。
        """
        params: dict[str, Any] = {
            "search": query,
            "locale": locale,
            "$top": min(max(top, 1), 20),
        }
        if category_filter:
            params["$filter"] = f"category eq '{category_filter}'"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(_LEARN_SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise LearnSearchError(
                f"Learn API HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise LearnSearchError(f"Learn API 連線失敗: {exc}") from exc

        results = data.get("results", [])
        return [_normalize(r) for r in results]


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """將 API 原始結果正規化為簡潔格式。"""
    breadcrumbs = raw.get("breadcrumbs") or []
    breadcrumb_text = " > ".join(b.get("name", "") for b in breadcrumbs if b.get("name"))

    # 取 descriptions 第一筆的 content（比 description 頂層更完整）
    descriptions = raw.get("descriptions") or []
    description = (
        descriptions[0].get("content", "")
        if descriptions
        else raw.get("description", "")
    )
    # 截短至 300 字，避免回應過長
    if len(description) > 300:
        description = description[:297] + "..."

    return {
        "title": raw.get("title", ""),
        "url": raw.get("url", ""),
        "description": description,
        "category": raw.get("category", ""),
        "breadcrumb": breadcrumb_text,
        "last_updated": (raw.get("lastUpdatedDate") or "")[:10],
    }
