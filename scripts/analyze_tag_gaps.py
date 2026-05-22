#!/usr/bin/env python3
"""分析 Azure 資源 tag 差距，產生 gap 報告。

讀取 .cache/tag-review/{date}/raw/*.json（若不存在則先拉資料），輸出：
  .cache/tag-review/{date}/gaps/_index.md         全域摘要
  .cache/tag-review/{date}/gaps/{sub_name}.md      每訂閱詳細差距

檢查項目：
  1. 缺漏必要 tag（CostCenter / EnvType / Purpose / owner）
  2. 已 review 的 RG 其 Purpose 與預設值不一致

排除規則（系統資源，不計入健康率）：
  - RG 前綴：NetworkWatcherRG、DefaultResourceGroup-、MC_/mc_（AKS 受管）、
             ME_/me_（ACA 受管）、DATABRICKS-RG-/databricks-rg-（Databricks 受管）、
             managed-rg-（Purview 受管）、cloud-shell-storage-（Cloud Shell）
  - 資源類型：VM Extension、EventGrid SystemTopic

用法：
    python scripts/analyze_tag_gaps.py [--date YYYY-MM-DD]
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
    {"id": "d71cbe04-6c66-4b51-affc-1389f315486e", "name": "IDTT-Data_Governance_Enhancement"},
    {"id": "2b3d67c6-07ce-4d8b-b9ff-c729a17b291a", "name": "TO-ABD360"},
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

REQUIRED_KEYS = ["CostCenter", "EnvType", "Purpose", "owner"]

# 系統資源排除規則（不計入健康率）
SYSTEM_RG_PREFIXES = (
    "networkwatcherrg",
    "defaultresourcegroup-",
    "mc_",                          # AKS 受管 RG
    "me_",                          # ACA 受管 RG
    "databricks-rg-",               # Databricks 受管 RG
    "managed-rg-",                  # Purview 受管 RG
    "cloud-shell-storage-",         # Cloud Shell 自動建立
)
SYSTEM_RG_EXACT = {"networkwatcherrg"}

SYSTEM_TYPES = {
    "microsoft.compute/virtualmachines/extensions",
    "microsoft.eventgrid/systemtopics",
}


def _is_system_resource(r: dict) -> bool:
    rg = r.get("resourceGroup", "").lower()
    rtype = r.get("type", "").lower()
    if rtype in SYSTEM_TYPES:
        return True
    if any(rg.startswith(p) for p in SYSTEM_RG_PREFIXES):
        return True
    return False

# EnvType 舊值 → 標準值
OLD_ENVTYPE = {
    "Develop": "dev",
    "Development": "dev",
    "Staging": "bst",
    "Production": "prod",
}
VALID_ENVTYPE = {"dev", "bst", "prod"}

# 已 review 的 RG → 合法 Purpose 集合（少數共用型 RG 可放多個值）
# key: (subscription_name, resource_group_lowercase)
REVIEWED_RG_PURPOSE_MAP: dict[tuple[str, str], set[str]] = {
    ("TO-ABD360", "fet-ids-prod-rg"): {"fet-ids"},
}

# ---------------------------------------------------------------------------
# 資料拉取
# ---------------------------------------------------------------------------

def pull_and_cache(sub: dict, raw_dir: Path) -> list[dict]:
    cache_file = raw_dir / f"{sub['name']}.json"
    if cache_file.exists():
        print(f"  [cache] {sub['name']}")
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data
    print(f"  [pull]  {sub['name']} ({sub['id']})", flush=True)
    cmd = [AZ, "resource", "list", "--subscription", sub["id"], "--output", "json"]
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
            r["subscriptionId"] = sub["id"]
        r["_sub_name"] = sub["name"]
        resources.append(r)
    raw_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(resources, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    → {len(resources)} 筆")
    return resources


# ---------------------------------------------------------------------------
# Gap 分析
# ---------------------------------------------------------------------------

VALID_ENVTYPE = {
    "Develop", "Development", "Staging", "Production",  # 合理的舊值
    "dev", "bst", "prod",                               # 標準化後的新值
}


def _reviewed_rg_purposes(r: dict) -> set[str] | None:
    sub_name = str(r.get("_sub_name", "")).strip()
    rg = str(r.get("resourceGroup", "")).strip().lower()
    if not sub_name or not rg:
        return None
    return REVIEWED_RG_PURPOSE_MAP.get((sub_name, rg))


def analyze_resource(r: dict) -> dict:
    tags = r.get("tags") or {}
    issues: list[str] = []

    # 1. 缺漏必要 tag
    missing = [k for k in REQUIRED_KEYS if not str(tags.get(k, "")).strip()]
    if missing:
        issues.append(f"缺: {', '.join(missing)}")

    # 2. EnvType 非標準值（有值但不在已知清單內）
    env = str(tags.get("EnvType", "")).strip()
    if env and env not in VALID_ENVTYPE:
        issues.append(f"EnvType 非標準值: {env}")

    # 3. 已 review 的 RG Purpose 必須符合預設值
    rg = str(r.get("resourceGroup", "")).strip()
    purpose = str(tags.get("Purpose", "")).strip()
    valid_purposes = _reviewed_rg_purposes(r)
    if valid_purposes and purpose and purpose not in valid_purposes:
        expected_str = " 或 ".join(sorted(valid_purposes))
        issues.append(f"Purpose 不符: RG={rg} 預設為 {expected_str}，實為 {purpose}")

    return {
        "name": r.get("name", ""),
        "type": "/".join(r.get("type", "").split("/")[-2:]),
        "rg": r.get("resourceGroup", ""),
        "issues": issues,
        "missing": missing,
        "tags": tags,
    }


# ---------------------------------------------------------------------------
# Markdown 輸出
# ---------------------------------------------------------------------------

def _esc(v: str) -> str:
    return str(v).replace("|", "\\|")


def write_sub_gap_md(path: Path, *, sub_name: str, snapshot_date: str,
                     resources: list[dict]) -> dict:
    real_resources = [r for r in resources if not _is_system_resource(r)]
    excluded = len(resources) - len(real_resources)

    by_rg: dict[str, list[dict]] = defaultdict(list)
    for r in real_resources:
        result = analyze_resource(r)
        if result["issues"]:
            by_rg[result["rg"]].append(result)

    total_issues = sum(len(v) for v in by_rg.values())
    lines = [
        "---",
        f"subscription: {sub_name}",
        f'snapshot_date: "{snapshot_date}"',
        f"total_resources: {len(real_resources)}",
        f"excluded_system: {excluded}",
        f"resources_with_issues: {total_issues}",
        "---",
        "",
        f"# {sub_name} — Tag Gap 報告",
        "",
        f"> 快照日期：{snapshot_date}　計入資源：{len(real_resources)}（排除系統資源 {excluded} 筆）　有問題：{total_issues}",
        "",
    ]

    rg_summary: list[dict] = []
    for rg in sorted(by_rg.keys()):
        items = by_rg[rg]
        rg_summary.append({"rg": rg, "count": len(items)})
        lines += [
            f"## {rg}（{len(items)} 筆）",
            "",
            "| 資源名稱 | 類型 | 問題 |",
            "| --- | --- | --- |",
        ]
        for item in sorted(items, key=lambda x: x["name"]):
            issues_str = "；".join(item["issues"])
            lines.append(f"| {_esc(item['name'])} | {_esc(item['type'])} | {_esc(issues_str)} |")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return {"sub_name": sub_name, "total": len(real_resources), "excluded": excluded, "issues": total_issues, "rg_breakdown": rg_summary}


def write_global_gap_index(path: Path, *, snapshot_date: str, sub_reports: list[dict]) -> None:
    grand_total = sum(s["total"] for s in sub_reports)
    grand_issues = sum(s["issues"] for s in sub_reports)
    coverage = round((grand_total - grand_issues) / grand_total * 100, 1) if grand_total else 0

    lines = [
        "---",
        f'snapshot_date: "{snapshot_date}"',
        f"grand_total: {grand_total}",
        f"grand_issues: {grand_issues}",
        "---",
        "",
        "# Tag Gap 全域摘要",
        "",
        f"> 快照日期：{snapshot_date}　資源總數：{grand_total}　有問題：{grand_issues}　無問題率：{coverage}%",
        "",
        "## 各訂閱摘要",
        "",
        "| 訂閱 | 計入資源 | 排除系統 | 有問題 | 健康率 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for s in sorted(sub_reports, key=lambda x: x["sub_name"]):
        pct = round((s["total"] - s["issues"]) / s["total"] * 100, 1) if s["total"] else 0
        lines.append(
            f"| [{s['sub_name']}](./{s['sub_name']}.md) |"
            f" {s['total']} | {s.get('excluded',0)} | {s['issues']} | {pct}% |"
        )

    # 各問題類型統計（需要 re-scan，這裡用估算顯示）
    lines += [
        "",
        "## 問題類型說明",
        "",
        "| 類型 | 說明 |",
        "| --- | --- |",
        "| 缺: KEY | 缺少必要 tag（CostCenter / EnvType / Purpose / owner）|",
        "| Purpose 不符 | 已 review 的 RG 預設 Purpose 與實際值不一致 |",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()))
    parser.add_argument("--cache-dir", default=".cache/tag-review")
    parser.add_argument("--force-pull", action="store_true", help="忽略 cache，重新拉資料")
    args = parser.parse_args()

    snapshot_date = args.date
    base_dir = Path(args.cache_dir) / snapshot_date
    raw_dir = base_dir / "raw"
    gaps_dir = base_dir / "gaps"

    if args.force_pull:
        import shutil
        if raw_dir.exists():
            shutil.rmtree(raw_dir)

    print(f"快照日期：{snapshot_date}")
    print(f"資料目錄：{raw_dir}")

    sub_reports = []
    for sub in SUBSCRIPTIONS:
        resources = pull_and_cache(sub, raw_dir)
        if not resources:
            continue
        report = write_sub_gap_md(
            gaps_dir / f"{sub['name']}.md",
            sub_name=sub["name"],
            snapshot_date=snapshot_date,
            resources=resources,
        )
        sub_reports.append(report)
        excl = report.get("excluded", 0)
        print(f"  {sub['name']}: {report['total']} 資源（排除 {excl} 系統）, {report['issues']} 筆有問題")

    if sub_reports:
        write_global_gap_index(
            gaps_dir / "_index.md",
            snapshot_date=snapshot_date,
            sub_reports=sub_reports,
        )

    grand_issues = sum(s["issues"] for s in sub_reports)
    print(f"\n[done] Gap 報告 → {gaps_dir}")
    print(f"       有問題資源：{grand_issues} 筆")
    return 0


if __name__ == "__main__":
    sys.exit(main())
