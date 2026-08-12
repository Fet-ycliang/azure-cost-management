from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from migrate_cost_center_tags import (
    _apply_plan,
    _load_retryable_resource_ids,
    build_migration_plan,
)


def _resource(tags: dict[str, str]) -> dict:
    return {
        "id": "/subscriptions/sub-a/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a",
        "name": "vm-a",
        "type": "Microsoft.Compute/virtualMachines",
        "resourceGroup": "rg-a",
        "subscriptionId": "sub-a",
        "tags": tags,
    }


def test_build_migration_plan_copies_then_deletes_legacy_tag() -> None:
    plans = build_migration_plan([_resource({"CostCenter": "3901"})])

    assert len(plans) == 1
    assert plans[0].action == "copy-and-delete"
    assert plans[0].legacy_value == "3901"


def test_build_migration_plan_deletes_matching_legacy_tag_only() -> None:
    plans = build_migration_plan(
        [_resource({"CostCenter": "3901", "cost_center": "3901"})]
    )

    assert len(plans) == 1
    assert plans[0].action == "delete-legacy"


def test_build_migration_plan_preserves_conflicting_values() -> None:
    plans = build_migration_plan(
        [_resource({"CostCenter": "3901", "cost_center": "6251"})]
    )

    assert len(plans) == 1
    assert plans[0].action == "conflict"


def test_build_migration_plan_skips_empty_legacy_value() -> None:
    plans = build_migration_plan([_resource({"CostCenter": ""})])

    assert len(plans) == 1
    assert plans[0].action == "skip-empty"


class RecordingTagWriter:
    def __init__(self, *, fail_merge: bool = False) -> None:
        self.fail_merge = fail_merge
        self.calls: list[tuple[str, dict[str, str] | list[str]]] = []

    async def patch_resource_tags(self, resource_id: str, *, tags: dict[str, str]) -> None:
        self.calls.append(("merge", tags))
        if self.fail_merge:
            raise httpx.HTTPError("merge failed")

    async def delete_resource_tags(self, resource_id: str, *, tag_keys: list[str]) -> None:
        self.calls.append(("delete", tag_keys))


def test_apply_plan_merges_standard_key_before_deleting_legacy_key() -> None:
    plan = build_migration_plan([_resource({"CostCenter": "3901"})])[0]
    writer = RecordingTagWriter()

    status, error = asyncio.run(_apply_plan(plan, [writer]))

    assert (status, error) == ("migrated", None)
    assert writer.calls == [
        ("merge", {"cost_center": "3901"}),
        ("delete", ["CostCenter"]),
    ]


def test_apply_plan_keeps_legacy_key_when_merge_fails() -> None:
    plan = build_migration_plan([_resource({"CostCenter": "3901"})])[0]
    writer = RecordingTagWriter(fail_merge=True)

    status, error = asyncio.run(_apply_plan(plan, [writer]))

    assert status == "failed-merge"
    assert error == "merge failed"
    assert writer.calls == [("merge", {"cost_center": "3901"})]


def test_load_retryable_resource_ids_only_includes_transient_errors(tmp_path: Path) -> None:
    report_file = tmp_path / "migration.json"
    report_file.write_text(
        json.dumps(
            {
                "outcomes": [
                    {
                        "resource_id": "/resources/retry",
                        "status": "failed-delete",
                        "error": "request failed with status 429",
                    },
                    {
                        "resource_id": "/resources/forbidden",
                        "status": "failed-merge",
                        "error": "request failed with status 403",
                    },
                    {
                        "resource_id": "/resources/success",
                        "status": "migrated",
                        "error": None,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    assert _load_retryable_resource_ids(str(report_file)) == {"/resources/retry"}
