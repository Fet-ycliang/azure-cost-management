"""Azure Cost MCP 設定管理。"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Azure Cost MCP 服務設定。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mcp_transport: Literal["stdio", "streamable-http"] = Field(
        default="stdio",
        validation_alias="AZURE_COST_MCP_TRANSPORT",
        description="MCP 傳輸模式。",
    )
    mcp_host: str = Field(
        default="127.0.0.1",
        validation_alias="AZURE_COST_MCP_HOST",
        description="Streamable HTTP 啟動主機位址。",
    )
    mcp_port: int = Field(
        default=8000,
        validation_alias="AZURE_COST_MCP_PORT",
        description="Streamable HTTP 啟動埠號。",
    )
    mcp_streamable_http_path: str = Field(
        default="/mcp",
        validation_alias="AZURE_COST_MCP_STREAMABLE_HTTP_PATH",
        description="MCP HTTP 端點路徑。",
    )
    azure_management_base_url: str = Field(
        default="https://management.azure.com",
        validation_alias="AZURE_MANAGEMENT_BASE_URL",
        description="Azure 管理平面基底 URL。",
    )
    azure_cost_management_api_version: str = Field(
        default="2025-03-01",
        validation_alias="AZURE_COST_MANAGEMENT_API_VERSION",
        description="Azure Cost Management REST API version。",
    )
    azure_consumption_api_version: str = Field(
        default="2024-08-01",
        validation_alias="AZURE_CONSUMPTION_API_VERSION",
        description="Azure Consumption REST API version。",
    )
    azure_resource_graph_api_version: str = Field(
        default="2024-04-01",
        validation_alias="AZURE_RESOURCE_GRAPH_API_VERSION",
        description="Azure Resource Graph REST API version。",
    )
    azure_cost_management_scope: str | None = Field(
        default=None,
        validation_alias="AZURE_COST_MANAGEMENT_SCOPE",
        description="Azure Cost Management 查詢 scope。",
    )
    azure_cost_department_tag_key: str = Field(
        default="Department",
        validation_alias="AZURE_COST_DEPARTMENT_TAG_KEY",
        description="部門成本歸屬使用的 tag key。",
    )
    azure_cost_storage_account_url: str | None = Field(
        default=None,
        validation_alias="AZURE_COST_STORAGE_ACCOUNT_URL",
        description="Azure Storage account URL。",
    )
    azure_cost_storage_container: str | None = Field(
        default=None,
        validation_alias="AZURE_COST_STORAGE_CONTAINER",
        description="成本資料容器名稱。",
    )
    azure_cost_storage_prefix: str = Field(
        default="cost-management",
        validation_alias="AZURE_COST_STORAGE_PREFIX",
        description="成本資料 prefix。",
    )
    databricks_mcp_server_url: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_SERVER_URL",
        description="Databricks MCP server URL。",
    )
    databricks_mcp_bearer_token: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_BEARER_TOKEN",
        description="Databricks MCP server Bearer token。",
    )
    databricks_mcp_timeout_seconds: int = Field(
        default=60,
        validation_alias="DATABRICKS_MCP_TIMEOUT_SECONDS",
        description="Databricks MCP server 呼叫逾時秒數。",
    )
    databricks_mcp_query_tool_name: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_QUERY_TOOL_NAME",
        description="Databricks MCP 查詢工具名稱。",
    )
    databricks_mcp_tag_audit_tool_name: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_TAG_AUDIT_TOOL_NAME",
        description="Databricks MCP tag audit 工具名稱。",
    )
    databricks_mcp_tag_remediation_tool_name: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_TAG_REMEDIATION_TOOL_NAME",
        description="Databricks MCP tag remediation 工具名稱。",
    )
    azure_cost_tag_apply_enabled: bool = Field(
        default=False,
        validation_alias="AZURE_COST_TAG_APPLY_ENABLED",
        description="是否允許直接套用 tag 修正。",
    )

    @field_validator("mcp_streamable_http_path")
    @classmethod
    def validate_streamable_http_path(cls, value: str) -> str:
        """驗證 HTTP 路徑格式。"""
        if not value.startswith("/"):
            raise ValueError("AZURE_COST_MCP_STREAMABLE_HTTP_PATH 必須以 '/' 開頭。")
        return value.rstrip("/") or "/mcp"

    @field_validator("azure_management_base_url")
    @classmethod
    def validate_management_base_url(cls, value: str) -> str:
        """標準化 Azure 管理平面 URL。"""
        return value.rstrip("/")

    @field_validator("azure_cost_department_tag_key")
    @classmethod
    def validate_department_tag_key(cls, value: str) -> str:
        """驗證部門 tag key。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("AZURE_COST_DEPARTMENT_TAG_KEY 不可為空字串。")
        return normalized

    @field_validator(
        "databricks_mcp_server_url",
        "databricks_mcp_query_tool_name",
        "databricks_mcp_tag_audit_tool_name",
        "databricks_mcp_tag_remediation_tool_name",
        mode="before",
    )
    @classmethod
    def strip_optional_strings(cls, value: str | None) -> str | None:
        """清理可選字串輸入。"""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """取得快取後的服務設定。"""
    return Settings()
