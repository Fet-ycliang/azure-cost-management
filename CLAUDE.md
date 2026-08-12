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
- **Azure 平台 catalog**：Azure 平台資料一律使用 `rag_analyst_catalog`（表已從 `system_catalog` 搬移）。直接 SQL 查詢時使用 `rag_analyst_catalog.system_report.daily_azure_cost_usage_*`。
- Genie space config 範例問題若出現 0 結果，可能是引用了已刪除欄位（view 欄位數量有優化）。

## Tag 標準規範

- **owner tag 格式**：`姓名 (行動電話簡碼)`，例如 `Ralph Liang (527714)`。括號內的 6 位數字是員工的**行動電話簡碼**（公司內部短碼），不是員工編號，也不是其他 ID 系統。
- **已核准 owner identity mapping**：短碼 `527308` 的標準值為 `Morris Chen (527308)`；既有 `Chen, Morris 陳建宏 (527308)` 應在明確核准的範圍內正規化為此值。
- **Environment 標準值**：`dev` / `bst` / `prod`（`bst` = BST staging，對應舊 `EnvType` 的 `Staging`）
- 舊 `EnvType` 值對照：`Develop`→`dev`、`Staging`→`bst`、`Production`→`prod`
- Tag key 全小寫 snake_case；Value 小寫連字號（如 `ai-verse`）

### Tag 轉換策略（重要架構決定）

- **`cost_center` 是 Azure 層的標準 key**。既有 `CostCenter` 必須先以相同值新增 `cost_center`，確認 Merge 成功後才刪除 `CostCenter`；兩者值不同或舊值空白時不得自動覆寫。
- Key / Value 正規化在**資料層（Genie / Databricks）**做：
  - `CostCenter` → `cost_center`（legacy migration，值不變）
  - `EnvType` → `environment`（值正規化：`Production`→`prod`、`Staging`→`bst`、`Develop`→`dev`）
  - `Purpose` → `application`（值全轉小寫）
- **fill_rg_tags.py / azure_cost_tag_apply 只使用標準 key**，不寫入 legacy `CostCenter`。

## 開發踩坑規則（Epic 2–4 整合後更新）

### 文件跨檔案術語更新 SOP（2026-05）
- **跨檔案術語更新前，必須先執行全域 grep**，不能只改幾個已知檔案：
  ```powershell
  grep -rn "舊術語" --include="*.md" .
  ```
  必掃範圍：`CLAUDE.md`、`README.md`、`.claude/**/*.md`（含 `worktrees/` 副本）。
- **`.claude/worktrees/` 有各 worktree branch 的副本**，主文件更新後必須一併更新；否則 worktree branch 仍保有舊術語，下次 agent 讀取時會拿到過期資料。
- **「備注/二線」用法不是安全的**：若某功能已廢棄（例如 `system_catalog` 表已搬移），連「或舊名稱」這類備注也應一起刪除。舊位置不可用，保留備注只會造成混淆並需要多輪清理。
- **Skill 文件的三個藏雷位置**：說明文字、SQL 範例、Genie 問法 prompt 三處都可能殘留舊術語，更新時三處都要掃。

### 路徑慣例
- **`.cache/`** 是 gitignored 的暫存目錄；可執行腳本必須放在 **`scripts/`**（repo 根目錄），不要放進 `.cache/`。
- **`.cache\knowledge-base\README.md`** 是 `.cache` 知識庫總入口；tag 管理、FinOps 說明、每月成本計算比較三個主題都先從這裡進。
- **`.cache\views-mapping` 的 canonical markdown 路徑在 `monthly/` 與 `refs/` 子目錄**：`monthly/refcard.md`、`monthly/reports/YYYY-MM.md`、`refs/db-schema-mapping.md`。根目錄的 `monthly-refcard.md`、`cost-report-YYYY-MM.md`、`04-db-schema-mapping.md` 若出現，多半是 legacy 產物或空檔副本。
- **清理 `.cache\views-mapping` 舊 markdown 時，必須連 generator script 與 `.obsidian/workspace.json` 一起更新**；只刪檔不改輸出路徑，舊檔下次還會被重新產生或被工作區重新指回去。
- **Markdown 相對連結一律使用 forward slash (`../refs/db-schema-mapping.md`)**，不要用 Windows 反斜線；Windows 路徑規則只適用於 shell / PowerShell 指令，不適用於 markdown link target。

