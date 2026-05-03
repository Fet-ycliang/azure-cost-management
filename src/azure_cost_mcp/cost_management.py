"""Azure Cost Management 與 Consumption API client。"""

from __future__ import annotations

from datetime import date
from typing import Any

from .cache import ApiCache
from .azure_management import AzureManagementApiClient
from .config import Settings


class CostManagementClient(AzureManagementApiClient):
    """Azure Cost Management / Consumption API client。"""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._default_scope = settings.azure_cost_management_scope
        self._cache = ApiCache(settings)

    def require_scope(self, scope: str | None = None) -> str:
        """取得必要的 Cost Management scope。"""
        resolved_scope = scope or self._default_scope
        if not resolved_scope:
            raise ValueError(
                "AZURE_COST_MANAGEMENT_SCOPE 尚未設定。請先設定 subscription、resource group、"
                "billing account、billing profile 或 management group scope。"
            )
        return resolved_scope

    async def query_usage(
        self,
        *,
        start_date: date,
        end_date: date,
        granularity: str,
        grouping: list[dict[str, str]] | None = None,
        filters: dict[str, Any] | None = None,
        scope: str | None = None,
        query_type: str = "Usage",
    ) -> dict[str, Any]:
        """查詢指定範圍的成本資料。"""
        resolved_scope = self.require_scope(scope)
        cache_key = {
            "scope": resolved_scope,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "granularity": granularity,
            "grouping": grouping,
            "filters": filters,
            "query_type": query_type,
            "api_version": self._settings.azure_cost_management_api_version,
        }

        async def loader() -> dict[str, Any]:
            dataset: dict[str, Any] = {
                "granularity": granularity,
                "aggregation": {
                    "totalCost": {
                        "name": "PreTaxCost",
                        "function": "Sum",
                    }
                },
            }
            if grouping:
                dataset["grouping"] = grouping
            if filters:
                dataset["filter"] = filters

            payload = {
                "type": query_type,
                "timeframe": "Custom",
                "timePeriod": {
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                },
                "dataset": dataset,
            }

            url = f"{resolved_scope}/providers/Microsoft.CostManagement/query"
            params = {"api-version": self._settings.azure_cost_management_api_version}
            pages: list[dict[str, Any]] = []
            next_url: str | None = url
            next_params: dict[str, str] | None = params

            while next_url:
                page = await self._request(
                    "POST",
                    next_url,
                    params=next_params,
                    json_body=payload,
                )
                next_params = None
                if page is None:
                    break
                pages.append(page)
                next_url = page.get("properties", {}).get("nextLink")

            return self._combine_query_pages(pages)

        return await self._cache.get_or_set("cost-query", cache_key, loader)

    async def list_benefit_recommendations(
        self,
        *,
        look_back_period: str,
        term: str,
        recommendation_scope: str,
        expand_usage: bool,
        scope: str | None = None,
    ) -> list[dict[str, Any]]:
        """取得 Savings Plan 建議。"""
        resolved_scope = self.require_scope(scope)
        cache_key = {
            "scope": resolved_scope,
            "look_back_period": look_back_period,
            "term": term,
            "recommendation_scope": recommendation_scope,
            "expand_usage": expand_usage,
            "api_version": self._settings.azure_cost_management_api_version,
        }

        async def loader() -> list[dict[str, Any]]:
            params: dict[str, str] = {
                "api-version": self._settings.azure_cost_management_api_version,
                "$filter": self._build_filter(
                    (
                        f"properties/lookBackPeriod eq '{look_back_period}'",
                        f"properties/term eq '{term}'",
                        f"properties/scope eq '{recommendation_scope}'",
                    )
                ),
            }
            if expand_usage:
                params["$expand"] = "properties/usage,properties/allRecommendationDetails"

            url = (
                f"{resolved_scope}/providers/Microsoft.CostManagement/"
                "benefitRecommendations"
            )
            return await self._collect_paged_values(url, params=params)

        return await self._cache.get_or_set("benefit-recommendations", cache_key, loader)

    async def list_reservation_recommendations(
        self,
        *,
        look_back_period: str,
        recommendation_scope: str,
        resource_type: str,
        scope: str | None = None,
    ) -> list[dict[str, Any]]:
        """取得 Reservation 建議。"""
        resolved_scope = self.require_scope(scope)
        cache_key = {
            "scope": resolved_scope,
            "look_back_period": look_back_period,
            "recommendation_scope": recommendation_scope,
            "resource_type": resource_type,
            "api_version": self._settings.azure_consumption_api_version,
        }

        async def loader() -> list[dict[str, Any]]:
            params = {
                "api-version": self._settings.azure_consumption_api_version,
                "$filter": self._build_filter(
                    (
                        f"properties/lookBackPeriod eq '{look_back_period}'",
                        f"properties/scope eq '{recommendation_scope}'",
                        f"properties/resourceType eq '{resource_type}'",
                    )
                ),
            }
            url = (
                f"{resolved_scope}/providers/Microsoft.Consumption/"
                "reservationRecommendations"
            )
            return await self._collect_paged_values(url, params=params)

        return await self._cache.get_or_set("reservation-recommendations", cache_key, loader)

    async def _collect_paged_values(
        self,
        url: str,
        *,
        params: dict[str, str],
    ) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        next_url: str | None = url
        next_params: dict[str, str] | None = params

        while next_url:
            page = await self._request("GET", next_url, params=next_params)
            next_params = None
            if page is None:
                break
            values.extend(page.get("value", []))
            next_url = page.get("nextLink")

        return values

    @staticmethod
    def rows_to_records(result: dict[str, Any]) -> list[dict[str, Any]]:
        """將 QueryResult 轉成易處理的 row dict list。"""
        properties = result.get("properties", {})
        columns = [column.get("name") for column in properties.get("columns", [])]
        records: list[dict[str, Any]] = []
        for row in properties.get("rows", []):
            records.append(dict(zip(columns, row, strict=False)))
        return records

    @staticmethod
    def _combine_query_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
        if not pages:
            return {"properties": {"columns": [], "rows": []}}

        first = pages[0]
        combined_rows: list[list[Any]] = []
        for page in pages:
            combined_rows.extend(page.get("properties", {}).get("rows", []))

        first_properties = dict(first.get("properties", {}))
        first_properties["rows"] = combined_rows
        first_properties["nextLink"] = None

        combined = dict(first)
        combined["properties"] = first_properties
        return combined

    @staticmethod
    def _build_filter(expressions: tuple[str, ...]) -> str:
        return " AND ".join(expression for expression in expressions if expression)
