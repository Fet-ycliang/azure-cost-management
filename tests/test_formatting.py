from __future__ import annotations

from datetime import date

from azure_cost_mcp.formatting import _format_scalar, to_markdown, to_response
from azure_cost_mcp.models import ResponseFormat


def test_to_markdown_renders_scalars_tables_and_empty_lists() -> None:
    markdown = to_markdown(
        "測試報表",
        {
            "summary": {"count": 2, "enabled": True},
            "rows": [{"name": "Storage", "cost": 1.23456}],
            "empty": [],
            "note": "ready",
        },
    )

    assert markdown.startswith("# 測試報表")
    assert "## summary" in markdown
    assert "- **count**: 2" in markdown
    assert "- **enabled**: true" in markdown
    assert "| name | cost |" in markdown
    assert "| Storage | 1.2346 |" in markdown
    assert "## empty" in markdown
    assert "- (empty)" in markdown
    assert "- **note**: ready" in markdown


def test_to_response_supports_json_output() -> None:
    response = to_response(
        "JSON",
        {"date": date(2026, 1, 1), "value": "資料"},
        ResponseFormat.JSON,
    )

    assert '"date": "2026-01-01"' in response
    assert '"value": "資料"' in response


def test_format_scalar_handles_nested_values() -> None:
    assert _format_scalar(1.2300) == "1.23"
    assert _format_scalar(False) == "false"
    assert _format_scalar(["a", "b"]) == '["a", "b"]'
