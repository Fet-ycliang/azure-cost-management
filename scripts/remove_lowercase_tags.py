#!/usr/bin/env python3
"""移除 legacy tag key（如 CostCenter），前提是資源已有對應標準 key（如 cost_center）。

用法：
    python scripts/remove_lowercase_tags.py --rg apim-app-bst-rg [--dry-run]

選項：
    --rg NAME           Resource Group 名稱（必填）
    --desired-dir PATH  desired JSON 目錄（預設：.cache/tag-inventory/desired）
    --remove-keys K,... 要移除的 legacy key，逗號分隔（預設：CostCenter）
    --require-keys K,.. 移除前需確認存在的標準 key，逗號分隔（預設：cost_center）
    --dry-run           只印出指令，不實際執行
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

AZ = "az.cmd" if platform.system() == "Windows" else "az"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rg", required=True)
    parser.add_argument("--desired-dir", default=".cache/tag-inventory/desired")
    parser.add_argument("--remove-keys", default="CostCenter", help="要移除的 tag key，逗號分隔")
    parser.add_argument("--require-keys", default="cost_center", help="移除前需確認存在的 tag key，逗號分隔")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    remove_keys = [k.strip() for k in args.remove_keys.split(",") if k.strip()]
    require_keys = [k.strip() for k in args.require_keys.split(",") if k.strip()]

    target = Path(args.desired_dir) / f"{args.rg}.json"
    if not target.exists():
        print(f"[error] 找不到 {target}", file=sys.stderr)
        return 1

    entries: list[dict] = json.loads(target.read_text(encoding="utf-8"))

    ok = err = skip = 0
    for e in entries:
        current = e.get("current_tags") or {}
        resource_id = e.get("resource_id") or e.get("id") or ""
        name = e.get("name", "?")

        # 確認 remove_keys 至少有一個存在於 current_tags
        keys_to_remove = [k for k in remove_keys if k in current]
        if not keys_to_remove:
            skip += 1
            continue

        # 確認 require_keys 都已存在且有值
        missing_required = [k for k in require_keys if not current.get(k)]
        if missing_required:
            print(f"  [skip] {name}：缺少必要 key {missing_required}，跳過不刪")
            skip += 1
            continue

        if not resource_id:
            print(f"  [skip] {name}：無 resource_id")
            skip += 1
            continue

        print(f"[{'dry-run' if args.dry_run else 'remove'}] {name}")
        print(f"  刪除 tags: {keys_to_remove}")

        if not args.dry_run:
            cmd = [
                AZ, "tag", "update",
                "--resource-id", resource_id,
                "--operation", "Delete",
                "--tags", *[f"{k}=" for k in keys_to_remove],
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                ok += 1
                print(f"  [ok]")
            else:
                err += 1
                print(f"  [error] {result.stderr.strip()}", file=sys.stderr)
        else:
            ok += 1

    total = ok + err + skip
    print(f"\n{'dry-run ' if args.dry_run else ''}完成：{total} 筆，移除 {ok}，跳過 {skip}，錯誤 {err}")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
