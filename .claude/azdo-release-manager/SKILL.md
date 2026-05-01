---
name: azdo-release-manager
description: |
  Azure DevOps 發布管理與文件生成助手。自動生成 Release Notes、Sprint 總結、Wiki 文檔。
  觸發詞: "generate release notes", "發布文檔", "sprint review", "產生變更記錄", "發布總結"
---

# Azure DevOps Release Manager

自動化發布管理工作流程，包含 Release Notes 生成、Sprint 總結、Wiki 文檔發布。

## 核心功能

### 1. Release Notes 生成

從 commits、pull requests 和 work items 自動產生結構化的發布說明。

**基本工作流程：**

```python
# 範例：生成 Release Notes
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_repo_search_commits
# - mcp_microsoft_azu_repo_list_pull_requests_by_commits
# - mcp_microsoft_azu_wit_get_work_items_batch_by_ids
# - mcp_microsoft_azu_wiki_create_or_update_page

async def generate_release_notes(project, repo, since_date, target_date):
    """
    生成發布說明文檔
    
    Args:
        project: Azure DevOps 專案名稱
        repo: Repository 名稱
        since_date: 起始日期（格式：YYYY-MM-DD）
        target_date: 結束日期（格式：YYYY-MM-DD）
    
    Returns:
        發布說明的 Markdown 內容
    """
    # 1. 搜尋指定期間的 commits
    commits = search_commits(project, repo, since_date, target_date)
    
    # 2. 取得相關的 Pull Requests
    prs = get_prs_by_commits(project, repo, commits)
    
    # 3. 從 PRs 中提取連結的 work items
    work_item_ids = extract_work_item_ids(prs)
    
    # 4. 取得 work items 詳細資訊
    work_items = get_work_items(project, work_item_ids)
    
    # 5. 分類整理變更
    categorized_changes = categorize_changes(work_items, prs)
    
    # 6. 生成 Markdown 文檔
    release_notes = format_release_notes(categorized_changes)
    
    # 7. 發布到 Wiki（可選）
    publish_to_wiki(project, release_notes)
    
    return release_notes
```

**變更分類：**
- 🚀 **新功能** (Feature / User Story)
- 🐛 **Bug 修復** (Bug)
- 🔧 **改進優化** (Task / Improvement)
- 📚 **文檔更新** (Documentation)
- ⚠️ **重大變更** (Breaking Change)

### 2. Sprint Review 總結

自動產生 Sprint 完成情況報告。

**工作流程：**

```python
# 範例：生成 Sprint 總結
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_work_list_iterations
# - mcp_microsoft_azu_wit_get_work_items_for_iteration
# - mcp_microsoft_azu_wit_get_work_items_batch_by_ids

async def generate_sprint_summary(project, team, iteration_path):
    """
    生成 Sprint 總結報告
    
    Args:
        project: 專案名稱
        team: 團隊名稱
        iteration_path: 迭代路徑（例如：Sprint 1）
    
    Returns:
        Sprint 總結的 Markdown 內容
    """
    # 1. 取得迭代中的 work items
    work_items = get_iteration_work_items(project, team, iteration_path)
    
    # 2. 統計完成情況
    stats = calculate_sprint_stats(work_items)
    
    # 3. 識別關鍵成就
    key_accomplishments = identify_key_features(work_items)
    
    # 4. 識別風險和阻礙
    risks_and_blockers = identify_risks(work_items)
    
    # 5. 生成報告
    summary = format_sprint_summary(stats, key_accomplishments, risks_and_blockers)
    
    return summary
```

**包含內容：**
- ✅ **完成統計**：已完成 vs 計劃的工作項目
- 📊 **速度追蹤**：Story Points / 工作時數
- 🎯 **關鍵成就**：主要功能和改進
- ⚠️ **風險識別**：阻礙和未完成項目
- 📈 **團隊容量**：實際 vs 計劃容量

### 3. Wiki 文檔管理

創建和維護結構化的 Wiki 文檔。

**工作流程：**