### server.py import 順序
- **在 `server.py` 的 import list 新增 model class 之前，必須先在 `models.py` 定義好**。`server.py` 的 module-level import 若引用不存在的 class，整個 server 模組會無法 import，導致所有 MCP tool 都掛掉。

### uv 依賴安裝
- **`uv sync`** 只安裝核心依賴，不安裝 optional dependency groups。
- 執行測試前需明確執行 **`uv sync --group test`**；安裝 lakebase 相關依賴需 **`uv sync --group lakebase`**。
- `[dependency-groups].test` 中需包含 `sqlalchemy[asyncio]>=2.0`，否則 ORM model 的 import 在測試時會失敗（即使不執行真實 DB 操作）。

### LakebaseClient 初始化
- **`create_mcp_server()` 是同步函數**，不能在其中 `await client.init()`。應採「懶初始化」：在每個需要 Lakebase 的 tool 內，先呼叫 `is_ready()`，若回傳 `False` 則 `await client.init()`，再執行操作。
- **`init()` 不是冪等的**：重複呼叫會覆蓋 `_engine` 但不釋放舊的 engine 連線池。永遠用 `if not client.is_ready():` 守門。
- 所有 Lakebase 呼叫都用 `try/except` 包住，失敗只 `logger.warning()`，不影響 MCP tool 的正常回傳。

### Lakebase 連線踩坑（Epic 4 Autoscaling 驗收後更新）
- **`databricks-sdk` 必須加進 `[dependency-groups].lakebase`**：`WorkspaceClient` 的 import 在 uv venv 裡若找不到 databricks-sdk，`_get_workspace_client` 會靜默回傳 `None`，導致 token 生成失敗、upsert 被 `logger.warning` 吞掉，完全沒有明顯錯誤提示。
- **`WorkspaceClient()` 讀 OS 環境變數，不讀 `.env`**：pydantic-settings 的 `.env` 只供 `Settings` class 使用；`WorkspaceClient()` 要有 `DATABRICKS_HOST`/`DATABRICKS_TOKEN` 才能正確使用 PAT 認證。解法：在 `Settings` 新增 `databricks_host`/`databricks_token` 欄位，並在 `_get_workspace_client` 明確傳入。
- **asyncpg + asyncpg SSL + SNI**：不可用 `connect_args["host"] = IP_address` 覆蓋 URL 中的 hostname，否則 TLS ClientHello 不含 SNI，Databricks Lakebase 會拒絕連線（`Connection does not have SNI`）。改用 `ssl=ssl.create_default_context()` 讓 asyncpg 用 URL hostname 進行 SNI 握手。
- **`snapshot_date` 型別**：asyncpg 的 `$2::DATE` 參數需傳 `datetime.date` 物件，不接受字串 `'2026-05-06'`（錯誤：`'str' object has no attribute 'toordinal'`）。在 `upsert_tag_snapshots` 呼叫 `_date.fromisoformat(snapshot_date)` 轉換。

### 多平台 Azure 認證（credential_fn 注入）
- **`AzureManagementApiClient` 接受 `credential_fn` 參數**：當不同 Azure 訂閱需要不同 credential 時，以 `credential_fn: Callable[[Settings], Any] | None` 注入建構子，而非在 `_request()` 裡寫死 `create_azure_credential`。`credential_fn=None` 時自動退回 `create_azure_credential`，向後相容。
- **`create_m365_credential(settings)` 三欄位同時填才生效**：`M365_COST_MANAGEMENT_TENANT` + `M365_SP_CLIENT_ID` + `M365_SP_CLIENT_SECRET` 三個欄位缺任一，自動退回 `create_azure_credential()`，不拋例外。
- **路由原則不能混淆**：`resource_graph_client` 與 `management_client`（tag 盤點 / apply 路徑）使用 `create_m365_credential`；`CostManagementClient` 與 `StorageExportClient`（Azure 平台路徑）保持預設 `create_azure_credential`。兩者若共用同一 credential，當 SP 權限範圍不含 Azure 平台訂閱時，cost query 會拿到 403。

