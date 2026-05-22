# Azure Cost MCP Service

> **目前狀態：已完成 `/init` 與第一版 MCP server 骨架，並接上 Azure Cost Management Query、Savings / Reservation Recommendations、Azure Resource Graph、Azure Storage 與 Databricks MCP proxy。**

這個專案要提供一個 **對外可呼叫的 MCP service**，協助 Azure FinOps 查詢、成本趨勢分析、節費方向判斷，以及 tag 治理與修正。

## 專案目標

第一版優先解決四個最高成本章節：

1. **Azure Databricks**
2. **Storage**
3. **VM**
4. **Network egress**

並先支援這五類高價值問題：

1. **部門費用查詢**
2. **費用趨勢查詢**
3. **節費方向與 Reservation / Savings Plan 建議**
4. **未標記資源與 tag 治理**
5. **透過 Databricks MCP server 查詢 Storage 上的成本資料**

## 規劃基準

本專案持續以兩條主線規劃：

1. **FinOps Foundation**：Inform → Optimize → Operate、showback / chargeback、tagging、benefit optimization。
2. **Azure 原生實踐**：Azure Cost Management REST API、Exports / FOCUS、Azure Resource Graph、Azure Policy、Azure Advisor、Reservations、Savings Plan、Azure Hybrid Benefit。

## 目前架構

### 系統資料流

```text
Azure Cost Management REST API / Exports / FOCUS
                ↓
          Azure Storage
                ↓
       Databricks MCP server
                ↓
    Azure Cost MCP service (Python / FastMCP)
```

### 服務啟動流程

1. `src\azure_cost_mcp\__main__.py` 解析 CLI 參數，支援 `stdio` 與 `streamable-http` 兩種 transport。
2. CLI 先用 `get_settings()` 載入環境設定，再用 `model_copy(update=...)` 套用命令列覆寫值。
3. `src\azure_cost_mcp\server.py` 的 `create_mcp_server()` 建立 `FastMCP` 實例，並初始化各個資料來源 client。
4. `server.py` 註冊所有 `azure_cost_*` tools，將輸入驗證、資料查詢、結果整理與回應格式串起來。
5. tool 執行後，統一透過 `src\azure_cost_mcp\formatting.py` 轉成 Markdown 或 JSON 回應。

### 程式模組分工

| 模組 | 角色 | 主要責任 |
| --- | --- | --- |
| `src\azure_cost_mcp\__main__.py` | CLI 入口 | 解析 `transport / host / port / path`，建立並啟動 MCP server |
| `src\azure_cost_mcp\server.py` | 組裝與工具註冊層 | 建立 `FastMCP`、初始化 client、註冊 `azure_cost_*` tools、組合查詢結果 |
| `src\azure_cost_mcp\config.py` | 設定層 | 定義 `Settings`、集中管理環境變數、處理驗證與預設值 |
| `src\azure_cost_mcp\azure_management.py` | Azure 管理平面共用基底 | 使用專案的 auth mode 設定建立 credential，透過 `httpx.AsyncClient` 呼叫 Azure 管理平面 API，並統一錯誤格式 |
| `src\azure_cost_mcp\cost_management.py` | 成本查詢層 | 封裝 Cost Management Query API、Benefit Recommendations API、Reservation Recommendations API，並處理 pagination 與 `rows -> records` 正規化 |
| `src\azure_cost_mcp\resource_graph.py` | 治理查詢層 | 封裝 Azure Resource Graph 查詢，用來找出缺少 tags 的資源，必要時由 `AZURE_COST_MANAGEMENT_SCOPE` 推導預設 subscription |
| `src\azure_cost_mcp\storage.py` | 匯出資料存取層 | 連線 Azure Blob Storage，列出成本匯出檔案與基本中繼資料 |
| `src\azure_cost_mcp\databricks_mcp.py` | Databricks 代理層 | 透過遠端 MCP server 呼叫 `ActualCost` / `AmortizedCost` 等 Databricks Genie 查詢 tools，並先驗證遠端 tool 是否存在 |
| `src\azure_cost_mcp\models.py` | 輸入模型層 | 定義各個 tools 的 Pydantic 參數模型，統一日期區間、tag 要求與回應格式輸入 |
| `src\azure_cost_mcp\formatting.py` | 輸出格式層 | 將結構化 payload 統一輸出成 Markdown 或 JSON |

### Tool 請求處理方式

目前所有 tools 都採用「**單一 Pydantic `params` 模型**」的輸入方式，流程如下：

1. MCP client 傳入 `params`
2. `models.py` 先做欄位驗證與預設值補齊
3. `server.py` 決定要呼叫哪個資料來源 client
4. client 回傳結構化資料
5. `formatting.py` 統一輸出結果

這讓每個 tool 都維持一致的輸入 shape、錯誤處理方式與回應格式。

### 第一版資料來源

| 來源 | 用途 |
| --- | --- |
| Azure Cost Management Query API | 部門成本、趨勢、主要成本服務 |
| Benefit Recommendations API | Savings Plan 建議 |
| Reservation Recommendations API | VM / DB / Storage / App Service 等 Reservation 建議 |
| Azure Resource Graph | 找出缺少 tags 的資源 |
| Azure Blob Storage | 成本匯出落地層與資料檢查 |
| Databricks Genie MCP server | `ActualCost` / `AmortizedCost` 等 NL-to-SQL 查詢入口 |

## 已實作 MCP tools

| Tool | 說明 |
| --- | --- |
| `azure_cost_get_bootstrap_status` | 回報目前服務與整合設定狀態 |
| `azure_cost_validate_connections` | 依序驗證 Cost Management、Resource Graph、Storage、Databricks MCP 連線狀態 |
| `azure_cost_get_planned_capabilities` | 回報已實作能力與後續研究焦點 |
| `azure_cost_department_cost` | 查詢指定部門成本，或列出部門成本排名 |
| `azure_cost_cost_trend` | 查詢日 / 月成本趨勢 |
| `azure_cost_cost_saving_opportunities` | 整合主要成本服務、Savings Plan 與 Reservation 建議 |
| `azure_cost_databricks_query` | 將自然語言問題或指定 SQL 代理到 `ActualCost` / `AmortizedCost` 對應的 Databricks Genie query tool，未指定來源時預設走 `AmortizedCost` |
| `azure_cost_untagged_resources` | 用 Azure Resource Graph 找出缺少必要 tags 的資源 |
| `azure_cost_list_storage_exports` | 列出 Azure Storage 中的成本匯出檔案 |

