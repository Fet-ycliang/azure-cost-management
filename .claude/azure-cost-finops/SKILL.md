---
name: azure-cost-finops
description: >
  Azure FinOps guidance for this project's MCP service. Use for Azure cost analysis,
  department cost breakdown, savings recommendations, cost trends, Databricks cost query,
  Storage and VM optimization, network egress analysis, untagged resource detection,
  tag governance planning, Cost Management REST API usage, and Reservation or Savings Plan decisions.
  Triggers: "Azure cost", "Databricks cost", "Storage cost", "VM cost", "network egress",
  "department cost", "cost trend", "untagged resources", "tag governance", "Cost Management API",
  "Reservation", "Savings Plan".
---

# Azure Cost FinOps

專注於本專案的 **Azure FinOps + MCP service** 規劃與實作。這不是通用雲端成本 skill，而是針對目前專案已確認的資料流、優先範圍與治理方式建立的 project-base skill。

## 何時使用

當需求涉及以下任一情境時，優先使用此 skill：

- 規劃或實作 Azure 成本查詢能力
- 設計 Databricks 成本分析流程
- 比較 Storage / VM / Network egress 成本
- 設計部門費用、費用趨勢、節費方向等 MCP tools
- 找出未打標記資源
- 規劃 tag governance roadmap（不要假設目前已有維護功能）
- 設計 Azure Cost Management REST API、Storage、Databricks MCP server 的整合方式

## 本專案目前已確認的優先順序

第一版最高優先章節：

1. **Azure Databricks**
2. **Storage**
3. **VM**
4. **Network egress**

第一版核心用例：

1. 查詢部門費用
2. 查詢節費方向與優化建議
3. 查詢費用趨勢
4. 找出未打標記的服務或資源
5. Databricks 僅提供成本查詢 / SQL 分析整合，tag 治理另案規劃

## 資料流原則

預設採用以下路徑：

1. **Azure Cost Management REST API**：即時查詢與比較
2. **Azure Cost Management exports / FOCUS**：歷史資料與長期趨勢
3. **Azure Storage**：成本資料落地層
4. **Databricks MCP server**：查詢數字、聚合分析
5. **對外 MCP service**：統一對外提供能力

選擇資料來源時，優先規則如下：

- **即時比較 / 快速切片** → 先看 Cost Management REST API
- **歷史趨勢 / amortized cost / 大量分析** → 先看 exports / FOCUS + Storage
- **Databricks 成本查詢 / UC SQL 分析** → 走 Databricks MCP server
- **tag audit / tag remediation / 維護流程** → 目前不假設存在，需另案規劃

## Cost Analysis views 使用前提

目前使用者既有的成本分析流程，**大量依賴 Azure Cost Analysis 的 saved views** 來整理數字與做成本計算。

因此後續如果要把流程做順，建議把 views 視為：

1. **業務語意層**：代表目前團隊怎麼看成本，而不是原始事實資料本身
2. **驗證基準**：新流程上線前，先拿既有 views 算出的數字做 reconciliation
3. **遷移來源**：把常用 view 的 filter、grouping、time range、cost metric，逐步轉成可程式化的 query spec

實作上請遵守：

