from __future__ import annotations

from typing import Any

from azure_cost_mcp.config import Settings


def make_settings(**overrides: Any) -> Settings:
    alias_by_field = {
        "mcp_transport": "AZURE_COST_MCP_TRANSPORT",
        "mcp_host": "AZURE_COST_MCP_HOST",
        "mcp_port": "AZURE_COST_MCP_PORT",
        "mcp_streamable_http_path": "AZURE_COST_MCP_STREAMABLE_HTTP_PATH",
        "azure_cost_auth_mode": "AZURE_COST_AUTH_MODE",
        "azure_tenant_id": "AZURE_TENANT_ID",
        "azure_client_id": "AZURE_CLIENT_ID",
        "azure_client_secret": "AZURE_CLIENT_SECRET",
        "azure_managed_identity_client_id": "AZURE_MANAGED_IDENTITY_CLIENT_ID",
        "azure_management_base_url": "AZURE_MANAGEMENT_BASE_URL",
        "azure_cost_management_api_version": "AZURE_COST_MANAGEMENT_API_VERSION",
        "azure_consumption_api_version": "AZURE_CONSUMPTION_API_VERSION",
        "azure_resource_graph_api_version": "AZURE_RESOURCE_GRAPH_API_VERSION",
        "azure_cost_management_scope": "AZURE_COST_MANAGEMENT_SCOPE",
        "azure_cost_department_tag_key": "AZURE_COST_DEPARTMENT_TAG_KEY",
        "azure_cost_storage_account_url": "AZURE_COST_STORAGE_ACCOUNT_URL",
        "azure_cost_storage_container": "AZURE_COST_STORAGE_CONTAINER",
        "azure_cost_storage_prefix": "AZURE_COST_STORAGE_PREFIX",
        "azure_cost_cache_mode": "AZURE_COST_CACHE_MODE",
        "azure_cost_cache_dir": "AZURE_COST_CACHE_DIR",
        "azure_cost_cache_ttl_seconds": "AZURE_COST_CACHE_TTL_SECONDS",
        "databricks_mcp_server_url": "DATABRICKS_MCP_SERVER_URL",
        "databricks_mcp_bearer_token": "DATABRICKS_MCP_BEARER_TOKEN",
        "databricks_mcp_timeout_seconds": "DATABRICKS_MCP_TIMEOUT_SECONDS",
        "databricks_mcp_amortized_server_url": "DATABRICKS_MCP_AMORTIZED_SERVER_URL",
        "databricks_mcp_actual_server_url": "DATABRICKS_MCP_ACTUAL_SERVER_URL",
        "databricks_mcp_amortized_query_tool_name": "DATABRICKS_MCP_AMORTIZED_QUERY_TOOL_NAME",
        "databricks_mcp_actual_query_tool_name": "DATABRICKS_MCP_ACTUAL_QUERY_TOOL_NAME",
        "databricks_mcp_query_tool_name": "DATABRICKS_MCP_QUERY_TOOL_NAME",
        "databricks_mcp_tag_audit_tool_name": "DATABRICKS_MCP_TAG_AUDIT_TOOL_NAME",
        "databricks_mcp_tag_remediation_tool_name": "DATABRICKS_MCP_TAG_REMEDIATION_TOOL_NAME",
        "azure_cost_tag_apply_enabled": "AZURE_COST_TAG_APPLY_ENABLED",
    }
    base = {
        "AZURE_COST_MCP_TRANSPORT": "stdio",
        "AZURE_COST_MCP_HOST": "127.0.0.1",
        "AZURE_COST_MCP_PORT": 8000,
        "AZURE_COST_MCP_STREAMABLE_HTTP_PATH": "/mcp",
        "AZURE_COST_AUTH_MODE": "azure-cli",
        "AZURE_TENANT_ID": "",
        "AZURE_CLIENT_ID": "",
        "AZURE_CLIENT_SECRET": "",
        "AZURE_MANAGED_IDENTITY_CLIENT_ID": "",
        "AZURE_MANAGEMENT_BASE_URL": "https://management.azure.com",
        "AZURE_COST_MANAGEMENT_API_VERSION": "2025-03-01",
        "AZURE_CONSUMPTION_API_VERSION": "2024-08-01",
        "AZURE_RESOURCE_GRAPH_API_VERSION": "2024-04-01",
        "AZURE_COST_MANAGEMENT_SCOPE": "/subscriptions/sub-default",
        "AZURE_COST_DEPARTMENT_TAG_KEY": "Department",
        "AZURE_COST_STORAGE_ACCOUNT_URL": "https://example.blob.core.windows.net",
        "AZURE_COST_STORAGE_CONTAINER": "costs",
        "AZURE_COST_STORAGE_PREFIX": "cost-management",
        "AZURE_COST_CACHE_MODE": "disabled",
        "AZURE_COST_CACHE_DIR": ".cache\\azure-cost-mcp-test",
        "AZURE_COST_CACHE_TTL_SECONDS": 900,
        "DATABRICKS_MCP_SERVER_URL": "https://example.com/mcp",
        "DATABRICKS_MCP_BEARER_TOKEN": "token",
        "DATABRICKS_MCP_TIMEOUT_SECONDS": 60,
        "DATABRICKS_MCP_AMORTIZED_SERVER_URL": "",
        "DATABRICKS_MCP_ACTUAL_SERVER_URL": "",
        "DATABRICKS_MCP_AMORTIZED_QUERY_TOOL_NAME": "",
        "DATABRICKS_MCP_ACTUAL_QUERY_TOOL_NAME": "",
        "DATABRICKS_MCP_QUERY_TOOL_NAME": "query_tool",
        "DATABRICKS_MCP_TAG_AUDIT_TOOL_NAME": "tag_audit_tool",
        "DATABRICKS_MCP_TAG_REMEDIATION_TOOL_NAME": "tag_remediation_tool",
        "AZURE_COST_TAG_APPLY_ENABLED": False,
    }
    normalized_overrides = {
        alias_by_field.get(key, key): value for key, value in overrides.items()
    }
    base.update(normalized_overrides)
    return Settings(**base)
