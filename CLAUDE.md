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

## Tag 標準規範

- **owner tag 格式**：`姓名 (行動電話簡碼)`，例如 `Ralph Liang (527714)`。括號內的 6 位數字是員工的**行動電話簡碼**（公司內部短碼），不是員工編號，也不是其他 ID 系統。
- **Environment 標準值**：`dev` / `bst` / `prod`（`bst` = BST staging，對應舊 `EnvType` 的 `Staging`）
- 舊 `EnvType` 值對照：`Develop`→`dev`、`Staging`→`bst`、`Production`→`prod`
- Tag key 全小寫 snake_case；Value 小寫連字號（如 `ai-verse`）

### Tag 轉換策略（重要架構決定）

- **舊 tag key 不在 Azure 層改名**，保留 `CostCenter`、`EnvType`、`Purpose` 原樣。
- Key / Value 正規化在**資料層（Genie / Databricks）**做，不在 Azure 做：
  - `CostCenter` → `cost_center`（值不變）
  - `EnvType` → `environment`（值正規化：`Production`→`prod`、`Staging`→`bst`、`Develop`→`dev`）
  - `Purpose` → `application`（值全轉小寫）
- **fill_rg_tags.py / azure_cost_tag_apply 只補真正缺漏的 key**（`workload`、`owner`），不重複寫舊 key 的新命名版本。

## 開發踩坑規則（Epic 2–4 整合後更新）

### 路徑慣例
- **`.cache/`** 是 gitignored 的暫存目錄；可執行腳本必須放在 **`scripts/`**（repo 根目錄），不要放進 `.cache/`。

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
  python scripts/gen_tag_inventory_md.py --required-tags "CostCenter,Purpose" --skip-desired
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
- **不要強設 EnvType**：這類資源沒有明確的環境歸屬，只需補 `CostCenter` 和 `owner`，EnvType 留空（`""`）跳過。

### Purpose 值與 CostCenter 對應規則
- `CostCenter=3101` → `Purpose=31_ai_lab`（非 `ai_lab`，非 `OperationAI`）
- `CostCenter=3901` → `Purpose=ai_verse`（非 `ai_lab`，非 `ids-bot`）
- 舊值對照：`OperationAI` → `31_ai_lab`；`ids-bot` → `ai_verse`；`ai_lab`（3101）→ `31_ai_lab`

### Purpose 預設值規則
- `Purpose` 預設值以 **resource group** 為單位維護，不以 `CostCenter` 做全域推導。
- 大多數 RG 的 `Purpose` 一旦定案通常不變；只有少數**共用型 RG** 會允許多個合法值。
- 只有**已 review** 的 RG 才加入 `scripts/analyze_tag_gaps.py` 的 `REVIEWED_RG_PURPOSE_MAP` 做 mismatch 檢查；未 review 的 RG 先不要報 `Purpose 不符`，避免誤判。
- 已確認：`TO-ABD360 / fet-ids-prod-rg` → `CostCenter=6251`、`Purpose=fet-ids`

### current_tags 快照更新腳本
手動刷新單一 RG 的快照並 patch desired JSON：
```python
import json, subprocess
AZ = 'az.cmd'
resources = json.loads(subprocess.run(
    [AZ, 'resource', 'list', '--subscription', SID, '--resource-group', RG],
    capture_output=True, text=True).stdout)
lookup = {r['id']: r.get('tags') or {} for r in resources}
data = json.loads(open(f'.cache/tag-inventory/desired/{RG}.json', encoding='utf-8').read())
for e in data:
    if e['resource_id'] in lookup:
        e['current_tags'] = lookup[e['resource_id']]
open(f'.cache/tag-inventory/desired/{RG}.json', 'w', encoding='utf-8').write(
    json.dumps(data, ensure_ascii=False, indent=2))
```

## Windows 開發環境注意

- **hooks 裡使用 jq**：Windows 上 jq 輸出會帶 `\r`（carriage return），pipe 取檔案路徑時需加 `| tr -d '\r'`，否則 Python 等工具會收到帶 `\r` 的路徑而報錯。
- **`uv run` 被執行中的 server 鎖住**：MCP server 執行中時，`uv run python scripts/xxx.py` 會失敗（`error: failed to remove file azure-cost-mcp.exe: 程序無法存取檔案`），因為 uv 試圖更新鎖定中的 `.exe`。**Fix**：改用 `python scripts/xxx.py` 直接呼叫，不透過 `uv run`。

## 導航提示

- 專案規範：`.claude\project-guidelines\SKILL.md`
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

