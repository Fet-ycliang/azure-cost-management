# 資料來源分工

## 主資料流

```text
Azure Cost Management REST API / 匯出資料 / FOCUS
                ↓
          Azure Storage
                ↓
       Databricks MCP server
                ↓
      對外提供的 MCP service
```

## 何時用哪種資料來源

### Azure Cost Management REST API

適合：

- 即時查詢
- 期間比較
- 快速做部門切片
- 快速看費用趨勢

不適合：

- 長期歷史資料沉澱
- 大量 amortized cost 分析
- 大規模批次離線整理

### Azure Cost Management exports / FOCUS

適合：

- 歷史資料保留
- 長期趨勢
- amortized cost 分析
- 後續做標準化成本資料模型

### Azure Storage

適合：

- 成本資料落地
- 保存原始匯出檔與整理後資料
- 提供 Databricks 後續查詢與聚合基礎

### Databricks MCP server

適合：

- 查詢數字
- 聚合分析
- tag audit
- tag remediation
- 後續延伸為 Databricks / Storage / VM / Network 成本診斷

## 設計建議

1. 需要快速比較時，先打 REST API。
2. 需要歷史視角時，優先看 Storage 上的匯出資料。
3. 需要做治理或實際修正時，優先規劃走 Databricks MCP server。
4. 對外 MCP service 盡量只負責協調與封裝，不直接承擔所有資料處理。
