# Copilot Instructions

> **主來源：[`CLAUDE.md`](../CLAUDE.md)**（語言規範、Git 流程、ADO 踩坑、Copilot Studio Agent 路由、計費口徑、tag 治理踩坑、Lakebase 踩坑）。  
> **架構與部署細節：[`README.md`](../README.md)**。

---

## 開發環境速查

```powershell
uv sync                    # 安裝核心依賴
uv sync --group test       # 安裝測試依賴
uv sync --group lakebase   # 安裝 Lakebase 相關依賴（asyncpg / alembic / databricks-sdk）
uv run pytest              # 執行全套測試（80% coverage 門檻）
uv run pytest tests/test_server_tools.py            # 執行單一測試檔
uv run pytest tests/test_server_tools.py::test_foo  # 執行單一測試函式

uv run azure-cost-mcp --transport stdio
uv run azure-cost-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

> MCP server 執行中時 `uv run` 會鎖住 `.exe`，改用 `python scripts/xxx.py` 直接呼叫。

---

## 高階架構

| 模組 | 職責 |
|---|---|
| `src/azure_cost_mcp/__main__.py` | CLI 入口，解析 transport / host / port |
| `src/azure_cost_mcp/server.py` | FastMCP 組裝中心；tool 註冊 |
| `src/azure_cost_mcp/config.py` | 所有設定的唯一來源（pydantic-settings） |
| `src/azure_cost_mcp/auth.py` | Azure 驗證模式 helper（DefaultAzureCredential / SP 注入） |
| `src/azure_cost_mcp/cost_management.py` | Cost Management Query / Benefit / Reservation APIs |
| `src/azure_cost_mcp/azure_management.py` | Azure 管理平面共用 client（httpx + credential 注入） |
| `src/azure_cost_mcp/resource_graph.py` | Azure Resource Graph（tag 缺漏偵測） |
| `src/azure_cost_mcp/storage.py` | Azure Storage 成本匯出資料 helper |
| `src/azure_cost_mcp/cache.py` | 成本資料快取 helper |
| `src/azure_cost_mcp/databricks_mcp.py` | Databricks MCP proxy（不直接打 REST） |
| `src/azure_cost_mcp/embedding.py` | Databricks AI Gateway embedding client |
| `src/azure_cost_mcp/lakebase.py` | Lakebase（PostgreSQL）非同步連線管理（OAuth token refresh） |
| `src/azure_cost_mcp/lakebase_models.py` | Lakebase ORM 模型（SQLAlchemy + pgvector） |
| `src/azure_cost_mcp/learn.py` | Microsoft Learn 文件搜尋 client（公開 API，無需認證） |
| `src/azure_cost_mcp/models.py` | Pydantic 輸入模型（每個 tool 一個 model） |
| `src/azure_cost_mcp/formatting.py` | Markdown / JSON 輸出整形 |
| `scripts/` | Tag 治理腳本（refresh / apply / fill / remove） |

---

## 關鍵慣例

- **MCP tool 前綴**：`azure_cost_`
- **新增設定**：同步更新 `config.py` + `.env.example` + `README.md`
- **Tag apply**：預設 dry-run；需 `apply=true` **且** `AZURE_COST_TAG_APPLY_ENABLED=true` 才真正套用
- **Databricks 成本口徑**：預設 `AmortizedCost`（`ActualCost` 可能為 0）
- **Rate limit**：Cost Management API 4 req/min；遇 429 讀 `Retry-After`，不可全局重試
- **`server.py` import**：新 model class 必須先在 `models.py` 定義，再加進 import list
- **fixture 複製**：含巢狀 dict 的 fixture 用 `copy.deepcopy()`，不用 `dict()`

完整規則請見 **[`CLAUDE.md`](../CLAUDE.md)**。