## Tag 治理策略

目前 repo 只提供 **未標記資源偵測**，尚未把 tag audit / remediation 當成正式對外能力。

若後續要規劃 tag 治理，建議原則仍然是：

1. **預設 dry-run / recommendation mode**
2. **明確指定 apply mode**
3. **治理能力與 `ActualCost` / `AmortizedCost` 查詢 backend 分開設計**

## Databricks MCP proxy 約定

若要啟用 Databricks MCP proxy，請提供：

| 變數 | 用途 |
| --- | --- |
| `DATABRICKS_MCP_AMORTIZED_SERVER_URL` | `AmortizedCost` 對應的 Databricks Genie MCP endpoint |
| `DATABRICKS_MCP_AMORTIZED_QUERY_TOOL_NAME` | `AmortizedCost` 對應的 query tool name |
| `DATABRICKS_MCP_ACTUAL_SERVER_URL` | `ActualCost` 對應的 Databricks Genie MCP endpoint |
| `DATABRICKS_MCP_ACTUAL_QUERY_TOOL_NAME` | `ActualCost` 對應的 query tool name |
| `DATABRICKS_MCP_BEARER_TOKEN` | 遠端 MCP Bearer token（若需要） |
| `DATABRICKS_MCP_SERVER_URL` | legacy fallback endpoint；未設定 source-specific URL 時才回退使用 |
| `DATABRICKS_MCP_QUERY_TOOL_NAME` | legacy fallback query tool；未設定 source-specific tool name 時才回退使用 |

目前 proxy 會先列出遠端 tools，再確認設定的 tool name 是否存在，避免直接把請求送到不存在的 remote tool。現在這層整合應優先視為 **建在 Databricks Genie 上的 NL-to-SQL 應用**，也就是 `ActualCost` / `AmortizedCost` 這兩個查詢入口；tool name 應以實際 Genie space 暴露的查詢工具為準。

`azure_cost_databricks_query` 的 routing 規則如下：

1. **未指定 `query_source` 時，預設走 `amortized`**
2. **只有明確指定 `query_source=actual` 時，才切去 `ActualCost`**
3. **Azure 平台 VM / Storage 的 `ActualCost` 主要保留給 gate / reconciliation 驗證，不是一般月度費用查詢的預設口徑**

若公司網路有 proxy，請把 **實際 Databricks workspace host** 加進 `NO_PROXY` / `no_proxy`。實測像 `adb-*.azuredatabricks.net` 這種 wildcard 不一定會被底層 HTTP client 正確辨識，建議直接填完整 host，例如 `adb-6748704777045471.11.azuredatabricks.net`。

## 本機驗證與部署驗證模式

建議先分兩階段：

1. **本機驗證**：`AZURE_COST_AUTH_MODE=azure-cli`，先用 `az login` 驗證所有功能與連線
2. **部署到 Azure Container Apps**：再切成 `service-principal`，用正式權限與憑證運行

目前支援四種模式：

| 模式 | 設定值 | 說明 |
| --- | --- | --- |
| Azure CLI | `azure-cli` | 本機開發預設，直接使用 `az login` |
| Service Principal | `service-principal` | 讀取 `.env` 內的 `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` |
| Managed Identity | `managed-identity` | 給 ACA / App Service 等 Azure 執行環境 |
| DefaultAzureCredential | `default` | 保留相容模式，讓 Azure SDK 自己決定 credential chain |

> **multi-tenant 注意事項**  
> 目前環境是 **兩個 tenant**，而且 **home tenant 在 tenant 2**。不要假設所有 subscription 都屬於同一個 tenant。  
> 本機 `az login`、後續 Service Principal 規劃、以及 subscription 查詢流程，都必須支援 **subscription-to-tenant mapping**。依目前已知條件，後續很可能要提供 **2 組認證** 來覆蓋兩個 tenant，而不是只靠單一 `AZURE_TENANT_ID`。

## 建議申請的 Service Principal 權限

如果後面要把服務放進 Azure Container Apps，且改成 **Service Principal**，建議先申請：

1. **Cost Management Reader**：針對 `AZURE_COST_MANAGEMENT_SCOPE`
2. **Reader**：針對要查詢的 subscription / resource group，供 ARM 與 Resource Graph 使用
3. **Storage Blob Data Reader**：針對成本匯出所在的 Storage container
4. **Databricks Workspace 存取權**：讓 Service Principal 可以進 workspace
5. **Databricks Genie query tool 權限**：對 `DATABRICKS_MCP_QUERY_TOOL_NAME` 對應的 `ActualCost` / `AmortizedCost` 查詢功能有執行權限
6. **資料平面讀取權限**：若 query tool 會讀 Unity Catalog / schema / table，需額外補相對應的 SELECT / USE 權限
7. **tenant 對應權限**：若目標 subscription 分散在不同 tenant，需逐一確認每個 tenant 都有對應權限與同意流程；若採 Service Principal，也要預留多組 credential 的可能性

## 成本資料快取策略

為了避免每次查詢都重新打 Azure Cost Management REST API，服務現在支援成本資料快取。

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `AZURE_COST_CACHE_MODE` | `disk` | `disabled` / `memory` / `disk` |
| `AZURE_COST_CACHE_DIR` | `.cache\\azure-cost-mcp` | disk cache 存放目錄 |
| `AZURE_COST_CACHE_TTL_SECONDS` | `900` | cache TTL，單位秒 |

目前快取套用在：

