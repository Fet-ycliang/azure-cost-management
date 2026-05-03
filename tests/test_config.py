from __future__ import annotations

import pytest

from azure_cost_mcp.config import Settings, get_settings


def test_settings_normalize_optional_values() -> None:
    settings = Settings(
        AZURE_COST_MCP_STREAMABLE_HTTP_PATH="/custom/",
        AZURE_MANAGEMENT_BASE_URL="https://management.azure.com/",
        DATABRICKS_MCP_SERVER_URL="   ",
        DATABRICKS_MCP_AMORTIZED_SERVER_URL=" https://example.com/amortized ",
        DATABRICKS_MCP_ACTUAL_QUERY_TOOL_NAME=" actual_tool ",
        DATABRICKS_MCP_QUERY_TOOL_NAME=" query_tool ",
    )

    assert settings.mcp_streamable_http_path == "/custom"
    assert settings.azure_management_base_url == "https://management.azure.com"
    assert settings.databricks_mcp_server_url is None
    assert (
        settings.databricks_mcp_amortized_server_url == "https://example.com/amortized"
    )
    assert settings.databricks_mcp_actual_query_tool_name == "actual_tool"
    assert settings.databricks_mcp_query_tool_name == "query_tool"


def test_settings_reject_invalid_path() -> None:
    with pytest.raises(ValueError, match="必須以 '/' 開頭"):
        Settings(AZURE_COST_MCP_STREAMABLE_HTTP_PATH="custom")


def test_settings_reject_blank_department_tag_key() -> None:
    with pytest.raises(ValueError, match="不可為空字串"):
        Settings(AZURE_COST_DEPARTMENT_TAG_KEY="  ")


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("AZURE_COST_DEPARTMENT_TAG_KEY", "Finance")

    first = get_settings()
    second = get_settings()

    assert first is second
    assert first.azure_cost_department_tag_key == "Finance"
    get_settings.cache_clear()
