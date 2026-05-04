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
