"""Azure Resource Graph client。"""

from __future__ import annotations

import re
from typing import Any

from .azure_management import AzureManagementApiClient
from .config import Settings

SUBSCRIPTION_SCOPE_PATTERN = re.compile(r"^/subscriptions/([^/]+)", re.IGNORECASE)


class ResourceGraphClient(AzureManagementApiClient):
    """Azure Resource Graph REST client。"""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._settings = settings

    async def find_resources_missing_tags(
        self,
        *,
        required_tag_keys: list[str],
        subscriptions: list[str] | None = None,
        resource_ids: list[str] | None = None,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """找出缺少指定 tags 的資源。"""
        if not required_tag_keys:
            raise ValueError("required_tag_keys 至少需要一個 tag key。")

        where_clauses = [self._missing_tag_condition(tag_key) for tag_key in required_tag_keys]
        if resource_ids:
            resource_literals = ", ".join(
                f"'{self._escape_kql_literal(resource_id)}'" for resource_id in resource_ids
            )
            where_clauses.append(f"id in~ ({resource_literals})")

        query = (
            "Resources\n"
            f"| where {' or '.join(where_clauses)}\n"
            "| project id, name, type, resourceGroup, location, subscriptionId, tags"
        )

        result = await self.query_resources(
            query,
            subscriptions=subscriptions,
            top=max_results,
        )
        data = result.get("data", [])
        if isinstance(data, list):
            return data
        return []

    async def get_all_resources_with_tags(
        self,
        *,
        subscriptions: list[str] | None = None,
        resource_types: list[str] | None = None,
        resource_groups: list[str] | None = None,
        max_results: int = 5000,
    ) -> list[dict[str, Any]]:
        """分頁抓取所有資源的完整 tag 現況。"""
        kql_parts = ["Resources"]
        if resource_types:
            type_list = ", ".join(
                f"'{self._escape_kql_literal(t)}'" for t in resource_types
            )
            kql_parts.append(f"| where type in~ ({type_list})")
        if resource_groups:
            rg_list = ", ".join(
                f"'{self._escape_kql_literal(rg)}'" for rg in resource_groups
            )
            kql_parts.append(f"| where resourceGroup in~ ({rg_list})")
        kql_parts.append(
            "| project id, name, type, resourceGroup, subscriptionId, location, tags"
        )
        query = "\n".join(kql_parts)

        _page_size = 1000
        all_resources: list[dict[str, Any]] = []
        skip_token: str | None = None

        while True:
            remaining = max_results - len(all_resources)
            result = await self.query_resources(
                query,
                subscriptions=subscriptions,
                top=min(_page_size, remaining),
                skip_token=skip_token,
            )
            data = result.get("data", [])
            if isinstance(data, list):
                all_resources.extend(data)
            skip_token = result.get("$skipToken")
            if not skip_token or len(all_resources) >= max_results:
                break

        return all_resources[:max_results]

    async def query_resources(
        self,
        query: str,
        *,
        subscriptions: list[str] | None = None,
        top: int | None = None,
        skip_token: str | None = None,
    ) -> dict[str, Any]:
        """執行 Resource Graph 查詢。"""
        body: dict[str, Any] = {"query": query}
        resolved_subscriptions = subscriptions or self.default_subscriptions()
        if resolved_subscriptions:
            body["subscriptions"] = resolved_subscriptions
        options: dict[str, Any] = {}
        if top is not None:
            options["$top"] = top
        if skip_token is not None:
            options["$skipToken"] = skip_token
        if options:
            body["options"] = options

        result = await self._request(
            "POST",
            "/providers/Microsoft.ResourceGraph/resources",
            params={"api-version": self._settings.azure_resource_graph_api_version},
            json_body=body,
            expected_statuses=(200,),
        )
        return result or {}

    def default_subscriptions(self) -> list[str] | None:
        """從 Cost Management scope 推導單一 subscription。"""
        scope = self._settings.azure_cost_management_scope
        if not scope:
            return None
        match = SUBSCRIPTION_SCOPE_PATTERN.match(scope)
        if not match:
            return None
        return [match.group(1)]

    def m365_subscriptions(self) -> list[str] | None:
        """從 M365 Cost Management scope 推導單一 subscription。"""
        scope = self._settings.m365_cost_management_scope
        if not scope:
            return None
        match = SUBSCRIPTION_SCOPE_PATTERN.match(scope)
        if not match:
            return None
        return [match.group(1)]

    def m365_or_default_subscriptions(self) -> list[str] | None:
        """優先從 M365 scope 推導，退回 Azure Cost Management scope。"""
        return self.m365_subscriptions() or self.default_subscriptions()

    @staticmethod
    def _missing_tag_condition(tag_key: str) -> str:
        escaped_tag_key = ResourceGraphClient._escape_kql_literal(tag_key)
        return f"isempty(tostring(tags['{escaped_tag_key}']))"

    @staticmethod
    def _escape_kql_literal(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "''")
