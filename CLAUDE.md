# Azure Cost MCP Agent Guide

這個 repo 的 agent 指令入口以 **`CLAUDE.md`** 為主，但實際的專案規範與主力 skills 來源請優先讀取 **`.claude`**。

## 長期學習原則

> Every time Claude makes a mistake -> it writes a rule.  
> Every correction -> permanent memory.  
> Every session -> smarter than the last.

- 這是本 repo 的高優先級原則。
- 只要發生錯誤、誤解、踩坑或被使用者糾正，應把可重用的規則寫回長期記憶。
- **跨任務、跨功能都適用的規則寫進 `CLAUDE.md`；特定領域或流程的規則寫進 `.claude` 對應的 `SKILL.md`。**

## 指令來源優先順序

1. `CLAUDE.md`
2. `.claude\project-guidelines\SKILL.md`
3. `.claude\*\SKILL.md`
4. `README.md`

若 `.claude` 與 `.agents` 有重複內容，**一律以 `.claude` 為準**。

## 專案定位

- 這是 **Python FastMCP** 服務，目標是提供 Azure FinOps 查詢與治理能力。
- 第一版聚焦五個高價值用例：
  1. 部門費用查詢
  2. 費用趨勢查詢
  3. 節費方向與 Reservation / Savings Plan 建議
  4. 未標記資源與 tag 治理
  5. 透過 Databricks MCP server 查詢 Storage 上的成本資料
- 成本優先順序固定以 **Azure Databricks、Storage、VM、Network egress** 為主。

## Agent 工作規則

- 所有人類可讀內容預設使用 **繁體中文**；程式識別子與技術術語維持英文。
- 新增或修改功能時，優先遵循 `.claude\project-guidelines\SKILL.md` 的規範。
- 若需要使用 repo 內 skills，先看 `.claude`，不要先看 `.agents`。
- `README.md` 是操作與部署主來源；**不要把 README 的大段操作步驟重複搬進這個檔案**。
- 詳細架構、設定與驗證指令以 `README.md` 與 `src\azure_cost_mcp\` 內實作為準。

## 開發環境

- 套件管理使用 **`uv`**，不用 pip：
  - 安裝依賴：`uv sync`
  - 執行服務：`uv run azure-cost-mcp --transport stdio`
  - 執行測試：`uv run pytest`（80% coverage 門檻）
- Python **3.11+**（`.python-version` 已鎖定）
- 內部 PyPI proxy：`nexus01p.fareastone.com.tw:8081/repository/pypi-proxy/`  
  在新環境安裝若失敗，優先確認此 proxy 是否可達。

## 實作時必守慣例

- MCP tool 名稱使用 `azure_cost_` 前綴。
- 新增設定時，至少同步更新：
  1. `src\azure_cost_mcp\config.py`
  2. `.env.example`
  3. `README.md`
- `tag remediation` 預設是建議 / dry-run；只有在參數與環境開關都允許時才直接套用。
- Databricks 相關能力優先走既有 MCP proxy 設計，不要直接繞過既有抽象層。
- Cost Management API 速率限制 **4 req/min per scope**；呼叫前確認是否已有 cache，遇 429 時讀 `Retry-After` header，不可全局重試。
- 查詢 **Azure Databricks 成本** 時，預設使用 **`AmortizedCost`**；Databricks 常走預繳 / reservation-backed 口徑，**`ActualCost` 可能為 0 或不具代表性**。

## 計費口徑原則

- **預設口徑：AmortizedCost**。除非特別說明，所有專案費用查詢一律用 AmortizedCost（攤提用）。
- **例外：Azure 平台整體服務報表**（第一份月報）使用混合口徑：
  - Azure Databricks → AmortizedCost
  - 其他所有服務 → ActualCost
- Databricks 走預繳 / Reservation，ActualCost 可能為 0，必用 AmortizedCost。

## Genie 查詢注意事項

- Genie 是 **NL-to-SQL**：直接用自然語言問，Genie 自動生成 SQL；問法不需寫 SQL 語法。
- **Genie 回應結構**：SQL 在 `attachments[].query.query`（非頂層 `sql`）；結果可疑時讀這個欄位驗證。
- **View schema**（2026-05 後）：Genie 底層換成預聚合 view，欄位全為 snake_case。
  - `CostInBillingCurrency` → `total_cost`、`Tags['Purpose']` → `purpose`（已小寫）、`ResourceGroup` → `resource_group_name`、`ServiceName` → `service_name`
  - 詳細對照：`.cache/views-mapping/refs/db-schema-mapping.md`
- **datasource 過濾**：`rag_develop_catalog` 同時含 m365 和 fabric，查詢時必加 `datasource='m365'` 或 `'fabric'`。
- Genie space config 範例問題若出現 0 結果，可能是引用了已刪除欄位（view 欄位數量有優化）。

## Windows 開發環境注意

- **hooks 裡使用 jq**：Windows 上 jq 輸出會帶 `\r`（carriage return），pipe 取檔案路徑時需加 `| tr -d '\r'`，否則 Python 等工具會收到帶 `\r` 的路徑而報錯。

## 導航提示

- 專案規範：`.claude\project-guidelines\SKILL.md`
- Genie 欄位對照：`.cache\views-mapping\refs\db-schema-mapping.md`
- 月報速查表：`.cache\views-mapping\monthly\refcard.md`
- 月報查詢規則：`.cache\views-mapping\monthly\query-rules.md`
- Genie Space 設定：`docs\ActualCost-config-only.json`、`docs\AmortizedCost-config-only.json`
- Python 程式碼：`src\azure_cost_mcp\`
- MCP server 組裝：`src\azure_cost_mcp\server.py`
- CLI 入口：`src\azure_cost_mcp\__main__.py`

