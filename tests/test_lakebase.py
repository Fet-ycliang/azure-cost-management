"""Unit tests for LakebaseClient and lakebase_models."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.helpers import make_settings


def _lb_settings(**overrides):
    return make_settings(
        lakebase_enabled=True,
        lakebase_pg_url="postgresql+asyncpg://user:pass@localhost:5432/testdb",
        **overrides,
    )


# ---------------------------------------------------------------------------
# LakebaseClient.is_configured
# ---------------------------------------------------------------------------


class TestIsConfigured:
    def test_false_when_disabled(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(make_settings(lakebase_enabled=False))
        assert not client.is_configured()

    def test_false_when_no_url_or_instance(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(
            make_settings(
                lakebase_enabled=True,
                lakebase_pg_url=None,
                lakebase_instance_name=None,
            )
        )
        assert not client.is_configured()

    def test_true_when_pg_url_set(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(_lb_settings())
        assert client.is_configured()

    def test_true_when_instance_and_database_set(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(
            make_settings(
                lakebase_enabled=True,
                lakebase_pg_url=None,
                lakebase_instance_name="my-instance",
                lakebase_database="mydb",
            )
        )
        assert client.is_configured()


# ---------------------------------------------------------------------------
# LakebaseClient.is_ready
# ---------------------------------------------------------------------------


class TestIsReady:
    def test_false_before_init(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(_lb_settings())
        assert not client.is_ready()

    def test_true_when_session_maker_set(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(_lb_settings())
        client._session_maker = MagicMock()
        assert client.is_ready()


# ---------------------------------------------------------------------------
# _check_imports helper
# ---------------------------------------------------------------------------


def test_check_imports_raises_helpful_error_when_missing() -> None:
    import sys
    from unittest.mock import patch

    with patch.dict(sys.modules, {"sqlalchemy": None, "asyncpg": None}):
        from azure_cost_mcp import lakebase as lb_module
        with pytest.raises(ImportError, match="uv sync --group lakebase"):
            lb_module._check_imports()


# ---------------------------------------------------------------------------
# upsert_tag_snapshots
# ---------------------------------------------------------------------------


class TestUpsertTagSnapshots:
    def test_returns_zero_when_not_configured(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(make_settings(lakebase_enabled=False))
        assert asyncio.run(client.upsert_tag_snapshots([], "2026-05-06")) == 0

    def test_returns_zero_when_not_ready(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(_lb_settings())
        assert asyncio.run(client.upsert_tag_snapshots([], "2026-05-06")) == 0

    def test_upserts_via_session(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        resources = [
            {
                "id": "/subscriptions/sub-a/vm-1",
                "name": "vm-1",
                "type": "Microsoft.Compute/virtualMachines",
                "resourceGroup": "rg-1",
                "subscriptionId": "sub-a",
                "location": "eastasia",
                "tags": {"cost_center": "eng"},
            }
        ]
        mock_session = AsyncMock()
        mock_session.merge = AsyncMock()

        @asynccontextmanager
        async def _fake_scope():
            yield mock_session

        client = LakebaseClient(_lb_settings())
        client._session_maker = MagicMock()

        with patch.object(client, "session_scope", _fake_scope):
            count = asyncio.run(client.upsert_tag_snapshots(resources, "2026-05-06"))

        assert count == 1
        mock_session.merge.assert_called_once()


# ---------------------------------------------------------------------------
# record_tag_changes
# ---------------------------------------------------------------------------


class TestRecordTagChanges:
    def test_returns_zero_when_not_configured(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(make_settings(lakebase_enabled=False))
        assert asyncio.run(client.record_tag_changes([], dry_run=True, rationale="")) == 0

    def test_returns_zero_when_not_ready(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(_lb_settings())
        assert asyncio.run(client.record_tag_changes([], dry_run=True, rationale="")) == 0

    def test_writes_change_row_with_correct_fields(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        diff_entries = [
            {
                "resource_id": "/sub/rg/vm-1",
                "unchanged": {"cost_center": "eng"},
                "added": {"Environment": "prod"},
                "modified": {},
            }
        ]
        mock_session = MagicMock()  # session.add() is sync, MagicMock avoids unawaited warning

        @asynccontextmanager
        async def _fake_scope():
            yield mock_session

        client = LakebaseClient(_lb_settings())
        client._session_maker = MagicMock()

        with patch.object(client, "session_scope", _fake_scope):
            count = asyncio.run(
                client.record_tag_changes(diff_entries, dry_run=False, rationale="batch fix")
            )

        assert count == 1
        mock_session.add.assert_called_once()
        row = mock_session.add.call_args[0][0]
        assert row.rationale == "batch fix"
        assert row.dry_run is False
        assert row.after_tags.get("Environment") == "prod"

    def test_marks_dry_run_status(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        mock_session = MagicMock()  # session.add() is sync

        @asynccontextmanager
        async def _fake_scope():
            yield mock_session

        diff_entries = [
            {"resource_id": "/r1", "unchanged": {}, "added": {"k": "v"}, "modified": {}}
        ]
        client = LakebaseClient(_lb_settings())
        client._session_maker = MagicMock()

        with patch.object(client, "session_scope", _fake_scope):
            asyncio.run(client.record_tag_changes(diff_entries, dry_run=True, rationale=""))

        row = mock_session.add.call_args[0][0]
        assert row.dry_run is True
        assert row.status == "dry-run"


# ---------------------------------------------------------------------------
# find_similar_tagged_resources
# ---------------------------------------------------------------------------


class TestFindSimilarTaggedResources:
    def test_returns_empty_when_not_configured(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(make_settings(lakebase_enabled=False))
        result = asyncio.run(
            client.find_similar_tagged_resources(
                "Microsoft.Compute/virtualMachines", "rg-1", required_keys=["cost_center"]
            )
        )
        assert result == []

    def test_returns_empty_when_not_ready(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        client = LakebaseClient(_lb_settings())
        result = asyncio.run(
            client.find_similar_tagged_resources("", "", required_keys=[])
        )
        assert result == []

    def test_returns_matching_rows(self) -> None:
        from azure_cost_mcp.lakebase import LakebaseClient

        mock_row = MagicMock()
        mock_row.to_dict.return_value = {"name": "vm-ref", "tags": {"cost_center": "eng"}}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_row]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def _fake_scope():
            yield mock_session

        client = LakebaseClient(_lb_settings())
        client._session_maker = MagicMock()

        with patch.object(client, "session_scope", _fake_scope):
            results = asyncio.run(
                client.find_similar_tagged_resources(
                    "Microsoft.Compute/virtualMachines",
                    "rg-1",
                    required_keys=["cost_center"],
                    limit=3,
                )
            )

        assert len(results) == 1
        assert results[0]["name"] == "vm-ref"


# ---------------------------------------------------------------------------
# LakebaseClient.close
# ---------------------------------------------------------------------------


def test_close_disposes_engine_and_cancels_task() -> None:
    from azure_cost_mcp.lakebase import LakebaseClient

    client = LakebaseClient(_lb_settings())

    mock_engine = AsyncMock()
    mock_task = MagicMock()
    mock_task.cancel = MagicMock()

    async def fake_await_task():
        from asyncio import CancelledError
        raise CancelledError

    mock_task.__await__ = lambda self: fake_await_task().__await__()

    client._engine = mock_engine
    client._token_refresh_task = None  # no background task
    client._session_maker = MagicMock()

    asyncio.run(client.close())

    mock_engine.dispose.assert_called_once()
    assert client._engine is None


# ---------------------------------------------------------------------------
# lakebase_models to_dict
# ---------------------------------------------------------------------------


class TestLakebaseModelsToDicts:
    def test_tag_snapshot_to_dict(self) -> None:
        from datetime import date, datetime, timezone

        from azure_cost_mcp.lakebase_models import TagSnapshot

        snap = TagSnapshot(
            id="test-uuid",
            snapshot_date=date(2026, 5, 6),
            subscription_id="sub-a",
            resource_id="/subscriptions/sub-a/vm-1",
            name="vm-1",
            type="Microsoft.Compute/virtualMachines",
            resource_group="rg-1",
            location="eastasia",
            tags={"cost_center": "eng"},
        )
        snap.created_at = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)

        d = snap.to_dict()

        assert d["name"] == "vm-1"
        assert d["tags"] == {"cost_center": "eng"}
        assert "2026-05-06" in str(d["snapshot_date"])

    def test_tag_change_to_dict(self) -> None:
        from datetime import datetime, timezone

        from azure_cost_mcp.lakebase_models import TagChange

        change = TagChange(
            id="change-uuid",
            resource_id="/r1",
            before_tags={},
            after_tags={"Environment": "prod"},
            applied_by="test",
            rationale="batch fix",
            dry_run=False,
            status="ok",
        )
        change.applied_at = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)

        d = change.to_dict()

        assert d["after_tags"] == {"Environment": "prod"}
        assert d["dry_run"] is False
        assert d["status"] == "ok"

    def test_tag_embedding_to_dict(self) -> None:
        from datetime import date

        from azure_cost_mcp.lakebase_models import TagEmbedding

        emb = TagEmbedding(
            id="emb-uuid",
            resource_id="/r1",
            tag_summary="name: vm-1, type: VirtualMachine",
            embedding=None,
            snapshot_date=date(2026, 5, 6),
        )

        d = emb.to_dict()

        assert d["resource_id"] == "/r1"
        assert "2026-05-06" in str(d["snapshot_date"])
