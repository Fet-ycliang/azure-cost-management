"""
refresh_current_tags.py
從 Azure 重抓所有 desired JSON 的 current_tags，並統一格式（id → resource_id）。

用法：
    python scripts/refresh_current_tags.py [--rg <rg-name>]

選項：
    --rg    只更新指定 RG 的 JSON（不指定則更新全部）
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

AZ = "az.cmd"
DESIRED_DIR = Path(".cache/tag-inventory/desired")
STANDARD_KEYS = ["resource_id", "name", "type", "current_tags", "desired_tags"]


def get_sub_and_rg(entry: dict) -> tuple[str, str] | None:
    """從 entry 取出 (subscription_id, resource_group)，兼容 resource_id / id 兩種欄位。"""
    rid = entry.get("resource_id") or entry.get("id") or ""
    m = re.match(r"/subscriptions/([^/]+)/resourceGroups/([^/]+)/", rid, re.I)
    if m:
        return m.group(1), m.group(2)
    return None


def normalize_entry(entry: dict) -> dict:
    """統一欄位格式：id → resource_id，移除 resource_group 欄位。"""
    return {
        "resource_id": entry.get("resource_id") or entry.get("id", ""),
        "name": entry.get("name", ""),
        "type": entry.get("type", ""),
        "current_tags": entry.get("current_tags", {}),
        "desired_tags": entry.get("desired_tags", {}),
    }


def refresh_file(f: Path) -> str:
    data = json.loads(f.read_text(encoding="utf-8"))
    if not data:
        return "skip (empty)"

    # 正規化格式
    data = [normalize_entry(e) for e in data]

    info = get_sub_and_rg(data[0])
    if not info:
        return "skip (no resource_id)"
    sub_id, rg = info

    # 從 Azure 重抓
    r = subprocess.run(
        [AZ, "resource", "list", "--subscription", sub_id, "--resource-group", rg],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return f"error: {r.stderr.strip()[:80]}"

    resources = json.loads(r.stdout)
    lookup = {res["id"].lower(): res.get("tags") or {} for res in resources}

    updated = 0
    for entry in data:
        rid_lower = entry["resource_id"].lower()
        if rid_lower in lookup:
            entry["current_tags"] = lookup[rid_lower]
            updated += 1

    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"OK ({updated}/{len(data)})"


def main():
    parser = argparse.ArgumentParser(description="Refresh current_tags from Azure")
    parser.add_argument("--rg", help="只更新指定 RG（不含 .json）")
    args = parser.parse_args()

    if args.rg:
        files = [DESIRED_DIR / f"{args.rg}.json"]
        files = [f for f in files if f.exists()]
        if not files:
            print(f"[ERROR] 找不到 {args.rg}.json")
            sys.exit(1)
    else:
        files = sorted(DESIRED_DIR.glob("*.json"))

    print(f"共 {len(files)} 個檔案，開始更新...")
    ok = err = skip = 0
    for f in files:
        result = refresh_file(f)
        status = result.split()[0]
        if status == "OK":
            ok += 1
        elif status == "skip":
            skip += 1
        else:
            err += 1
        print(f"  [{status}] {f.name}: {result}")

    print(f"\n完成: {ok} 成功, {err} 錯誤, {skip} 跳過")


if __name__ == "__main__":
    main()