### 測試 fixture 淺層複製
- **`dict(obj)` 是淺層複製**：module-level fixture dict 若含巢狀 dict（如 `desired_tags`），`dict(ENTRY)` 後 nested dict 仍指向同一物件。test A 若修改 `entry["desired_tags"]`，會靜默污染後續 tests（症狀：某 test 單跑 pass，全套跑 fail，且錯誤值來自另一個 test 的副作用）。
- **Fix**：對含有巢狀 mutable 值的 fixture，一律用 `copy.deepcopy(ENTRY)` 而非 `dict(ENTRY)`。

## Tag 治理踩坑規則（Epic 5 批次補標後更新）

### desired JSON 保護
- **`gen_tag_inventory_md.py` 重跑會覆蓋 desired JSON**：已補上 `--skip-desired` 旗標，更新 Obsidian 時必須加此旗標以保留已填好的值。
  ```bash
  python scripts/gen_tag_inventory_md.py --required-tags "cost_center,Purpose" --skip-desired
  ```
- **desired JSON 維護原則**：current_tags 可隨時重抓覆蓋（反映 Azure 現況）；desired_tags 是人工設定的目標值，**永遠不要讓腳本自動覆蓋**。

### remove_lowercase_tags.py 前提條件
- **必須先刷新 current_tags 快照，再執行刪除**：腳本以 `current_tags` 有無大寫 key 來判斷是否可刪小寫版本。若快照過期（大寫 key 剛補上但 current_tags 未同步），會誤判為「大寫不存在」而跳過，導致刪不掉。
- **刷新 + 刪除的正確順序**：
  1. `az resource list` 重抓 → 更新 `desired/{rg}.json` 的 `current_tags`
  2. `python scripts/remove_lowercase_tags.py --rg <rg>`

### apply_rg_tags.py 空字串語意
- desired_tags 中的空字串 `""` 代表「尚未決定」，apply 時**自動略過**（`if v and current.get(k) != v`）。
- 填值時不需特別清空欄位，留空即可等日後補上後再 apply。

### NIC / Private Endpoint tag 繼承原則
- NIC 和 Private Endpoint 應比照**其附掛的母資源**設定相同 tag。
- 命名推導規則：`<parent-name>-endpoint` → 母資源為 `<parent-name>`；`<parent-name>-endpoint-nic` → 同上。
- **先補母資源，再補 NIC/PEP**，避免繼承到空值。

### Tag value 前導/尾綴空白（Leading Whitespace）
- **Azure 不清洗 tag 值的空白**：`' Digital'`（前有空格）和 `'Digital'` 是完全不同的值，`az resource list` 會回傳兩個不同的 bucket，漏補的那群資源不會被偵測到。
- **修正方式**：在 desired_tags 中明確設 `"Purpose": "Digital"`（不含空白），apply_rg_tags.py 的 Merge 操作會自動覆蓋帶空白的舊值。
- **掃描時主動偵測**：分群時先 `p.strip()` 再比對，或在結果中列印 `repr(p)` 看是否有不可見字元。

### 多 Purpose 共用 RG 處理策略
- **大型共用 RG**（如 ABD360-RG，200+ 資源、多種 Purpose/CC）的正確流程：
  1. `az resource list` 取完整清單存為 raw JSON
  2. 按 `Purpose` tag 分群，列出各群資源數及 CC/owner 現況
  3. **逐群確認** CC / owner / EnvType 後再建 desired JSON
  4. 一次性 apply，不要分批手動改
- **不要依賴先前的估算數字**：每次都用新鮮 `az resource list` 掃描的結果建 desired JSON。