1. Cost Management usage query
2. Benefit recommendations
3. Reservation recommendations

本機驗證時建議先保留 `disk`，這樣同樣的查詢可以直接讀本地快取；之後若部署進容器，再依使用情境改成 `memory` 或維持 `disk`。

## Cost Analysis view retrieval 與欄位模型

目前較穩定的做法，不是把 raw saved view name 直接當 API 契約，也不是把抓回來的成本資料寫在 Markdown。建議拆成三層：

| 層 | 角色 | 建議承載內容 |
| --- | --- | --- |
| Markdown / catalog | 定義層 | `logical_view_key`、`saved_view_name`、服務對應、owner、cost basis 規則 |
| memory / disk cache | 加速層 | 短 TTL 的 Cost Management REST API 回應 |
| table store | 資料層 | 依日期區間拉回來並正規化後的成本 facts |

其中 **Databricks reservation-backed** 的 view，應預設視為 **`AmortizedCost`** 口徑；不要把 `ActualCost` 當主要對帳基準。

### Query API 可穩定收集的常用欄位

以下欄位已用實際 Query API 驗證，適合拿來做費用歸屬：

| 類型 | 常用欄位 | 說明 |
| --- | --- | --- |
| 金額 / 指標 | `Cost`、`PreTaxCost`、`UsageQuantity` | `Cost` 最常用；若 saved view 或 aggregation 有定義，也可能出現 `CostUSD` |
| 日期 | `BillingMonth`、`UsageDate` | `Monthly` granularity 會回 `BillingMonth`；`Daily` granularity 會回 `UsageDate` |
| 歸屬維度 | `ResourceGroupName`、`ServiceName`、`SubscriptionId`、`SubscriptionName`、`ResourceLocation` | 適合做 subscription / RG / service 層級歸戶 |
| 計費維度 | `Meter`、`MeterCategory`、`MeterSubCategory`、`ServiceTier` | 若要做更細的 service / SKU 拆分，優先用這組 |
| Benefit / 定價模式 | `PricingModel`、`BenefitName`、`ChargeType` | 用來辨識 OnDemand / Reservation / SavingsPlan 等口徑 |
| 標籤 | `TagKey`、`TagValue` | 以 `TagKey` grouping 時，回傳的是這兩欄，不會直接回 `Purpose` 或 `cost_center` 欄名 |

### 實測到的回應 shape

| 查詢模式 | 回傳欄位 |
| --- | --- |
| `ResourceGroupName + ServiceName` | `Cost`, `ResourceGroupName`, `ServiceName`, `Currency` |
| `TagKey: purpose` | `Cost`, `TagKey`, `TagValue`, `Currency` |
| `TagKey: cost_center + ServiceName` | `Cost`, `TagKey`, `TagValue`, `ServiceName`, `Currency` |
| `MeterCategory + MeterSubCategory` | `Cost`, `MeterCategory`, `MeterSubCategory`, `Currency` |
| `Monthly` trend | `Cost`, `BillingMonth`, `Currency` |
| `PricingModel + BenefitName` | `Cost`, `PricingModel`, `BenefitName`, `Currency` |

### 直接讀 view 與 replay view 的差別

這裡要分成兩種呼叫：

1. **讀取 saved view definition**  
   呼叫 `.../providers/Microsoft.CostManagement/views/{viewName}` 時，拿到的是 **view metadata**，例如：
   - `displayName`
   - `query.type`
   - `query.dataSet.granularity`
   - `query.dataSet.grouping`
   - `query.dataSet.filter`
   - `dateRange`
   - `currency`
   - `chart`
   - `kpis`
   - `pivots`

2. **用 view definition replay 成 Query API**  
   這時拿到的才是 **成本 rows**。欄位不會自動比一般 Query API 更多；它只會回 **該 view 目前定義裡會產生的欄位**。

因此：

- 如果某個 view 只 group `ServiceName`，那 replay 出來通常就是 `Cost`, `ServiceName`, `Currency`
- 如果某個 view group `TagKey: purpose`，那 replay 出來會是 `Cost`, `TagKey`, `TagValue`, `Currency`
- 如果某個 view 有 `Monthly` granularity，才會看到 `BillingMonth`
- 如果 view 沒有把 `ResourceGroupName`、`Meter*`、`PricingModel`、`BenefitName` 放進 grouping / aggregation，就不會出現在 rows 裡

換句話說，**view 方式不是「欄位更多」；而是「欄位比較固定，跟著 view 定義走」**。如果你要抓比較完整的歸屬欄位，通常還是要自己組 Query API，或落到 export / fact table 後再 join。

### 使用這些欄位時要注意

1. **最多只能 group 2 個欄位**，所以 `ResourceGroup + Service + Purpose` 不能一次在同一個 query 完成，必須拆查或正規化後再 join。
2. **`ResourceGroupName` 可能為空字串**，例如部分 shared charge 或 platform charge。這類成本不能只靠 RG 歸屬，需回退到 `ServiceName`、tag、`PricingModel`、`BenefitName`。
3. Cost Analysis 介面中的 **metric** 多半是 query definition 的口徑（例如 `ActualCost` / `AmortizedCost`），不是每列都會回一個 `metric_name` 欄位。若要做服務細分，應優先使用 `ServiceName` + `Meter*` 欄位。
4. 若要靠 tag 歸戶，建議在正規化後轉成固定欄位，例如 `purpose`、`cost_center`，不要把 `TagKey` / `TagValue` 直接當最終報表模型。
5. **多支 aggregated query 只能在報表層或對帳層接起來，不能當成 lossless 明細表直接 join。** 若不同 query 的 grain 不一致，最多只能做 side-by-side 分析；若要一張可再切維度的 fact table，必須改用欄位數夠的單次查詢，或直接改走 exports / FOCUS。

### 建議的 normalized fact 欄位

若後續要把日期區間拉回來後存進 Databricks / Delta table，建議至少保留：

