#!/usr/bin/env python3
"""批次填寫 desired tags — 同一 RG 用相同的 tag 值

讀取 gen_tag_inventory_md.py 產生的 desired/{rg}.json，把每一筆
desired_tags 裡的空值填入指定的 key=value，再寫回原檔。

用法：
    python scripts/fill_rg_tags.py \\
        --rg ppenv-3901-prod-rg \\
        --tags "cost_center=3901,environment=prod,workload=ppenv,application=ppenv-platform,owner=ycliang@fareastone.com.tw" \\
        --desired-dir .cache/tag-inventory/desired

選項：
    --rg NAME           Resource Group 名稱（必填）
    --tags K=V,...      要填入的 tag key-value 對，逗號分隔（必填）
    --desired-dir PATH  desired JSON 目錄（預設：.cache/tag-inventory/desired）
    --overwrite         強制覆蓋已有值的欄位（預設：僅填空值）
    --dry-run           只印出變更，不寫入檔案
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _parse_tags(raw: str) -> dict[str, str]:
    """解析 'k1=v1,k2=v2' 格式為 dict。"""
    result: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"tag 格式錯誤，應為 key=value，但收到：{pair!r}")
        k, v = pair.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            raise ValueError(f"tag key 不得為空：{pair!r}")
        result[k] = v
    return result


def _fill_entry(
    entry: dict[str, Any],
    fill_tags: dict[str, str],
    *,
    overwrite: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    """填寫單一 entry 的 desired_tags，回傳 (更新後 entry, 本次實際填入的 key-value)。"""
    desired: dict[str, str] = entry.get("desired_tags") or {}
    changed: dict[str, str] = {}
    for k, v in fill_tags.items():
        if k not in desired:
            # 若 desired_tags 裡根本沒有這個 key，直接新增
            desired[k] = v
            changed[k] = v
        elif overwrite or not desired[k]:
            if desired[k] != v:
                desired[k] = v
                changed[k] = v
    entry["desired_tags"] = desired
    return entry, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="批次填寫 desired tags（同 RG 相同值）")
    parser.add_argument("--rg", required=True, help="Resource Group 名稱")
    parser.add_argument("--tags", required=True, help="tag key-value 對，格式：k1=v1,k2=v2")
    parser.add_argument(
        "--desired-dir",
        default=".cache/tag-inventory/desired",
        help="desired JSON 目錄（預設：.cache/tag-inventory/desired）",
    )
    parser.add_argument("--overwrite", action="store_true", help="強制覆蓋已有值的欄位")
    parser.add_argument("--dry-run", action="store_true", help="只印出變更，不寫入檔案")
    args = parser.parse_args()

    desired_dir = Path(args.desired_dir)
    target_file = desired_dir / f"{args.rg}.json"

    if not target_file.exists():
        print(f"[error] 找不到 desired JSON：{target_file}", file=sys.stderr)
        return 1

    try:
        fill_tags = _parse_tags(args.tags)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    if not fill_tags:
        print("[error] --tags 不能為空", file=sys.stderr)
        return 1

    print(f"[info] 目標檔案：{target_file}")
    print(f"[info] 填入 tags：{fill_tags}")
    if args.overwrite:
        print("[info] 模式：強制覆蓋（--overwrite）")
    else:
        print("[info] 模式：僅填空值")
    if args.dry_run:
        print("[info] dry-run 模式，不寫入檔案")

    try:
        entries: list[dict[str, Any]] = json.loads(target_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[error] 無法讀取 {target_file}：{exc}", file=sys.stderr)
        return 1

    if not isinstance(entries, list):
        print(f"[error] {target_file} 格式錯誤，預期為 JSON array", file=sys.stderr)
        return 1

    total = len(entries)
    updated_count = 0
    updated_entries: list[dict[str, Any]] = []

    for entry in entries:
        entry, changed = _fill_entry(entry, fill_tags, overwrite=args.overwrite)
        updated_entries.append(entry)
        if changed:
            updated_count += 1
            if args.dry_run:
                name = entry.get("name", entry.get("resource_id", "?"))
                print(f"  [dry-run] {name}: {changed}")

    print(f"[info] {total} 筆資源，{updated_count} 筆有變更")

    if not args.dry_run:
        target_file.write_text(
            json.dumps(updated_entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[done] 已寫回：{target_file}")
    else:
        print("[done] dry-run 完成，未寫入任何檔案")

    return 0


if __name__ == "__main__":
    sys.exit(main())
