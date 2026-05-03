"""成本資料快取 helper。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from .config import Settings


class ApiCache:
    """提供 memory / disk cache 的簡單快取層。"""

    def __init__(self, settings: Settings) -> None:
        self._mode = settings.azure_cost_cache_mode
        self._ttl_seconds = settings.azure_cost_cache_ttl_seconds
        self._cache_dir = Path(settings.azure_cost_cache_dir)
        self._memory: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get_or_set(
        self,
        namespace: str,
        key_payload: dict[str, Any],
        loader: Callable[[], Awaitable[Any]],
    ) -> Any:
        """先讀 cache，沒有命中才呼叫 loader。"""
        cached = await self.get(namespace, key_payload)
        if cached is not None:
            return cached

        value = await loader()
        await self.set(namespace, key_payload, value)
        return value

    async def get(self, namespace: str, key_payload: dict[str, Any]) -> Any | None:
        """取得快取內容。"""
        if self._mode == "disabled" or self._ttl_seconds == 0:
            return None

        key = self._build_key(namespace, key_payload)
        now = time.time()

        async with self._lock:
            memory_entry = self._memory.get(key)
            if memory_entry:
                expires_at, value = memory_entry
                if expires_at > now:
                    return value
                self._memory.pop(key, None)

        if self._mode != "disk":
            return None

        cache_file = self._cache_file(key)
        if not cache_file.exists():
            return None

        try:
            payload = await asyncio.to_thread(self._read_payload, cache_file)
        except (OSError, ValueError, json.JSONDecodeError):
            await asyncio.to_thread(self._safe_unlink, cache_file)
            return None

        expires_at = float(payload.get("expires_at", 0))
        if expires_at <= now:
            await asyncio.to_thread(self._safe_unlink, cache_file)
            return None

        value = payload.get("value")
        async with self._lock:
            self._memory[key] = (expires_at, value)
        return value

    async def set(
        self,
        namespace: str,
        key_payload: dict[str, Any],
        value: Any,
    ) -> None:
        """寫入快取內容。"""
        if self._mode == "disabled" or self._ttl_seconds == 0:
            return

        key = self._build_key(namespace, key_payload)
        expires_at = time.time() + self._ttl_seconds

        async with self._lock:
            self._memory[key] = (expires_at, value)

        if self._mode == "disk":
            payload = {"expires_at": expires_at, "value": value}
            await asyncio.to_thread(self._write_payload, self._cache_file(key), payload)

    def _cache_file(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    @staticmethod
    def _build_key(namespace: str, key_payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            key_payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"{namespace}-{digest}"

    def _write_payload(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _read_payload(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return
