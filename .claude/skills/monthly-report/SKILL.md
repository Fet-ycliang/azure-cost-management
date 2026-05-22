---
name: monthly-report
description: >
  每月月初執行三份資料查詢並寫入 cache 的完整工作流程。
  涵蓋 Gate 驗證、Azure 平台費用、AI Verse（m365）、MS Fabric（fabric）四個步驟。
  觸發時機：「月報」「monthly report」「三份資料」「月初查詢」「帳單到了」「帳單更新」「月度報表」。
disable-model-invocation: false
---

# 月報三份資料工作流程

每月月初依序執行以下章節。詳細查詢規範見 `.cache/views-mapping/monthly-report-workflow.md`。

## Chapter 01 — 帳單確認

確認兩個 tenant 帳單已更新：
- `system_catalog` / `rag_analyst_catalog`（Azure 平台）
- `rag_develop_catalog`（M365 + Fabric）

## Chapter 02 — Gate 驗證（六道關卡）

必須全部 PASS 才能繼續：

| Gate | Genie Space |
|------|------------|
| amortized_by_servicename_azure | AmortizedCost |
| actual_by_servicename_azure | ActualCost |
| amortized_databricks_azure | AmortizedCost |
| amortized_by_servicename_m365 | AmortizedCost |
| actual_by_servicename_m365 | ActualCost |
| amortized_databricks_m365 | AmortizedCost |

任何一道 FAIL → 停止，找差異根因後重驗。  
Gate 結果存入 `gate-status.json`（專案根目錄）。

## Chapter 03 — 第一份：Azure 平台各服務費用

- 來源：`system_catalog`（或 `rag_analyst_catalog`，以 Genie 實際 SQL 為準），口徑：**混合**
  - Azure Databricks → AmortizedCost
  - 其他所有服務（含 Unassigned）→ ActualCost
- period = 當月首日（如 `'2026-04-01'`）
- 輸出：依 service_name 字母排序，Tab 分隔，數字不加千分位
- 存入 cache 欄位：`azure_platform_monthly_cost`

## Chapter 04 — 第二份：AI Verse（m365）

- 來源：`rag_develop_catalog`，**必加 `datasource='m365'`**
- ActualCost（全部資源）→ `ai_verse_azure`
- AmortizedCost（service_name='Azure Databricks'）→ `ai_verse_databricks`

⚠️ `ai_verse_databricks` 2026-04 = 149,418，與歷史模板 ~62,764 有落差，scope 待釐清。

## Chapter 05 — 第三份：MS Fabric（fabric）

- 來源：`rag_develop_catalog`，**必加 `datasource='fabric'`**
- MS Fabric RI → **固定**，直接沿用上個月 cache 的值（RI 每月費用相同）
- MS Fabric Others → ActualCost，`pricing_model != 'Reservation'`

⚠️ MS Fabric RI 篩選條件（pricing_model='Reservation'）目前查不到資料，待確認正確篩選欄位。

## Chapter 06 — 專案費用對照

詳見 `/cost-reconcile` skill。

## Chapter 07 — 封存

三份資料寫入：
```
.cache/monthly-reports/<YYYY>/<MM>/monthly-report.json
```

欄位結構：
- `azure_platform_monthly_cost`
- `rag_develop_summary.data.ai_verse_azure`
- `rag_develop_summary.data.ai_verse_databricks`
- `rag_develop_summary.data.ms_fabric_ri`
- `rag_develop_summary.data.ms_fabric_others`

## Genie 問法範本（提高命中率）

### 標準問法結構

Genie 底層使用預聚合 view，欄位均為 snake_case。正確的欄位名稱：
- 成本：`total_cost`（非 `CostInBillingCurrency`）
- 服務名稱：`service_name`（非 `ServiceName` 或 `MeterCategory`）
- 月份：`period`（DATE 型別，月份首日代表整月）
- 平台來源：`datasource`（'m365' 或 'fabric'）

```
在 [ActualCost|AmortizedCost] 中，
查 period='YYYY-MM-01'，
[若需要：datasource='m365'|'fabric']
GROUP BY service_name，
回傳 service_name 和 SUM(total_cost)，
依金額降序排列。
```

### 第一份：Azure 平台（rag_analyst_catalog）
```
步驟1：問 ActualCost 全服務
「在 rag_analyst_catalog ActualCost 中，查 period='2026-04-01'，
GROUP BY service_name，SUM(total_cost) 降序排列，全部列出包含 Unassigned」

步驟2（followup 延伸）：
「Azure Databricks 的部分改用 AmortizedCost，其他服務維持 ActualCost，
請重算並合併輸出」
```

### 第二份：AI Verse（rag_develop_catalog, datasource='m365'）
```
「在 rag_develop_catalog AmortizedCost 中，
period='2026-04-01' AND datasource='m365'，
查 service_name='Azure Databricks' 的 SUM(total_cost)」
```

### Genie 回應結構

每次查詢回傳四個部分：
1. **答案**：`attachments[].text.content` — 自然語言回答
2. **查詢元數據**：`get_message_query_result()` — 欄位定義、statement_id
3. **SQL**：`attachments[].query.query` — Genie 生成的完整 SQL
4. **建議問題**：`attachments[].suggested_questions` — 後續延伸問題

**核對 SQL 的時機**：結果可疑時，讀 `attachments[].query.query` 確認：
- `period` 條件是否正確
- 是否用了 `total_cost`（而非 `CostInBillingCurrency`）
- `service_name` 篩選是否正確
- `datasource` 過濾是否有加

### 回應診斷
| 現象 | 診斷 | 修正 |
|------|------|------|
| 結果為 0 | SQL 條件錯誤 | 讀 `attachments[].query.query`，確認 period、datasource、service_name |
| 回傳 text_response | 問題太模糊 | 加入期間、平台、GROUP BY 條件後重問 |
| Databricks 金額太小 | 用了 ActualCost | Followup：「請改用 AmortizedCost 重查」 |
| 兩個訂閱混在一起 | 缺少 datasource 過濾 | Followup：「請加上 `datasource='m365'` 條件」 |

## 核心計費口徑原則

**預設一律使用 AmortizedCost（攤提口徑）。**

| 場景 | 口徑 |
|------|------|
| 專案費用對照（攤提，含 VM / Storage / Databricks 全部服務） | **AmortizedCost** |
| 第一份月報：Azure 平台整體服務報表 | **混合**：Databricks → AmortizedCost；其他 → ActualCost |

> Databricks 走預繳 / Reservation，用 ActualCost 查到的值可能為 0，必須走 AmortizedCost。

## 查詢通用注意事項

| 陷阱 | 正確做法 |
|------|---------|
| 舊欄位名稱 | view 使用 snake_case：`total_cost`, `service_name`, `purpose`, `resource_group_name`, `pricing_model`, `period` |
| datasource 過濾 | `rag_develop_catalog` 含 m365 與 fabric，必須加 `datasource='m365'` 或 `'fabric'` 分開查 |
| Period 語意 | 月份首日代表整月，`period = '2026-04-01'` = 整個 4 月 |
| ws-cluster tag | 若 Genie 查 ws-cluster，用 `cluster_name` 欄位（view 已預處理），勿假設仍需 `Tags['ws-cluster']` |
