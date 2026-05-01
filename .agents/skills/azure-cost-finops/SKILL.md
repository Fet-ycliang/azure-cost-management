---
name: azure-cost-finops
description: >
  Azure FinOps guidance for this project's MCP service. Use for Azure cost analysis,
  department cost breakdown, savings recommendations, cost trends, Databricks cost governance,
  Storage and VM optimization, network egress analysis, untagged resource detection, tag
  remediation design, Cost Management REST API usage, and Reservation or Savings Plan decisions.
  Triggers: "Azure cost", "Databricks cost", "Storage cost", "VM cost", "network egress",
  "department cost", "cost trend", "untagged resources", "tag remediation", "Cost Management API",
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
- 規劃或實作 tag remediation
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
5. 透過 Databricks MCP server 修正 tag 內容

## 資料流原則

預設採用以下路徑：

1. **Azure Cost Management REST API**：即時查詢與比較
2. **Azure Cost Management exports / FOCUS**：歷史資料與長期趨勢
3. **Azure Storage**：成本資料落地層
4. **Databricks MCP server**：查詢數字、聚合分析、tag 修正
5. **對外 MCP service**：統一對外提供能力

選擇資料來源時，優先規則如下：

- **即時比較 / 快速切片** → 先看 Cost Management REST API
- **歷史趨勢 / amortized cost / 大量分析** → 先看 exports / FOCUS + Storage
- **Databricks、tag audit、tag remediation** → 走 Databricks MCP server

## 設計與實作原則

1. **先對齊 FinOps 標準，再實作工具。** 每個 MCP tool 都要能對應到 Inform / Optimize / Operate 其中一個能力。
2. **優先使用 Azure 原生做法。** 包括 Cost Management、FOCUS、Advisor、Azure Policy、Resource Graph、Reservations、Savings Plan、Azure Hybrid Benefit。
3. **先查詢，後治理。** 先把查詢、趨勢、未標記偵測做穩，再擴展到 tag remediation。
4. **tag 修正預設先建議，明確指定才 apply。** 不要預設直接改資料。
5. **每次涉及 Azure 成本 API、定價、限制或服務行為時，都要再用 `microsoft-docs` 驗證最新資訊。**

## tag remediation 守則

- 預設模式：**先產生修正建議**
- 進階模式：**明確指定直接 apply**
- 必須定義：
  - tag 欄位白名單
  - 輸入驗證
  - dry-run / apply 切換條件
  - 稽核與錯誤回報

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
- Azure 官方文件與原生實踐

若後續需要引入更完整的外部 reference，需保留原始出處與授權資訊。