```python
# 範例：更新 Wiki 頁面
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_wiki_get_wiki
# - mcp_microsoft_azu_wiki_create_or_update_page
# - mcp_microsoft_azu_wiki_list_pages

async def update_wiki_documentation(project, wiki_name, page_path, content):
    """
    更新 Wiki 頁面
    
    Args:
        project: 專案名稱
        wiki_name: Wiki 識別碼
        page_path: 頁面路徑（例如：/Release-Notes/v1.0.0）
        content: Markdown 內容
    """
    # 1. 檢查 Wiki 是否存在
    wiki = get_wiki(project, wiki_name)
    
    # 2. 創建或更新頁面
    page = create_or_update_page(project, wiki_name, page_path, content)
    
    return page
```

## 常用範本

### Release Notes 範本

```markdown
# Release v{version} - {date}

## 🚀 新功能
- [#{work_item_id}] {標題} (@{作者})
  {簡短描述}

## 🐛 Bug 修復
- [#{work_item_id}] {標題} (@{作者})
  {問題描述與修復說明}

## 🔧 改進優化
- [#{work_item_id}] {標題} (@{作者})
  {改進內容}

## ⚠️ 重大變更
- {變更描述}
  - **影響範圍**: {說明}
  - **遷移指南**: {步驟}

## 📚 文檔更新
- {文檔變更列表}

## 🙏 貢獻者
{貢獻者列表}
```

### Sprint Summary 範本

```markdown
# Sprint {number} Review - {start_date} to {end_date}

## 📊 Sprint 統計
- **完成率**: {完成數}/{計劃數} ({百分比}%)
- **Story Points**: {完成點數}/{計劃點數}
- **速度**: {平均速度}
- **團隊容量**: {實際}/{計劃} 小時

## 🎯 關鍵成就
1. {主要功能 1}
   - Work Item: #{id}
   - 價值: {業務價值說明}

2. {主要功能 2}
   - Work Item: #{id}
   - 價值: {業務價值說明}

## ⚠️ 風險與阻礙
- {風險項目 1}
  - 狀態: {狀態}
  - 應對計畫: {說明}

## 📈 下一步計畫
- {計畫項目列表}
```

## 最佳實踐

1. **自動化定期生成** - 在 Sprint 結束時自動觸發 Release Notes 生成
2. **連結 Work Items** - 確保所有 PRs 都連結到 work items 以獲得完整追蹤
3. **分類標準化** - 使用統一的 work item 類型和標籤進行分類
4. **版本標記** - 在 commits 和 tags 中使用語義化版本號
5. **審查流程** - 生成後人工審查並補充重要細節
6. **歷史記錄** - 在 Wiki 中維護所有 Release Notes 的索引頁面
7. **通知相關方** - 發布後自動通知團隊和利害關係人

## 參考文件

| 文件 | 內容 |
|------|------|
| [references/release-notes-templates.md](references/release-notes-templates.md) | Release Notes 完整範本庫 |
| [references/sprint-metrics.md](references/sprint-metrics.md) | Sprint 指標計算方法 |
| [references/wiki-structure.md](references/wiki-structure.md) | Wiki 組織結構最佳實踐 |

## 使用範例

### 範例 1：生成本週的變更記錄

```plaintext
User: 請生成從上週五到今天的 Release Notes

Agent 執行流程：
1. 計算日期範圍
2. 搜尋 commits
3. 取得相關 PRs 和 work items
4. 分類整理
5. 生成 Markdown 文檔
6. 詢問是否發布到 Wiki
```

### 範例 2：Sprint Review 準備

```plaintext
User: 為 Sprint 5 產生總結報告

Agent 執行流程：
1. 識別 Sprint 5 的迭代路徑
2. 取得所有 work items
3. 計算統計數據
4. 識別關鍵成就和風險
5. 生成報告
6. 可選：創建簡報投影片
```

### 範例 3：版本發布文檔

```plaintext
User: 我們要發布 v2.1.0，請準備發布文檔

Agent 執行流程：
1. 從上一個版本標籤到現在的變更
2. 生成 Release Notes
3. 識別重大變更
4. 產生升級指南
5. 更新 Wiki 的 Release History 頁面
6. 準備發布公告
```

## 整合建議

- **與 CI/CD 整合** - 在部署完成後自動生成 Release Notes
- **Slack/Teams 通知** - 發布後發送摘要到團隊頻道
- **郵件訂閱** - 讓利害關係人訂閱自動發送的 Release Notes
- **版本比較** - 提供版本間的差異比較功能
