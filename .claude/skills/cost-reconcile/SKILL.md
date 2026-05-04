---
name: cost-reconcile
description: >
  專案費用對照查詢工作流程。比較原始費用表格 vs Genie 計算值，
  處理差距大的 row，更新 project-cost-table.json。
  觸發時機：「專案費用」「費用對照」「差距大」「project cost」「cost reconcile」「35 行」「費用差距」「對照表」。
disable-model-invocation: false
---

# 專案費用對照工作流程

詳細對照表見 `.cache/views-mapping/cost-report-YYYY-MM.md`。

## Genie View Schema 說明

Genie 底層使用預聚合 view（非原始 actual/amortized 表），欄位均為 **snake_case**：

| 舊欄位（已失效） | 新欄位 |
|---|---|
| `CostInBillingCurrency` | `total_cost` |
| `Tags['Purpose']` / `LOWER(Tags['Purpose'])` | `purpose`（已預處理為小寫） |
| `ResourceGroup` | `resource_group_name` |
| `ServiceName` / `MeterCategory` | `service_name` |
| `PricingModel` | `pricing_model` |
| `Period` | `period` |
| `Datasource` | `datasource` |

View 表名：
- Azure 平台：`system_catalog.system_report.daily_azure_cost_usage_actual_view`（或 `_amortized_view`）
- M365 平台：`rag_develop_catalog.system_report.daily_azure_cost_usage_actual_view`（或 `_amortized_view`）

## 核心計費口徑原則

**預設一律使用 AmortizedCost（攤提口徑）。**

| 場景 | 口徑 | 說明 |
|------|------|------|
| 專案費用對照（攤提）| **AmortizedCost** | 預設，包含 VM / Storage / Databricks 全部服務 |
| Azure 平台整體服務報表（第一份月報）| **混合**：Databricks → AmortizedCost；其他 → ActualCost | 僅第一份月報用 |

Databricks 走預繳 / Reservation，ActualCost 可能為 0，必須用 AmortizedCost 才能反映實際算力成本。

## 狀態分類

| 狀態 | 定義 | 處理方式 |
|------|------|---------|
| ✅ 接近 | 誤差 < 20% | 直接採用計算值 |
| 🟡 有差距 | 20–35% 差異 | 逐一確認 filter 條件 |
| 🔴 差距大 | > 40% 差異 | 找正確 RG / purpose tag |
| 🔒 固定 | 不需重查 | 帶入固定值或上月平均 |
| ❓ 待查 | filter 條件未知 | 釐清後補查 |
| ⛔ 無法計算 | 由下一筆反推 | Azure VMs 通常未標 purpose tag |

## 差距大 🔴 的排查步驟

### Step 1 — 確認 source 規則

- `source='Azure'`：查 `system_catalog`，依 resource_group_name 或 purpose tag 篩選
- `source='Databricks'`：查 AmortizedCost，依 purpose tag 篩選
- `source='由下一筆反推'`：Azure 費用 = 總費用 - Databricks，VMs 通常未標 tag

### Step 2 — 找對應 view 過濾條件

查詢 `.cache/views-mapping/01-purpose-tags.md` 或 `02-resource-groups.md`，確認：
- 對應的 purpose 值（view 已預處理為小寫，直接比對）
- 對應的 resource_group_name 清單

### Step 3 — 診斷 purpose 覆蓋率

```sql
SELECT DISTINCT purpose, COUNT(*) as cnt
FROM system_catalog.system_report.daily_azure_cost_usage_actual_view
WHERE period = '2026-04-01'
  AND resource_group_name IN (...)
GROUP BY purpose
```

### Step 4 — 確認 service_name 正確性

若結果可疑，在 Genie 的 followup 中要求查看 SQL，確認：
- 使用了 `service_name` 欄位（view 已正確映射，不存在 ConsumedService 問題）
- `period` 條件正確
- `purpose` 欄位名稱（小寫，直接比對，不需 LOWER()）

## Genie 問法範本（高命中率）

**問法結構**：告訴 Genie 用哪個欄位、什麼條件、要回傳什麼
```
在 [ActualCost|AmortizedCost] 中，
period='YYYY-MM-01'，
[purpose IN ('value1','value2')] 或 [resource_group_name IN ('rg1','rg2')]，
[service_name != 'Azure Databricks' 或 service_name = 'Azure Databricks']，
回傳 SUM(total_cost)
```

**結果可疑時先看 SQL**：Genie 回應包含 `attachments[].query.query`，確認：
- 使用了 `total_cost` 而非舊的 `CostInBillingCurrency`
- `period` 條件正確
- `purpose` 欄位名稱正確（小寫，不需 LOWER()）
- `resource_group_name` 或 `service_name` 條件如預期

若 SQL 有誤，在 followup 直接說明：「你的 SQL 用了 X，請改用 Y 重查」

**0 元結果診斷流程**：
1. 先問：`SELECT DISTINCT purpose, COUNT(*) FROM <view> WHERE period='2026-04-01' AND resource_group_name='rg-name'`
2. 確認 purpose 覆蓋率 → 若大部分為 NULL，說明資源未標 purpose tag
3. 若 purpose 存在但結果還是 0 → 看 SQL 確認 period 和 service_name 條件

## 常見 View 查詢模式

### Purpose tag 查詢
```sql
-- AmortizedCost (Databricks)
SELECT SUM(total_cost) 
FROM system_catalog.system_report.daily_azure_cost_usage_amortized_view
WHERE period = '2026-04-01'
  AND purpose IN ('purpose_value')
  AND service_name = 'Azure Databricks'

-- ActualCost (Azure 一般服務)
SELECT SUM(total_cost)
FROM system_catalog.system_report.daily_azure_cost_usage_actual_view
WHERE period = '2026-04-01'
  AND purpose IN ('purpose_value')
  AND service_name != 'Azure Databricks'
```

### ResourceGroup 查詢
```sql
SELECT SUM(total_cost)
FROM system_catalog.system_report.daily_azure_cost_usage_actual_view
WHERE period = '2026-04-01'
  AND resource_group_name IN ('rg-name-1', 'rg-name-2')
```

## 特殊已知問題

| Row | 問題 | 說明 |
|-----|------|------|
| DCB Azure | 幾乎為 0 | VMs 未標記 purpose=dcb，需找對應 resource_group_name |
| mesh_plus ws-cluster | 需確認 | cluster_name 欄位對應 ws-cluster tag，查詢改用 `cluster_name` |
| MS Fabric RI | 查不到 | pricing_model='Reservation' 無資料，待確認篩選欄位 |
| BDP LBS Azure Storage | 返回 0 | purpose=bdsd 未標在 Storage 資源，需找 resource_group_name |

## 輸出格式

更新 `.cache/monthly-reports/<YYYY>/<MM>/project-cost-table.json` 各 row 的：
- `computed`: 計算值
- `diff_pct`: 差異百分比
- `status`: ✅ / 🟡 / 🔴 / 🔒 / ❓ / ⛔
- `query_note`: 使用的 filter 條件說明
