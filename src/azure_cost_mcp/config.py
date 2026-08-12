"""Azure Cost MCP 設定管理。"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
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
    azure_cost_auth_mode: Literal[
        "azure-cli",
        "service-principal",
        "managed-identity",
        "default",
    ] = Field(
        default="azure-cli",
        validation_alias="AZURE_COST_AUTH_MODE",
        description="Azure 驗證模式。",
    )
    azure_tenant_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AZURE_TENANT_ID", "AZURE_SP_TENANT_ID"),
        description="Azure Service Principal 使用的 tenant ID。",
    )
    azure_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AZURE_CLIENT_ID", "AZURE_SP_CLIENT_ID"),
        description="Azure Service Principal 或 User Assigned Managed Identity 的 client ID。",
    )
    azure_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AZURE_CLIENT_SECRET", "AZURE_SP_CLIENT_SECRET"),
        description="Azure Service Principal 使用的 client secret。",
    )
    azure_managed_identity_client_id: str | None = Field(
        default=None,
        validation_alias="AZURE_MANAGED_IDENTITY_CLIENT_ID",
        description="User Assigned Managed Identity 的 client ID。",
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
    m365_cost_management_tenant: str | None = Field(
        default=None,
        validation_alias="M365_COST_MANAGEMENT_TENANT",
        description="M365 成本驗證使用的 tenant ID（目前主要供 operator-run 驗證流程使用）。",
    )
    m365_sp_client_id: str | None = Field(
        default=None,
        validation_alias="M365_SP_CLIENT_ID",
        description="M365 平台專用 Service Principal client ID（dw_fabric_ap）。",
    )
    m365_sp_client_secret: str | None = Field(
        default=None,
        validation_alias="M365_SP_CLIENT_SECRET",
        description="M365 平台專用 Service Principal client secret。",
    )
    m365_cost_management_scope: str | None = Field(
        default=None,
        validation_alias="M365_COST_MANAGEMENT_SCOPE",
        description="M365 成本驗證使用的 scope（目前主要供 operator-run 驗證流程使用）。",
    )
    m365_cost_department_tag_key: str = Field(
        default="cost_center",
        validation_alias="M365_COST_DEPARTMENT_TAG_KEY",
        description="M365 部門成本歸屬使用的 tag key（目前主要供 operator-run 驗證流程使用）。",
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
    azure_cost_cache_mode: Literal["disabled", "memory", "disk"] = Field(
        default="disk",
        validation_alias="AZURE_COST_CACHE_MODE",
        description="成本資料快取模式。",
    )
    azure_cost_cache_dir: str = Field(
        default=".cache\\azure-cost-mcp",
        validation_alias="AZURE_COST_CACHE_DIR",
        description="成本資料 disk cache 目錄。",
    )
    azure_cost_cache_ttl_seconds: int = Field(
        default=900,
        ge=0,
        validation_alias="AZURE_COST_CACHE_TTL_SECONDS",
        description="成本資料快取有效時間（秒）。",
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
    databricks_mcp_amortized_server_url: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_AMORTIZED_SERVER_URL",
        description="AmortizedCost Genie 對應的 Databricks MCP server URL。",
    )
    databricks_mcp_actual_server_url: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_ACTUAL_SERVER_URL",
        description="ActualCost Genie 對應的 Databricks MCP server URL。",
    )
    databricks_mcp_amortized_query_tool_name: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_AMORTIZED_QUERY_TOOL_NAME",
        description="AmortizedCost Genie 查詢工具名稱。",
    )
    databricks_mcp_actual_query_tool_name: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_ACTUAL_QUERY_TOOL_NAME",
        description="ActualCost Genie 查詢工具名稱。",
    )
    databricks_mcp_query_tool_name: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_MCP_QUERY_TOOL_NAME",
        description="Databricks MCP 查詢工具名稱（legacy fallback）。",
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
    azure_cost_tag_inventory_cache_dir: str = Field(
        default=".cache/tag-inventory",
        validation_alias="AZURE_COST_TAG_INVENTORY_CACHE_DIR",
        description="Tag 盤點快取目錄。",
    )
    azure_cost_required_tag_keys: str = Field(
        default="cost_center,environment,workload,application,owner",
        validation_alias="AZURE_COST_REQUIRED_TAG_KEYS",
        description=(
            "Tag 盤點必要的 tag keys，逗號分隔。"
            "FinOps 標準五鍵：cost_center, environment, workload, application, owner。"
            "FET 現有 Purpose→application、EnvType→environment 需遷移。"
        ),
    )
    lakebase_enabled: bool = Field(
        default=False,
        validation_alias="LAKEBASE_ENABLED",
        description="是否啟用 Lakebase 狀態儲存（tag 快照與 audit trail）。",
    )
    lakebase_pg_url: str | None = Field(
        default=None,
        validation_alias="LAKEBASE_PG_URL",
        description="Lakebase PostgreSQL 靜態連線 URL（本地開發用）。",
    )
    lakebase_instance_name: str | None = Field(
        default=None,
        validation_alias="LAKEBASE_INSTANCE_NAME",
        description="Lakebase Provisioned instance name（舊版模式）。",
    )
    lakebase_database: str | None = Field(
        default=None,
        validation_alias="LAKEBASE_DATABASE_NAME",
        description="Lakebase 資料庫名稱。",
    )
    lakebase_schema: str = Field(
        default="azure_cost_mcp",
        validation_alias="LAKEBASE_SCHEMA_NAME",
        description="Lakebase schema 名稱。",
    )
    lakebase_host: str | None = Field(
        default=None,
        validation_alias="LAKEBASE_HOST",
        description="Lakebase PostgreSQL 主機位址。",
    )
    lakebase_endpoint: str | None = Field(
        default=None,
        validation_alias="LAKEBASE_ENDPOINT",
        description="Lakebase Autoscaling endpoint 完整路徑，例如 projects/my-app/branches/production/endpoints/primary。",
    )
    lakebase_user: str | None = Field(
        default=None,
        validation_alias="LAKEBASE_USER",
        description="Lakebase 連線使用者（Databricks 帳號 email）。",
    )
    databricks_host: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_HOST",
        description="Databricks workspace URL，供 Lakebase OAuth token 生成使用。",
    )
    databricks_token: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_TOKEN",
        description="Databricks PAT，供 Lakebase OAuth token 生成使用。",
    )
    azure_cost_tag_apply_batch_size: int = Field(
        default=10,
        ge=1,
        le=100,
        validation_alias="AZURE_COST_TAG_APPLY_BATCH_SIZE",
        description="azure_cost_tag_apply 每批次最多同時更新的資源數量。",
    )
    azure_cost_tag_apply_delay_ms: int = Field(
        default=250,
        ge=0,
        le=5000,
        validation_alias="AZURE_COST_TAG_APPLY_DELAY_MS",
        description="azure_cost_tag_apply 批次之間的等待毫秒數（避免觸發 API 速率限制）。",
    )
    databricks_embedding_url: str | None = Field(
        default=None,
        validation_alias="DATABRICKS_EMBEDDING_URL",
        description="Databricks AI Gateway embedding endpoint，例如 https://<workspace>/ai-gateway/mlflow/v1/embeddings。",
    )
    databricks_embedding_model: str = Field(
        default="databricks-bge-large-en",
        validation_alias="DATABRICKS_EMBEDDING_MODEL",
        description="Databricks embedding 模型名稱。",
    )
    databricks_embedding_dim: int = Field(
        default=1024,
        ge=64,
        le=4096,
        validation_alias="DATABRICKS_EMBEDDING_DIM",
        description="embedding 向量維度（BGE-Large-EN=1024，Ada-002=1536）。",
    )

    @property
    def azure_cost_required_tag_keys_list(self) -> list[str]:
        """將逗號分隔的 required tag keys 解析為清單。"""
        return [k.strip() for k in self.azure_cost_required_tag_keys.split(",") if k.strip()]

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

    @field_validator("azure_cost_department_tag_key", "m365_cost_department_tag_key")
    @classmethod
    def validate_department_tag_key(cls, value: str) -> str:
        """驗證部門 tag key。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("部門 tag key 不可為空字串。")
        return normalized

    @field_validator(
        "databricks_mcp_server_url",
        "databricks_mcp_amortized_server_url",
        "databricks_mcp_actual_server_url",
        "azure_tenant_id",
        "azure_client_id",
        "azure_client_secret",
        "azure_managed_identity_client_id",
        "azure_cost_cache_dir",
        "m365_cost_management_tenant",
        "m365_cost_management_scope",
        "m365_sp_client_id",
        "m365_sp_client_secret",
        "databricks_mcp_amortized_query_tool_name",
        "databricks_mcp_actual_query_tool_name",
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

    @field_validator("azure_cost_cache_dir")
    @classmethod
    def validate_cache_dir(cls, value: str | None) -> str:
        """驗證 cache 目錄。"""
        if value is None:
            raise ValueError("AZURE_COST_CACHE_DIR 不可為空。")
        normalized = value.strip()
        if not normalized:
            raise ValueError("AZURE_COST_CACHE_DIR 不可為空。")
        return normalized

    def resolve_databricks_query_target(
        self,
        source: Literal["amortized", "actual"],
    ) -> tuple[str | None, str | None]:
        """依來源類型解析 Databricks query target。"""
        if source == "actual":
            return (
                self.databricks_mcp_actual_server_url or self.databricks_mcp_server_url,
                self.databricks_mcp_actual_query_tool_name
                or self.databricks_mcp_query_tool_name,
            )
        return (
            self.databricks_mcp_amortized_server_url or self.databricks_mcp_server_url,
            self.databricks_mcp_amortized_query_tool_name
            or self.databricks_mcp_query_tool_name,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """取得快取後的服務設定。"""
    return Settings()
