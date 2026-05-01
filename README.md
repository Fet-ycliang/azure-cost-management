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

```text
Azure Cost Management REST API / Exports / FOCUS
                ↓
          Azure Storage
                ↓
       Databricks MCP server
                ↓
    Azure Cost MCP service (Python / FastMCP)
```

### 第一版資料來源

| 來源 | 用途 |
| --- | --- |
| Azure Cost Management Query API | 部門成本、趨勢、主要成本服務 |
| Benefit Recommendations API | Savings Plan 建議 |
| Reservation Recommendations API | VM / DB / Storage / App Service 等 Reservation 建議 |
| Azure Resource Graph | 找出缺少 tags 的資源 |
| Azure Blob Storage | 成本匯出落地層與資料檢查 |
| Databricks MCP server | 進階查詢、tag audit、tag remediation proxy |

## 已實作 MCP tools

| Tool | 說明 |
| --- | --- |
| `azure_cost_get_bootstrap_status` | 回報目前服務與整合設定狀態 |
| `azure_cost_get_planned_capabilities` | 回報已實作能力與後續研究焦點 |
| `azure_cost_department_cost` | 查詢指定部門成本，或列出部門成本排名 |
| `azure_cost_cost_trend` | 查詢日 / 月成本趨勢 |
| `azure_cost_cost_saving_opportunities` | 整合主要成本服務、Savings Plan 與 Reservation 建議 |
| `azure_cost_databricks_query` | 將自然語言問題或 SQL 代理到 Databricks MCP query tool |
| `azure_cost_untagged_resources` | 用 Azure Resource Graph 找出缺少必要 tags 的資源 |
| `azure_cost_tag_audit` | 優先透過 Databricks MCP server 執行 tag audit，否則回退到 Resource Graph |
| `azure_cost_tag_remediation` | 透過 Databricks MCP server 執行 tag 修正 |
| `azure_cost_list_storage_exports` | 列出 Azure Storage 中的成本匯出檔案 |

## Tag 治理策略

tag 修正支援兩種模式：

1. **預設 dry-run / recommendation mode**
2. **明確指定 apply mode**

直接套用必須同時滿足：

1. tool 呼叫時 `apply=true`
2. 環境變數 `AZURE_COST_TAG_APPLY_ENABLED=true`

這樣可以保留建議模式為預設行為，同時支援明確授權後的治理自動化。

## Databricks MCP proxy 約定

若要啟用 Databricks MCP proxy，請提供：

| 變數 | 用途 |
| --- | --- |
| `DATABRICKS_MCP_SERVER_URL` | Databricks MCP server 位址 |
| `DATABRICKS_MCP_BEARER_TOKEN` | 遠端 MCP Bearer token（若需要） |
| `DATABRICKS_MCP_TAG_AUDIT_TOOL_NAME` | 遠端 tag audit tool 名稱 |
| `DATABRICKS_MCP_TAG_REMEDIATION_TOOL_NAME` | 遠端 tag remediation tool 名稱 |
| `DATABRICKS_MCP_QUERY_TOOL_NAME` | 遠端 Databricks query tool 名稱 |

目前 proxy 會先列出遠端 tools，再確認設定的 tool name 是否存在，避免直接把請求送到不存在的 remote tool。

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

### 3. 以 stdio 啟動

```powershell
uv run azure-cost-mcp --transport stdio
```

### 4. 以 Streamable HTTP 啟動

```powershell
uv run azure-cost-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

### 5. Copilot CLI 開發輔助

- repo 已附上 `.mcp.json`，Copilot CLI 進入此專案時可直接載入 **Azure MCP server**。
- 這是開發時的 MCP 能力擴充，不是 `azure-cost-mcp` 應用本身對外提供的工具。
- 若要參考 `D:\azure_code\databricks-lineage\.mcp.json` 啟用 Databricks SQL MCP，請在本機 user config 新增 `databricks-sql`，不要直接把個人 workspace URL / token 寫進 repo-level `.mcp.json`。
- 推薦使用互動式 `/mcp add`；等價 CLI 寫法如下：

```powershell
copilot mcp add --transport http --header "Authorization: Bearer <personal-access-token>" databricks-sql https://<workspace>.azuredatabricks.net/api/2.0/mcp/sql
```

- `databricks-sql` 是給 Copilot CLI 直接使用 Databricks SQL MCP endpoint；本服務 runtime 仍使用 `DATABRICKS_MCP_*` 這組設定。
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

- `.agents\skills\azure-cost-finops\SKILL.md`

其內容承接目前這個專案的 FinOps / Azure Cost / Databricks / tag governance 規劃方向，供後續持續擴充。
