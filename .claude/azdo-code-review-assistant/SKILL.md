---
name: azdo-code-review-assistant
description: |
  Azure DevOps Pull Request 審查助手。自動化 PR 創建、審查檢查、評論管理。
  觸發詞: "create PR", "review pull request", "PR 檢查", "merge request", "code review", "審查程式碼"
---

# Azure DevOps Code Review Assistant

自動化 Pull Request 工作流程，包含 PR 創建、審查檢查清單、評論管理和合併追蹤。

## 核心功能

### 1. PR 創建與設定

使用標準化流程創建包含完整上下文的 Pull Request。

**基本工作流程：**

```python
# 範例：創建 Pull Request
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_repo_get_repo_by_name_or_id
# - mcp_microsoft_azu_repo_get_branch_by_name
# - mcp_microsoft_azu_repo_create_pull_request
# - mcp_microsoft_azu_wit_link_work_item_to_pull_request

async def create_standardized_pr(
    project, 
    repo_name, 
    source_branch, 
    target_branch,
    title,
    description,
    work_item_ids=None,
    reviewers=None,
    auto_complete=False
):
    """
    創建標準化的 Pull Request
    
    Args:
        project: 專案名稱
        repo_name: Repository 名稱
        source_branch: 來源分支
        target_branch: 目標分支（通常是 main 或 develop）
        title: PR 標題
        description: PR 描述
        work_item_ids: 關聯的 work item IDs 列表
        reviewers: 審查者列表
        auto_complete: 是否啟用自動完成
    
    Returns:
        創建的 PR 物件
    """
    # 1. 取得 repository 資訊
    repo = get_repo(project, repo_name)
    
    # 2. 驗證分支存在
    source = get_branch(project, repo_name, source_branch)
    target = get_branch(project, repo_name, target_branch)
    
    # 3. 生成標準化的 PR 描述
    formatted_description = format_pr_description(
        description, 
        work_item_ids,
        source_branch
    )
    
    # 4. 創建 Pull Request
    pr = create_pull_request(
        project,
        repo_name,
        source_branch,
        target_branch,
        title,
        formatted_description,
        reviewers
    )
    
    # 5. 連結 Work Items
    if work_item_ids:
        for work_item_id in work_item_ids:
            link_work_item_to_pr(pr.id, work_item_id)
    
    # 6. 設定自動完成（可選）
    if auto_complete:
        set_auto_complete(pr.id)
    
    return pr
```

**PR 標題規範：**
- `feat: [功能描述]` - 新功能
- `fix: [問題描述]` - Bug 修復
- `refactor: [重構描述]` - 程式碼重構
- `docs: [文檔描述]` - 文檔更新
- `test: [測試描述]` - 測試相關
- `chore: [維護描述]` - 維護任務

### 2. PR 審查檢查清單

自動檢查 PR 是否符合團隊規範。

**檢查項目：**

```python
# 範例：PR 審查檢查
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_repo_get_pull_request_by_id
# - mcp_microsoft_azu_repo_list_pull_request_threads
# - mcp_microsoft_azu_repo_get_build_status

async def review_pr_checklist(project, repo_name, pr_id):
    """
    執行 PR 審查檢查清單
    
    Args:
        project: 專案名稱
        repo_name: Repository 名稱
        pr_id: Pull Request ID
    
    Returns:
        檢查結果報告
    """
    pr = get_pull_request(project, repo_name, pr_id)
    
    checks = {
        "title_format": check_title_format(pr.title),
        "description_complete": check_description(pr.description),
        "work_items_linked": check_work_items(pr),
        "reviewers_assigned": check_reviewers(pr),
        "conflicts_resolved": check_conflicts(pr),
        "build_passing": check_build_status(pr),
        "comments_resolved": check_comments(pr),
        "file_size_limit": check_file_sizes(pr),
        "test_coverage": check_test_coverage(pr)
    }
    
    return generate_checklist_report(checks)
```

**檢查清單：**

