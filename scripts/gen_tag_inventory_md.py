#!/usr/bin/env python3
"""Tag 盤點 JSON → Obsidian Markdown + desired tags 範本

讀取 azure_cost_tag_inventory 工具寫入的快照 JSON，產生：
  - .cache/tag-inventory/obsidian/{sub_id}/{rg}.md   (每個 RG 一份)
  - .cache/tag-inventory/obsidian/_index.md          (RG 覆蓋率總表)
  - .cache/tag-inventory/obsidian/tag-gap-summary.md (缺漏 Top N)
  - .cache/tag-inventory/desired/{rg}.json           (desired tags 範本)

用法：
    python scripts/gen_tag_inventory_md.py [OPTIONS]

選項：
    --snapshot-date YYYY-MM-DD   指定快照日期；預設讀最新一天
    --required-tags KEY,...      必要 tag keys，逗號分隔（預設：cost_center）
    --cache-dir PATH             快取根目錄（預設：.cache/tag-inventory）
    --top-gap N                  gap summary 最多顯示幾筆（預設：20）
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 讀取快照
# ---------------------------------------------------------------------------


def _find_latest_snapshot_dir(cache_dir: Path) -> Path | None:
    date_dirs = sorted(
        (d for d in cache_dir.iterdir() if d.is_dir() and len(d.name) == 10 and d.name[4] == "-"),
        reverse=True,
    )
    return date_dirs[0] if date_dirs else None


def _load_snapshots(snapshot_dir: Path) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for json_file in sorted(snapshot_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            resources.extend(data.get("resources", []))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[warn] 無法讀取 {json_file}: {exc}", file=sys.stderr)
    return resources


# ---------------------------------------------------------------------------
# Tag 判斷工具
# ---------------------------------------------------------------------------


def _is_fully_tagged(tags: dict[str, Any], required_keys: list[str]) -> bool:
    return all(str(tags.get(k, "")).strip() for k in required_keys)


def _missing_keys(tags: dict[str, Any], required_keys: list[str]) -> list[str]:
    return [k for k in required_keys if not str(tags.get(k, "")).strip()]


# ---------------------------------------------------------------------------
# PBI 2.1 — 每個 RG 一份 Markdown
# ---------------------------------------------------------------------------


def _rg_md_path(obsidian_dir: Path, sub_id: str, rg: str) -> Path:
    safe_sub = sub_id.replace("/", "_").strip("_")
    safe_rg = rg.replace("/", "_").strip("_")
    return obsidian_dir / safe_sub / f"{safe_rg}.md"


def _write_rg_md(
    path: Path,
    *,
    rg: str,
    sub_id: str,
    snapshot_date: str,
    resources: list[dict[str, Any]],
    required_keys: list[str],
) -> None:
    tagged = sum(1 for r in resources if _is_fully_tagged(r.get("tags") or {}, required_keys))
    untagged = len(resources) - tagged
    tags_yaml = "[" + ", ".join(required_keys) + "]"

    lines: list[str] = [
        "---",
        f"rg: {rg}",
        f"subscription: {sub_id}",
        f'snapshot_date: "{snapshot_date}"',
        f"total_resources: {len(resources)}",
        f"tagged: {tagged}",
        f"untagged: {untagged}",
        f"required_tags: {tags_yaml}",
        "---",
        "",
        f"# {rg}",
        "",
        f"> 快照日期：{snapshot_date}　訂閱：`{sub_id}`",
        f"> 資源總數：{len(resources)}　完整標記：{tagged}　缺標記：{untagged}",
        "",
    ]

    # 表頭
    header = "| 名稱 | 類型 | 位置 |" + "".join(f" {k} |" for k in required_keys)
    separator = "| --- | --- | --- |" + " --- |" * len(required_keys)
    lines.append(header)
    lines.append(separator)

    for r in sorted(resources, key=lambda x: x.get("name", "")):
        tags = r.get("tags") or {}
        name = r.get("name", "")
        rtype = r.get("type", "")
        short_type = "/".join(rtype.split("/")[-2:]) if "/" in rtype else rtype
        loc = r.get("location", "")
        row = f"| {name} | {short_type} | {loc} |"
        for k in required_keys:
            val = str(tags.get(k, "")).strip()
            row += f" {val if val else '_(缺)_'} |"
        lines.append(row)

    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# PBI 2.2 — _index.md 總索引
# ---------------------------------------------------------------------------


def _write_index_md(
    path: Path,
    *,
    snapshot_date: str,
    rg_stats: list[dict[str, Any]],
) -> None:
    rg_stats_sorted = sorted(rg_stats, key=lambda x: x["coverage_pct"])

    lines: list[str] = [
        "---",
        f'snapshot_date: "{snapshot_date}"',
        f"total_resource_groups: {len(rg_stats)}",
        "---",
        "",
        "# Tag 盤點總覽",
        "",
        f"> 快照日期：{snapshot_date}",
        "",
        "| Resource Group | 訂閱 | 總數 | 完整標記 | 缺標記 | 覆蓋率 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]

    for stat in rg_stats_sorted:
        rg = stat["rg"]
        sub = stat["subscription_id"]
        safe_sub = sub.replace("/", "_").strip("_")
        safe_rg = rg.replace("/", "_").strip("_")
        md_rel = f"./{safe_sub}/{safe_rg}.md"
        pct = stat["coverage_pct"]
        lines.append(
            f"| [{rg}]({md_rel}) | `{sub}` | {stat['total']} |"
            f" {stat['tagged']} | {stat['untagged']} | {pct:.1f}% |"
        )

    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# PBI 2.2 — tag-gap-summary.md
# ---------------------------------------------------------------------------


def _write_gap_summary_md(
    path: Path,
    *,
    snapshot_date: str,
    resources: list[dict[str, Any]],
    required_keys: list[str],
    top: int,
) -> None:
    gap_resources = [
        r for r in resources
        if not _is_fully_tagged(r.get("tags") or {}, required_keys)
    ]
    gap_resources.sort(
        key=lambda r: (-len(_missing_keys(r.get("tags") or {}, required_keys)), r.get("name", ""))
    )
    top_resources = gap_resources[:top]

    missing_counter: Counter[str] = Counter()
    for r in gap_resources:
        for k in _missing_keys(r.get("tags") or {}, required_keys):
            missing_counter[k] += 1

    lines: list[str] = [
        "---",
        f'snapshot_date: "{snapshot_date}"',
        f"total_untagged: {len(gap_resources)}",
        "---",
        "",
        "# Tag 缺漏摘要",
        "",
        f"> 快照日期：{snapshot_date}　缺標記資源總數：{len(gap_resources)}",
        "",
        "## 各 Tag Key 缺漏統計",
        "",
        "| Tag Key | 缺漏資源數 |",
        "| --- | ---: |",
    ]
    for key, count in missing_counter.most_common():
        lines.append(f"| `{key}` | {count} |")

    lines += [
        "",
        f"## 缺漏最多的資源（Top {top}）",
        "",
        "| 名稱 | 類型 | RG | 訂閱 | 缺漏 Tag Keys |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in top_resources:
        tags = r.get("tags") or {}
        name = r.get("name", "")
        rtype = r.get("type", "")
        short_type = "/".join(rtype.split("/")[-2:]) if "/" in rtype else rtype
        rg = r.get("resourceGroup", "")
        sub = r.get("subscriptionId", "")
        missing_str = ", ".join(f"`{k}`" for k in _missing_keys(tags, required_keys))
        lines.append(f"| {name} | {short_type} | {rg} | `{sub}` | {missing_str} |")

    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# PBI 2.3 — desired tags 範本
# ---------------------------------------------------------------------------


def _write_desired_json(
    path: Path,
    *,
    resources: list[dict[str, Any]],
    required_keys: list[str],
) -> None:
    entries = []
    for r in resources:
        tags = r.get("tags") or {}
        if _is_fully_tagged(tags, required_keys):
            continue
        desired: dict[str, str] = {k: tags.get(k, "") or "" for k in required_keys}
        entries.append(
            {
                "resource_id": r.get("id", ""),
                "name": r.get("name", ""),
                "type": r.get("type", ""),
                "resource_group": r.get("resourceGroup", ""),
                "subscription_id": r.get("subscriptionId", ""),
                "current_tags": tags,
                "desired_tags": desired,
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Tag 盤點 JSON → Obsidian Markdown + desired 範本")
    parser.add_argument("--snapshot-date", default=None, help="快照日期（YYYY-MM-DD）；預設讀最新一天")
    parser.add_argument("--required-tags", default="cost_center", help="必要 tag keys，逗號分隔")
    parser.add_argument("--cache-dir", default=".cache/tag-inventory", help="快取根目錄")
    parser.add_argument("--top-gap", type=int, default=20, help="gap summary 最多顯示幾筆")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    required_keys = [k.strip() for k in args.required_tags.split(",") if k.strip()]
    if not required_keys:
        print("[error] --required-tags 不能為空", file=sys.stderr)
        return 1

    if args.snapshot_date:
        snapshot_dir = cache_dir / args.snapshot_date
        if not snapshot_dir.is_dir():
            print(f"[error] 找不到快照目錄：{snapshot_dir}", file=sys.stderr)
            return 1
    else:
        snapshot_dir = _find_latest_snapshot_dir(cache_dir)
        if snapshot_dir is None:
            print(f"[error] 在 {cache_dir} 找不到任何快照目錄（需為 YYYY-MM-DD 格式）", file=sys.stderr)
            return 1

    snapshot_date = snapshot_dir.name
    print(f"[info] 讀取快照：{snapshot_dir}")

    resources = _load_snapshots(snapshot_dir)
    if not resources:
        print("[warn] 快照中沒有資源，結束。", file=sys.stderr)
        return 0

    print(f"[info] 共 {len(resources)} 筆資源，必要 tags：{required_keys}")

    obsidian_dir = cache_dir / "obsidian"
    desired_dir = cache_dir / "desired"

    # 依 (subscription, rg) 分組
    by_sub_rg: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in resources:
        sub_id = r.get("subscriptionId") or "unknown"
        rg = r.get("resourceGroup") or "(unknown)"
        by_sub_rg[sub_id][rg].append(r)

    rg_stats: list[dict[str, Any]] = []
    desired_by_rg: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for sub_id, rg_dict in sorted(by_sub_rg.items()):
        for rg, rg_resources in sorted(rg_dict.items()):
            md_path = _rg_md_path(obsidian_dir, sub_id, rg)
            _write_rg_md(
                md_path,
                rg=rg,
                sub_id=sub_id,
                snapshot_date=snapshot_date,
                resources=rg_resources,
                required_keys=required_keys,
            )

            tagged = sum(1 for r in rg_resources if _is_fully_tagged(r.get("tags") or {}, required_keys))
            coverage = round(tagged / len(rg_resources) * 100, 1) if rg_resources else 0.0
            rg_stats.append(
                {
                    "rg": rg,
                    "subscription_id": sub_id,
                    "total": len(rg_resources),
                    "tagged": tagged,
                    "untagged": len(rg_resources) - tagged,
                    "coverage_pct": coverage,
                }
            )
            for r in rg_resources:
                if not _is_fully_tagged(r.get("tags") or {}, required_keys):
                    desired_by_rg[rg].append(r)

    rg_count = sum(len(rgs) for rgs in by_sub_rg.values())
    print(f"[info] 已產生 {rg_count} 個 RG 的 Markdown → {obsidian_dir}")

    _write_index_md(obsidian_dir / "_index.md", snapshot_date=snapshot_date, rg_stats=rg_stats)
    print(f"[info] 總索引 → {obsidian_dir / '_index.md'}")

    _write_gap_summary_md(
        obsidian_dir / "tag-gap-summary.md",
        snapshot_date=snapshot_date,
        resources=resources,
        required_keys=required_keys,
        top=args.top_gap,
    )
    print(f"[info] Tag 缺漏摘要 → {obsidian_dir / 'tag-gap-summary.md'}")

    desired_written = 0
    for rg, untagged_resources in sorted(desired_by_rg.items()):
        safe_rg = rg.replace("/", "_").strip("_")
        _write_desired_json(
            desired_dir / f"{safe_rg}.json",
            resources=untagged_resources,
            required_keys=required_keys,
        )
        desired_written += 1

    if desired_written:
        print(f"[info] desired tags 範本（{desired_written} 個 RG）→ {desired_dir}")

    total = len(resources)
    total_untagged = sum(r["untagged"] for r in rg_stats)
    coverage_pct = round((total - total_untagged) / total * 100, 1) if total else 0.0
    print(f"[done] 完成！資源總數：{total}，缺標記：{total_untagged}，覆蓋率：{coverage_pct}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