- `logical_view_key`
- `saved_view_name`
- `project_code`
- `project_name`
- `tenant_id`
- `subscription_id`
- `subscription_name`
- `query_scope`
- `cost_basis`
- `billing_month`
- `usage_date`
- `resource_group_name`
- `service_name`
- `meter`
- `meter_category`
- `meter_subcategory`
- `resource_location`
- `pricing_model`
- `benefit_name`
- `purpose`
- `cost_center`
- `cost`
- `currency`

### 429 與資料來源分流建議

Azure Cost Management Query API 的 **per-scope limit 是 4 requests/minute**。如果把每個 view、每個月份、每種歸屬欄位都拆成獨立 request，很快就會 hit 429。

建議做法：

1. **不要一個月打一個 request。** 能用單次 `Custom` + `Monthly` 拉回整段月份時，就一次抓整段。
2. **同一個 scope 要有自己的 queue / rate limiter。** 穩定做法是把 steady-state 控在 **每 20 秒 1 個 request**，不要平行轟同一個 subscription / billing scope。
3. **跨 scope / 跨 tenant 再平行。** 真正適合做 concurrency 的單位是 scope，不是同 scope 內的多個 query。
4. **遇到 429 時，只暫停那個 scope 的 queue。** 讀取所有 `x-ms-ratelimit-microsoft.costmanagement-*-retry-after` header，取最長值再恢復，不要全域停擺。
5. **把 `nextLink` 分頁也視為同一條 queue 的後續 request。** 分頁不能繞過 scope limit。

資料來源建議分工如下：

| 使用情境 | 建議來源 |
| --- | --- |
| 單一 view 驗證、Portal 對帳、目前月份快速查詢 | Cost Management Query API |
| 少量 view 的月趨勢 replay | Cost Management Query API |
| 每月 2 號對帳、且以 **D-2** 為準的正式對帳資料 | `system_catalog`（或 `rag_analyst_catalog`）`.system_report.daily_azure_cost_usage_*` |
| 多個月、又要同時看 `resource_group` / `service_name` / `purpose` / `cost_center` | Databricks 明細表 / 彙總表 |
| 月結後的正式報表、variance、forecast 基礎資料 | 已落地的 Databricks / Delta fact table |

換句話說：

- **REST API**：適合互動式查詢、saved view replay、current month / last month 對帳
- **Databricks system_report tables**：適合 D-2 對帳、長區間明細、複合歸屬分析（`rag_analyst_catalog`）
- **Cache**：只解決重複查同一個 request，不解決大批量 ingestion

如果要做穩定 ingestion，建議流程是：

1. 先用 REST API 驗證 view 定義與月總額
2. 以 `system_catalog.system_report.daily_azure_cost_usage_actual` / `_amortized` 當明細來源（Genie 有時改用 `rag_analyst_catalog`，以實際 SQL 為準）
3. 以 `system_catalog.system_report.daily_azure_cost_usage_actual_agg` / `_amortized_agg` 當快速對帳或彙總來源
4. 由 Databricks 正規化成 `cost_fact`
5. 只有 current month 或 view replay 才回頭打 REST API

### Databricks system_report tables 的建議角色

目前若要做每月 2 號對帳，且已知 **D-2 以上的費用才準確**，比較推薦直接把下列表當成主來源：

> **Catalog 說明：** Azure 平台資料存在兩個 catalog：`system_catalog`（整體平台）與 `rag_analyst_catalog`（特定專案 / 分析用）。  
> Genie NL 查詢時會自動選擇，**以 Genie 實際生成的 SQL 為準**；直接 SQL 查詢時視需求選用。

| Table | 建議用途 |
| --- | --- |
| `system_catalog.system_report.daily_azure_cost_usage_actual` | Actual 明細（整體平台）|
| `system_catalog.system_report.daily_azure_cost_usage_amortized` | Amortized 明細（整體平台）|
| `rag_analyst_catalog.system_report.daily_azure_cost_usage_actual` | Actual 明細（分析 / 特定專案）|
| `rag_analyst_catalog.system_report.daily_azure_cost_usage_amortized` | Amortized 明細（分析 / 特定專案）|
| `system_catalog.system_report.daily_azure_cost_usage_actual_agg` | Actual 彙總 / 快速對帳 |
| `system_catalog.system_report.daily_azure_cost_usage_amortized_agg` | Amortized 彙總 / 快速對帳 |

建議原則：

1. **正式對帳**：優先查 Databricks tables，不靠 REST API 即時計算。
2. **Databricks 成本**：優先查 `amortized` 口徑。
3. **REST API**：保留給 saved view filter 驗證、欄位補充測試、與 current month spot check。

### 上個月份資料可用 gate

Databricks Genie 內的 **「上個月份資料可使用」**，不是看單一平台是否對齊，而是要把 **Azure 平台** 與 **M365 平台** 分開驗證後，再一起判斷。

目前建議規則：

1. **Azure 平台** 與 **M365 平台** 各自維護自己的 tenant、scope、REST baseline、`validated_through_month`、`gate_status`
2. **只有兩個平台都通過同月份驗證**，才能說 Genie 裡該月份資料可放行
3. **REST baseline 以月份為單位留存**。同一月份只要已有完整 baseline，就持續重用，不要每次重抓
4. **前月正式 gate 建議在每月 2 號 10:00（Asia/Taipei）後再判定**。這之前若有差異，常見原因是 export 落地與後續 ingestion 延遲
5. **費用日界線 / 月界線以 GMT/UTC 00:00 為準**。Asia/Taipei 的 00:00~08:00 如果直接問「今天 / 昨天 / 上個月」，很容易差一天

目前已驗證結論：

- **Azure 平台 2026-04：已通過**
- **M365 平台：尚待用同一套流程獨立驗證**

### 這次踩到的雷與注意事項

1. **Actual 與 Amortized 要分開驗**
   - Databricks 預設看 `AmortizedCost`
   - Azure 平台的 `ActualCost` 至少要驗 **VM + Storage**