- ✅ **標題格式** - 符合命名規範（type: description）
- ✅ **描述完整** - 包含變更說明、測試計畫、影響範圍
- ✅ **Work Items 連結** - 至少連結一個 work item
- ✅ **審查者指派** - 指派適當的審查者
- ✅ **衝突解決** - 無合併衝突
- ✅ **建置通過** - CI/CD pipeline 成功
- ✅ **評論處理** - 所有審查評論已解決
- ✅ **檔案大小** - 無超大檔案（>1MB）
- ✅ **測試覆蓋** - 包含相應的單元測試

### 3. 審查評論管理

管理審查過程中的評論和討論串。

**工作流程：**

```python
# 範例：管理審查評論
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_repo_create_pull_request_thread
# - mcp_microsoft_azu_repo_list_pull_request_threads
# - mcp_microsoft_azu_repo_reply_to_comment
# - mcp_microsoft_azu_repo_update_pull_request_thread

async def manage_review_comments(project, repo_name, pr_id, action):
    """
    管理 PR 審查評論
    
    Args:
        project: 專案名稱
        repo_name: Repository 名稱
        pr_id: Pull Request ID
        action: 操作類型（add_comment, resolve_thread, get_summary）
    """
    if action == "add_comment":
        # 新增程式碼審查評論
        thread = create_review_comment(
            project, repo_name, pr_id,
            file_path, line_number, comment_text
        )
        return thread
    
    elif action == "resolve_thread":
        # 標記討論串為已解決
        threads = list_threads(project, repo_name, pr_id)
        for thread in threads:
            if should_resolve(thread):
                update_thread_status(thread.id, "closed")
    
    elif action == "get_summary":
        # 取得評論摘要
        threads = list_threads(project, repo_name, pr_id)
        summary = summarize_comments(threads)
        return summary
```

**評論類別：**
- 🔴 **必須修改** (Must Fix) - 阻礙合併的問題
- 🟡 **建議修改** (Suggestion) - 改進建議
- 🔵 **討論** (Question) - 需要澄清
- 🟢 **讚賞** (Praise) - 正面回饋
- ⚪ **備註** (Note) - 資訊性評論

### 4. PR 狀態追蹤

追蹤 PR 從創建到合併的完整生命週期。

**工作流程：**

```python
# 範例：PR 狀態追蹤
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_repo_list_pull_requests_by_repo_or_project
# - mcp_microsoft_azu_repo_get_pull_request_by_id
# - mcp_microsoft_azu_repo_update_pull_request

async def track_pr_status(project, repo_name, status_filter=None):
    """
    追蹤 PR 狀態
    
    Args:
        project: 專案名稱
        repo_name: Repository 名稱
        status_filter: 狀態篩選（active, completed, abandoned）
    
    Returns:
        PR 狀態報告
    """
    # 1. 取得所有 PRs
    prs = list_pull_requests(project, repo_name, status=status_filter)
    
    # 2. 分類 PRs
    categorized = {
        "ready_to_merge": [],
        "waiting_review": [],
        "has_conflicts": [],
        "build_failing": [],
        "waiting_author": []
    }
    
    for pr in prs:
        category = determine_pr_category(pr)
        categorized[category].append(pr)
    
    # 3. 生成狀態報告
    report = generate_status_report(categorized)
    
    return report
```

## PR 描述範本

### 標準 PR 範本

```markdown
## 📝 變更說明
{簡要描述此 PR 的目的和變更內容}

## 🔗 相關 Work Items
- Fixes #{work_item_id}
- Related to #{work_item_id}

## 🧪 測試計畫
- [ ] 單元測試已新增/更新
- [ ] 整合測試已執行
- [ ] 手動測試場景：
  - {測試場景 1}
  - {測試場景 2}

## 📸 截圖（如適用）
{UI 變更的截圖}

## 🎯 影響範圍
- **影響的功能**: {列出受影響的功能}
- **破壞性變更**: {是/否，如果有請說明}
- **資料庫變更**: {是/否，如果有請說明}

## ✅ 檢查清單
- [ ] 程式碼遵循團隊規範
- [ ] 已進行自我審查
- [ ] 已新增必要的註解
- [ ] 文檔已更新
- [ ] 無新的警告訊息
- [ ] 已新增測試且測試通過
- [ ] 相依更新已檢查

## 🔍 審查重點
{提示審查者應特別注意的部分}
```

