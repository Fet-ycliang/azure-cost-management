# Copilot Instructions for Azure Cost MCP

## 專案定位

這個 repo 是一個 **Python FastMCP 服務**，目標是提供 Azure FinOps 查詢與治理能力。第一版焦點不是通用雲端工具，而是這個專案已經明確定義的五個高價值用例：

1. 部門費用查詢
2. 費用趨勢查詢
3. 節費方向與 Reservation / Savings Plan 建議
4. 未標記資源與 tag 治理
5. 透過 Databricks MCP server 查詢 Storage 上的成本資料

成本優先順序固定以 **Azure Databricks、Storage、VM、Network egress** 為主。

## Build / run / validation commands

### 安裝依賴

```powershell
uv sync
```

### 本機啟動

```powershell
uv run azure-cost-mcp --transport stdio
uv run azure-cost-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

### 容器建置與執行

```powershell
docker build -t azure-cost-mcp:local .
docker run --rm -p 8000:8000 --env-file .env azure-cost-mcp:local
```

### 目前 repo 內可用的輕量驗證

```powershell
uv run python -m compileall src\azure_cost_mcp
uv run azure-cost-mcp --help
```

目前 **沒有** 已配置的 `pytest`、`ruff`、`mypy`、`nox` 或單一測試執行命令；如果新增測試框架，請同步更新這份文件。

## 高階架構

### 啟動與組裝

- `src\azure_cost_mcp\__main__.py` 是 CLI 入口。
- CLI 只負責讀取 transport / host / port / path，然後用 `create_mcp_server()` 啟動 FastMCP。
- `src\azure_cost_mcp\server.py` 是組裝中心：建立 settings、client、tool 註冊與回應整形 helper。

### 設定來源

- `src\azure_cost_mcp\config.py` 是所有 runtime 設定的唯一來源。
- 所有環境變數都透過 `Settings` 的 `validation_alias` 定義。
- `get_settings()` 有 cache；CLI 參數覆蓋是用 `model_copy(update=...)` 套上去，不是直接改環境變數。

### Azure 管理平面整合

- `src\azure_cost_mcp\azure_management.py` 提供共用的 Azure 管理平面 client。
- 這裡統一處理 `DefaultAzureCredential`、`https://management.azure.com/.default` token、`httpx.AsyncClient` 與錯誤格式化。
- 新的 Azure REST 整合應優先建立專屬 client module，並重用這個 base client，不要把裸 HTTP request 直接塞進 tool handler。

### 成本與建議來源

- `src\azure_cost_mcp\cost_management.py`
  - Query API：部門成本、趨勢、主要服務成本
  - Benefit Recommendations API：Savings Plan 建議
  - Reservation Recommendations API：Reservation 建議
  - 內建 pagination 合併與 `rows -> dict` 正規化

### 資源治理與資料來源

- `src\azure_cost_mcp\resource_graph.py`
  - 用 Azure Resource Graph 找缺少 tags 的資源
  - 若呼叫端沒給 subscriptions，會從 `AZURE_COST_MANAGEMENT_SCOPE` 推導預設 subscription
- `src\azure_cost_mcp\storage.py`
  - 用 Blob Storage 列出成本匯出檔案
  - 同樣走 `DefaultAzureCredential`

### Databricks MCP proxy

- `src\azure_cost_mcp\databricks_mcp.py` 不是直接打 Databricks REST，而是透過遠端 MCP server。
- proxy 會先 `list_tools()`，再驗證 `DATABRICKS_MCP_*_TOOL_NAME` 是否真的存在，才允許 `call_tool()`。
- `server.py` 中的 Databricks 相關 tools 都依賴這個 proxy layer。

### 工具輸入與輸出

- `src\azure_cost_mcp\models.py` 定義每個 tool 的 Pydantic 輸入模型。
- `src\azure_cost_mcp\formatting.py` 統一將 payload 轉成 markdown 或 JSON。
- 大多數 tools 都接受 `response_format`，並且應透過 `to_response()` 回傳，不要自己各寫一套格式。

## 關鍵慣例

### 文字語言慣例

- repo 內的人類可讀內容以 **繁體中文** 為主：
  - `README.md`
  - `.env.example` 註解
  - docstring
  - code comments
  - user-facing error / message
- 程式識別子與技術名詞維持英文，例如 `FastMCP`、`DefaultAzureCredential`、`streamable-http`。

### MCP tool 設計慣例

- tool 名稱一律使用 `azure_cost_` 前綴。
- 新增 tool 時，通常要同步更新：
  - `server.py` 的 tool 註冊
  - `IMPLEMENTED_TOOLS`
  - `README.md` 的 MCP tools 表格
- 這個 repo 的 tools 目前是「單一 Pydantic 參數模型」模式；用 MCP client 呼叫時，arguments shape 要像：

```json
{
  "params": {
    "response_format": "json"
  }
}
```

不要直接傳平面 arguments。

### 設定與 secrets 慣例

- 不要硬寫 scope、token、storage URL 或 remote tool 名稱。
- 新設定一定要同時更新：
  1. `config.py`
  2. `.env.example`
  3. 相關 README 說明（如果是使用者要設定的項目）

### Tag 治理慣例

- tag remediation 預設是 **建議 / dry-run**，不是直接 apply。
- 只有在：
  1. tool 參數 `apply=true`
  2. `AZURE_COST_TAG_APPLY_ENABLED=true`

  同時成立時，才允許直接套用。

- `tag-audit` 的優先順序是：
  1. Databricks MCP proxy
  2. Azure Resource Graph fallback

### 資料來源選擇慣例

- 即時切片 / 部門成本 / 趨勢：先用 Cost Management Query API
- Savings Plan / Reservation 判斷：先用 recommendations APIs
- 未標記資源：先用 Azure Resource Graph
- 大量歷史資料或 Storage 上的分析：走 Databricks MCP server + Storage

### 部署慣例

- `Dockerfile` 預設以 `streamable-http` 在 `8000` port 暴露 `/mcp`。
- 若部署到 ACA，預設仍沿用這個 transport / port / path 組合，不要任意改成其他入口格式，除非同時更新 README 與 `.env.example`。

## Repo-level MCP servers

- 這個 repo 已提供 `.mcp.json`，預設幫 Copilot CLI 啟用 **Azure MCP server**。
- 這是給「開發時的 Copilot 能力擴充」用，不影響 `azure-cost-mcp` 這個應用本身的 runtime。
- 若要參考 `D:\azure_code\databricks-lineage\.mcp.json` 啟用 Databricks SQL MCP，請改在**本機 user config** 新增 `databricks-sql`，不要直接寫進 repo-level `.mcp.json`，因為它需要每位開發者自己的 Databricks workspace URL 與 PAT。
- 推薦用互動式 `/mcp add`；等價 CLI 寫法如下：

```powershell
copilot mcp add --transport http --header "Authorization: Bearer <personal-access-token>" databricks-sql https://<workspace>.azuredatabricks.net/api/2.0/mcp/sql
```

- `databricks-sql` 是給 Copilot CLI 直接使用 Databricks SQL MCP endpoint；`azure-cost-mcp` 應用本身的 Databricks proxy 仍沿用 `DATABRICKS_MCP_*` 這組 runtime 設定。
- 不要把實際 Databricks URL、PAT token 或其他密鑰提交進 repo。