### 資源數量估算落差（cdp 踩坑）
- 早期估算 cdp 14 筆，實際掃描 31 筆。差距來自 **PEP、NIC、NSG、Disk、ACR endpoint** 等子資源常被初步分析遺漏。
- **規則**：永遠用新鮮 `az resource list` 的實際清單為準，不要用口頭估算數字建 desired JSON。

### 同名不同 type 資源（name 衝突）
- 同一 RG 中可能有同名但不同 resource type 的資源（例如 `recommend-vault` 同時是 Key Vault 本體和 DNS private zone 子資源），Python 迴圈**必須用 `resource_id`（完整 ARM path）識別**，絕不能用 `name` 去重或比對。

### Databricks auto-created NSG
- `databricksnsg*` 是 Databricks workspace 自動建立的 NSG，Purpose 通常繼承自 workspace 的 tag。
- **不要強設 EnvType**：這類資源沒有明確的環境歸屬，只需補 `cost_center` 和 `owner`，EnvType 留空（`""`）跳過。

### Purpose 值與 cost_center 對應規則
- `cost_center=3101` → `Purpose=31_ai_lab`（非 `ai_lab`，非 `OperationAI`）
- `cost_center=3901` → `Purpose=ai_verse`（非 `ai_lab`，非 `ids-bot`）
- `Purpose=cdp` → `cost_center=6251`；既有 `3101`、`3201` 或缺漏值均須正規化為 `6251`。
- 舊值對照：`OperationAI` → `31_ai_lab`；`ids-bot` → `ai_verse`；`ai_lab`（3101）→ `31_ai_lab`

### Purpose 預設值規則
- `Purpose` 預設值以 **resource group** 為單位維護，不以 `cost_center` 做全域推導。
- 大多數 RG 的 `Purpose` 一旦定案通常不變；只有少數**共用型 RG** 會允許多個合法值。
- 只有**已 review** 的 RG 才加入 `scripts/analyze_tag_gaps.py` 的 `REVIEWED_RG_PURPOSE_MAP` 做 mismatch 檢查；未 review 的 RG 先不要報 `Purpose 不符`，避免誤判。
- 已確認：`TO-ABD360 / fet-ids-prod-rg` → `cost_center=6251`、`Purpose=fet-ids`

### IDTT-AIVerse_Dev 共用訂閱規則
- `IDTT-AIVerse_Dev` 供多人共用開發；`owner` 與 `cost_center` **不設訂閱層級預設值**。
- 每個 Resource Group 需各自 review 與維護規則；混合型 RG 必須再依資源子群或直接既有 tag 判定，不得將單一 profile 套用至全 RG。
- 缺少直接證據的值維持空白，待人工確認後才納入 dry-run；禁止從全域 `cost_center → owner` 對照表推定。
- `aibde-common-rg` 的 `Microsoft.Network/privateDnsZones/virtualNetworkLinks` 屬於共用 DNS 基礎設施，固定使用 `owner=Ralph Liang (527714)`、`cost_center=3101`，不跟隨目標 VNet 的 tag。
- 同 RG 的 `Microsoft.Network/privateDnsZones` Zone 本體固定使用 `owner=Ralph Liang (527714)`、`cost_center=3101`。
- `apim-app-bst-rg` 的 `cae-fet-aiverse-01-dev` Container Apps environment、其 Private Endpoint 與 NIC 為同一 3901 子群，固定使用 `owner=John Zeng (598493)`；三者必須一致。
- 同 RG 的 `cae-fet-digital-01-dev` Container Apps environment、其 Private Endpoint 與 NIC 為同一 3201 子群，固定使用 `owner=Johnny Chen (515514)`；三者必須一致。
- `aiverse-01-sql-bst/master` 繼承母 SQL Server，固定使用 `owner=John Zeng (598493)`、`cost_center=3901`。
- 同 RG 的 `Workload=ai-gateway`、`ManagedBy=apim_deploy` 之 3201 子群固定使用 `owner=Johnny Chen (515514)`；`Owner=TBD` 視為無效值，應正規化。

