# Tag 治理與修正

## 第一版能力

第一版至少要支援兩種能力：

1. **tag-audit**：找出未標記或標記不完整資源
2. **tag-remediation**：修正 tag 內容

## 預設模式

預設採 **先產生修正建議** 模式。

原因：

- 比較安全
- 適合先確認規則
- 可降低誤寫風險
- 容易加入人為覆核流程

## 直接 apply 模式

可支援明確指定直接 apply，但必須同時符合：

- 有欄位白名單
- 有輸入驗證
- 有明確權限界線
- 有稽核或操作紀錄
- 有錯誤回報

## 第一版建議治理邊界

- 僅允許修改有限 tag 欄位
- 不允許任意新增不受管控的 tag key
- 對 apply 類操作保留明確旗標
- 把 dry-run 與 apply 視為不同等級操作

## 與 Databricks MCP server 的關係

在本專案中，tag remediation 目前規劃透過 **Databricks MCP server** 執行，因此：

- 對外 MCP service 不直接寫死修正邏輯
- 對外 MCP service 負責封裝輸入、驗證、模式選擇與回傳結果
- 真正的查詢與修正流程，可逐步收斂到 Databricks MCP server

## Azure Tags API 實作注意事項（Epic 3 踩坑）

### 正確的 Tag Apply API

用以下 endpoint 進行 tag **合併**寫入（Merge 語意，不刪除已有的 tag）：

```
PATCH {resource_id}/providers/Microsoft.Resources/tags/default?api-version=2021-04-01
Body: { "operation": "Merge", "properties": { "tags": { ... } } }
```

**不要**使用資源層級的 `PATCH /subscriptions/.../resourceGroups/.../providers/{type}/{name}`，那個 endpoint 的 tags 欄位語意是「全量替換」，會刪除未列出的既有 tag。

### Diff 語意限制

Tag diff 只追蹤 **`added`** 與 **`modified`**，**不追蹤 `removed`**。

原因：使用 Merge API 時，未在 body 裡出現的 tag key 會保留，所以刪除語意無法靠 Merge 做到，且大多數治理場景下誤刪 tag 的風險比誤加更高。若未來需要支援刪除，需改用 `Replace` operation 並做額外確認流程。

### desired_dir 設計

`.cache/tag-inventory/desired/{rg}.json` 在生成時**同時存入 `current_tags`**，讓 diff 工具不需重新查詢 Azure 即可比對。

格式：
```json
[
  {
    "resource_id": "/subscriptions/sub-a/.../vm-1",
    "current_tags": { "cost_center": "eng" },
    "desired_tags": { "cost_center": "eng", "Environment": "prod" }
  }
]
```

注意：若快取時間與 apply 時間相隔過久（如超過 1 天），apply 前應重確認 current state。

## Lakebase 選配整合原則（Epic 4 踩坑）

Lakebase 是 **選配層**，不是必要依賴。以下原則確保在沒有 DB 的環境中 MCP tool 仍能正常運作：

1. **所有 Lakebase 操作用 `try/except` 包住**，失敗只寫 `logger.warning()`，不 raise。
2. **`is_configured()` 先判斷**：設定未完成時直接 return，不執行任何 DB 操作。
3. **`is_ready()` 守 init**：懶初始化時先問 `is_ready()`，若 `False` 才 `await client.init()`，避免重複建連線池。
4. **環境變數 `LAKEBASE_ENABLED=false`（預設）**：不設定時整個 Lakebase 路徑靜默略過。