2. **Relative time 容易被時區誤導**
   - `前一個月`、`上個月` 最好明確轉成 UTC 邏輯，或直接指定月份
3. **Actual 的 Reservation 要先講清楚要不要算**
   - 若 REST view 漏了 `PricingModel = 'Reservation'`，會在少數高點日期產生大額 mismatch
   - 若 Genie 要排除 Reservation，應直接寫 `PricingModel != 'Reservation'`，不要用 `MINUS` 去減每日 Reservation 總額
4. **平台 scope 要明講**
   - 像 `Virtual Machines`、`Storage` 這類 Actual 驗證，要明確說是 **Azure 平台** 或 **M365 平台**
5. **429 是常態，不是例外**
   - 同一個 scope 的 Query API 要排隊，不能平行猛打

### 分段查詢何時可行

如果只是為了：

- 驗證某個月總額
- 看 `resource_group` 的分布
- 看 `purpose` 或 `cost_center` 的歸屬比例
- 看 `PricingModel` 是否為 Reservation

那可以接受把同一組 filter 拆成多支 query，然後在 **報表層** 並排看。

但如果目標是：

- 後面還要任意切 `resource_group`、`meter`、`purpose`、`cost_center`、`pricing_model`
- 想把資料落地成可再 join / aggregate 的事實表

那就不要依賴多支 aggregated query 回來再硬接，應直接改用：

1. 欄位數夠的單次查詢（如果維度數仍在 API 限制內）
2. 或 exports / FOCUS → Storage → Databricks 的明細路徑

## 本機啟動

### 1. 安裝依賴

```powershell
uv sync
```

### 2. 建立設定

```powershell
Copy-Item .env.example .env
```

至少要先補：

1. `AZURE_COST_MANAGEMENT_SCOPE`
2. Storage / Databricks 相關設定（如果要啟用對應工具）

若要做 **M365 平台** 的 operator-run 驗證，可另外在 `.env` 記錄：

```env
M365_COST_MANAGEMENT_TENANT=<tenant-id>
M365_COST_MANAGEMENT_SCOPE=/subscriptions/<subscription-id>
M365_COST_DEPARTMENT_TAG_KEY=cost_center
```

> 目前這組 `M365_COST_MANAGEMENT_*` 主要是給人工 / agent 驗證流程使用。repo 內的 `Settings` 已可讀取這組設定，但完整的 M365 對帳流程仍未正式產品化成 MCP tool。

### 3. 以 stdio 啟動

```powershell
uv run azure-cost-mcp --transport stdio
```

### 4. 以 Streamable HTTP 啟動

```powershell
uv run azure-cost-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

### 5. Copilot CLI 開發輔助

- repo 已附上 `.mcp.json`，Copilot CLI 進入此專案時可直接載入 **Azure MCP server**、**`ActualCost`** 與 **`AmortizedCost`**。
- 這是開發時的 MCP 能力擴充，不是 `azure-cost-mcp` 應用本身對外提供的工具。
- `ActualCost` / `AmortizedCost` 底層是 **Databricks Genie 的 NL-to-SQL 應用**。
- 若要在本機 user config 覆蓋 repo 內設定，請沿用 `ActualCost` / `AmortizedCost` 命名即可。
- 不要把實際 URL / token 提交進 repo。

## Docker / ACA

專案已附上 `Dockerfile`，預設使用 `streamable-http` 暴露 `/mcp`。

### 本機建置

```powershell
docker build -t azure-cost-mcp:local .
docker run --rm -p 8000:8000 --env-file .env azure-cost-mcp:local
```

### Azure Container Apps 方向

第一個部署目標仍是 **Azure Container Apps**。目前建議：

1. 將 `.env` 中的值搬到 ACA environment variables / secrets。
2. 對外 ingress 開啟，target port 使用 `8000`。
3. transport 固定為 `streamable-http`，path 使用 `/mcp`。
4. 身分優先考慮 Managed Identity，供 Azure Cost Management、Resource Graph、Blob Storage 使用。

可先用類似下面的方式上版：

```azurecli
az containerapp up `
  --name azure-cost-mcp `
  --resource-group <resource-group> `
  --environment <aca-environment> `
  --source .