- **不要只靠人工進 Portal 看 view 結果**，要能透過 REST API 或可程式化查詢重現
- **不要把每個 view 都當獨立邏輯重新手刻**，先抽成共用的 metric definition / query template
- **先保留 views 當 analyst 入口**，再把穩定邏輯下沉到 export / Databricks / materialized tables
- **所有新計算都要能回對既有 view 的數字**，否則難以建立信任
- **不要把 raw saved view name 直接當 API 主鍵**，應分成 `logical_view_key` 與 `saved_view_name`
- **不要假設 Portal 看得到的 view 一定存在於目前 subscription-scope 的 Views API**，registry 需明確保存 `view_scope_type`、`view_scope_id`、`tenant_id`
- **查詢 Azure Databricks 成本時，預設走 `AmortizedCost` / `*_amortized*`**；Databricks 常走預繳 / reservation-backed 口徑，`ActualCost` / `*_actual*` 可能為 0 或不具代表性
- **若使用者只問「Databricks 費用」但未指定成本口徑**，預設回 amortized 數字，並清楚標示為攤銷 / 估列口徑
- **若使用者以「`(Azure平台) 服務名稱 前一個月的費用`」這類月度服務費用語法發問，且未明確指定成本口徑**，一律預設走 `AmortizedCost` Genie
- **Azure 平台 VM / Storage 的 `ActualCost` 只作為月度 reconciliation / gate status 驗證用途**；gate 通過後，回到一般查詢情境時，未指定口徑仍一律走 `AmortizedCost`
- **TagKey grouping 的回應 shape 是 `TagKey` + `TagValue`**，不是直接回 `Purpose` 或 `cost_center` 欄位
- **`ResourceGroupName` 可能為空**，shared/platform charge 需回退到 `ServiceName`、tag、`PricingModel`、`BenefitName`
- **不要把大區間回補做成「每月一支 API」**；能一次拉整段月份，就不要拆成逐月 request
- **同一 scope 的 Cost Management Query 要序列化或做低併發節流**；適合平行化的是不同 scope / tenant
- **月結與多歸屬欄位分析優先走 exports / FOCUS**，REST API 主要留給互動查詢、saved view replay、與 reconciliation
- **對「上個月」的 reconciliation，REST API baseline 以「每月抓一次」為原則**；同一月份、tenant、scope、service 與 cost basis 只要已有內容，就持續重用，不要重抓
- **只有 baseline 缺失、使用者明確要求強制刷新、或改抓不同月份 / 不同條件時，才重新抓 REST API**
- **只有 Azure 平台與 M365 平台都各自通過同月份的 reconciliation gate，才能說「Databricks Genie 的上個月份資料可使用」**；單一平台驗過不代表整體可放行
- **Azure 平台與 M365 平台必須分別維護自己的 tenant、scope、REST baseline、validated_through_month 與 gate_status**
- **Genie 的「上個月」資料要到每月 2 號 10:00（Asia/Taipei）後才視為完整**；根因通常是 export 落地與後續 ingestion 較慢，在此之前若看到月底差異，仍要標示為異常，但應一併提醒「先不用擔心，晚點資料補齊後再確認」**
- **前月正式 reconciliation / release gate 應在每月 2 號 10:00（Asia/Taipei）後再判定**；cutoff 前可先觀察，但不要直接判成 `reingest_required`
- **費用查詢的日界線與月界線一律以 GMT/UTC 00:00 為準**；`今天`、`昨天`、`上個月` 這類相對時間都要先換成 UTC 再判斷
- **Asia/Taipei 的 00:00~08:00 期間特別容易差一天**；這段時間若直接問相對時間，結果可能仍落在前一個 UTC 日
- **做 reconciliation、排程或月結驗證時，優先明確指定月份（例如 `2026 年 4 月`）或明確以 UTC date 計算**，不要只依賴未標時區的相對時間
- **Genie 做 ActualCost 驗證時，要明確指定平台 / scope（例如 `Azure 平台 Virtual Machines`、`Azure 平台 Storage`）**；否則可能被擴成跨 `system_catalog` 與 `rag_develop_catalog` 的 union 查詢
- **若 VM / Storage 的 ActualCost mismatch 只集中在少數高點日期，先查 `PricingModel = 'Reservation'` 的每日明細**；若金額與 diff 對齊，通常代表 REST view / 對應 query 漏了 Reservation 成本
- **若要從 ActualCost 每日總額中排除 Reservation，不要用 `MINUS` 去減「Reservation 每日總額」**；因為總額列與 Reservation 列金額不同，通常不會被消掉。應直接 filter `PricingModel != 'Reservation'`，或按日期先算總額再減 Reservation 金額
- **`M365_COST_MANAGEMENT_*` 可作為 operator-run 驗證流程的設定來源**；`Settings` 已可讀取這組變數，但完整的 M365 對帳流程仍未正式產品化成 repo 內 tool
- **多支 aggregated query 不能視為可無損回拼的明細表**；若 query grain 不一致，最多只能在報表層並排分析
- **若後續要把資料落成可再切維度的 fact table，優先選欄位數夠的單次查詢；不夠就改走 exports / FOCUS**
- **若已有 Databricks `system_catalog.system_report.daily_azure_cost_usage_*` tables，月結與 D-2 對帳優先直接查這組表，不要再把 exports 當預設主來源**
- **`*_actual` / `*_actual_agg` 與 `*_amortized` / `*_amortized_agg` 應分工使用：detail 表做歸屬與回溯，agg 表做快速對帳與 summary**

## Budget 對照表前提

目前使用者提供的 budget 對照表，至少包含這幾個欄位：

1. **view_name**：第一欄，對應實際使用的 Cost Analysis saved view
2. **annual_budget**：年度預算
3. **monthly_budget**：月預算
4. **code column**：中間還有一個代碼欄位，但目前語意尚未完全定義
5. **project_name**：最後一欄，專案名稱

設計時請注意：

