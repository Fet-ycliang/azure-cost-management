from __future__ import annotations

import asyncio
import json

import pytest

from azure_cost_mcp.cache import ApiCache

from .helpers import make_settings


def test_api_cache_disabled_bypasses_cache() -> None:
    cache = ApiCache(make_settings(azure_cost_cache_mode="disabled"))
    calls = {"count": 0}

    async def loader() -> dict[str, int]:
        calls["count"] += 1
        return {"value": calls["count"]}

    first = asyncio.run(cache.get_or_set("usage", {"scope": "sub-a"}, loader))
    second = asyncio.run(cache.get_or_set("usage", {"scope": "sub-a"}, loader))

    assert first == {"value": 1}
    assert second == {"value": 2}
    assert calls["count"] == 2


def test_api_cache_memory_hits_until_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    current_time = {"value": 100.0}
    monkeypatch.setattr("azure_cost_mcp.cache.time.time", lambda: current_time["value"])

    cache = ApiCache(
        make_settings(
            azure_cost_cache_mode="memory",
            azure_cost_cache_ttl_seconds=10,
        )
    )
    calls = {"count": 0}

    async def loader() -> dict[str, int]:
        calls["count"] += 1
        return {"value": calls["count"]}

    first = asyncio.run(cache.get_or_set("usage", {"scope": "sub-a"}, loader))
    current_time["value"] = 105.0
    second = asyncio.run(cache.get_or_set("usage", {"scope": "sub-a"}, loader))
    current_time["value"] = 111.0
    third = asyncio.run(cache.get_or_set("usage", {"scope": "sub-a"}, loader))

    assert first == {"value": 1}
    assert second == {"value": 1}
    assert third == {"value": 2}
    assert calls["count"] == 2


def test_api_cache_disk_round_trip_restores_into_memory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("azure_cost_mcp.cache.time.time", lambda: 100.0)
    settings = make_settings(
        azure_cost_cache_mode="disk",
        azure_cost_cache_dir=str(tmp_path),
        azure_cost_cache_ttl_seconds=30,
    )
    cache = ApiCache(settings)

    asyncio.run(cache.set("usage", {"scope": "sub-a"}, {"value": 42}))

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["value"] == {"value": 42}

    restored_cache = ApiCache(settings)
    value = asyncio.run(restored_cache.get("usage", {"scope": "sub-a"}))

    assert value == {"value": 42}
    assert len(restored_cache._memory) == 1


def test_api_cache_disk_ignores_expired_and_corrupt_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("azure_cost_mcp.cache.time.time", lambda: 100.0)
    settings = make_settings(
        azure_cost_cache_mode="disk",
        azure_cost_cache_dir=str(tmp_path),
        azure_cost_cache_ttl_seconds=30,
    )
    cache = ApiCache(settings)
    key = cache._build_key("usage", {"scope": "sub-a"})

    expired_file = tmp_path / f"{key}.json"
    expired_file.write_text(
        json.dumps({"expires_at": 99.0, "value": {"value": 1}}),
        encoding="utf-8",
    )

    assert asyncio.run(cache.get("usage", {"scope": "sub-a"})) is None
    assert expired_file.exists() is False

    corrupt_file = tmp_path / f"{key}.json"
    corrupt_file.write_text("{not-json", encoding="utf-8")

    assert asyncio.run(cache.get("usage", {"scope": "sub-a"})) is None
    assert corrupt_file.exists() is False


def test_api_cache_zero_ttl_never_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("azure_cost_mcp.cache.time.time", lambda: 100.0)
    cache = ApiCache(
        make_settings(
            azure_cost_cache_mode="disk",
            azure_cost_cache_ttl_seconds=0,
        )
    )

    asyncio.run(cache.set("usage", {"scope": "sub-a"}, {"value": 1}))

    assert asyncio.run(cache.get("usage", {"scope": "sub-a"})) is None
