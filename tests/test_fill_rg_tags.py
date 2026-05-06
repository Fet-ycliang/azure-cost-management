from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from fill_rg_tags import _fill_entry, _parse_tags, main


# ---------------------------------------------------------------------------
# _parse_tags
# ---------------------------------------------------------------------------


def test_parse_tags_basic():
    result = _parse_tags("cost_center=3901,environment=prod")
    assert result == {"cost_center": "3901", "environment": "prod"}


def test_parse_tags_single():
    assert _parse_tags("owner=alice@example.com") == {"owner": "alice@example.com"}


def test_parse_tags_value_with_equals():
    # value 本身含 = 時，只以第一個 = 切割
    result = _parse_tags("owner=a=b")
    assert result["owner"] == "a=b"


def test_parse_tags_strips_whitespace():
    result = _parse_tags(" cost_center = 3901 , environment = dev ")
    assert result == {"cost_center": "3901", "environment": "dev"}


def test_parse_tags_empty_pair_ignored():
    result = _parse_tags("cost_center=3901,,environment=dev")
    assert result == {"cost_center": "3901", "environment": "dev"}


def test_parse_tags_missing_equals_raises():
    with pytest.raises(ValueError, match="key=value"):
        _parse_tags("badvalue")


def test_parse_tags_empty_key_raises():
    with pytest.raises(ValueError, match="key 不得為空"):
        _parse_tags("=value")


# ---------------------------------------------------------------------------
# _fill_entry
# ---------------------------------------------------------------------------

ENTRY_EMPTY = {
    "resource_id": "/subscriptions/sub/resourceGroups/rg/providers/M.C/vm/vm1",
    "name": "vm1",
    "type": "Microsoft.Compute/virtualMachines",
    "resource_group": "rg",
    "subscription_id": "sub",
    "current_tags": {},
    "desired_tags": {"cost_center": "", "environment": "", "owner": ""},
}

ENTRY_PARTIAL = {
    **ENTRY_EMPTY,
    "desired_tags": {"cost_center": "3901", "environment": "", "owner": ""},
}


def test_fill_entry_fills_empty_values():
    fill = {"cost_center": "3901", "environment": "prod", "owner": "alice"}
    entry, changed = _fill_entry(copy.deepcopy(ENTRY_EMPTY), fill, overwrite=False)
    assert entry["desired_tags"] == {"cost_center": "3901", "environment": "prod", "owner": "alice"}
    assert set(changed.keys()) == {"cost_center", "environment", "owner"}


def test_fill_entry_skips_existing_without_overwrite():
    fill = {"cost_center": "9999", "environment": "prod", "owner": "alice"}
    entry, changed = _fill_entry(copy.deepcopy(ENTRY_PARTIAL), fill, overwrite=False)
    # cost_center 已有值，不覆蓋
    assert entry["desired_tags"]["cost_center"] == "3901"
    assert entry["desired_tags"]["environment"] == "prod"
    assert "cost_center" not in changed


def test_fill_entry_overwrite_replaces_existing():
    fill = {"cost_center": "9999"}
    entry, changed = _fill_entry(copy.deepcopy(ENTRY_PARTIAL), fill, overwrite=True)
    assert entry["desired_tags"]["cost_center"] == "9999"
    assert changed == {"cost_center": "9999"}


def test_fill_entry_no_change_returns_empty_changed():
    # 值相同，不算 changed
    fill = {"cost_center": "3901"}
    _, changed = _fill_entry(copy.deepcopy(ENTRY_PARTIAL), fill, overwrite=True)
    assert changed == {}


def test_fill_entry_adds_new_key():
    fill = {"workload": "ppenv"}
    entry, changed = _fill_entry(copy.deepcopy(ENTRY_EMPTY), fill, overwrite=False)
    assert entry["desired_tags"]["workload"] == "ppenv"
    assert changed == {"workload": "ppenv"}


# ---------------------------------------------------------------------------
# main (CLI integration)
# ---------------------------------------------------------------------------


@pytest.fixture()
def desired_dir(tmp_path: Path) -> Path:
    d = tmp_path / "desired"
    d.mkdir()
    return d


def _write_desired(desired_dir: Path, rg: str, entries: list[dict]) -> Path:
    f = desired_dir / f"{rg}.json"
    f.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return f


def test_main_fills_empty_values(desired_dir: Path, monkeypatch: pytest.MonkeyPatch):
    entries = [dict(ENTRY_EMPTY)]
    _write_desired(desired_dir, "rg-1", entries)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fill_rg_tags.py",
            "--rg", "rg-1",
            "--tags", "cost_center=3901,environment=prod,owner=alice",
            "--desired-dir", str(desired_dir),
        ],
    )
    assert main() == 0

    result = json.loads((desired_dir / "rg-1.json").read_text(encoding="utf-8"))
    assert result[0]["desired_tags"]["cost_center"] == "3901"
    assert result[0]["desired_tags"]["environment"] == "prod"
    assert result[0]["desired_tags"]["owner"] == "alice"


def test_main_dry_run_does_not_write(desired_dir: Path, monkeypatch: pytest.MonkeyPatch):
    entries = [dict(ENTRY_EMPTY)]
    f = _write_desired(desired_dir, "rg-1", entries)
    original = f.read_text(encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fill_rg_tags.py",
            "--rg", "rg-1",
            "--tags", "cost_center=3901",
            "--desired-dir", str(desired_dir),
            "--dry-run",
        ],
    )
    assert main() == 0
    assert f.read_text(encoding="utf-8") == original


def test_main_missing_file_returns_error(desired_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fill_rg_tags.py",
            "--rg", "nonexistent-rg",
            "--tags", "cost_center=3901",
            "--desired-dir", str(desired_dir),
        ],
    )
    assert main() == 1


def test_main_bad_tags_format_returns_error(desired_dir: Path, monkeypatch: pytest.MonkeyPatch):
    _write_desired(desired_dir, "rg-1", [dict(ENTRY_EMPTY)])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fill_rg_tags.py",
            "--rg", "rg-1",
            "--tags", "badvalue",
            "--desired-dir", str(desired_dir),
        ],
    )
    assert main() == 1


def test_main_overwrite_replaces_existing(desired_dir: Path, monkeypatch: pytest.MonkeyPatch):
    entries = [dict(ENTRY_PARTIAL)]
    _write_desired(desired_dir, "rg-1", entries)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fill_rg_tags.py",
            "--rg", "rg-1",
            "--tags", "cost_center=9999",
            "--desired-dir", str(desired_dir),
            "--overwrite",
        ],
    )
    assert main() == 0

    result = json.loads((desired_dir / "rg-1.json").read_text(encoding="utf-8"))
    assert result[0]["desired_tags"]["cost_center"] == "9999"