- **不要把 `view_name` 當唯一業務主鍵**，因為同一個專案可能對應多個 view
- **不要先假設 code column 是唯一 project key**，它比較像分群或歸戶欄位，語意要後續再定
- **`project_name` 比較接近目前的人類可讀彙總主體**
- **`annual_budget` 應視為主要來源，`monthly_budget` 盡量由規則推導或驗證一致性**
- **需要一張 mapping / registry 表**，把 `view_name`、budget、project metadata、code column、tenant、scope 關係收齊

## 目前範圍限制

目前專案**沒有**把 tag 治理當成已實作的維護功能，請遵守以下邊界：

1. **不要預設 Databricks MCP server 有 tag audit / tag remediation tool**
2. **不要把 tag 維護能力算進目前 local validation 的必要範圍**
3. **tag 相關需求先視為 roadmap / planning topic，不是既有維運能力**
4. **若目前 Databricks 端是 `ActualCost` / `AmortizedCost` 這類 Genie Space，應解讀成 query backend，而不是治理 backend**
5. **目前已驗證成功的範圍僅限 Azure 平台**；即使 Azure 平台已對齊，也**不能**推論 M365 平台已對齊，M365 必須獨立做同一套 REST vs Genie 驗證流程

## Multi-tenant auth 前提

目前環境不是 single-tenant，請直接以 **multi-tenant Azure auth** 為前提設計：

1. **目前跨兩個 tenant 處理多組 subscription**
2. **home tenant 在 tenant 2**
3. **subscription 數量會持續增加，不要把 tenant 與 subscription 關係寫死在單一 if/else**
4. **任何 auth / cache / query flow 都應支援 subscription-to-tenant mapping**
5. **後續 Service Principal / credential 規劃，需預留至少 2 組認證的可能性**

這代表：

- 本機 `azure-cli` 驗證不能假設一個登入 tenant 就能覆蓋所有 scope
- 後續 `service-principal` / `managed-identity` 設計，也不能假設單一 tenant 足夠
- Resource Graph、Cost Management、Storage、Databricks 的驗證流程要分別考慮 tenant 歸屬

## 設計與實作原則

1. **先對齊 FinOps 標準，再實作工具。** 每個 MCP tool 都要能對應到 Inform / Optimize / Operate 其中一個能力。
2. **優先使用 Azure 原生做法。** 包括 Cost Management、FOCUS、Advisor、Azure Policy、Resource Graph、Reservations、Savings Plan、Azure Hybrid Benefit。
3. **先查詢，後治理。** 先把查詢、趨勢、未標記偵測做穩，再擴展到 tag remediation。
4. **tag 修正預設先建議，明確指定才 apply。** 不要預設直接改資料。
5. **每次涉及 Azure 成本 API、定價、限制或服務行為時，都要再用 `microsoft-docs` 驗證最新資訊。**

## Databricks 擴充能力選型

當需求開始超出「單純查成本」時，優先用下面的方式判斷該擴充到哪一層：

| 能力 | 優先選項 | 適用情境 | 不建議拿來做什麼 |
|---|---|---|---|
| 結構化成本分析 | **已驗證的成本 tables / gold tables** | 成本彙整、部門對帳、趨勢分析、validated table 查詢 | 不要拿來存應用程式短生命週期 state |
| 自然語言查詢 | **`ActualCost` / `AmortizedCost` Genie Space** | 已有整理好的 Unity Catalog table，想做 NL-to-SQL 問答入口 | 不要把 Genie 當資料治理或 ETL 本體 |
| 治理 / 血緣 / system usage | **Unity Catalog system tables** | billing、audit、query history、lineage、volume 操作 | 不要當主交易資料庫 |
| OLTP / 應用 state / agent memory | **Lakebase** | 低延遲交易資料、workflow state、chat / agent memory、reverse ETL serving | 不要當 Azure Cost REST API 原始落地層 |
| 語意檢索 / RAG | **Databricks Vector Search** | Delta / UC 為主資料源、需要 managed vector index 與自動同步 | 不要拿來取代關聯式 OLTP 資料模型 |

## 目前架構方向決策

目前工作方向改回採用 **Option 2 -> Option 3** 的演進路線。

請遵守：

1. **短期** 先用 registry file / table 把 budget、view、alias mapping 收斂
2. **中期** 再把 registry 放進 Databricks table，由 MCP 查詢與計算
3. **Option 4: Lakebase / OLTP + Databricks analytics** 保留為後期候選，不是目前預設路線
4. **README 先不要寫死目標架構**，等 schema、auth、tenant mapping、owner 邊界更明確時再正式落文件

## Lakebase / pgvector 使用守則

