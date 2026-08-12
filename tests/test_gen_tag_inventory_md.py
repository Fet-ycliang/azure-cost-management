from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from gen_tag_inventory_md import (
    _find_latest_snapshot_dir,
    _is_fully_tagged,
    _load_snapshots,
    _missing_keys,
    _write_desired_json,
    _write_gap_summary_md,
    _write_index_md,
    _write_rg_md,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REQUIRED = ["cost_center", "Environment"]

RESOURCES = [
    {
        "id": "/subscriptions/sub-a/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1",
        "name": "vm-1",
        "type": "Microsoft.Compute/virtualMachines",
        "resourceGroup": "rg-1",
        "subscriptionId": "sub-a",
        "location": "eastus",
        "tags": {"cost_center": "eng", "Environment": "prod"},
    },
    {
        "id": "/subscriptions/sub-a/resourceGroups/rg-1/providers/Microsoft.Storage/storageAccounts/st-1",
        "name": "st-1",
        "type": "Microsoft.Storage/storageAccounts",
        "resourceGroup": "rg-1",
        "subscriptionId": "sub-a",
        "location": "eastus",
        "tags": {"cost_center": "eng"},
    },
    {
        "id": "/subscriptions/sub-a/resourceGroups/rg-2/providers/Microsoft.Compute/virtualMachines/vm-2",
        "name": "vm-2",
        "type": "Microsoft.Compute/virtualMachines",
        "resourceGroup": "rg-2",
        "subscriptionId": "sub-a",
        "location": "westus",
        "tags": {},
    },
]


# ---------------------------------------------------------------------------
# 工具函式
# ---------------------------------------------------------------------------


def test_is_fully_tagged_all_present() -> None:
    tags = {"cost_center": "eng", "Environment": "prod"}
    assert _is_fully_tagged(tags, REQUIRED) is True


def test_is_fully_tagged_missing_one() -> None:
    tags = {"cost_center": "eng"}
    assert _is_fully_tagged(tags, REQUIRED) is False


def test_is_fully_tagged_empty_string_counts_as_missing() -> None:
    tags = {"cost_center": "", "Environment": "prod"}
    assert _is_fully_tagged(tags, REQUIRED) is False


def test_missing_keys_returns_absent_and_empty() -> None:
    tags = {"cost_center": "eng", "Environment": ""}
    assert _missing_keys(tags, REQUIRED) == ["Environment"]


# ---------------------------------------------------------------------------
# 讀取快照
# ---------------------------------------------------------------------------


def test_find_latest_snapshot_dir(tmp_path: Path) -> None:
    (tmp_path / "2026-05-01").mkdir()
    (tmp_path / "2026-05-06").mkdir()
    (tmp_path / "not-a-date").mkdir()
    result = _find_latest_snapshot_dir(tmp_path)
    assert result is not None
    assert result.name == "2026-05-06"


def test_find_latest_snapshot_dir_empty(tmp_path: Path) -> None:
    assert _find_latest_snapshot_dir(tmp_path) is None


def test_load_snapshots_reads_resources(tmp_path: Path) -> None:
    payload = {
        "subscription_id": "sub-a",
        "snapshot_date": "2026-05-06",
        "resource_count": 1,
        "resources": [RESOURCES[0]],
    }
    (tmp_path / "sub-a.json").write_text(json.dumps(payload), encoding="utf-8")
    result = _load_snapshots(tmp_path)
    assert len(result) == 1
    assert result[0]["name"] == "vm-1"


def test_load_snapshots_skips_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("not-json", encoding="utf-8")
    result = _load_snapshots(tmp_path)
    assert result == []


# ---------------------------------------------------------------------------
# PBI 2.1 — 每個 RG 的 Markdown
# ---------------------------------------------------------------------------


def test_write_rg_md_creates_file_with_frontmatter(tmp_path: Path) -> None:
    md_path = tmp_path / "sub-a" / "rg-1.md"
    _write_rg_md(
        md_path,
        rg="rg-1",
        sub_id="sub-a",
        snapshot_date="2026-05-06",
        resources=RESOURCES[:2],
        required_keys=REQUIRED,
    )
    content = md_path.read_text(encoding="utf-8")
    assert "rg: rg-1" in content
    assert 'snapshot_date: "2026-05-06"' in content
    assert "total_resources: 2" in content
    assert "tagged: 1" in content
    assert "untagged: 1" in content


def test_write_rg_md_table_contains_missing_marker(tmp_path: Path) -> None:
    md_path = tmp_path / "rg.md"
    _write_rg_md(
        md_path,
        rg="rg-1",
        sub_id="sub-a",
        snapshot_date="2026-05-06",
        resources=RESOURCES[:2],
        required_keys=REQUIRED,
    )
    content = md_path.read_text(encoding="utf-8")
    assert "_(缺)_" in content
    assert "vm-1" in content
    assert "st-1" in content


# ---------------------------------------------------------------------------
# PBI 2.2 — _index.md 與 tag-gap-summary.md
# ---------------------------------------------------------------------------


def test_write_index_md_lists_all_rgs(tmp_path: Path) -> None:
    rg_stats = [
        {"rg": "rg-1", "subscription_id": "sub-a", "total": 2, "tagged": 1, "untagged": 1, "coverage_pct": 50.0},
        {"rg": "rg-2", "subscription_id": "sub-a", "total": 1, "tagged": 0, "untagged": 1, "coverage_pct": 0.0},
    ]
    index_path = tmp_path / "_index.md"
    _write_index_md(index_path, snapshot_date="2026-05-06", rg_stats=rg_stats)
    content = index_path.read_text(encoding="utf-8")
    assert "rg-1" in content
    assert "rg-2" in content
    assert "50.0%" in content
    assert "0.0%" in content


def test_write_gap_summary_md_shows_missing_counts(tmp_path: Path) -> None:
    gap_path = tmp_path / "tag-gap-summary.md"
    _write_gap_summary_md(
        gap_path,
        snapshot_date="2026-05-06",
        resources=RESOURCES,
        required_keys=REQUIRED,
        top=10,
    )
    content = gap_path.read_text(encoding="utf-8")
    assert "total_untagged: 2" in content
    assert "`Environment`" in content
    assert "st-1" in content
    assert "vm-2" in content


# ---------------------------------------------------------------------------
# PBI 2.3 — desired tags 範本
# ---------------------------------------------------------------------------


def test_write_desired_json_only_includes_untagged(tmp_path: Path) -> None:
    desired_path = tmp_path / "rg-1.json"
    _write_desired_json(desired_path, resources=RESOURCES[:2], required_keys=REQUIRED)
    entries = json.loads(desired_path.read_text(encoding="utf-8"))
    # vm-1 is fully tagged; st-1 is missing Environment
    assert len(entries) == 1
    assert entries[0]["name"] == "st-1"
    assert "Environment" in entries[0]["desired_tags"]
    assert entries[0]["desired_tags"]["cost_center"] == "eng"


def test_write_desired_json_empty_when_all_tagged(tmp_path: Path) -> None:
    desired_path = tmp_path / "rg.json"
    _write_desired_json(desired_path, resources=[RESOURCES[0]], required_keys=REQUIRED)
    entries = json.loads(desired_path.read_text(encoding="utf-8"))
    assert entries == []


# ---------------------------------------------------------------------------
# 整合：main() 端對端
# ---------------------------------------------------------------------------


def test_main_end_to_end(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "2026-05-06"
    snapshot_dir.mkdir()
    payload = {
        "subscription_id": "sub-a",
        "snapshot_date": "2026-05-06",
        "resource_count": len(RESOURCES),
        "resources": RESOURCES,
    }
    (snapshot_dir / "sub-a.json").write_text(json.dumps(payload), encoding="utf-8")

    exit_code = main.__wrapped__ if hasattr(main, "__wrapped__") else None
    result = main.__wrapped__([  # type: ignore[attr-defined]
        "--cache-dir", str(tmp_path),
        "--required-tags", "cost_center,Environment",
        "--snapshot-date", "2026-05-06",
    ]) if exit_code else None

    # Invoke via sys.argv patching
    import sys as _sys
    old_argv = _sys.argv
    _sys.argv = [
        "gen_tag_inventory_md.py",
        "--cache-dir", str(tmp_path),
        "--required-tags", "cost_center,Environment",
        "--snapshot-date", "2026-05-06",
    ]
    try:
        ret = main()
    finally:
        _sys.argv = old_argv

    assert ret == 0

    obsidian_dir = tmp_path / "obsidian"
    assert (obsidian_dir / "_index.md").exists()
    assert (obsidian_dir / "tag-gap-summary.md").exists()
    assert (obsidian_dir / "sub-a" / "rg-1.md").exists()
    assert (obsidian_dir / "sub-a" / "rg-2.md").exists()

    desired_dir = tmp_path / "desired"
    assert (desired_dir / "rg-1.json").exists()
    assert (desired_dir / "rg-2.json").exists()


def test_main_returns_error_when_snapshot_dir_missing(tmp_path: Path) -> None:
    import sys as _sys
    old_argv = _sys.argv
    _sys.argv = [
        "gen_tag_inventory_md.py",
        "--cache-dir", str(tmp_path),
        "--snapshot-date", "2099-01-01",
    ]
    try:
        ret = main()
    finally:
        _sys.argv = old_argv
    assert ret == 1


def _write_project_cost_table(base_dir: Path, projects: list[dict]) -> None:
    target = base_dir / "monthly-reports" / "2026" / "04"
    target.mkdir(parents=True)
    payload = {
        "period_columns": ["2026-04"],
        "projects": projects,
    }
    (target / "project-cost-table.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_view_md(
    base_dir: Path,
    *,
    name: str,
    resource_groups: list[str] | None = None,
    purposes: list[str] | None = None,
    metric: str = "ActualCost",
) -> None:
    target = base_dir / "views-mapping" / "views"
    target.mkdir(parents=True, exist_ok=True)

    lines = [
        "---",
        f'name: "{name}"',
        f"metric: {metric}",
    ]
    if resource_groups:
        lines.append("resource_groups:")
        lines.extend(f'  - "{rg}"' for rg in resource_groups)
    if purposes:
        lines.append("purposes:")
        lines.extend(f'  - "{purpose}"' for purpose in purposes)
    lines += ["---", "", f"# {name}", ""]
    (target / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


def test_write_rg_md_splits_sections_and_marks_pending_cost(tmp_path: Path) -> None:
    required = ["cost_center", "EnvType", "Purpose", "owner"]
    resources = [
        {
            "id": "/subscriptions/sub-a/resourceGroups/rg-1/providers/Microsoft.Compute/virtualMachines/vm-1",
            "name": "vm-1",
            "type": "Microsoft.Compute/virtualMachines",
            "resourceGroup": "rg-1",
            "subscriptionId": "sub-a",
            "location": "eastus",
            "tags": {
                "cost_center": "3901",
                "EnvType": "Production",
                "Purpose": "fet-ids",
                "owner": "John Zeng (598493)",
            },
        },
        {
            "id": "/subscriptions/sub-a/resourceGroups/rg-1/providers/Microsoft.Storage/storageAccounts/st-1",
            "name": "st-1",
            "type": "Microsoft.Storage/storageAccounts",
            "resourceGroup": "rg-1",
            "subscriptionId": "sub-a",
            "location": "eastus",
            "tags": {
                "cost_center": "3901",
                "EnvType": "Production",
                "Purpose": "fet-ids",
            },
        },
    ]
    md_path = tmp_path / "sub-a" / "rg-1.md"

    _write_rg_md(
        md_path,
        rg="rg-1",
        sub_id="sub-a",
        snapshot_date="2026-05-06",
        resources=resources,
        required_keys=required,
        related_tag_links={
            "cost_center": ["[[tag-graph/cost-centers/3901|3901]]"],
            "Purpose": ["[[tag-graph/purposes/fet-ids|fet-ids]]"],
        },
        cost_entries=[],
        cost_period="2026-04",
    )

    content = md_path.read_text(encoding="utf-8")
    assert "## 成本摘要（2026-04）" in content
    assert "- **狀態**: 整理中" in content
    assert "## Tag 關聯" in content
    assert "## 一致" in content
    assert "## 需檢查或確認" in content
    assert "[[tag-graph/index|Tag 關聯圖]]" in content


def test_main_generates_cost_mapping_graph_notes_and_case_insensitive_rg_groups(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "2026-05-06"
    snapshot_dir.mkdir()
    resources = [
        {
            "id": "/subscriptions/sub-a/resourceGroups/RG-1/providers/Microsoft.Compute/virtualMachines/vm-1",
            "name": "vm-1",
            "type": "Microsoft.Compute/virtualMachines",
            "resourceGroup": "RG-1",
            "subscriptionId": "sub-a",
            "location": "eastus",
            "tags": {
                "cost_center": "3901",
                "EnvType": "Production",
                "Purpose": "fet-ids",
                "owner": "John Zeng (598493)",
            },
        },
        {
            "id": "/subscriptions/sub-a/resourceGroups/rg-1/providers/Microsoft.Storage/storageAccounts/st-1",
            "name": "st-1",
            "type": "Microsoft.Storage/storageAccounts",
            "resourceGroup": "rg-1",
            "subscriptionId": "sub-a",
            "location": "eastus",
            "tags": {
                "cost_center": "3901",
                "EnvType": "Production",
                "Purpose": "fet-ids",
            },
        },
        {
            "id": "/subscriptions/sub-a/resourceGroups/rg-2/providers/Microsoft.Storage/storageAccounts/st-2",
            "name": "st-2",
            "type": "Microsoft.Storage/storageAccounts",
            "resourceGroup": "rg-2",
            "subscriptionId": "sub-a",
            "location": "eastus2",
            "tags": {
                "cost_center": "3101",
                "EnvType": "Production",
                "Purpose": "31_ai_lab",
                "owner": "Ralph Liang (527714)",
            },
        },
        {
            "id": "/subscriptions/sub-a/resourceGroups/RG-2/providers/Microsoft.Compute/virtualMachines/vm-2",
            "name": "vm-2",
            "type": "Microsoft.Compute/virtualMachines",
            "resourceGroup": "RG-2",
            "subscriptionId": "sub-a",
            "location": "eastus2",
            "tags": {
                "cost_center": "6251",
                "EnvType": "Production",
                "Purpose": "fet-ids",
                "owner": "John Zeng (598493)",
            },
        },
    ]
    payload = {
        "subscription_id": "sub-a",
        "snapshot_date": "2026-05-06",
        "resource_count": len(resources),
        "resources": resources,
    }
    (snapshot_dir / "sub-a.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "subscription-tenant-map.json").write_text(
        json.dumps(
            [
                {
                    "id": "sub-a",
                    "name": "Subscription Alpha",
                    "tenantId": "tenant-1",
                }
            ]
        ),
        encoding="utf-8",
    )

    _write_project_cost_table(
        tmp_path,
        [
            {
                "source": "rg-1",
                "description": "Project Alpha",
                "platform": "Azure",
                "costs": [1000],
                "computed_2026_04": 900,
                "compute_status": "接近",
            }
        ],
    )
    _write_view_md(tmp_path, name="rg-1", resource_groups=["rg-1"])

    import sys as _sys

    old_argv = _sys.argv
    _sys.argv = [
        "gen_tag_inventory_md.py",
        "--cache-dir", str(tmp_path),
        "--required-tags", "cost_center,EnvType,Purpose,owner",
        "--snapshot-date", "2026-05-06",
    ]
    try:
        ret = main()
    finally:
        _sys.argv = old_argv

    assert ret == 0

    obsidian_dir = tmp_path / "obsidian"
    index_content = (obsidian_dir / "_index.md").read_text(encoding="utf-8")
    assert "cost_period: 2026-04" in index_content
    assert "## Tenant / Subscription / RG" in index_content
    assert "Tenant `tenant-1`" in index_content
    assert "Subscription `Subscription Alpha` (`sub-a`)" in index_content
    assert "## 已對應" in index_content
    assert "Project Alpha" in index_content
    assert "單一 cost_center 掛帳 (3901)" in index_content
    assert "## 需檢查或確認" in index_content
    assert "Cross cost_center 拆帳" in index_content
    assert "total_resource_groups: 2" in index_content
    assert "tag-graph/index" in index_content

    rg_md = obsidian_dir / "sub-a" / "rg-1.md"
    assert rg_md.exists()
    rg_content = rg_md.read_text(encoding="utf-8")
    assert "cost_status: 已對應" in rg_content
    assert "tenant_id: tenant-1" in rg_content
    assert "subscription_name: Subscription Alpha" in rg_content
    assert "charge_model: 單一 cost_center 掛帳 (3901)" in rg_content
    assert "## 帳務歸屬" in rg_content
    assert "Project Alpha" in rg_content
    assert "## 一致" in rg_content
    assert "## 需檢查或確認" in rg_content

    pending_rg_content = (obsidian_dir / "sub-a" / "rg-2.md").read_text(encoding="utf-8")
    assert "charge_model: Cross cost_center 拆帳" in pending_rg_content
    assert "- **charge_model**: Cross cost_center 拆帳" in pending_rg_content

    tag_graph_index = (obsidian_dir / "tag-graph" / "index.md").read_text(encoding="utf-8")
    assert "[[_index|Vault 首頁]]" in tag_graph_index
    assert "[[tag-graph/cost-centers/3901|3901]]" in tag_graph_index

    cost_center_note = (obsidian_dir / "tag-graph" / "cost-centers" / "3901.md").read_text(encoding="utf-8")
    assert "Project Alpha" in cost_center_note
    assert "[[sub-a/rg-1|RG-1]]" in cost_center_note