### IDTT Info cost center 規則
- `IDTT-AIVerse_Prod / fet-idtt-info-rg` 的所有非系統資源固定使用 `cost_center=3901`，包含跨訂閱目標的 Private DNS VNet link。
- 此規則只決定 `cost_center`；`owner` 必須獨立依直接既有 tag 或人工 review 決定，不得因 cost center 自動推定。

### IDTT 已確認統一 RG profile
- `IDTT-AIVerse_Dev / fet-rag-bst-rg`：所有非系統資源使用 `owner=Ralph Liang (527714)`、`cost_center=3101`。
- `IDTT-AIVerse_Dev / fet-aifndry-bst-rg`：所有非系統資源使用 `owner=John Zeng (598493)`、`cost_center=3901`。
- `IDTT-AIVerse_Dev / fet-ai-km-dev-rg`：所有非系統資源使用 `owner=Lili Huang (598520)`；既有 `cost_center`、`Purpose` 與 `EnvType` 維持各資源原值。
- `IDTT-AIVerse_Dev / ppenv-3901-dev-rg` 與 `ppenv-3901-prod-rg`：所有可標記的非系統資源使用 `owner=Ralph Liang (527714)`、`cost_center=3101`。已連結 environment 的 `Microsoft.PowerPlatform/enterprisePolicies` 例外。
- `IDTT-AIVerse_Prod / fet-ebu-aiverse-prod` 與 `fet-ebu-mess-prod`：所有非系統資源使用 `owner=Jeff Yu (597061)`、`cost_center=3901`。
- `IDTT-AIVerse_Prod / fet-idtt-info-out-rg`：所有非系統資源使用 `owner=Lili Huang (598520)`、`cost_center=3901`。
- `IDTT-AgentAssistant / fet-process-prod-rg`：所有非系統資源使用 `owner=Jerry Lin (525241)`、`cost_center=7201`。
- `IDTT-AIVerse_Dev / fet-aigw-dev`：所有非系統資源使用 `owner=Kevin Hung (527501)`、`cost_center=3501`、`Purpose=IT_llm`、`EnvType=Develop`。
- `IDTT-AgentAssistant / fet-aigw-prod`：所有非系統資源使用 `owner=Kevin Hung (527501)`、`cost_center=3501`、`Purpose=IT_llm`、`EnvType=Production`。

### Databricks Workspace 不加 Purpose
- **`Microsoft.Databricks/workspaces` 一律不補 `Purpose` tag**。
- Databricks workspace 由平台服務管理，`databricks-cluster` 等系統 tag 由服務自動維護；`Purpose` 在此層級無意義且可能被服務覆蓋。
- apply_rg_tags.py 建立 desired JSON 時，ADB workspace 的 `desired_tags.Purpose` 設為空字串（`""`）跳過。
- 規則適用範圍：所有 RG 下的 ADB workspace，不論 `Purpose` 是否已存在。

### current_tags 快照更新腳本
使用正式腳本更新，支援全部或單一 RG，並自動統一格式（`id` → `resource_id`）：
```bash
# 全部更新
python scripts/refresh_current_tags.py

# 單一 RG
python scripts/refresh_current_tags.py --rg <rg-name>
```

**格式規範（desired JSON 標準欄位）：**
`resource_id`, `name`, `type`, `current_tags`, `desired_tags`
- 舊格式有 `id` + `resource_group` 欄位（如 fabric-prod-rg 初版），`refresh_current_tags.py` 執行時會自動正規化。

## Windows 開發環境注意

