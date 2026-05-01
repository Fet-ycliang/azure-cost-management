"""Azure Cost MCP server 建立與工具註冊。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from .azure_management import AzureManagementApiError
from .config import Settings, get_settings
from .cost_management import CostManagementClient
from .databricks_mcp import DatabricksMcpClient, DatabricksMcpClientError
from .formatting import to_response
from .models import (
    CostTrendParams,
    DatabricksQueryParams,
    DepartmentCostParams,
    ResponseOptions,
    SavingsRecommendationParams,
    StorageExportsParams,
    TagAuditParams,
    TagRemediationParams,
    TrendGranularity,
    UntaggedResourcesParams,
)
from .resource_graph import ResourceGraphClient
from .storage import StorageClientError, StorageExportClient

PROJECT_PRIORITIES = [
    "Azure Databricks",
    "Storage",
    "VM",
    "Network egress",
]

USE_CASES = [
    "查詢部門費用",
    "查詢節費方向與優化建議",
    "查詢費用趨勢",
    "找出未打標記的服務或資源",
    "透過 Databricks MCP server 修正 tag 內容",
]

IMPLEMENTED_TOOLS = [
    "azure_cost_get_bootstrap_status",
    "azure_cost_get_planned_capabilities",
    "azure_cost_department_cost",
    "azure_cost_cost_trend",
    "azure_cost_cost_saving_opportunities",
    "azure_cost_databricks_query",
    "azure_cost_untagged_resources",
    "azure_cost_tag_audit",
    "azure_cost_tag_remediation",
    "azure_cost_list_storage_exports",
]

def _to_float(value: Any) -> float:
    """將 cost 欄位轉為 float。"""
    if isinstance(value, dict):
        value = value.get("value", 0)
    if value in (None, ""):
        return 0.0
    return float(value)


def _round_cost(value: Any) -> float:
    """統一 cost 精度。"""
    return round(_to_float(value), 4)


def _detect_cost_field(records: list[dict[str, Any]]) -> str:
    """找出成本欄位。"""
    if not records:
        return "PreTaxCost"
    for candidate in ("PreTaxCost", "Cost", "totalCost"):
        if candidate in records[0]:
            return candidate
    for key, value in records[0].items():
        if isinstance(value, (int, float)):
            return key
    return "PreTaxCost"


def _detect_group_field(records: list[dict[str, Any]], preferred: str | None = None) -> str:
    """找出分組欄位。"""
    if not records:
        return preferred or "group"
    reserved = {"PreTaxCost", "Cost", "totalCost", "Currency", "UsageDate"}
    if preferred and preferred in records[0]:
        return preferred
    for key in records[0]:
        if key not in reserved:
            return key
    return preferred or "group"


def _detect_currency(records: list[dict[str, Any]]) -> str | None:
    """找出幣別欄位。"""
    for record in records:
        currency = record.get("Currency")
        if currency:
            return str(currency)
    return None


def _normalize_group_value(value: Any) -> str:
    """正規化分組值。"""
    if value in (None, "", "null"):
        return "(untagged)"
    return str(value)


def _normalize_trend_date(value: Any, granularity: TrendGranularity) -> str:
    """將 Cost Management 回傳日期轉成 ISO-like 顯示格式。"""
    if value in (None, ""):
        return "-"
    text = str(value)
    if text.isdigit() and len(text) == 8:
        parsed = datetime.strptime(text, "%Y%m%d")
        return parsed.date().isoformat()
    if text.isdigit() and len(text) == 6 and granularity == TrendGranularity.MONTHLY:
        return f"{text[:4]}-{text[4:6]}"
    return text


def _service_hypothesis(service_name: str) -> str:
    normalized = service_name.lower()
    if "databricks" in normalized:
        return (
            "檢查 job cluster / all-purpose cluster 比例、auto-stop、warehouse idle timeout、"
            "Photon 與 DBU 版本設定。"
        )
    if any(keyword in normalized for keyword in ("virtual machines", "virtual machine", "vm")):
        return "檢查 Reservation / Savings Plan、rightsizing、排程關機與 Azure Hybrid Benefit。"
    if "storage" in normalized or "blob" in normalized or "disk" in normalized:
        return "檢查 Hot/Cool/Cold 分層、LRS/ZRS 搭配、snapshot/version 清理與 lifecycle policy。"
    if any(keyword in normalized for keyword in ("bandwidth", "data transfer", "egress", "network")):
        return "檢查跨區流量、NAT / outbound 流量與 Databricks、Storage 是否同區。"
    if "app service" in normalized or "web app" in normalized:
        return "檢查 App Service Plan 利用率、autoscale、是否適合改為 ACA 或以 Savings Plan 吃掉穩定 compute。"
    return "建議依 meter、region、resource group 與使用模式進一步拆分，再決定是否適用 Reservation 或架構優化。"


def _build_optimization_hypotheses(service_costs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """根據主要成本服務產出對應假說。"""
    hypotheses = []
    for service in service_costs:
        service_name = service["service_name"]
        hypotheses.append(
            {
                "service_name": service_name,
                "cost": service["cost"],
                "focus": _service_hypothesis(service_name),
            }
        )
    return hypotheses


def _annotate_missing_tags(
    resources: list[dict[str, Any]],
    required_tag_keys: list[str],
) -> list[dict[str, Any]]:
    """補上缺漏的 tag keys。"""
    annotated = []
    for resource in resources:
        tags = resource.get("tags") or {}
        missing_tags = [
            tag_key for tag_key in required_tag_keys if not str(tags.get(tag_key, "")).strip()
        ]
        annotated.append(
            {
                "id": resource.get("id"),
                "name": resource.get("name"),
                "type": resource.get("type"),
                "resource_group": resource.get("resourceGroup"),
                "location": resource.get("location"),
                "subscription_id": resource.get("subscriptionId"),
                "missing_tags": missing_tags,
                "tags": tags,
            }
        )
    return annotated


def _summarize_missing_tags(resources: list[dict[str, Any]]) -> dict[str, Any]:
    """彙整未標記資源摘要。"""
    by_type = Counter(resource["type"] for resource in resources)
    by_tag = Counter(
        missing_tag
        for resource in resources
        for missing_tag in resource.get("missing_tags", [])
    )
    return {
        "resource_count": len(resources),
        "counts_by_type": dict(by_type.most_common()),
        "counts_by_missing_tag": dict(by_tag.most_common()),
    }


def _normalize_savings_plan_recommendations(
    recommendations: list[dict[str, Any]],
    *,
    top: int,
) -> list[dict[str, Any]]:
    normalized = []
    for recommendation in recommendations:
        properties = recommendation.get("properties", {})
        details = properties.get("recommendationDetails", {})
        normalized.append(
            {
                "scope": properties.get("scope"),
                "term": properties.get("term"),
                "arm_sku_name": properties.get("armSkuName"),
                "currency": properties.get("currencyCode"),
                "commitment_amount": details.get("commitmentAmount"),
                "savings_amount": _round_cost(details.get("savingsAmount")),
                "savings_percentage": details.get("savingsPercentage"),
                "coverage_percentage": details.get("coveragePercentage"),
                "average_utilization_percentage": details.get("averageUtilizationPercentage"),
                "wastage_cost": _round_cost(details.get("wastageCost")),
            }
        )
    normalized.sort(key=lambda item: item["savings_amount"], reverse=True)
    return normalized[:top]


def _normalize_reservation_recommendations(
    recommendations: list[dict[str, Any]],
    *,
    top: int,
) -> list[dict[str, Any]]:
    normalized = []
    for recommendation in recommendations:
        properties = recommendation.get("properties", {})
        net_savings = properties.get("netSavings")
        currency = None
        if isinstance(net_savings, dict):
            currency = net_savings.get("currency")
        normalized.append(
            {
                "scope": properties.get("scope"),
                "term": properties.get("term"),
                "resource_type": properties.get("resourceType"),
                "sku": recommendation.get("sku") or properties.get("skuName"),
                "location": recommendation.get("location") or properties.get("location"),
                "recommended_quantity": properties.get("recommendedQuantity"),
                "net_savings": _round_cost(net_savings),
                "currency": currency,
            }
        )
    normalized.sort(key=lambda item: item["net_savings"], reverse=True)
    return normalized[:top]


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """建立 Azure Cost MCP server。"""
    current_settings = settings or get_settings()
    cost_client = CostManagementClient(current_settings)
    resource_graph_client = ResourceGraphClient(current_settings)
    databricks_client = DatabricksMcpClient(current_settings)
    storage_client = StorageExportClient(current_settings)

    mcp = FastMCP(
        name="azure_cost_mcp",
        instructions=(
            "這是一個用於 Azure FinOps 查詢、趨勢分析、節費建議與 tag 治理的 MCP 服務。"
            "第一版優先聚焦 Azure Databricks、Storage、VM 與 Network egress。"
        ),
        host=current_settings.mcp_host,
        port=current_settings.mcp_port,
        streamable_http_path=current_settings.mcp_streamable_http_path,
        log_level="INFO",
    )

    @mcp.tool(
        name="azure_cost_get_bootstrap_status",
        annotations={
            "title": "取得初始化狀態",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def azure_cost_get_bootstrap_status(params: ResponseOptions) -> str:
        """取得目前 MCP 服務骨架與整合設定狀態。"""

        payload = {
            "server_name": "azure_cost_mcp",
            "default_transport": current_settings.mcp_transport,
            "streamable_http_path": current_settings.mcp_streamable_http_path,
            "implemented_tools": IMPLEMENTED_TOOLS,
            "integrations": {
                "azure_cost_management_scope_configured": bool(
                    current_settings.azure_cost_management_scope
                ),
                "default_department_tag_key": current_settings.azure_cost_department_tag_key,
                "azure_storage_configured": bool(
                    current_settings.azure_cost_storage_account_url
                    and current_settings.azure_cost_storage_container
                ),
                "databricks_mcp_server_configured": bool(
                    current_settings.databricks_mcp_server_url
                ),
                "databricks_mcp_query_tool_configured": bool(
                    current_settings.databricks_mcp_query_tool_name
                ),
                "databricks_mcp_tag_audit_tool_configured": bool(
                    current_settings.databricks_mcp_tag_audit_tool_name
                ),
                "databricks_mcp_tag_remediation_tool_configured": bool(
                    current_settings.databricks_mcp_tag_remediation_tool_name
                ),
                "tag_direct_apply_enabled": current_settings.azure_cost_tag_apply_enabled,
            },
            "next_focus": PROJECT_PRIORITIES,
        }
        return to_response("Azure Cost MCP 初始化狀態", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_get_planned_capabilities",
        annotations={
            "title": "取得規劃能力",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def azure_cost_get_planned_capabilities(params: ResponseOptions) -> str:
        """取得目前已確認的第一版能力規劃。"""

        payload = {
            "use_cases": USE_CASES,
            "implemented_tools": IMPLEMENTED_TOOLS,
            "data_flow": [
                "Azure Cost Management REST API / 匯出資料 / FOCUS",
                "Azure Storage",
                "Databricks MCP server",
                "對外 MCP service",
            ],
            "remaining_focus": [
                "ACA / ACI / App Service / Web App 比較與成本選型",
                "APIM 選型",
                "Lakebase / SQL Server / Cosmos DB / Azure AI Search / pgvector 評估",
                "Storage LRS / ZRS 與 Hot / Cool / Cold 配置建議",
            ],
            "tag_strategy": {
                "default_mode": "先產生修正建議",
                "direct_apply_mode": "需明確指定且受設定控制",
            },
        }
        return to_response("Azure Cost MCP 規劃能力", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_department_cost",
        annotations={
            "title": "查詢部門費用",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_department_cost(params: DepartmentCostParams) -> str:
        """查詢部門費用，或列出各部門成本排名。"""

        start_date, end_date = params.resolved_window()
        department_tag_key = (
            params.department_tag_key or current_settings.azure_cost_department_tag_key
        )

        filters = None
        if params.department_name:
            filters = {
                "tags": {
                    "name": department_tag_key,
                    "operator": "In",
                    "values": [params.department_name],
                }
            }

        grouping = (
            [{"name": "ServiceName", "type": "Dimension"}]
            if params.department_name
            else [{"name": department_tag_key, "type": "TagKey"}]
        )
        result = await cost_client.query_usage(
            start_date=start_date,
            end_date=end_date,
            granularity="None",
            grouping=grouping,
            filters=filters,
        )
        records = cost_client.rows_to_records(result)
        cost_field = _detect_cost_field(records)
        currency = _detect_currency(records)

        if params.department_name:
            group_field = _detect_group_field(records, preferred="ServiceName")
            top_services = sorted(
                [
                    {
                        "service_name": _normalize_group_value(record.get(group_field)),
                        "cost": _round_cost(record.get(cost_field)),
                    }
                    for record in records
                ],
                key=lambda item: item["cost"],
                reverse=True,
            )[: params.top]
            payload = {
                "department_name": params.department_name,
                "department_tag_key": department_tag_key,
                "window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                "currency": currency,
                "total_cost": round(
                    sum(_round_cost(record.get(cost_field)) for record in records),
                    4,
                ),
                "top_services": top_services,
                "source": "Azure Cost Management Query API",
            }
        else:
            group_field = _detect_group_field(records, preferred=department_tag_key)
            departments = sorted(
                [
                    {
                        "department": _normalize_group_value(record.get(group_field)),
                        "cost": _round_cost(record.get(cost_field)),
                    }
                    for record in records
                ],
                key=lambda item: item["cost"],
                reverse=True,
            )[: params.top]
            payload = {
                "department_tag_key": department_tag_key,
                "window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                "currency": currency,
                "departments": departments,
                "source": "Azure Cost Management Query API",
            }

        return to_response("Azure 部門成本分析", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_cost_trend",
        annotations={
            "title": "查詢費用趨勢",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_cost_trend(params: CostTrendParams) -> str:
        """查詢費用趨勢。"""

        start_date, end_date = params.resolved_window()
        department_tag_key = (
            params.department_tag_key or current_settings.azure_cost_department_tag_key
        )

        filters_list = []
        if params.service_name:
            filters_list.append(
                {
                    "dimensions": {
                        "name": "ServiceName",
                        "operator": "In",
                        "values": [params.service_name],
                    }
                }
            )
        if params.department_name:
            filters_list.append(
                {
                    "tags": {
                        "name": department_tag_key,
                        "operator": "In",
                        "values": [params.department_name],
                    }
                }
            )

        filters = None
        if len(filters_list) == 1:
            filters = filters_list[0]
        elif filters_list:
            filters = {"and": filters_list}

        result = await cost_client.query_usage(
            start_date=start_date,
            end_date=end_date,
            granularity=params.granularity.value,
            filters=filters,
        )
        records = cost_client.rows_to_records(result)
        cost_field = _detect_cost_field(records)
        trend = [
            {
                "period": _normalize_trend_date(
                    record.get("UsageDate"),
                    params.granularity,
                ),
                "cost": _round_cost(record.get(cost_field)),
            }
            for record in records
        ]
        payload = {
            "window": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "granularity": params.granularity.value,
            "filters": {
                "service_name": params.service_name,
                "department_name": params.department_name,
                "department_tag_key": department_tag_key if params.department_name else None,
            },
            "currency": _detect_currency(records),
            "total_cost": round(sum(item["cost"] for item in trend), 4),
            "trend": trend,
            "source": "Azure Cost Management Query API",
        }
        return to_response("Azure 費用趨勢", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_cost_saving_opportunities",
        annotations={
            "title": "節費方向與建議",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_cost_saving_opportunities(
        params: SavingsRecommendationParams,
    ) -> str:
        """整合主要費用服務、Savings Plan 與 Reservation 建議。"""

        start_date, end_date = params.resolved_window()
        department_tag_key = (
            params.department_tag_key or current_settings.azure_cost_department_tag_key
        )

        filters = None
        if params.department_name:
            filters = {
                "tags": {
                    "name": department_tag_key,
                    "operator": "In",
                    "values": [params.department_name],
                }
            }

        service_result = await cost_client.query_usage(
            start_date=start_date,
            end_date=end_date,
            granularity="None",
            grouping=[{"name": "ServiceName", "type": "Dimension"}],
            filters=filters,
        )
        service_records = cost_client.rows_to_records(service_result)
        service_cost_field = _detect_cost_field(service_records)
        service_group_field = _detect_group_field(service_records, preferred="ServiceName")
        top_services = sorted(
            [
                {
                    "service_name": _normalize_group_value(record.get(service_group_field)),
                    "cost": _round_cost(record.get(service_cost_field)),
                }
                for record in service_records
            ],
            key=lambda item: item["cost"],
            reverse=True,
        )[: params.top]

        recommendation_errors = []
        savings_plan_recommendations = []
        reservation_recommendations = []

        if params.include_savings_plan:
            try:
                savings_plan_recommendations = _normalize_savings_plan_recommendations(
                    await cost_client.list_benefit_recommendations(
                        look_back_period=params.look_back_period.value,
                        term=params.savings_plan_term.value,
                        recommendation_scope=params.savings_plan_scope.value,
                        expand_usage=params.expand_savings_plan_usage,
                    ),
                    top=params.top,
                )
            except AzureManagementApiError as error:
                recommendation_errors.append(str(error))

        if params.include_reservation:
            try:
                reservation_recommendations = _normalize_reservation_recommendations(
                    await cost_client.list_reservation_recommendations(
                        look_back_period=params.look_back_period.value,
                        recommendation_scope=params.reservation_scope.value,
                        resource_type=params.reservation_resource_type.value,
                    ),
                    top=params.top,
                )
            except AzureManagementApiError as error:
                recommendation_errors.append(str(error))

        payload = {
            "window": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "department_name": params.department_name,
            "top_services": top_services,
            "optimization_hypotheses": _build_optimization_hypotheses(top_services),
            "savings_plan_recommendations": savings_plan_recommendations,
            "reservation_recommendations": reservation_recommendations,
            "recommendation_errors": recommendation_errors,
            "sources": [
                "Azure Cost Management Query API",
                "Azure Cost Management Benefit Recommendations API",
                "Azure Consumption Reservation Recommendations API",
            ],
        }
        return to_response("Azure 節費方向與優化建議", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_databricks_query",
        annotations={
            "title": "透過 Databricks 查詢",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_databricks_query(params: DatabricksQueryParams) -> str:
        """將自然語言或 SQL 原樣代理到 Databricks MCP query tool。"""

        remote_result = await databricks_client.call_configured_tool(
            tool_name=current_settings.databricks_mcp_query_tool_name,
            env_var_name="DATABRICKS_MCP_QUERY_TOOL_NAME",
            purpose="databricks-query",
            arguments={
                "question": params.question,
                "sql": params.sql,
                "catalog": params.catalog,
                "schema_name": params.schema_name,
                "arguments": params.arguments,
            },
        )
        payload = {
            "mode": "databricks-proxy",
            "remote_server": current_settings.databricks_mcp_server_url,
            "result": remote_result,
        }
        return to_response("Azure Databricks 查詢代理", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_untagged_resources",
        annotations={
            "title": "找出未標記資源",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_untagged_resources(params: UntaggedResourcesParams) -> str:
        """以 Azure Resource Graph 找出缺少必要 tags 的資源。"""

        raw_resources = await resource_graph_client.find_resources_missing_tags(
            required_tag_keys=params.required_tag_keys,
            subscriptions=params.subscriptions,
            max_results=params.max_results,
        )
        resources = _annotate_missing_tags(raw_resources, params.required_tag_keys)
        payload = {
            "required_tag_keys": params.required_tag_keys,
            "subscriptions": (
                params.subscriptions or resource_graph_client.default_subscriptions()
            ),
            "summary": _summarize_missing_tags(resources),
            "resources": resources,
            "source": "Azure Resource Graph",
        }
        return to_response("Azure 未標記資源", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_tag_audit",
        annotations={
            "title": "檢查 tag 規則",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_tag_audit(params: TagAuditParams) -> str:
        """優先透過 Databricks MCP server 執行 tag audit，否則回退到 Resource Graph。"""

        if params.use_databricks and databricks_client.is_configured():
            try:
                remote_result = await databricks_client.call_configured_tool(
                    tool_name=current_settings.databricks_mcp_tag_audit_tool_name,
                    env_var_name="DATABRICKS_MCP_TAG_AUDIT_TOOL_NAME",
                    purpose="tag-audit",
                    arguments={
                        "required_tag_keys": params.required_tag_keys,
                        "resource_ids": params.resource_ids,
                        "max_results": params.max_results,
                    },
                )
                payload = {
                    "mode": "databricks-proxy",
                    "remote_server": current_settings.databricks_mcp_server_url,
                    "result": remote_result,
                }
                return to_response("Azure tag audit", payload, params.response_format)
            except DatabricksMcpClientError as error:
                fallback_reason = str(error)
        else:
            fallback_reason = "Databricks MCP server 未設定，改用 Azure Resource Graph 執行本地 audit。"

        raw_resources = await resource_graph_client.find_resources_missing_tags(
            required_tag_keys=params.required_tag_keys,
            subscriptions=params.subscriptions,
            resource_ids=params.resource_ids,
            max_results=params.max_results,
        )
        resources = _annotate_missing_tags(raw_resources, params.required_tag_keys)
        payload = {
            "mode": "resource-graph-fallback",
            "fallback_reason": fallback_reason,
            "required_tag_keys": params.required_tag_keys,
            "summary": _summarize_missing_tags(resources),
            "resources": resources,
            "source": "Azure Resource Graph",
        }
        return to_response("Azure tag audit", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_tag_remediation",
        annotations={
            "title": "修正 tag",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def azure_cost_tag_remediation(params: TagRemediationParams) -> str:
        """透過 Databricks MCP server 執行 tag 修正。"""

        if params.apply and not current_settings.azure_cost_tag_apply_enabled:
            raise ValueError(
                "已要求直接 apply，但目前 AZURE_COST_TAG_APPLY_ENABLED=false。"
                "請先確認權限與治理流程後再開啟。"
            )

        remote_result = await databricks_client.call_configured_tool(
            tool_name=current_settings.databricks_mcp_tag_remediation_tool_name,
            env_var_name="DATABRICKS_MCP_TAG_REMEDIATION_TOOL_NAME",
            purpose="tag-remediation",
            arguments={
                "apply": params.apply,
                "required_tag_keys": params.required_tag_keys,
                "resource_ids": params.resource_ids,
                "proposed_tags": params.proposed_tags,
                "rationale": params.rationale,
            },
        )
        payload = {
            "mode": "databricks-proxy",
            "apply": params.apply,
            "tag_direct_apply_enabled": current_settings.azure_cost_tag_apply_enabled,
            "remote_server": current_settings.databricks_mcp_server_url,
            "result": remote_result,
        }
        return to_response("Azure tag remediation", payload, params.response_format)

    @mcp.tool(
        name="azure_cost_list_storage_exports",
        annotations={
            "title": "列出 Storage 匯出檔",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def azure_cost_list_storage_exports(params: StorageExportsParams) -> str:
        """列出 Azure Storage 中的成本匯出 blob。"""

        try:
            blobs = await storage_client.list_cost_blobs(
                prefix=params.prefix,
                max_results=params.max_results,
            )
        except StorageClientError as error:
            raise ValueError(str(error)) from error

        payload = {
            "storage_account_url": current_settings.azure_cost_storage_account_url,
            "container": current_settings.azure_cost_storage_container,
            "prefix": params.prefix or current_settings.azure_cost_storage_prefix,
            "blob_count": len(blobs),
            "blobs": blobs,
            "source": "Azure Blob Storage",
        }
        return to_response("Azure 成本匯出檔案", payload, params.response_format)

    return mcp