```

## 測試與程式涵蓋率

目前測試策略改成固定三層：

1. **連線驗證**：先確認 Azure Cost Management、Azure Resource Graph、Azure Storage、Databricks MCP server 是否可連
2. **功能驗證**：再驗證資料模型、格式化、彙整邏輯與 proxy fallback
3. **End-to-End 情境演練**：最後才跑完整 user flow，例如部門成本查詢、tag audit、Databricks query 代理

目前已補上以 **單元測試** 為主的測試骨架，優先覆蓋：

1. 設定驗證與 CLI 參數解析
2. 資料模型驗證與日期區間處理
3. Markdown / JSON 格式化邏輯
4. Cost Management、Resource Graph、Databricks MCP proxy、Storage client 的本地邏輯與錯誤轉換
5. `server.py` 內部的成本彙整與 tag 摘要 helper

### 安裝測試依賴

```powershell
uv sync --group test
```

### 執行測試

```powershell
uv run --group test pytest
```

### 先做連線驗證

啟動 MCP server 後，建議第一個先呼叫：

- `azure_cost_validate_connections`

這個 tool 會依序檢查：

1. Cost Management scope 與查詢 API
2. Resource Graph 查詢
3. Azure Storage blob 列舉
4. Databricks MCP tool discovery

如果某個外部端點尚未設定，結果會標成 `skipped`，避免把未配置環境誤判成功能失敗。

### 檢視 coverage

`pytest` 會自動輸出 terminal coverage summary，並產生 `coverage.xml`。

如果要看更詳細的缺口，可直接使用：

```powershell
uv run --group test pytest --cov-report=term-missing
```

## 專案設定

`.env.example` 已整理目前主要變數：

- MCP transport / host / port / path
- Azure 管理平面 API versions
- Cost Management scope 與 Department tag key
- Storage account / container / prefix
- Databricks MCP server URL / token / remote tool names
- tag 直接套用開關

## 接下來的研究與實作

目前已經從「規劃-only」進入「可執行 MCP server」階段，但還有幾塊會繼續補：

1. **ACA / ACI / Web App / App Service 成本與特性比較**
2. **APIM 選型**
3. **Lakebase / SQL Server / Cosmos DB / Azure AI Search / pgvector 比較**
4. **Storage 的 LRS / ZRS / Hot / Cool / Cold 決策規則**
5. **透過 Databricks MCP server 對 Storage 上成本資料做更完整分析**

## 相關 skill / 參考基底

目前 repo 內已補上 project-base skill：

- `.claude\azure-cost-finops\SKILL.md`

其內容承接目前這個專案的 FinOps / Azure Cost / Databricks / tag governance 規劃方向，供後續持續擴充。

---

## Tag 管理系統開發 Backlog

> **目標**：建立完整的 Azure 資源 tag 盤點 → 本地整理 → 批次回寫流程，並用 Lakebase + pgvector 記錄每個階段歷史狀態。
>
> **優先順序**：M365 訂閱（`M365_COST_MANAGEMENT_SCOPE`）資源優先；Azure 平台訂閱為第二批。
>
> **驗收策略**：每個 Epic 完成後以 **gstack**（headless browser）做功能截圖驗收；Epic 2 另加 Obsidian 最終確認（可延後，不阻塞其他 Epic）。
>
> 狀態：`[ ]` 未開始 ｜ `[x]` 完成 ｜ `[-]` 進行中

---

### Epic 1：Tag 盤點與快取（Tag Inventory）

#### PBI 1.1 — 擴充 ResourceGraphClient：全資源完整 tag 查詢

- **目標**：讓 `ResourceGraphClient` 可以拉回指定訂閱下所有資源的完整 tag 現況
- **關鍵檔案**：`src/azure_cost_mcp/resource_graph.py`
- **實作重點**：
  - 新增 `get_all_resources_with_tags(subscriptions, resource_types, resource_groups)` 方法
  - KQL：`Resources | project id, name, type, resourceGroup, subscriptionId, location, tags`
  - 支援分頁（`$skipToken`）、最多 1000 筆 / 頁
- **相依 PBI**：無
- **驗收條件**：呼叫方法後能回傳 `id, name, type, resourceGroup, subscriptionId, location, tags` 欄位；分頁能正確串接

- [x] 實作（2026-05-06：`get_all_resources_with_tags` + 分頁 + `m365_subscriptions`）

#### PBI 1.2 — 新增 `azure_cost_tag_inventory` MCP tool

- **目標**：提供一個 MCP tool，讓 agent 一鍵盤點 M365 訂閱（預設）或任意訂閱的資源 tag 現況
- **關鍵檔案**：`src/azure_cost_mcp/server.py`、`src/azure_cost_mcp/models.py`
- **實作重點**：
  - 新增 `TagInventoryParams`（`subscription_ids`, `resource_types`, `resource_groups`, `force_refresh`）
  - `subscription_ids` 預設讀 `m365_cost_management_scope`
  - 結果快取至 `.cache/tag-inventory/YYYY-MM-DD/{subscription_id}.json`（複用 `ApiCache` disk mode）
  - 輸出摘要：資源總數、有 tag / 無 tag 比例、各 RG tag 覆蓋率
- **相依 PBI**：PBI 1.1
- **驗收條件**：
  - gstack 截圖 MCP Inspector → `azure_cost_tag_inventory` → 回傳含資源數量與 tag 覆蓋率摘要
  - `.cache/tag-inventory/` 目錄有對應日期的 JSON 快取

- [x] 實作（2026-05-06：`azure_cost_tag_inventory` tool + `_build_tag_coverage_summary`）

#### PBI 1.3 — 新增 tag inventory 相關 config 設定

- **目標**：讓 tag inventory 的 cache 路徑與必要 tag keys 可以透過環境變數設定
- **關鍵檔案**：`src/azure_cost_mcp/config.py`、`.env.example`、`README.md`
- **實作重點**：
  - `AZURE_COST_TAG_INVENTORY_CACHE_DIR`（預設 `.cache/tag-inventory`）
  - `AZURE_COST_REQUIRED_TAG_KEYS`（逗號分隔，M365 預設含 `cost_center`）
- **相依 PBI**：PBI 1.2
- **驗收條件**：`.env.example` 已補充；`Settings` 可正確讀取

- [x] 實作（2026-05-06：config.py + .env.example 已補充）

---

### Epic 2：Obsidian 整合（本地可讀格式輸出）

> **Obsidian 驗收依賴說明**：gstack 可先做 HTML 預覽初驗；Obsidian 最終驗收可延後，不阻塞其他 Epic。

#### PBI 2.1 — gen_tag_inventory_md.py：每個 RG 產出一份 md

- **目標**：把 JSON 快取轉成 Obsidian-compatible YAML frontmatter Markdown，每個 RG 一份
- **關鍵檔案**：`scripts/gen_tag_inventory_md.py`
- **實作重點**：
  - 輸入：`.cache/tag-inventory/YYYY-MM-DD/{subscription_id}.json`
  - 輸出：`.cache/tag-inventory/obsidian/{subscription}/{rg}.md`
  - YAML frontmatter：`rg, subscription, subscription_name, tenant_id, charge_model, snapshot_date, total_resources, tagged, untagged, cost_status, cost_period, required_tags`
  - RG 頁結構：
    - 頁首固定有 vault 回鏈
    - 先顯示 `Tenant / Subscription / RG` 所屬脈絡
    - 帳務歸屬（`單一 CostCenter 掛帳` / `Cross CostCenter 拆帳` / `待確認`）
    - 成本摘要（已對應 project 成本；沒有 mapping 時顯示「整理中」）
    - Tag 關聯（連到 CostCenter / Purpose / owner / EnvType graph notes）
    - 兩個資源表格：`一致`、`需檢查或確認`
- **相依 PBI**：PBI 1.2
- **驗收條件**：
  - gstack 初驗：`python -m http.server` + headless browser 開啟，截圖確認 frontmatter 表格與缺漏標記正確
  - Obsidian 最終驗收（可延後）：vault 開啟確認 frontmatter 顯示正確

- [x] 實作（2026-05-06）

#### PBI 2.2 — 總索引與 tag gap 分析

- **目標**：產出跨 RG 的總覽，並讓使用者從單一入口展開 `RG ↔ project 成本關係`
- **關鍵檔案**：`scripts/gen_tag_inventory_md.py`（同 PBI 2.1 腳本）
- **實作重點**：
  - root `_index.md`：Obsidian vault 的唯一主入口
  - 主軸先按 **Tenant → Subscription → RG** 展開，再進入成本與治理視角
  - `_index.md` 內至少有三個入口：
    - `已對應`：已找到 `RG ↔ project 成本` 關係的 RG
    - `需檢查或確認`：尚未整理完成的 RG
    - `tag-gap-summary.md`、`tag-graph/index.md` 的功能入口
  - `已對應 / 需檢查或確認` 兩區都會標示 `charge_model`，用來區分：
    - `單一 CostCenter 掛帳`
    - `Cross CostCenter 拆帳`
    - `待確認`
  - `tag-gap-summary.md`：缺漏最多的資源 Top 20，並可直接連回對應 RG 頁
  - `tag-graph/index.md`：從 CostCenter 展開到 Purpose / owner / EnvType / Resource Groups 的 graph 入口
- **相依 PBI**：PBI 2.1
- **驗收條件**：gstack 截圖 `_index.md` 確認排序與連結正確

- [x] 實作（2026-05-06）

#### PBI 2.3 — desired_tags 範本自動產生

- **目標**：為缺 tag 的資源自動建立待填寫的 desired 範本，讓使用者在 Obsidian 或任意編輯器填入期望 tag 值
- **關鍵檔案**：`scripts/gen_tag_inventory_md.py`（同 PBI 2.1 腳本）
- **實作重點**：
  - 輸出：`.cache/tag-inventory/desired/{rg}.json`
  - 格式：`[{ "resource_id": "...", "name": "...", "type": "...", "current_tags": {}, "desired_tags": {} }]`
  - 只為「有缺漏必要 tag」的資源產出，已完整 tag 的資源不產出
- **相依 PBI**：PBI 2.1
- **驗收條件**：
  - 產出的 JSON 格式可被 PBI 3.1 的 diff tool 正確讀取
  - `desired_tags` 欄位預填 required keys，值供使用者手動填寫

- [x] 實作（2026-05-06）

---

### Epic 3：本地比對與批次回寫（Diff & Apply）

#### PBI 3.1 — 新增 `azure_cost_tag_diff` MCP tool

- **目標**：比對 desired JSON（使用者填好的期望值）與 Azure 現況，輸出 diff 清單
- **關鍵檔案**：`src/azure_cost_mcp/server.py`、`src/azure_cost_mcp/models.py`
- **實作重點**：
  - 讀取 `.cache/tag-inventory/desired/*.json` 作為期望值
  - Azure 現況優先讀當天 cache（`tag-inventory/YYYY-MM-DD`），過期才重新查
  - 輸出：diff 清單（新增 tag、修改 tag、刪除 tag），預設 Markdown 表格
  - 純 dry-run，無副作用
  - `current_tags` 直接來自 desired JSON（PBI 2.3 生成時已抓快照），無需重新查 Azure
- **相依 PBI**：PBI 2.3
- **驗收條件**：
  - gstack 截圖 MCP Inspector → `azure_cost_tag_diff` → 回傳 diff 表格，欄位含 resource_id、tag key、actual value、desired value

- [x] 實作（2026-05-06）

#### PBI 3.2 — 新增 `azure_cost_tag_apply` MCP tool

- **目標**：根據 diff 結果批次更新 Azure 資源 tag，預設 dry-run；需明確開啟才實際執行
- **關鍵檔案**：`src/azure_cost_mcp/server.py`、`src/azure_cost_mcp/azure_management.py`
- **實作重點**：
  - `azure_management.py` 新增 `patch_resource_tags(resource_id, tags)` 方法（Merge 語意，不刪除其他 tag）
  - PATCH `{resource_id}/providers/Microsoft.Resources/tags/default?api-version=2021-04-01` 使用 Merge operation
  - 安全機制：`azure_cost_tag_apply_enabled=True`（`.env` 開關）才實際執行，否則僅回傳 dry-run 清單
  - 每筆變更寫入 Lakebase `tag_changes` table（依賴 Epic 4；若 Lakebase 未啟用則跳過）
  - 複用 `AzureManagementApiClient`（既有基底類）
- **相依 PBI**：PBI 3.1；PBI 4.3（選配：audit trail）
- **驗收條件**：
  - dry-run 模式：gstack 截圖確認回傳「會修改什麼」但 Azure portal 無變化
  - apply 模式：gstack 截圖 Azure portal 資源 tag 頁面確認更新

- [x] 實作（2026-05-06）

#### PBI 3.3 — Rate limiting 與批次控制設定

- **目標**：避免批次 apply 時打爆 Resource Management API 速率限制
- **關鍵檔案**：`src/azure_cost_mcp/config.py`、`.env.example`
- **實作重點**：
  - `AZURE_COST_TAG_APPLY_BATCH_SIZE`（預設 10）
  - `AZURE_COST_TAG_APPLY_DELAY_MS`（預設 250）：每批次之間的等待毫秒（0 表示不等待）
- **相依 PBI**：PBI 3.2
- **驗收條件**：批次 50 筆資源時，執行時間 ≥ `50/10 * 250ms = 1.25s`，不因速率限制出現 429

- [x] 實作（2026-05-06）

---

### Epic 4：Lakebase 狀態儲存（pgvector 歷史記錄）

> **參考實作**：`D:/azure_code/AuroraOps/databricks-builder-app/server/db/database.py`（OAuth token refresh + async pool 完整實作，直接移植）

#### PBI 4.1 — Lakebase 連線設定

- **目標**：讓 azure-cost-mcp 可選擇性地連接 Databricks Lakebase（PostgreSQL），預設關閉不影響現有功能
- **關鍵檔案**：`src/azure_cost_mcp/lakebase.py`（新增）、`src/azure_cost_mcp/config.py`、`.env.example`
- **實作重點**：
  - 移植 AuroraOps `database.py` 的 async engine + OAuth token refresh（每 50 分鐘）模式
  - 新增 config：`LAKEBASE_HOST`、`LAKEBASE_DATABASE`、`LAKEBASE_SCHEMA`、`LAKEBASE_INSTANCE_NAME`
  - `LAKEBASE_ENABLED=false`（預設）；設成 `true` 才初始化連線
  - 連線失敗不 crash 整個 server，只記 warning
- **相依 PBI**：無（獨立）
- **驗收條件**：`azure_cost_validate_connections` 在 Lakebase enabled 時顯示連線狀態；disabled 時顯示 `skipped`

- [x] 實作（2026-05-06）

#### PBI 4.2 — DB Schema（Alembic migrations）

- **目標**：建立 tag 管理所需的三張 table
- **關鍵檔案**：`alembic/`（新增目錄）、`alembic/versions/`
- **Table 設計**：

  ```sql
  -- 每次盤點快照
  tag_snapshots (
    id UUID PK,
    snapshot_date DATE NOT NULL,
    subscription_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    name TEXT,
    type TEXT,
    resource_group TEXT,
    location TEXT,
    tags JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
  )

  -- 每次套用變更紀錄（audit trail）
  tag_changes (
    id UUID PK,
    applied_at TIMESTAMPTZ DEFAULT now(),
    resource_id TEXT NOT NULL,
    before_tags JSONB,
    after_tags JSONB,
    applied_by TEXT,
    dry_run BOOL DEFAULT TRUE,
    status TEXT  -- 'applied', 'skipped', 'failed'
  )

  -- 資源 tag 向量（pgvector，用於相似性建議）
  tag_embeddings (
    id UUID PK,
    resource_id TEXT NOT NULL,
    tag_summary TEXT,
    embedding vector(1536),
    snapshot_date DATE
  )
  ```

- **相依 PBI**：PBI 4.1
- **驗收條件**：`alembic upgrade head` 成功；三張 table 在 Lakebase 可查詢

- [x] 實作（2026-05-06）

#### PBI 4.3 — Tag 快照自動寫入

- **目標**：每次執行 `azure_cost_tag_inventory` 時，若 Lakebase 已啟用，自動 upsert 快照資料
- **關鍵檔案**：`src/azure_cost_mcp/server.py`、`src/azure_cost_mcp/lakebase.py`
- **實作重點**：
  - Lakebase disabled 時跳過，不影響 tool 正常執行
  - upsert on `(resource_id, snapshot_date)` conflict
- **相依 PBI**：PBI 1.2、PBI 4.2
- **驗收條件**：執行 `azure_cost_tag_inventory` 後查詢 `tag_snapshots`，確認當天快照已寫入

- [x] 實作（2026-05-06）

#### PBI 4.4 — pgvector 相似性建議（`azure_cost_tag_suggest`）

- **目標**：給定一個無 tag 的資源，找出最相似的已 tag 資源，建議補哪些 tag 值
- **關鍵檔案**：`src/azure_cost_mcp/server.py`（新增 tool）、`src/azure_cost_mcp/lakebase.py`
- **實作重點**：
  - tag summary text：`"name: {name}, type: {type}, rg: {resource_group}, location: {location}"`
  - Embedding 來源：優先 Databricks Vector Search（`databricks-vector-search` skill）；備選 Azure OpenAI Embedding API
  - 查詢 `tag_embeddings`，回傳相似度 Top 5 + 建議 tag 值
  - 新 MCP tool：`azure_cost_tag_suggest`
- **相依 PBI**：PBI 4.2、PBI 4.3
- **驗收條件**：
  - gstack 截圖 MCP Inspector → `azure_cost_tag_suggest` → 回傳含 suggested tags + similarity score
  - 建議值與目標資源 type/location 一致（合理性驗證）
- **實作說明**：SQL 相似性查詢（同 type、同 RG 已完整標記的最新快照）作為 pgvector 的備選實作；`embedding_json` 欄位以 JSONB 預留，後續可升級為 `vector(1536)`

- [x] 實作（2026-05-06）

---

### Tag 管理架構總覽

```text
[Azure Resource Graph API]
        ↓ KQL（全資源 + 完整 tags，M365 訂閱優先）
[azure_cost_tag_inventory tool]
        ↓
[.cache/tag-inventory/YYYY-MM-DD/{sub}.json]  ← 原始快取
        ↓ gen_tag_inventory_md.py
[.cache/tag-inventory/obsidian/]              ← Obsidian Vault 目錄
  ├── _index.md                               ← Vault 唯一主入口（Tenant → Subscription → RG → 成本/治理）
  ├── {subscription}/{rg}.md                 ← 每個 RG 一份 md（tenant/subscription、charge model、成本摘要、tag graph、一致/需檢查）
  ├── tag-gap-summary.md                     ← 缺漏資源 Top 20
  └── tag-graph/index.md                     ← CostCenter graph 入口
        ↓ 產出範本
[.cache/tag-inventory/desired/{rg}.json]      ← 期望狀態（使用者填寫）

[azure_cost_tag_diff tool]                    ← actual vs desired 比對
        ↓ 確認差異後
[azure_cost_tag_apply tool]                   ← PATCH Azure Resource Management API
        ↓ audit trail
[Lakebase PostgreSQL]
  ├── tag_snapshots                           ← 每次盤點快照
  ├── tag_changes                             ← 每次套用變更紀錄
  └── tag_embeddings (pgvector)              ← 資源向量，相似性建議
```