- **hooks 裡使用 jq**：Windows 上 jq 輸出會帶 `\r`（carriage return），pipe 取檔案路徑時需加 `| tr -d '\r'`，否則 Python 等工具會收到帶 `\r` 的路徑而報錯。
- **`uv run` 被執行中的 server 鎖住**：MCP server 執行中時，`uv run python scripts/xxx.py` 會失敗（`error: failed to remove file azure-cost-mcp.exe: 程序無法存取檔案`），因為 uv 試圖更新鎖定中的 `.exe`。**Fix**：改用 `python scripts/xxx.py` 直接呼叫，不透過 `uv run`。
- **部分 Azure 子資源不支援 tag PATCH**：`Microsoft.Automation/automationAccounts/runbooks` 中某些 runbook 執行 `az tag update` 會回傳 `ProviderError: The requested resource does not support http method 'PATCH'`。這是平台限制，非腳本 bug；`apply_rg_tags.py` 已有 `[error]` 繼續執行的機制，此類資源直接略過即可。
- **已連結 environment 的 Enterprise Policy 不可更新 tag**：`Microsoft.PowerPlatform/enterprisePolicies` 的 generic tag PATCH 會回傳 `EnterprisePolicyUpdateNotAllowed`。不可為補 tag 解除 environment 連結；維持排除於 tag gap audit，並記錄為平台例外。
- **Resource ID 含括號時 subprocess list form 會失敗**：`az.cmd` 在 Windows 上透過 cmd.exe 執行，括號 `(` `)` 是 CMD 的群組字元。呼叫 `az` 時若 resource ID 含括號（如 `ContainerInsights(xxx)`、`SecurityCenterFree(xxx)`），用 list form 傳入參數，cmd.exe 仍會解析括號導致 "不應有 --operation / --query" 等錯誤。**Fix**：改用 `shell=True` 並以雙引號包裹 resource ID 與含特殊字元的 tag 值：
  ```python
  tag_str = ' '.join(f'"{k}={v}"' for k, v in to_add.items())
  cmd = f'az tag update --resource-id "{rid}" --operation Merge --tags {tag_str}'
  result = subprocess.run(cmd, shell=True, ...)
  ```

## Azure CLI / VM 維運踩坑

### az login --service-principal 取代 user session
- **`az login --service-principal`** 執行後，目前的 user credential 會被 SP session **取代**，不是並存。
- SP 操作完成後，原本的 user az session **已消失**，`az account set` 會報 "no active accounts"。
- **每次使用 SP 登入做完操作後，必須重新執行 `az login` 恢復 user session**。
- 建議作業模式：SP 登入 → 執行操作 → `az logout` → `az login` 恢復。
- abd-adls SP（Contributor on TO-ABD360）的 secret 在 `.env` 的 `token_abd-adls` 欄位；使用時用 `Get-Content .env | Select-String "token_abd-adls"` 取得。

### VM Resize 作業流程
- **先 dev，觀察 1–2 週，再 prod**：不要因為 Advisor 建議就直接操作 prod。
- VM resize 會觸發重開機，應在非尖峰時段執行。
- 執行命令：`az vm resize -g <resource-group> -n <vm-name> --size <target-sku>`
- 執行後 `provisioningState` 需為 `Succeeded` 才算完成；失敗時回 `az vm show` 確認實際 SKU。

## Databricks Embedding Endpoint 踩坑規則

### Endpoint URL 格式（非 AI Gateway）
- **`DatabricksEmbeddingClient` 支援兩種 URL 格式**，但語意不同：
  - AI Gateway 路徑：`https://<workspace>/ai-gateway/mlflow/v1/embeddings`（多模型路由）
  - Serving Endpoint 直連：`https://<workspace>/serving-endpoints/<name>/invocations`（單一端點）
- **External Model 類型的 serving endpoint 直接用 `/invocations` 路徑**，回應是 OpenAI-compatible 格式（`data[].embedding`），程式碼 parsing 相容，不需修改 `embedding.py`。

### .env 設定對應 serving endpoint
```env
DATABRICKS_EMBEDDING_URL=https://<workspace>.azuredatabricks.net/serving-endpoints/<endpoint-name>/invocations
DATABRICKS_EMBEDDING_MODEL=<endpoint-name>     # 填 endpoint 名稱，不是底層模型名
DATABRICKS_EMBEDDING_DIM=1536                  # text-embedding-3-small = 1536；BGE-Large-EN = 1024
```

