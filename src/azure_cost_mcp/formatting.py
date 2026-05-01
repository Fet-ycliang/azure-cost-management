"""MCP tool 回應格式化 helper。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from .models import ResponseFormat


def to_response(title: str, payload: dict[str, Any], response_format: ResponseFormat) -> str:
    """依指定格式輸出回應。"""
    if response_format == ResponseFormat.JSON:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)
    return to_markdown(title, payload)


def to_markdown(title: str, payload: dict[str, Any]) -> str:
    """將結構化資料轉成 Markdown。"""
    lines = [f"# {title}", ""]
    for key, value in payload.items():
        lines.extend(_render_section(key, value))
    return "\n".join(line for line in lines if line is not None).strip()


def _render_section(key: str, value: Any) -> list[str]:
    heading = f"## {key}"

    if isinstance(value, list):
        if not value:
            return [heading, "- (empty)", ""]
        if all(isinstance(item, Mapping) for item in value):
            return [heading, "", *_render_table(value), ""]
        return [heading, *(f"- {_format_scalar(item)}" for item in value), ""]

    if isinstance(value, Mapping):
        if not value:
            return [heading, "- (empty)", ""]
        if all(not isinstance(item, (Mapping, list)) for item in value.values()):
            return [
                heading,
                *(f"- **{nested_key}**: {_format_scalar(nested_value)}" for nested_key, nested_value in value.items()),
                "",
            ]
        return [heading, "```json", json.dumps(value, ensure_ascii=False, indent=2, default=_json_default), "```", ""]

    return [f"- **{key}**: {_format_scalar(value)}"]


def _render_table(rows: list[Mapping[str, Any]]) -> list[str]:
    columns = list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    data_rows = [
        "| "
        + " | ".join(_format_scalar(row.get(column)).replace("\n", "<br>") for column in columns)
        + " |"
        for row in rows
    ]
    return [header, separator, *data_rows]


def _format_scalar(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, default=_json_default)
    return str(value)


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)
