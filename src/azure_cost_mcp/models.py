"""Azure Cost MCP 共用資料模型。"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ResponseFormat(str, Enum):
    """工具回應格式。"""

    MARKDOWN = "markdown"
    JSON = "json"


class ResponseOptions(BaseModel):
    """共用回應格式輸入。"""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="回應格式，可選 markdown 或 json。",
    )


class ConnectionValidationParams(ResponseOptions):
    """連線驗證工具輸入。"""

    subscriptions: list[str] | None = Field(
        default=None,
        description="Resource Graph 驗證時使用的 subscription IDs；若省略則由設定推導。",
    )


class DateRangeOptions(BaseModel):
    """共用日期區間輸入。"""

    start_date: date | None = Field(
        default=None,
        description="自訂查詢起始日期，格式為 YYYY-MM-DD。",
    )
    end_date: date | None = Field(
        default=None,
        description="自訂查詢結束日期，格式為 YYYY-MM-DD。",
    )
    lookback_days: int = Field(
        default=30,
        ge=1,
        le=366,
        description="未指定 start_date / end_date 時，向前回看的天數。",
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "DateRangeOptions":
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("start_date 與 end_date 必須同時提供，或同時省略。")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date 不可晚於 end_date。")
        return self

    def resolved_window(self) -> tuple[date, date]:
        """解析實際使用的日期區間。"""
        if self.start_date and self.end_date:
            return self.start_date, self.end_date
        end_date = date.today()
        start_date = end_date - timedelta(days=self.lookback_days - 1)
        return start_date, end_date


class RequiredTagsOptions(BaseModel):
    """共用 tag 檢查輸入。"""

    required_tag_keys: list[str] = Field(
        default_factory=lambda: ["Department"],
        description="必須存在的 tag keys。",
    )

    @field_validator("required_tag_keys")
    @classmethod
    def validate_required_tag_keys(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value and value.strip()]
        if not normalized:
            raise ValueError("required_tag_keys 至少需要一個非空字串。")
        return list(dict.fromkeys(normalized))


class TrendGranularity(str, Enum):
    """費用趨勢粒度。"""

    DAILY = "Daily"
    MONTHLY = "Monthly"


class DatabricksQuerySource(str, Enum):
    """Databricks 查詢來源。"""

    AMORTIZED = "amortized"
    ACTUAL = "actual"


class RecommendationLookBackPeriod(str, Enum):
    """Recommendation look-back period。"""

    LAST_7_DAYS = "Last7Days"
    LAST_30_DAYS = "Last30Days"
    LAST_60_DAYS = "Last60Days"


class RecommendationScope(str, Enum):
    """Recommendation scope。"""

    SHARED = "Shared"
    SINGLE = "Single"


class RecommendationTerm(str, Enum):
    """Benefit term。"""

    ONE_YEAR = "P1Y"
    THREE_YEARS = "P3Y"


class ReservationResourceType(str, Enum):
    """Reservation recommendation resource type。"""

    VIRTUAL_MACHINES = "VirtualMachines"
    SQL_DATABASES = "SQLDatabases"
    POSTGRESQL = "PostgreSQL"
    MANAGED_DISK = "ManagedDisk"
    MYSQL = "MySQL"
    REDIS_CACHE = "RedisCache"
    COSMOS_DB = "CosmosDB"
    APP_SERVICE = "AppService"
    BLOCK_BLOB = "BlockBlob"
    AZURE_DATA_EXPLORER = "AzureDataExplorer"


class DepartmentCostParams(ResponseOptions, DateRangeOptions):
    """部門費用查詢輸入。"""

    department_name: str | None = Field(
        default=None,
        description="部門名稱；若省略則列出指定區間內的各部門成本排名。",
    )
    department_tag_key: str | None = Field(
        default=None,
        description="查詢部門費用使用的 tag key；若省略則使用系統設定。",
    )
    top: int = Field(
        default=10,
        ge=1,
        le=50,
        description="回傳的部門或服務筆數上限。",
    )


class CostTrendParams(ResponseOptions, DateRangeOptions):
    """費用趨勢查詢輸入。"""

    granularity: TrendGranularity = Field(
        default=TrendGranularity.DAILY,
        description="趨勢粒度。",
    )
    service_name: str | None = Field(
        default=None,
        description="限定單一 Azure ServiceName。",
    )
    department_name: str | None = Field(
        default=None,
        description="限定單一部門名稱。",
    )
    department_tag_key: str | None = Field(
        default=None,
        description="部門 tag key；若省略則使用系統設定。",
    )


class SavingsRecommendationParams(ResponseOptions, DateRangeOptions):
    """節費建議查詢輸入。"""

    department_name: str | None = Field(
        default=None,
        description="限定單一部門名稱。",
    )
    department_tag_key: str | None = Field(
        default=None,
        description="部門 tag key；若省略則使用系統設定。",
    )
    include_savings_plan: bool = Field(
        default=True,
        description="是否查詢 Savings Plan 建議。",
    )
    include_reservation: bool = Field(
        default=True,
        description="是否查詢 Reservation 建議。",
    )
    look_back_period: RecommendationLookBackPeriod = Field(
        default=RecommendationLookBackPeriod.LAST_30_DAYS,
        description="Savings / Reservation recommendation look-back period。",
    )
    savings_plan_term: RecommendationTerm = Field(
        default=RecommendationTerm.ONE_YEAR,
        description="Savings Plan 建議的承諾期間。",
    )
    savings_plan_scope: RecommendationScope = Field(
        default=RecommendationScope.SHARED,
        description="Savings Plan 建議的 scope。",
    )
    reservation_scope: RecommendationScope = Field(
        default=RecommendationScope.SHARED,
        description="Reservation 建議的 scope。",
    )
    reservation_resource_type: ReservationResourceType = Field(
        default=ReservationResourceType.VIRTUAL_MACHINES,
        description="Reservation 建議的資源類型。",
    )
    expand_savings_plan_usage: bool = Field(
        default=False,
        description="是否展開 Savings Plan usage 明細。",
    )
    top: int = Field(
        default=5,
        ge=1,
        le=20,
        description="回傳服務或 recommendation 筆數上限。",
    )


class UntaggedResourcesParams(ResponseOptions, RequiredTagsOptions):
    """未標記資源查詢輸入。"""

    subscriptions: list[str] | None = Field(
        default=None,
        description="限定查詢的 subscription IDs；若省略則嘗試由設定推導。",
    )
    max_results: int = Field(
        default=50,
        ge=1,
        le=200,
        description="最多回傳多少筆未標記資源。",
    )


class TagAuditParams(ResponseOptions, RequiredTagsOptions):
    """tag audit 工具輸入。"""

    subscriptions: list[str] | None = Field(
        default=None,
        description="限定查詢的 subscription IDs；若省略則嘗試由設定推導。",
    )
    resource_ids: list[str] | None = Field(
        default=None,
        description="若提供則只檢查指定資源。",
    )
    max_results: int = Field(
        default=50,
        ge=1,
        le=200,
        description="最多回傳多少筆資源。",
    )
    use_databricks: bool = Field(
        default=True,
        description="若 Databricks MCP server 已設定，是否優先透過它執行 audit。",
    )


class DatabricksQueryParams(ResponseOptions):
    """Databricks MCP 查詢代理輸入。"""

    query_source: DatabricksQuerySource = Field(
        default=DatabricksQuerySource.AMORTIZED,
        description="查詢來源；未指定時預設走 amortized。",
    )
    question: str | None = Field(
        default=None,
        description="要交給 Databricks MCP tool 的自然語言問題。",
    )
    sql: str | None = Field(
        default=None,
        description="要交給 Databricks MCP tool 的 SQL。",
    )
    catalog: str | None = Field(
        default=None,
        description="可選的 Databricks catalog。",
    )
    schema_name: str | None = Field(
        default=None,
        description="可選的 Databricks schema。",
    )
    arguments: dict[str, Any] | None = Field(
        default=None,
        description="其他要原樣透傳給 Databricks MCP tool 的參數。",
    )

    @model_validator(mode="after")
    def validate_query_payload(self) -> "DatabricksQueryParams":
        if not any((self.question, self.sql, self.arguments)):
            raise ValueError("至少提供 question、sql 或 arguments 其中之一。")
        return self


class TagInventoryParams(ResponseOptions):
    """Tag 盤點工具輸入。"""

    subscription_ids: list[str] | None = Field(
        default=None,
        description=(
            "要盤點的 subscription IDs；省略時優先使用 M365_COST_MANAGEMENT_SCOPE，"
            "再退回 AZURE_COST_MANAGEMENT_SCOPE。"
        ),
    )
    resource_types: list[str] | None = Field(
        default=None,
        description="限定資源類型（例如 Microsoft.Compute/virtualMachines）；省略則查全部。",
    )
    resource_groups: list[str] | None = Field(
        default=None,
        description="限定 resource group 名稱；省略則查全部。",
    )
    required_tag_keys: list[str] | None = Field(
        default=None,
        description=(
            "覆蓋 tag 覆蓋率計算使用的必要 tag keys；省略時使用系統設定 AZURE_COST_REQUIRED_TAG_KEYS。"
        ),
    )
    force_refresh: bool = Field(
        default=False,
        description="強制重新查詢，忽略當日快取。",
    )
    max_results: int = Field(
        default=5000,
        ge=1,
        le=20000,
        description="最多回傳多少筆資源；預設 5000。",
    )


class TagDiffParams(ResponseOptions):
    """Tag diff 工具輸入。"""

    desired_dir: str | None = Field(
        default=None,
        description=(
            "desired tags JSON 目錄路徑；省略時使用 AZURE_COST_TAG_INVENTORY_CACHE_DIR/desired。"
        ),
    )
    rg_filter: list[str] | None = Field(
        default=None,
        description="只比對指定 resource group 名稱（大小寫不敏感）；省略則比對全部。",
    )
    subscription_filter: list[str] | None = Field(
        default=None,
        description="只比對指定 subscription IDs；省略則比對全部。",
    )


class TagApplyParams(ResponseOptions):
    """Tag apply 工具輸入。"""

    desired_dir: str | None = Field(
        default=None,
        description=(
            "desired tags JSON 目錄路徑；省略時使用 AZURE_COST_TAG_INVENTORY_CACHE_DIR/desired。"
        ),
    )
    rg_filter: list[str] | None = Field(
        default=None,
        description="只套用指定 resource group；省略則套用全部。",
    )
    subscription_filter: list[str] | None = Field(
        default=None,
        description="只套用指定 subscription IDs；省略則套用全部。",
    )
    apply: bool = Field(
        default=False,
        description=(
            "設為 True 且 AZURE_COST_TAG_APPLY_ENABLED=true 時才實際執行；"
            "否則僅回傳 dry-run 清單。"
        ),
    )
    rationale: str | None = Field(
        default=None,
        description="本次套用原因，寫入 audit log。",
    )


class TagSuggestParams(ResponseOptions):
    """Tag 相似性建議工具輸入。"""

    resource_type: str | None = Field(
        default=None,
        description="限定資源類型（例如 Microsoft.Compute/virtualMachines）；省略則不限類型。",
    )
    resource_group: str | None = Field(
        default=None,
        description="限定 resource group 名稱；省略則查全部。",
    )
    required_tag_keys: list[str] | None = Field(
        default=None,
        description="覆蓋必要 tag keys；省略時使用系統設定 AZURE_COST_REQUIRED_TAG_KEYS。",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="最多回傳幾筆相似已標記資源。",
    )
    query_text: str | None = Field(
        default=None,
        description=(
            "要搜尋的自由文字（例如資源名稱、用途描述）。"
            "有設定 DATABRICKS_EMBEDDING_URL 時使用 pgvector 向量搜尋；否則退回 SQL 篩選。"
        ),
    )


class TagEmbedParams(ResponseOptions):
    """Tag embedding 生成工具輸入。"""

    snapshot_date: str = Field(
        description="要處理的快照日期（YYYY-MM-DD），需已存在於 tag_snapshots 表中。",
    )
    resource_group: str | None = Field(
        default=None,
        description="限定 resource group；省略則處理該日期所有 RG。",
    )
    subscription_id: str | None = Field(
        default=None,
        description="限定訂閱 ID；省略則不限。",
    )
    batch_size: int = Field(
        default=50,
        ge=1,
        le=200,
        description="每次送給 embedding API 的文字數量。",
    )


class TagRemediationParams(ResponseOptions, RequiredTagsOptions):
    """tag remediation 工具輸入。"""

    resource_ids: list[str] | None = Field(
        default=None,
        description="要修正的資源 IDs；若省略則交由遠端 Databricks MCP tool 自行決定。 ",
    )
    proposed_tags: dict[str, str] | None = Field(
        default=None,
        description="希望套用或建議修正的 tags。",
    )
    apply: bool = Field(
        default=False,
        description="是否直接執行套用；預設為 dry-run / recommendation mode。",
    )
    rationale: str | None = Field(
        default=None,
        description="本次修正原因，便於稽核。",
    )


class LearnSearchParams(ResponseOptions):
    """Microsoft Learn 文件搜尋工具輸入。"""

    query: str = Field(
        description="搜尋關鍵字，例如 'Azure Cost Management reservation' 或 'Databricks 費用優化'。",
    )
    top: int = Field(
        default=5,
        ge=1,
        le=20,
        description="回傳結果筆數上限（1–20），預設 5。",
    )
    locale: str = Field(
        default="zh-tw",
        description="語系代碼，預設 zh-tw（繁體中文）；無繁中內容時 Learn API 會自動退回英文。",
    )
    category_filter: str | None = Field(
        default=None,
        description=(
            "限定 Learn 資源類型：'Documentation'（技術文件）或 'Learn'（互動課程模組）；"
            "省略則同時回傳所有類型。"
        ),
    )


class StorageExportsParams(ResponseOptions):
    """Storage 匯出查詢輸入。"""

    prefix: str | None = Field(
        default=None,
        description="Blob prefix；若省略則使用系統預設 prefix。",
    )
    max_results: int = Field(
        default=20,
        ge=1,
        le=100,
        description="最多列出多少筆 blob。",
    )
