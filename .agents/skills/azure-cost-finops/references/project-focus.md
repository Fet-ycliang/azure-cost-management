# 專案焦點

## 第一版最高優先章節

1. Azure Databricks
2. Storage
3. VM
4. Network egress

這四個章節優先，是因為它們目前費用占比最高。

## 第一版核心用例

- 查詢部門費用
- 查詢節費方向與優化建議
- 查詢費用趨勢
- 找出未打標記的服務或資源
- 透過 Databricks MCP server 修正 tag 內容

## 第一版預期 MCP tools

- `department-cost`
- `cost-trend`
- `cost-saving-opportunities`
- `untagged-resources`
- `tag-audit`
- `tag-remediation`

## 第一版設計原則

- 先查詢再治理
- 先 local 驗證再上 ACA
- 先完成 Python MCP server 骨架，再串 Azure Cost Management、Storage、Databricks MCP server
- 不平均鋪開全部 Azure 服務，而是先深耕最高成本占比的四個章節