### Token 是 workspace-scoped
- **`DATABRICKS_TOKEN` 只對發行它的 workspace 有效**；跨 workspace 呼叫直接回 403 `Invalid access token`。
- 多 workspace 環境查 `~/.databrickscfg` 找正確 profile，例如：
  - `[develop]` → `adb-6748704777045471.11`
  - `[azure-rag-bst]` → `adb-2654999172504234.14`

### Azure OpenAI VNet 限制 × Databricks External Model

- **External Model 服務端流量走 Databricks 控制平面（NAT gateway），不走 customer VNet。**
  - 因此 Azure OpenAI 上設定的 VNet rules（customer subnet）對此流量**無效**。
  - 必須在 Azure OpenAI 的 **IP firewall rules**（`ipRules`）加入 Databricks 控制平面的 egress IP。

- **Southeast Asia Databricks egress CIDR（截至 2026-07）**：
  ```
  13.67.21.136/29
  20.43.41.152/29
  20.43.65.144/29
  20.43.130.96/28
  20.195.138.176/29
  20.195.154.152/29
  52.187.0.85
  52.187.3.203
  52.187.145.107
  ```
  > 注意：單一 IP（`/32`）Azure OpenAI **不接受**，直接填裸 IP（不加 `/32`）。

- **加入 IP rules 的 CLI 指令**：
  ```powershell
  az cognitiveservices account network-rule add \
      --name "<aoai-resource>" \
      --resource-group "<rg>" \
      --subscription "<subscription>" \
      --ip-address <cidr-or-ip>
  ```

- **取得最新 Databricks IP 清單（ServiceTags JSON）**：
  ```powershell
  # 1. 查最新檔名
  $page = Invoke-WebRequest "https://www.microsoft.com/en-us/download/details.aspx?id=56519" -UseBasicParsing
  $file = ($page.Content | Select-String "ServiceTags_Public_\d+\.json").Matches.Value
  # 2. 下載並過濾 Southeast Asia
  Invoke-WebRequest "https://download.microsoft.com/download/7/1/D/71D86715-5596-4529-9B13-DA13A5DE5B63/$file" -OutFile "$env:TEMP\svc.json" -UseBasicParsing
  $data = Get-Content "$env:TEMP\svc.json" -Raw | ConvertFrom-Json
  ($data.values | Where-Object name -eq "AzureDatabricks").properties.addressPrefixes | Where-Object { $_ -match "^(13\.67|20\.43|20\.195|52\.187)" }
  ```

## Copilot Memory 使用注意

- `/memory` 是 Copilot CLI 的**互動 slash command**，**不是** shell 指令，agent 無法代替使用者執行。
- 需要在 CLI prompt 直接輸入 `/memory` 才能查看狀態或啟用/停用。
- Memory 分兩層：**repo-level facts**（任何方案可用）與 **user-level preferences**（需 Pro/Pro+）。
- 28 天未更新自動到期（TTL）；enterprise/org 預設關閉；個人 Pro 預設開啟。
- Copilot Memory 啟用後，CLI 會在工作過程中自動累積此 repo 的 context，下次 session 不需重新說明。

## 語言規範速查

| 情境 | 語言 |
|---|---|
| README、文件、docstring、code comment、commit message、error message | **繁體中文** |
| 程式識別子（變數、函式、class）、技術術語（FastMCP, Docker, OAuth） | **英文** |
| 國際開源貢獻或需跨國協作 | 英文 |

- **Commit message 格式**：`type: 繁體中文描述`（type 英文：`feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`）
- **docstring 樣式**：Google Style，欄位標籤繁中（`參數:`, `回傳:`, `引發:`）

## Git 流程

- **分支策略**：新功能 / bugfix 先進 `develop`；`main` 只接受來自 `develop` 的合併。
- **合入 main**：一律 `git merge --no-ff <branch>`，保留分支歷史，不允許 fast-forward。

## Azure DevOps 踩坑規則

### Task 狀態流程（強制順序）

```
New → To Do → In Progress → Done
```

禁止跳過中間狀態；禁止建立後直接設 Done。

### 建立 Task 的正確三步驟