若你要引入 **Lakebase + pgvector**，在本專案中建議定位為：

1. **應用程式狀態層**：保存 agent state、查詢歷史、工作流 state、人工覆核紀錄。
2. **低延遲 serving 層**：把已整理好的成本摘要、建議結果、治理結果同步出去，提供應用快速讀取。
3. **向量化知識層**：把成本治理規則、歷史修正案例、文件摘要放進 pgvector，方便後續語意檢索。

但 **不要** 把 Lakebase 當成這個專案第一層成本資料來源。原則如下：

- **原始成本事實** 仍以 Azure Cost Management REST API / exports / FOCUS / Storage 為主
- **Lakebase** 放的是整理後、需要低延遲或交易一致性的資料
- **短 TTL API 回應** 應先走本地 memory / disk cache，不要直接把 Lakebase 當快取替代品

換句話說：

- **快取** 解決「避免重複 call REST API」
- **Lakebase** 解決「系統需要 durable state、OLTP、pgvector 與後續應用擴充」

這兩者可以同時存在，但不要混成同一層責任。

### LakebaseClient 實作踩坑（Epic 4 整合後）

**兩步驟可用性判斷**：`is_configured()`（讀 Settings，sync）≠ `is_ready()`（engine 已 init，async 後才為 True）。兩個要分開用：

```python
if lakebase_client.is_configured():
    if not lakebase_client.is_ready():
        await lakebase_client.init()
    await lakebase_client.upsert_tag_snapshots(...)
```

**`init()` 不是冪等**：重複呼叫會覆蓋 `_engine` 但不 dispose 舊連線池，造成資源洩漏。永遠用 `is_ready()` 守門。

**test group 需含 SQLAlchemy**：`[dependency-groups].test` 必須加 `"sqlalchemy[asyncio]>=2.0"`。即使測試沒有連真實 DB，ORM model 的 `import` 也需要此依賴，否則 `from azure_cost_mcp.lakebase_models import TagSnapshot` 就會失敗。安裝時執行 `uv sync --group test`（不加 group flag 不會裝）。

**`AsyncMock` vs `MagicMock` for SQLAlchemy session**：

| session method | 正確 mock 類型 | 原因 |
|---|---|---|
| `session.merge()` | `AsyncMock` | SQLAlchemy async merge 是 coroutine |
| `session.execute()` | `AsyncMock` | async execute |
| `session.add()` | `MagicMock` 或直接不 mock | SQLAlchemy `add()` 是**同步**方法；用 `AsyncMock` 會導致 `RuntimeWarning: coroutine never awaited` |

使用 `AsyncMock()` 作為 session 時，**所有** attribute access 都會回傳 coroutine，包括 `add()`，因此含 `session.add()` 的測試應改用 `MagicMock()` 作為 session。

**`session_scope` mock 模式**：測試 Lakebase 業務邏輯時，最乾淨的方法是用 `patch.object` 完全替換 `session_scope`：

```python
@asynccontextmanager
async def _fake_scope():
    yield mock_session

with patch.object(client, "session_scope", _fake_scope):
    count = asyncio.run(client.upsert_tag_snapshots(resources, "2026-05-06"))
```

這樣完全繞過 engine 建立，讓測試只驗證 session 操作的業務邏輯。

**pgvector JSONB fallback**：目前 `tag_embeddings.embedding_json` 用 `JSONB` 存 embedding，`embedding vector(1536)` 需 pgvector extension 安裝後才能啟用。現階段相似性查詢走 tag key 覆蓋率過濾，非真正向量搜尋。

## Databricks 能力擴充建議順序

若後續要把專案能力往上擴，建議順序如下：

1. **先把 Cost / Trend / Tag audit 的資料模型穩定下來**
2. **再補本地 cache 與 FOCUS / export ingestion**
3. **接著補成本 gold tables**
4. **之後以 `ActualCost` / `AmortizedCost` Genie Space 當自然語言入口**
5. **若開始需要 agent state / app backend / pgvector，再引入 Lakebase**
6. **若主要需求是 Delta 上的文件或文本語意檢索，再評估 Vector Search**

## Databricks 權限與前置條件提醒

只要需求涉及 Databricks 擴充，至少先確認：

1. **Workspace 可存取**
2. **`ActualCost` / `AmortizedCost` Genie Space 可用**
3. **Unity Catalog 權限足夠**
4. **對應 MCP tool name 已確認**
5. **若使用 Lakebase**，需另外確認 Postgres 角色、OAuth credential 與資料庫權限

## 可持續搬入的 Databricks 參考主題