## 最佳實踐

1. **小型 PR** - 保持 PR 規模適中（建議 <400 行變更）
2. **單一目的** - 每個 PR 只處理一個功能或修復
3. **描述詳細** - 提供充分的上下文讓審查者理解變更
4. **及時回應** - 24 小時內回應審查評論
5. **自我審查** - 提交前先自己審查一遍
6. **測試完整** - 確保包含適當的測試
7. **保持更新** - 定期從目標分支合併最新變更
8. **尊重審查** - 認真對待每一條評論
9. **學習機會** - 將審查視為學習和改進的機會
10. **自動化檢查** - 利用 CI/CD 自動化基本檢查

## 審查者指南

### 審查流程

1. **理解上下文** - 閱讀 PR 描述和關聯的 work items
2. **檢查大局** - 評估整體設計和架構是否合理
3. **細節審查** - 檢查程式碼品質、邏輯正確性
4. **測試驗證** - 確認測試覆蓋度和測試品質
5. **文檔檢查** - 驗證文檔是否更新
6. **提供回饋** - 給予建設性和具體的評論
7. **批准或請求變更** - 明確表達審查結果

### 審查重點

- **正確性** - 程式碼是否正確實現需求
- **設計** - 架構設計是否合理
- **可讀性** - 程式碼是否易於理解
- **效能** - 是否有明顯的效能問題
- **安全性** - 是否有安全漏洞
- **測試** - 測試是否充分
- **文檔** - 文檔是否清晰完整

## 參考文件

| 文件 | 內容 |
|------|------|
| [references/pr-templates.md](references/pr-templates.md) | 各種 PR 範本集合 |
| [references/review-checklist.md](references/review-checklist.md) | 完整的審查檢查清單 |
| [references/comment-guidelines.md](references/comment-guidelines.md) | 評論撰寫指南 |

## 使用範例

### 範例 1：創建功能 PR

```plaintext
User: 我完成了會員登入功能，請幫我創建 PR

Agent 執行流程：
1. 確認當前分支和目標分支
2. 搜尋相關的 work items
3. 生成 PR 標題和描述
4. 創建 PR 並連結 work items
5. 指派預設審查者
6. 提供 PR 連結
```

### 範例 2：檢查 PR 狀態

```plaintext
User: 檢查 PR #12345 是否可以合併

Agent 執行流程：
1. 取得 PR 詳細資訊
2. 執行檢查清單
3. 檢查建置狀態
4. 檢查評論是否解決
5. 生成檢查報告
6. 如果準備好，建議合併
```

### 範例 3：批次審查

```plaintext
User: 顯示所有等待我審查的 PRs

Agent 執行流程：
1. 搜尋指派給用戶的 PRs
2. 按優先級排序（年齡、重要性）
3. 顯示摘要列表
4. 提供快速審查連結
```

### 範例 4：解決評論

```plaintext
User: PR #12345 的所有評論都已處理，請協助確認

Agent 執行流程：
1. 取得所有討論串
2. 檢查每個討論串的狀態
3. 識別待解決的討論
4. 提供待處理項目清單
5. 建議下一步行動
```

## 自動化整合

- **PR 範本** - 在 repository 中設定 `.azuredevops/pull_request_template.md`
- **分支政策** - 設定必要的審查者數量、建置檢查
- **自動指派** - 根據程式碼擁有者自動指派審查者
- **狀態檢查** - 整合 linters、測試、安全掃描
- **自動合併** - 條件滿足時自動完成合併
- **通知設定** - 配置適當的通知避免打擾

## 團隊協作建議

- **審查輪替** - 輪流分配審查任務避免瓶頸
- **配對審查** - 複雜變更考慮配對審查
- **知識分享** - 利用 PR 審查促進知識傳播
- **回饋文化** - 建立建設性和尊重的回饋文化
- **持續改進** - 定期回顧和優化審查流程