❌ **禁止用 `wit_add_child_work_items`**（Area Path 權限問題）

✅ 改用：
1. `wit_create_work_item`（帶 `System.AreaPath`，初始狀態預設 To Do）
2. `wit_work_items_link`（批次建立 parent 連結）
3. `wit_update_work_item` → `In Progress` → `Done`，只填 `CompletedWork`

### 其他 ADO 陷阱

- **禁止設 `RemainingWork=0`**（ADO 報 `InvalidNotEmpty`）
- **PBI `Effort` 欄位**在 Done 狀態為唯讀，須在 New / Approved 時設定
- **描述格式**：`System.Description` 必須用 HTML（`<h3>`, `<p>`, `<ul><li>`），不能用 Markdown（`## `、backtick、`- [x]`，ADO 不渲染）
- **Work item URL 格式**：`https://dev.azure.com/FET-IDTT/5c1d1372-d7f9-44cb-a3df-42a44a0cc770/_workitems/edit/{id}`

## Copilot Studio Agent 路由

| 需求類型 | 使用子 Agent |
|---|---|
| 設計建議（how should I build…） | **Advisor** |
| 建立 / 修改 agent 功能 | **Author** |
| 審查 / 稽核 agent YAML | **Advisor** |
| 問題排查（topic 不觸發、hallucination、驗證錯誤） | **Advisor** |
| 測試 / 評估 | **Test** |
| clone / push / pull / publish | **Manage** |

- **Author 前提**：workspace 必須有 `agent.mcs.yml`；沒有則先用 **Manage** clone，再交給 Author。
- **Skill 限制**：skills 只用於簡單資訊查詢；建立、修改、排查、測試一律走子 Agent，不直接呼叫 skill 代勞。

## copilot-instructions 維護原則

- **`.github/copilot-instructions.md`** 存在於 **repo root**，供 GitHub Copilot CLI 讀取；不是 worktree 副本。
- 內容維持**輕量版**：開發指令速查 + 架構表 + 關鍵慣例要點，完整規則指向 `CLAUDE.md`。
- 更新 `CLAUDE.md` 的規則後，**不需要同步回 `copilot-instructions.md`**（指標頁不含規則本身）。
- worktree 的 `.github/copilot-instructions.md` 副本應保持與 root 同步（同樣輕量版）。

## 導航提示

- **Copilot 工作規則（本檔）**：`CLAUDE.md`
- **Copilot 快速入口（輕量版）**：`.github\copilot-instructions.md`
- 專案規範：`.claude\project-guidelines\SKILL.md`
- `.cache` 知識庫總入口：`.cache\knowledge-base\README.md`
- `.cache` 知識庫使用手冊：`.cache\knowledge-base\usage-guide.md`
- Genie 欄位對照：`.cache\views-mapping\refs\db-schema-mapping.md`
- 月報速查表：`.cache\views-mapping\monthly\refcard.md`
- 月報查詢規則：`.cache\views-mapping\monthly\query-rules.md`
- Genie Space 設定：`docs\ActualCost-config-only.json`、`docs\AmortizedCost-config-only.json`
- Python 程式碼：`src\azure_cost_mcp\`
- MCP server 組裝：`src\azure_cost_mcp\server.py`
- CLI 入口：`src\azure_cost_mcp\__main__.py`
- Tag 盤點 MD 生成：`scripts\gen_tag_inventory_md.py`（產生 Obsidian + desired JSON）
- Tag 批次填值：`scripts\fill_rg_tags.py`（`--dry-run` 先確認再執行；`--overwrite` 強制覆蓋已有值）
- Tag 批次套用：`scripts\apply_rg_tags.py --rg <rg> [--dry-run]`（空字串 desired 自動跳過）
- 小寫 tag 刪除：`scripts\remove_lowercase_tags.py --rg <rg> [--dry-run]`（需先刷新 current_tags 快照）
- **current_tags 刷新：`scripts\refresh_current_tags.py [--rg <rg>]`**（全部或單一 RG，自動正規化格式）


## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