目前已從 user-level Databricks skills 觀察到，後續值得持續吸收進 project base 的方向包括：

- Lakebase Autoscaling / Provisioned 的選型規則
- Vector Search 與 pgvector 的邊界
- `ActualCost` / `AmortizedCost` 背後的 materialized view、AI functions、query serving 模式
- Genie Space 的空間設計與 Conversation API 流程
- Unity Catalog system tables 在 billing / audit / lineage 的使用方式

## tag remediation 守則

以下內容屬於**未來若要規劃 tag 治理能力**時的守則，不代表目前專案已經提供維護功能：

- 預設模式：**先產生修正建議**
- 進階模式：**明確指定直接 apply**
- 必須定義：
  - tag 欄位白名單
  - 輸入驗證
  - dry-run / apply 切換條件
  - 稽核與錯誤回報

## Genie Space 欄位注意事項

Genie space 底層使用預聚合 view（`daily_azure_cost_usage_actual_view` / `_amortized_view`），**欄位為 snake_case**，與 REST API 欄位名稱不同：

| REST API 欄位 | Genie View 欄位 |
|---|---|
| `CostInBillingCurrency` | `total_cost` |
| `Tags['Purpose']` | `purpose`（已小寫） |
| `ResourceGroupName` | `resource_group_name` |
| `ServiceName` / `MeterCategory` | `service_name` |
| `PricingModel` | `pricing_model` |

**注意**：本 skill 其他段落中涉及 `PricingModel`、`ServiceName`、`ResourceGroupName` 的規則，是 **REST API context**，在 REST API 查詢中仍然正確。若透過 Genie 查詢，需改用上表的 view 欄位名稱。

詳細欄位對照表見 `.cache/views-mapping/refs/db-schema-mapping.md`。

## Genie 已知 SQL 生成問題

透過 NL-to-SQL 查詢時，Genie 可能產生有問題的 SQL，每次結果可疑時優先確認：

1. **OR 替代 AND（多條件組合）**：同時 filter `purpose` 和 `resource_group_name` 時，Genie 可能生成各條件間用 OR 而非 AND，導致結果暴增。重查時明確說：「兩個 filter 條件之間要用 AND」。

2. **ILIKE 模糊比對替代精確 `=`**：Genie 可能生成 `purpose ILIKE '%chatbot%'` 而非 `purpose = 'chatbot'`，多比到其他 purpose 值。重查時指定「用精確比對（=），不要用 LIKE 或 ILIKE」。

3. **`GROUP BY service_name` + `IS NOT NULL` 漏掉 null 記錄**：某些 RG 的 `service_name` 為 null，加上 `IS NOT NULL` 會漏掉這些費用。改用 `GROUP BY resource_group_name` 交叉驗證，或明確說「不要加 IS NOT NULL 條件」。

4. **View 名稱 ≠ purpose tag 實際值**：View display name 不等於底層 purpose tag 的實際值。  
   - `2025_mi_cat_mly` → purpose tag 是 `mi_cat`（不是 view 名）  
   - `2025_digital_bandwidth_mly` → 底層對應 `2025_channel_bandwidth_mly`  
   - 查詢時要用實際 purpose tag，不能用 view 名稱當 filter 值。

5. **結果可疑先讀 SQL**：Genie 回應的 SQL 在 `attachments[].query.query`，不在頂層。若數字異常，先讀 SQL 確認 WHERE 條件，再決定是否補充說明重查。

## 搭配使用的 skills

- **`microsoft-docs`**：驗證 Azure Cost Management API、Pricing、ACA、APIM 等官方文件
- **`kql`**：撰寫或修正 Azure Resource Graph / Log Analytics / Cost 查詢
- **`cloud-solution-architect`**：服務選型、ACA 架構與 Azure 治理設計

## 參考檔案

| 檔案 | 用途 |
|---|---|
| `references/project-focus.md` | 本專案第一版優先範圍、用例與 MCP 能力 |
| `references/data-sources.md` | REST API、exports / FOCUS、Storage、Databricks MCP 的分工 |
| `references/tag-governance.md` | tag audit / remediation 的治理原則 |

## 來源說明

此 skill 為本專案客製化整理，內容方向參考：

- 本 repo 的專案規劃與 README
- OptimNow `cloud-finops-skills` 的 FinOps / Azure / Databricks / tagging references
- `C:\Users\ycliang\.claude\skills.databricks\` 內與 Lakebase、Genie、Unity Catalog、Vector Search 相關的實務 skill
- Azure 官方文件與原生實踐

若後續需要引入更完整的外部 reference，需保留原始出處與授權資訊。
