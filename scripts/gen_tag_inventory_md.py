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
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

AZ = "az.cmd" if sys.platform == "win32" else "az"


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


def _load_subscription_metadata(
    cache_root: Path,
    subscription_ids: set[str],
) -> dict[str, dict[str, str]]:
    metadata = {
        sub_id: {
            "tenant_id": "(unknown-tenant)",
            "subscription_name": sub_id,
        }
        for sub_id in subscription_ids
    }
    cache_file = cache_root / "subscription-tenant-map.json"

    def _merge(records: list[dict[str, Any]]) -> None:
        for record in records:
            sub_id = str(record.get("id") or "").strip()
            if not sub_id or sub_id not in metadata:
                continue
            tenant_id = str(record.get("tenantId") or "").strip()
            name = str(record.get("name") or "").strip()
            if tenant_id:
                metadata[sub_id]["tenant_id"] = tenant_id
            if name:
                metadata[sub_id]["subscription_name"] = name

    if cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = []
        if isinstance(cached, list):
            _merge([item for item in cached if isinstance(item, dict)])

    unresolved = {
        sub_id
        for sub_id, info in metadata.items()
        if info["tenant_id"] == "(unknown-tenant)" and info["subscription_name"] == sub_id
    }
    if not unresolved:
        return metadata

    result = subprocess.run(
        [AZ, "account", "list", "--all", "--output", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return metadata

    try:
        accounts = json.loads(result.stdout)
    except json.JSONDecodeError:
        return metadata
    if not isinstance(accounts, list):
        return metadata

    account_records = [item for item in accounts if isinstance(item, dict)]
    _merge(account_records)

    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        filtered = [item for item in account_records if str(item.get("id") or "").strip() in subscription_ids]
        cache_file.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass

    return metadata


# ---------------------------------------------------------------------------
# Tag 判斷工具
# ---------------------------------------------------------------------------


def _is_fully_tagged(tags: dict[str, Any], required_keys: list[str]) -> bool:
    return all(str(tags.get(k, "")).strip() for k in required_keys)


def _missing_keys(tags: dict[str, Any], required_keys: list[str]) -> list[str]:
    return [k for k in required_keys if not str(tags.get(k, "")).strip()]


GRAPH_TAG_KEYS = ("CostCenter", "Purpose", "owner", "EnvType")
GRAPH_TAG_DIRS = {
    "CostCenter": "cost-centers",
    "Purpose": "purposes",
    "owner": "owners",
    "EnvType": "env-types",
}


def _safe_note_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\\\|?*]', "_", value).strip()
    return cleaned or "(empty)"


def _normalize_rg_key(rg: str) -> str:
    return rg.strip().lower()


def _safe_rg_path(rg: str) -> str:
    return rg.replace("/", "_").strip("_").lower()


def _rg_note_link(sub_id: str, rg: str) -> str:
    safe_sub = sub_id.replace("/", "_").strip("_")
    safe_rg = _safe_rg_path(rg)
    return f"[[{safe_sub}/{safe_rg}|{rg}]]"


def _tag_note_link(tag_key: str, value: str) -> str:
    folder = GRAPH_TAG_DIRS[tag_key]
    return f"[[tag-graph/{folder}/{_safe_note_name(value)}|{value}]]"


def _load_desired_overrides(desired_dir: Path) -> dict[str, dict[str, str]]:
    overrides: dict[str, dict[str, str]] = {}
    if not desired_dir.is_dir():
        return overrides

    for json_file in sorted(desired_dir.glob("*.json")):
        try:
            entries = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(entries, list):
            continue

        for entry in entries:
            resource_id = str(entry.get("resource_id") or "").strip()
            if not resource_id:
                continue
            desired = {
                str(k): str(v).strip()
                for k, v in (entry.get("desired_tags") or {}).items()
                if str(v).strip()
            }
            if desired:
                overrides[resource_id] = desired
    return overrides


def _effective_tags(resource: dict[str, Any], desired_overrides: dict[str, dict[str, str]]) -> dict[str, str]:
    current = {
        str(k): str(v).strip()
        for k, v in (resource.get("tags") or {}).items()
        if str(v).strip()
    }
    resource_id = str(resource.get("id") or "").strip()
    override = desired_overrides.get(resource_id, {})
    return {**current, **override}


def _render_resource_table(resources: list[dict[str, Any]], required_keys: list[str]) -> list[str]:
    header = "| 名稱 | 類型 | 位置 |" + "".join(f" {k} |" for k in required_keys)
    separator = "| --- | --- | --- |" + " --- |" * len(required_keys)
    lines = [header, separator]

    if not resources:
        placeholder = "| _(無)_ | _(無)_ | _(無)_ |" + "".join(" _(無)_ |" for _ in required_keys)
        return [*lines, placeholder]

    for r in sorted(resources, key=lambda x: x.get("name", "")):
        tags = r.get("tags") or {}
        name = r.get("name", "")
        rtype = r.get("type", "")
        short_type = "/".join(rtype.split("/")[-2:]) if "/" in rtype else rtype
        loc = r.get("location", "")
        row = f"| {name} | {short_type} | {loc} |"
        for k in required_keys:
            val = str(tags.get(k, "")).strip()
            if val and k in GRAPH_TAG_DIRS:
                row += f" {_tag_note_link(k, val)} |"
            else:
                row += f" {val if val else '_(缺)_'} |"
        lines.append(row)
    return lines


def _render_cost_summary_table(cost_entries: list[dict[str, Any]]) -> list[str]:
    if not cost_entries:
        return []

    lines = [
        "| 專案 | 平台 | 表格值 (TWD) | 計算值 (TWD) | 狀態 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for entry in cost_entries:
        reported = entry.get("reported_cost")
        computed = entry.get("computed_cost")
        reported_str = _format_cost_value(reported)
        computed_str = _format_cost_value(computed)
        lines.append(
            f"| {entry['description']} | {entry['platform']} | {reported_str} | {computed_str} | {entry['status']} |"
        )
    return lines


def _render_cost_section(
    cost_entries: list[dict[str, Any]],
    *,
    cost_period: str | None,
    pending_message: str,
) -> list[str]:
    title = f"## 成本摘要（{cost_period}）" if cost_period else "## 成本摘要"
    if not cost_entries:
        return [
            title,
            "",
            "- **狀態**: 整理中",
            f"- **說明**: {pending_message}",
            "",
        ]
    return [title, "", *_render_cost_summary_table(cost_entries), ""]


def _format_cost_value(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number - round(number)) < 0.005:
        return f"{int(round(number)):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _find_latest_project_cost_table(monthly_reports_dir: Path) -> Path | None:
    candidates: list[tuple[int, int, Path]] = []
    for year_dir in monthly_reports_dir.iterdir() if monthly_reports_dir.is_dir() else []:
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
            cost_file = month_dir / "project-cost-table.json"
            if cost_file.is_file():
                candidates.append((int(year_dir.name), int(month_dir.name), cost_file))
    if not candidates:
        return None
    _, _, latest = sorted(candidates, reverse=True)[0]
    return latest


def _load_project_cost_rows(project_cost_table: Path | None) -> tuple[str | None, list[dict[str, Any]]]:
    if project_cost_table is None or not project_cost_table.is_file():
        return None, []

    try:
        payload = json.loads(project_cost_table.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, []

    periods = payload.get("period_columns") or []
    if not periods:
        return None, []

    latest_period = str(periods[-1])
    latest_index = len(periods) - 1
    computed_key = f"computed_{latest_period.replace('-', '_')}"

    rows: list[dict[str, Any]] = []
    for project in payload.get("projects", []):
        costs = project.get("costs") or []
        reported_cost = costs[latest_index] if latest_index < len(costs) else None
        rows.append(
            {
                "source": str(project.get("source") or "").strip(),
                "description": str(project.get("description") or "").strip(),
                "platform": str(project.get("platform") or "").strip(),
                "period": latest_period,
                "reported_cost": reported_cost,
                "computed_cost": project.get(computed_key),
                "status": str(project.get("compute_status") or "").strip(),
                "note": str(project.get("compute_note") or "").strip(),
            }
        )
    return latest_period, rows


def _parse_frontmatter_list(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw.startswith("[") or not raw.endswith("]"):
        return []
    content = raw[1:-1].strip()
    if not content:
        return []
    return [item.strip().strip('"').strip("'") for item in content.split(",") if item.strip()]


def _load_view_metadata(view_dir: Path) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    if not view_dir.is_dir():
        return metadata

    for md_file in sorted(view_dir.glob("*.md")):
        try:
            lines = md_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        if not lines or lines[0].strip() != "---":
            continue

        current_list_key: str | None = None
        data: dict[str, Any] = {}
        for line in lines[1:]:
            stripped = line.strip()
            if stripped == "---":
                break
            if stripped.startswith("- ") and current_list_key:
                data.setdefault(current_list_key, []).append(stripped[2:].strip().strip('"'))
                continue
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            key = key.strip()
            raw = raw.strip()
            if not raw:
                data[key] = []
                current_list_key = key
            elif raw.startswith("[") and raw.endswith("]"):
                data[key] = _parse_frontmatter_list(raw)
                current_list_key = None
            else:
                data[key] = raw.strip('"')
                current_list_key = None

        name = str(data.get("name") or "").strip()
        if not name:
            continue
        metadata[_normalize_lookup_key(name)] = {
            "name": name,
            "metric": str(data.get("metric") or "").strip(),
            "resource_groups": [str(v).strip() for v in data.get("resource_groups", []) if str(v).strip()],
            "purposes": [str(v).strip() for v in data.get("purposes", []) if str(v).strip()],
        }
    return metadata


def _normalize_lookup_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _match_view_for_source(source: str, views: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        source,
        f"{source}-cost",
        f"{source}_cost",
    ]
    for candidate in candidates:
        matched = views.get(_normalize_lookup_key(candidate))
        if matched:
            return matched
    return None


def _cost_entry_id(entry: dict[str, Any]) -> str:
    return "::".join(
        [
            str(entry.get("source") or ""),
            str(entry.get("description") or ""),
            str(entry.get("period") or ""),
        ]
    )


def _cost_entry_sort_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("description") or ""),
        str(entry.get("platform") or ""),
        str(entry.get("source") or ""),
    )


def _dedupe_cost_entries(cost_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for entry in cost_entries:
        deduped[_cost_entry_id(entry)] = entry
    return sorted(deduped.values(), key=_cost_entry_sort_key)


def _collect_resource_cost_entries(
    resource: dict[str, Any],
    desired_overrides: dict[str, dict[str, str]],
    rg_cost_entries: dict[str, list[dict[str, Any]]],
    purpose_cost_entries: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rg = str(resource.get("resourceGroup") or "").strip().lower()
    direct = rg_cost_entries.get(rg, [])
    if direct:
        return _dedupe_cost_entries(direct)

    effective = _effective_tags(resource, desired_overrides)
    purpose = effective.get("Purpose", "").strip().lower()
    if purpose:
        return _dedupe_cost_entries(purpose_cost_entries.get(purpose, []))
    return []


def _collect_rg_cost_entries(
    resources: list[dict[str, Any]],
    desired_overrides: dict[str, dict[str, str]],
    rg_cost_entries: dict[str, list[dict[str, Any]]],
    purpose_cost_entries: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if not resources:
        return []

    rg = str(resources[0].get("resourceGroup") or "").strip().lower()
    direct = rg_cost_entries.get(rg, [])
    if direct:
        return _dedupe_cost_entries(direct)

    inferred: list[dict[str, Any]] = []
    for resource in resources:
        effective = _effective_tags(resource, desired_overrides)
        purpose = effective.get("Purpose", "").strip().lower()
        if purpose:
            inferred.extend(purpose_cost_entries.get(purpose, []))
    return _dedupe_cost_entries(inferred)


def _infer_charge_model(
    resources: list[dict[str, Any]],
    desired_overrides: dict[str, dict[str, str]],
) -> str:
    cost_centers = sorted(
        {
            effective.get("CostCenter", "").strip()
            for effective in (_effective_tags(resource, desired_overrides) for resource in resources)
            if effective.get("CostCenter", "").strip()
        }
    )
    if len(cost_centers) > 1:
        return "Cross CostCenter 拆帳"
    if len(cost_centers) == 1:
        return f"單一 CostCenter 掛帳 ({cost_centers[0]})"
    return "待確認"


def _summarize_projects(cost_entries: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(entry.get("description") or "").strip()
            for entry in cost_entries
            if str(entry.get("description") or "").strip()
        }
    )


def _build_cost_indexes(
    project_cost_table: Path | None,
    view_dir: Path,
) -> tuple[str | None, dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    latest_period, cost_rows = _load_project_cost_rows(project_cost_table)
    if not cost_rows:
        return latest_period, {}, {}

    views = _load_view_metadata(view_dir)
    by_rg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_purpose: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in cost_rows:
        source = row.get("source") or ""
        if not source:
            continue
        view = _match_view_for_source(source, views)
        if not view:
            continue
        entry = {**row, "view_name": view["name"], "metric": view.get("metric", "")}
        for rg in view.get("resource_groups", []):
            by_rg[rg.lower()].append(entry)
        for purpose in view.get("purposes", []):
            by_purpose[purpose.lower()].append(entry)
    return latest_period, by_rg, by_purpose


def _collect_rg_tag_links(
    resources: list[dict[str, Any]],
    desired_overrides: dict[str, dict[str, str]],
) -> dict[str, list[str]]:
    links: dict[str, set[str]] = {key: set() for key in GRAPH_TAG_KEYS}
    for resource in resources:
        effective = _effective_tags(resource, desired_overrides)
        for key in GRAPH_TAG_KEYS:
            value = effective.get(key, "").strip()
            if value:
                links[key].add(_tag_note_link(key, value))
    return {key: sorted(values) for key, values in links.items() if values}


def _empty_graph_node() -> dict[str, Any]:
    return {
        "related": {key: set() for key in GRAPH_TAG_KEYS},
        "resource_groups": set(),
        "cost_ids": set(),
    }


def _build_tag_graph(
    resources: list[dict[str, Any]],
    desired_overrides: dict[str, dict[str, str]],
    rg_cost_entries: dict[str, list[dict[str, Any]]],
    purpose_cost_entries: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, dict[str, Any]]]:
    graph = {key: defaultdict(_empty_graph_node) for key in GRAPH_TAG_KEYS}
    cost_registry: dict[str, dict[str, Any]] = {}

    for resource in resources:
        effective = _effective_tags(resource, desired_overrides)
        values = {key: effective.get(key, "").strip() for key in GRAPH_TAG_KEYS if effective.get(key, "").strip()}
        if not values:
            continue

        sub_id = str(resource.get("subscriptionId") or "unknown")
        rg = str(resource.get("resourceGroup") or "(unknown)")
        resource_costs = _collect_resource_cost_entries(
            resource,
            desired_overrides,
            rg_cost_entries,
            purpose_cost_entries,
        )

        cost_ids = set()
        for cost_entry in resource_costs:
            cost_id = _cost_entry_id(cost_entry)
            cost_registry[cost_id] = cost_entry
            cost_ids.add(cost_id)

        for key, value in values.items():
            node = graph[key][value]
            node["resource_groups"].add((sub_id, rg))
            node["cost_ids"].update(cost_ids)
            for related_key, related_value in values.items():
                if related_key == key:
                    continue
                node["related"][related_key].add(related_value)

    return graph, cost_registry


def _write_tag_graph_notes(
    obsidian_dir: Path,
    graph: dict[str, dict[str, dict[str, Any]]],
    cost_registry: dict[str, dict[str, Any]],
    cost_period: str | None,
) -> None:
    tag_graph_dir = obsidian_dir / "tag-graph"
    tag_graph_dir.mkdir(parents=True, exist_ok=True)

    index_lines = [
        "---",
        f"cost_period: {cost_period or ''}",
        "---",
        "",
        "# Tag 關聯圖",
        "",
        "- [[_index|Vault 首頁]]",
        "",
        "> 從 CostCenter 進入，再展開到 Purpose / owner / EnvType / Resource Groups。",
        "",
        "## CostCenter",
        "",
    ]
    for value in sorted(graph["CostCenter"].keys()):
        index_lines.append(f"- {_tag_note_link('CostCenter', value)}")
    index_lines.append("")
    (tag_graph_dir / "index.md").write_text("\n".join(index_lines), encoding="utf-8")

    for tag_key, nodes in graph.items():
        folder = tag_graph_dir / GRAPH_TAG_DIRS[tag_key]
        folder.mkdir(parents=True, exist_ok=True)
        for value, node in sorted(nodes.items()):
            note_lines = [
                "---",
                f"tag_key: {tag_key}",
                f"tag_value: {value}",
                f"resource_group_count: {len(node['resource_groups'])}",
                "---",
                "",
                f"# {tag_key}: {value}",
                "",
                "- [[_index|Vault 首頁]]",
                "- [[tag-graph/index|Tag 關聯圖]]",
                "",
            ]
            cost_entries = _dedupe_cost_entries(
                [cost_registry[cost_id] for cost_id in node["cost_ids"]]
            )
            note_lines.extend(
                _render_cost_section(
                    cost_entries,
                    cost_period=cost_period,
                    pending_message="尚未整理出這個 tag 節點對應的 project 成本。",
                )
            )

            for related_key in GRAPH_TAG_KEYS:
                related_values = sorted(node["related"][related_key])
                if not related_values:
                    continue
                note_lines.extend([f"## {related_key}", ""])
                for related_value in related_values:
                    note_lines.append(f"- {_tag_note_link(related_key, related_value)}")
                note_lines.append("")

            resource_groups = sorted(node["resource_groups"])
            if resource_groups:
                normalized_resource_groups: dict[tuple[str, str], str] = {}
                for sub_id, rg in resource_groups:
                    normalized_resource_groups.setdefault((sub_id, _normalize_rg_key(rg)), rg)
                note_lines.extend(["## Resource Groups", ""])
                for (sub_id, _), rg in sorted(normalized_resource_groups.items(), key=lambda item: item[1]):
                    note_lines.append(f"- {_rg_note_link(sub_id, rg)}")
                note_lines.append("")

            (folder / f"{_safe_note_name(value)}.md").write_text("\n".join(note_lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# PBI 2.1 — 每個 RG 一份 Markdown
# ---------------------------------------------------------------------------


def _rg_md_path(obsidian_dir: Path, sub_id: str, rg: str) -> Path:
    safe_sub = sub_id.replace("/", "_").strip("_")
    safe_rg = _safe_rg_path(rg)
    return obsidian_dir / safe_sub / f"{safe_rg}.md"


def _write_rg_md(
    path: Path,
    *,
    rg: str,
    sub_id: str,
    snapshot_date: str,
    resources: list[dict[str, Any]],
    required_keys: list[str],
    tenant_id: str | None = None,
    subscription_name: str | None = None,
    charge_model: str | None = None,
    related_tag_links: dict[str, list[str]] | None = None,
    cost_entries: list[dict[str, Any]] | None = None,
    cost_period: str | None = None,
) -> None:
    tagged = sum(1 for r in resources if _is_fully_tagged(r.get("tags") or {}, required_keys))
    untagged = len(resources) - tagged
    tags_yaml = "[" + ", ".join(required_keys) + "]"
    consistent_resources = [r for r in resources if _is_fully_tagged(r.get("tags") or {}, required_keys)]
    review_resources = [r for r in resources if not _is_fully_tagged(r.get("tags") or {}, required_keys)]
    cost_status = "已對應" if cost_entries else "整理中"

    lines: list[str] = [
        "---",
        f"rg: {rg}",
        f"subscription: {sub_id}",
        f"subscription_name: {subscription_name or ''}",
        f"tenant_id: {tenant_id or ''}",
        f"charge_model: {charge_model or '待確認'}",
        f'snapshot_date: "{snapshot_date}"',
        f"total_resources: {len(resources)}",
        f"tagged: {tagged}",
        f"untagged: {untagged}",
        f"cost_status: {cost_status}",
        f"cost_period: {cost_period or ''}",
        f"required_tags: {tags_yaml}",
        "---",
        "",
        f"# {rg}",
        "",
        "- [[_index|Vault 首頁]]",
        "- [[tag-gap-summary|Tag 缺漏摘要]]",
        "- [[tag-graph/index|Tag 關聯圖]]",
        "",
        f"> 快照日期：{snapshot_date}"
        + (f"　Tenant：`{tenant_id}`" if tenant_id else "")
        + (
            f"　Subscription：`{subscription_name}` (`{sub_id}`)"
            if subscription_name
            else f"　訂閱：`{sub_id}`"
        ),
        f"> 資源總數：{len(resources)}　完整標記：{tagged}　缺標記：{untagged}",
        "",
    ]

    lines += [
        "## 帳務歸屬",
        "",
        f"- **charge_model**: {charge_model or '待確認'}",
        "",
    ]

    lines += _render_cost_section(
        cost_entries or [],
        cost_period=cost_period,
        pending_message="尚未找到這個 RG 對應的 project 成本關係。",
    )

    if related_tag_links:
        lines += ["## Tag 關聯", ""]
        for key in GRAPH_TAG_KEYS:
            values = related_tag_links.get(key)
            if values:
                lines.append(f"- **{key}**: {', '.join(values)}")
        lines.append("")

    lines += ["## 一致", "", *_render_resource_table(consistent_resources, required_keys), ""]
    lines += ["## 需檢查或確認", "", *_render_resource_table(review_resources, required_keys), ""]

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
    subscription_metadata: dict[str, dict[str, str]] | None = None,
    cost_period: str | None = None,
) -> None:
    mapped = sorted(
        (stat for stat in rg_stats if stat.get("cost_status") == "已對應"),
        key=lambda x: (-x.get("project_count", 0), x["rg"]),
    )
    pending = sorted(
        (stat for stat in rg_stats if stat.get("cost_status") != "已對應"),
        key=lambda x: (x["coverage_pct"], x["rg"]),
    )

    hierarchy_lines: list[str] = []
    by_tenant: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for stat in sorted(rg_stats, key=lambda x: (x["subscription_id"], x["rg"])):
        sub_id = stat["subscription_id"]
        meta = (subscription_metadata or {}).get(
            sub_id,
            {"tenant_id": "(unknown-tenant)", "subscription_name": sub_id},
        )
        tenant_id = meta.get("tenant_id") or "(unknown-tenant)"
        sub_label = meta.get("subscription_name") or sub_id
        by_tenant[tenant_id][f"{sub_label}|||{sub_id}"].append(stat)

    for tenant_id in sorted(by_tenant):
        hierarchy_lines.extend([f"### Tenant `{tenant_id}`", ""])
        for sub_key in sorted(by_tenant[tenant_id]):
            sub_label, sub_id = sub_key.split("|||", 1)
            hierarchy_lines.extend(
                [
                    f"#### Subscription `{sub_label}` (`{sub_id}`) — {len(by_tenant[tenant_id][sub_key])} RG",
                    "",
                ]
            )
            for stat in sorted(by_tenant[tenant_id][sub_key], key=lambda item: item["rg"]):
                rg = stat["rg"]
                safe_sub = sub_id.replace("/", "_").strip("_")
                safe_rg = _safe_rg_path(rg)
                hierarchy_lines.append(f"- [{rg}](./{safe_sub}/{safe_rg}.md)")
            hierarchy_lines.append("")

    lines: list[str] = [
        "---",
        f'snapshot_date: "{snapshot_date}"',
        f"cost_period: {cost_period or ''}",
        f"total_resource_groups: {len(rg_stats)}",
        "---",
        "",
        "# RG x Project 成本總覽",
        "",
        f"> 快照日期：{snapshot_date}" + (f"　成本期別：{cost_period}" if cost_period else ""),
        "",
        "## Tenant / Subscription / RG",
        "",
        *hierarchy_lines,
        "## 入口",
        "",
        "- [[tag-gap-summary|Tag 缺漏摘要]]",
        "- [[tag-graph/index|Tag 關聯圖]]",
        "",
        "## 已對應",
        "",
        "| Resource Group | 訂閱 | 掛帳方式 | 專案數 | 專案 | 覆蓋率 |",
        "| --- | --- | --- | ---: | --- | ---: |",
    ]

    if mapped:
        for stat in mapped:
            rg = stat["rg"]
            sub = stat["subscription_id"]
            safe_sub = sub.replace("/", "_").strip("_")
            safe_rg = _safe_rg_path(rg)
            md_rel = f"./{safe_sub}/{safe_rg}.md"
            projects = ", ".join(stat.get("projects") or []) or "-"
            lines.append(
                f"| [{rg}]({md_rel}) | `{sub}` | {stat.get('charge_model', '待確認')} | {stat.get('project_count', 0)} | {projects} | {stat['coverage_pct']:.1f}% |"
            )
    else:
        lines.append("| _(無)_ | - | - | 0 | - | - |")

    lines += [
        "",
        "## 需檢查或確認",
        "",
        "| Resource Group | 訂閱 | 掛帳方式 | 總數 | 缺標記 | 覆蓋率 | 狀態 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    if pending:
        for stat in pending:
            rg = stat["rg"]
            sub = stat["subscription_id"]
            safe_sub = sub.replace("/", "_").strip("_")
            safe_rg = _safe_rg_path(rg)
            md_rel = f"./{safe_sub}/{safe_rg}.md"
            lines.append(
                f"| [{rg}]({md_rel}) | `{sub}` | {stat.get('charge_model', '待確認')} | {stat['total']} | {stat['untagged']} | {stat['coverage_pct']:.1f}% | 整理中 |"
            )
    else:
        lines.append("| _(無)_ | - | - | 0 | 0 | - | - |")

    lines += [
        "",
        "## 全部 RG",
        "",
        "| Resource Group | 訂閱 | 總數 | 完整標記 | 缺標記 | 覆蓋率 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for stat in sorted(rg_stats, key=lambda x: x["coverage_pct"]):
        rg = stat["rg"]
        sub = stat["subscription_id"]
        safe_sub = sub.replace("/", "_").strip("_")
        safe_rg = _safe_rg_path(rg)
        md_rel = f"./{safe_sub}/{safe_rg}.md"
        lines.append(
            f"| [{rg}]({md_rel}) | `{sub}` | {stat['total']} |"
            f" {stat['tagged']} | {stat['untagged']} | {stat['coverage_pct']:.1f}% |"
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
        "- [[_index|Vault 首頁]]",
        "- [[tag-graph/index|Tag 關聯圖]]",
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
        lines.append(f"| {name} | {short_type} | {_rg_note_link(sub, rg)} | `{sub}` | {missing_str} |")

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
    parser.add_argument("--skip-desired", action="store_true", help="不重新產生 desired JSON（保留已填好的值）")
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
    shared_cache_dir = cache_dir.parent if cache_dir.name == "tag-inventory" else cache_dir
    desired_overrides = _load_desired_overrides(desired_dir)
    subscription_metadata = _load_subscription_metadata(
        shared_cache_dir,
        {str(r.get("subscriptionId") or "unknown") for r in resources},
    )
    project_cost_table = _find_latest_project_cost_table(shared_cache_dir / "monthly-reports")
    cost_period, rg_cost_entries, purpose_cost_entries = _build_cost_indexes(
        project_cost_table,
        shared_cache_dir / "views-mapping" / "views",
    )
    graph, cost_registry = _build_tag_graph(
        resources,
        desired_overrides,
        rg_cost_entries,
        purpose_cost_entries,
    )
    _write_tag_graph_notes(obsidian_dir, graph, cost_registry, cost_period)
    print(f"[info] Tag 關聯圖 → {obsidian_dir / 'tag-graph' / 'index.md'}")

    # 依 (subscription, rg) 分組
    by_sub_rg: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    rg_display_names: dict[tuple[str, str], str] = {}
    for r in resources:
        sub_id = r.get("subscriptionId") or "unknown"
        rg = r.get("resourceGroup") or "(unknown)"
        rg_key = _normalize_rg_key(str(rg))
        by_sub_rg[sub_id][rg_key].append(r)
        rg_display_names.setdefault((sub_id, rg_key), str(rg))

    rg_stats: list[dict[str, Any]] = []
    desired_by_rg: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for sub_id, rg_dict in sorted(by_sub_rg.items()):
        for rg_key, rg_resources in sorted(rg_dict.items()):
            rg = rg_display_names[(sub_id, rg_key)]
            md_path = _rg_md_path(obsidian_dir, sub_id, rg)
            cost_entries = _collect_rg_cost_entries(
                rg_resources,
                desired_overrides,
                rg_cost_entries,
                purpose_cost_entries,
            )
            charge_model = _infer_charge_model(rg_resources, desired_overrides)
            sub_meta = subscription_metadata.get(
                str(sub_id),
                {"tenant_id": "(unknown-tenant)", "subscription_name": str(sub_id)},
            )
            _write_rg_md(
                md_path,
                rg=rg,
                sub_id=sub_id,
                snapshot_date=snapshot_date,
                resources=rg_resources,
                required_keys=required_keys,
                tenant_id=sub_meta.get("tenant_id"),
                subscription_name=sub_meta.get("subscription_name"),
                charge_model=charge_model,
                related_tag_links=_collect_rg_tag_links(rg_resources, desired_overrides),
                cost_entries=cost_entries,
                cost_period=cost_period,
            )

            tagged = sum(1 for r in rg_resources if _is_fully_tagged(r.get("tags") or {}, required_keys))
            coverage = round(tagged / len(rg_resources) * 100, 1) if rg_resources else 0.0
            projects = _summarize_projects(cost_entries)
            rg_stats.append(
                {
                    "rg": rg,
                    "subscription_id": sub_id,
                    "total": len(rg_resources),
                    "tagged": tagged,
                    "untagged": len(rg_resources) - tagged,
                    "coverage_pct": coverage,
                    "cost_status": "已對應" if cost_entries else "整理中",
                    "charge_model": charge_model,
                    "project_count": len(projects),
                    "projects": projects,
                }
            )
            for r in rg_resources:
                if not _is_fully_tagged(r.get("tags") or {}, required_keys):
                    desired_by_rg[rg].append(r)

    rg_count = sum(len(rgs) for rgs in by_sub_rg.values())
    print(f"[info] 已產生 {rg_count} 個 RG 的 Markdown → {obsidian_dir}")

    _write_index_md(
        obsidian_dir / "_index.md",
        snapshot_date=snapshot_date,
        rg_stats=rg_stats,
        subscription_metadata=subscription_metadata,
        cost_period=cost_period,
    )
    print(f"[info] 總索引 → {obsidian_dir / '_index.md'}")

    _write_gap_summary_md(
        obsidian_dir / "tag-gap-summary.md",
        snapshot_date=snapshot_date,
        resources=resources,
        required_keys=required_keys,
        top=args.top_gap,
    )
    print(f"[info] Tag 缺漏摘要 → {obsidian_dir / 'tag-gap-summary.md'}")

    if args.skip_desired:
        print("[info] --skip-desired：跳過 desired JSON 產生")
    else:
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
