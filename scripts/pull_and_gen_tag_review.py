#!/usr/bin/env python3
"""拉取 Azure 資源 tag 快照並產生全欄位 Markdown Review。

功能：
  1. 對指定 subscription 列表執行 az resource list
  2. 依訂閱 → RG 分組，產生每 RG 一份 markdown（含所有 tag 欄位）
  3. 產生每訂閱一份 index markdown
  4. 產生全域 _index.md

用法：
    python scripts/pull_and_gen_tag_review.py [--date YYYY-MM-DD] [--out-dir PATH] [--dry-run]

選項：
    --date YYYY-MM-DD   快照日期（預設：今天）
    --out-dir PATH      輸出目錄（預設：.cache/tag-review）
    --sub-ids ID,...    只處理指定 subscription ID（逗號分隔）；預設全部
    --dry-run           只列印，不寫檔
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

AZ = "az.cmd" if sys.platform == "win32" else "az"

SUBSCRIPTIONS = [
    {"id": "23adb6f9-dc6a-40ed-aad6-c549b9bbe4c0", "name": "IDTT-AIVerse_Prod"},
    {"id": "ae0cdff2-430d-4d9c-8b1f-56f7f7163261", "name": "IDTT-Customer_Data_Platform"},
    {"id": "1d077479-3fc2-4f1f-82b4-0a5789393fd2", "name": "IDTT-AIVerse_Dev"},
    {"id": "8ba00d96-08ee-451f-a0c7-809fb4c1d29c", "name": "IDTT-Agent_Assistant"},
]

EXCLUDE_TYPES = {
    "microsoft.network/networkinterfaces",
    "microsoft.network/privateendpoints",
    "microsoft.network/privatednszones",
    "microsoft.network/privatednszones/virtualnetworklinks",
    "microsoft.automation/automationaccounts/runbooks",
    "microsoft.cognitiveservices/accounts/projects",
    "microsoft.powerplatform/enterprisepolicies",
}


# ---------------------------------------------------------------------------
# 拉資料
# ---------------------------------------------------------------------------

def pull_resources(sub_id: str, sub_name: str) -> list[dict]:
    print(f"  [pull] {sub_name} ({sub_id})", flush=True)
    cmd = [AZ, "resource", "list", "--subscription", sub_id, "--output", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [error] {result.stderr.strip()[:200]}", file=sys.stderr)
        return []
    raw: list[dict] = json.loads(result.stdout)
    resources = []
    for r in raw:
        if r.get("type", "").lower() in EXCLUDE_TYPES:
            continue
        if "subscriptionId" not in r:
            r["subscriptionId"] = sub_id
        r["_sub_name"] = sub_name
        resources.append(r)
    print(f"    → {len(resources)} 筆（排除 {len(raw) - len(resources)} 筆子資源）", flush=True)
    return resources


# ---------------------------------------------------------------------------
# Markdown 產生
# ---------------------------------------------------------------------------

def _short_type(rtype: str) -> str:
    return "/".join(rtype.split("/")[-2:]) if "/" in rtype else rtype


def _collect_tag_keys(resources: list[dict]) -> list[str]:
    keys: set[str] = set()
    for r in resources:
        keys.update((r.get("tags") or {}).keys())
    # 固定優先順序，其餘 alphabetical
    priority = ["cost_center", "EnvType", "Purpose", "workload", "owner"]
    ordered = [k for k in priority if k in keys]
    rest = sorted(k for k in keys if k not in priority)
    return ordered + rest


def write_rg_md(path: Path, *, rg: str, sub_name: str, snapshot_date: str,
                resources: list[dict], tag_keys: list[str]) -> None:
    lines = [
        "---",
        f"rg: {rg}",
        f"subscription: {sub_name}",
        f'snapshot_date: "{snapshot_date}"',
        f"total_resources: {len(resources)}",
        "---",
        "",
        f"# {rg}",
        "",
        f"> 快照日期：{snapshot_date}　訂閱：{sub_name}　資源數：{len(resources)}",
        "",
    ]

    if tag_keys:
        header = "| 資源名稱 | 類型 |" + "".join(f" {k} |" for k in tag_keys)
        sep = "| --- | --- |" + " --- |" * len(tag_keys)
        lines += [header, sep]
        for r in sorted(resources, key=lambda x: x.get("name", "")):
            tags = r.get("tags") or {}
            row = f"| {r.get('name','')} | {_short_type(r.get('type',''))} |"
            for k in tag_keys:
                v = str(tags.get(k, "")).strip()
                row += f" {v if v else '_(空)_'} |"
            lines.append(row)
    else:
        lines += ["| 資源名稱 | 類型 |", "| --- | --- |"]
        for r in sorted(resources, key=lambda x: x.get("name", "")):
            lines.append(f"| {r.get('name','')} | {_short_type(r.get('type',''))} |")

    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_sub_index(path: Path, *, sub_name: str, snapshot_date: str,
                    rg_stats: list[dict]) -> None:
    rg_stats_sorted = sorted(rg_stats, key=lambda x: x["rg"])
    lines = [
        "---",
        f"subscription: {sub_name}",
        f'snapshot_date: "{snapshot_date}"',
        f"total_rgs: {len(rg_stats)}",
        "---",
        "",
        f"# {sub_name} — RG 清單",
        "",
        f"> 快照日期：{snapshot_date}　RG 數：{len(rg_stats)}",
        "",
        "| Resource Group | 資源數 | Tag Keys |",
        "| --- | ---: | --- |",
    ]
    for s in rg_stats_sorted:
        keys_str = ", ".join(s["tag_keys"][:8]) + ("…" if len(s["tag_keys"]) > 8 else "")
        lines.append(f"| [{s['rg']}](./{s['rg']}.md) | {s['total']} | {keys_str} |")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_global_index(path: Path, *, snapshot_date: str, sub_stats: list[dict]) -> None:
    lines = [
        "---",
        f'snapshot_date: "{snapshot_date}"',
        "---",
        "",
        "# Tag Review 全域索引",
        "",
        f"> 快照日期：{snapshot_date}",
        "",
        "| 訂閱 | RG 數 | 資源數 |",
        "| --- | ---: | ---: |",
    ]
    for s in sorted(sub_stats, key=lambda x: x["sub_name"]):
        lines.append(
            f"| [{s['sub_name']}](./{s['sub_name']}/_index.md) |"
            f" {s['rg_count']} | {s['resource_count']} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--out-dir", default=".cache/tag-review")
    parser.add_argument("--sub-ids", default=None, help="只處理指定 sub ID，逗號分隔")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    snapshot_date = args.date
    out_dir = Path(args.out_dir) / snapshot_date

    if args.sub_ids:
        filter_ids = {s.strip() for s in args.sub_ids.split(",")}
        subs = [s for s in SUBSCRIPTIONS if s["id"] in filter_ids]
    else:
        subs = SUBSCRIPTIONS

    print(f"快照日期：{snapshot_date}，訂閱數：{len(subs)}，輸出：{out_dir}")

    all_resources: list[dict] = []
    for sub in subs:
        resources = pull_resources(sub["id"], sub["name"])
        all_resources.extend(resources)

    if not all_resources:
        print("[warn] 沒有取得任何資源", file=sys.stderr)
        return 1

    print(f"\n共 {len(all_resources)} 筆資源，開始產生 Markdown…")

    # 依訂閱 → RG 分組
    by_sub: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in all_resources:
        sub_name = r.get("_sub_name", "unknown")
        rg = r.get("resourceGroup") or r.get("resource_group") or "(unknown)"
        by_sub[sub_name][rg].append(r)

    sub_stats = []
    for sub_name, rg_dict in sorted(by_sub.items()):
        rg_stats = []
        for rg, rg_resources in sorted(rg_dict.items()):
            tag_keys = _collect_tag_keys(rg_resources)
            rg_stats.append({"rg": rg, "total": len(rg_resources), "tag_keys": tag_keys})

            if not args.dry_run:
                md_path = out_dir / sub_name / f"{rg}.md"
                write_rg_md(
                    md_path,
                    rg=rg, sub_name=sub_name, snapshot_date=snapshot_date,
                    resources=rg_resources, tag_keys=tag_keys,
                )
            else:
                print(f"  [dry-run] {sub_name}/{rg}.md  ({len(rg_resources)} 資源, tags: {tag_keys[:5]})")

        if not args.dry_run:
            write_sub_index(
                out_dir / sub_name / "_index.md",
                sub_name=sub_name, snapshot_date=snapshot_date, rg_stats=rg_stats,
            )
        sub_stats.append({
            "sub_name": sub_name,
            "rg_count": len(rg_dict),
            "resource_count": sum(s["total"] for s in rg_stats),
        })

    if not args.dry_run:
        write_global_index(
            out_dir / "_index.md",
            snapshot_date=snapshot_date, sub_stats=sub_stats,
        )

    total_rgs = sum(s["rg_count"] for s in sub_stats)
    total_res = sum(s["resource_count"] for s in sub_stats)
    print(f"\n[done] 訂閱：{len(sub_stats)}，RG：{total_rgs}，資源：{total_res}")
    if not args.dry_run:
        print(f"       輸出目錄：{out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
