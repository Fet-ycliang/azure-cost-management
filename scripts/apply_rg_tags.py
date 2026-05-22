#!/usr/bin/env python3
"""讀取 desired JSON，用 az tag update --operation Merge 批次補寫 tags。

用法：
    python scripts/apply_rg_tags.py --rg fet-cdpai-prod [--dry-run]

選項：
    --rg NAME           Resource Group 名稱（必填）
    --desired-dir PATH  desired JSON 目錄（預設：.cache/tag-inventory/desired）
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

# 這些 RG pattern 由系統管理，有 deny assignment，永遠跳過
SKIP_RG_PREFIXES = (
    "databricks-rg-",
    "mc_",                        # AKS managed node RG
    "networkwatcherrg",
    "defaultresourcegroup-",
    "synapseworkspace-managedrg-", # Synapse managed RG
    "azureapp-auto-alerts-",       # Azure Monitor auto-alert RG
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rg", required=True)
    parser.add_argument("--desired-dir", default=".cache/tag-inventory/desired")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--name-filter", default="", help="只處理名稱含此字串的資源（不區分大小寫）")
    args = parser.parse_args()

    target = Path(args.desired_dir) / f"{args.rg}.json"
    if not target.exists():
        print(f"[error] 找不到 {target}", file=sys.stderr)
        return 1

    entries: list[dict] = json.loads(target.read_text(encoding="utf-8"))
    if args.name_filter:
        entries = [e for e in entries if args.name_filter.lower() in e.get("name", "").lower()]
        print(f"[filter] --name-filter={args.name_filter!r}，符合 {len(entries)} 筆")

    ok = err = skip = 0
    for e in entries:
        current = e.get("current_tags") or {}
        desired = e.get("desired_tags") or {}
        # 只補真正需要新增 / 修改的 key；空字串視為「尚未決定」，略過
        to_add = {k: v for k, v in desired.items() if v and current.get(k) != v}
        if not to_add:
            skip += 1
            continue

        resource_id = e.get("resource_id") or e.get("id") or ""
        if not resource_id:
            print(f"  [skip] 無 resource_id，略過 {e.get('name')}")
            skip += 1
            continue

        # 跳過系統管理的 RG（有 deny assignment，無法寫 tag）
        rid_lower = resource_id.lower()
        rg_part = ""
        try:
            rg_part = rid_lower.split("/resourcegroups/")[1].split("/")[0]
        except IndexError:
            pass
        if any(rg_part.startswith(p) for p in SKIP_RG_PREFIXES):
            print(f"  [skip] 系統管理 RG ({rg_part})，略過 {e.get('name')}")
            skip += 1
            continue

        print(f"[{'dry-run' if args.dry_run else 'apply'}] {e['name']}")
        print(f"  新增 tags: {to_add}")

        if not args.dry_run:
            # Windows az.cmd 透過 cmd.exe 執行，括號是 CMD 群組字元。
            # resource ID 含括號時（如 ContainerInsights(xxx)）用 shell=True + 字串引號。
            has_parens = "(" in resource_id or ")" in resource_id
            if has_parens:
                tag_str = " ".join(f'"{k}={v}"' for k, v in to_add.items())
                cmd_str = f'{AZ} tag update --resource-id "{resource_id}" --operation Merge --tags {tag_str}'
                result = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
            else:
                cmd = [
                    AZ, "tag", "update",
                    "--resource-id", resource_id,
                    "--operation", "Merge",
                    "--tags", *[f"{k}={v}" for k, v in to_add.items()],
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
    print(f"\n{'dry-run ' if args.dry_run else ''}完成：{total} 筆，更新 {ok}，跳過（已符合）{skip}，錯誤 {err}")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
