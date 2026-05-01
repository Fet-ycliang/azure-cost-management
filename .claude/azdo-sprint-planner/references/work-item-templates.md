# Work Item 範本集合

本文檔提供各種 Work Item 的完整 JSON 範本，可用於批量創建或程式化管理。

## Feature 範本

### 標準 Feature

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Feature"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "[Feature Title]"
},
{
  "op": "add",
  "path": "/fields/System.Description",
  "value": "<div>功能描述...</div>"
},
{
  "op": "add",
  "path": "/fields/System.AreaPath",
  "value": "ProjectName\\TeamName"
},
{
  "op": "add",
  "path": "/fields/System.IterationPath",
  "value": "ProjectName\\Sprint 1"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.Priority",
  "value": 2
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.ValueArea",
  "value": "Business"
},
{
  "op": "add",
  "path": "/fields/System.Tags",
  "value": "feature; high-priority"
}
```

### Epic-level Feature

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Feature"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "[Major Feature Title]"
},
{
  "op": "add",
  "path": "/fields/System.Description",
  "value": "<div><h2>業務價值</h2><p>...</p><h2>成功指標</h2><ul><li>指標1</li></ul></div>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.Priority",
  "value": 1
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.Risk",
  "value": "2 - Medium"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.BusinessValue",
  "value": 100
},
{
  "op": "add",
  "path": "/fields/System.Tags",
  "value": "epic-feature; strategic"
}
```

## Product Backlog Item (PBI) 範本

### 標準 PBI

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Product Backlog Item"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "[User Story Title]"
},
{
  "op": "add",
  "path": "/fields/System.Description",
  "value": "<div><h3>使用者故事</h3><p>As a [role], I want [feature] so that [benefit]</p><h3>驗收條件</h3><ul><li>條件1</li><li>條件2</li></ul></div>"
},
{
  "op": "add",
  "path": "/fields/System.AreaPath",
  "value": "ProjectName\\TeamName"
},
{
  "op": "add",
  "path": "/fields/System.IterationPath",
  "value": "ProjectName\\Sprint 1"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
  "value": 5
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.Priority",
  "value": 2
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.ValueArea",
  "value": "Business"
}
```

### Technical PBI

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Product Backlog Item"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "[Technical Task Title]"
},
{
  "op": "add",
  "path": "/fields/System.Description",
  "value": "<div><h3>技術需求</h3><p>...</p><h3>技術細節</h3><p>...</p><h3>完成定義</h3><ul><li>...</li></ul></div>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
  "value": 3
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.ValueArea",
  "value": "Architectural"
},
{
  "op": "add",
  "path": "/fields/System.Tags",
  "value": "technical-debt; refactoring"
}
```

## Task 範本

### 開發 Task

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Task"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "[Development Task]"
},
{
  "op": "add",
  "path": "/fields/System.Description",
  "value": "<div><h3>實作細節</h3><p>...</p><h3>技術考量</h3><p>...</p></div>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Scheduling.RemainingWork",
  "value": 8
},
{
  "op": "add",
  "path": "/fields/System.AssignedTo",
  "value": "developer@company.com"
},
{
  "op": "add",
  "path": "/fields/System.Tags",
  "value": "development; backend"
}
```

### 測試 Task

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Task"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "[Testing Task]"
},
{
  "op": "add",
  "path": "/fields/System.Description",
  "value": "<div><h3>測試範圍</h3><ul><li>測試項目1</li></ul><h3>測試資料</h3><p>...</p></div>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Scheduling.RemainingWork",
  "value": 4
},
{
  "op": "add",
  "path": "/fields/System.Tags",
  "value": "testing; qa"
}
```

### Code Review Task

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Task"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "Code Review: [Component]"
},
{
  "op": "add",
  "path": "/fields/System.Description",
  "value": "<div><h3>Review Checklist</h3><ul><li>程式碼品質</li><li>單元測試</li><li>文檔</li></ul></div>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Scheduling.RemainingWork",
  "value": 2
},
{
  "op": "add",
  "path": "/fields/System.Tags",
  "value": "code-review"
}
```

## Bug 範本

### 標準 Bug

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Bug"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "[Bug Summary]"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.TCM.ReproSteps",
  "value": "<div><h3>重現步驟</h3><ol><li>步驟1</li><li>步驟2</li></ol><h3>預期結果</h3><p>...</p><h3>實際結果</h3><p>...</p></div>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.Severity",
  "value": "2 - High"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.Priority",
  "value": 1
},
{
  "op": "add",
  "path": "/fields/System.AreaPath",
  "value": "ProjectName\\Component"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Scheduling.Effort",
  "value": 5
}
```

### Production Bug

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Bug"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "[PROD] [Bug Summary]"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.TCM.ReproSteps",
  "value": "<div><h3>環境</h3><p>Production</p><h3>影響範圍</h3><p>...</p><h3>重現步驟</h3><ol><li>...</li></ol><h3>錯誤訊息/日誌</h3><pre>...</pre></div>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.Severity",
  "value": "1 - Critical"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.Priority",
  "value": 0
},
{
  "op": "add",
  "path": "/fields/System.Tags",
  "value": "production; hotfix"
}
```

## Test Case 範本

### 功能測試案例

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Test Case"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "[Test Case Title]"
},
{
  "op": "add",
  "path": "/fields/System.Description",
  "value": "<div><h3>測試目標</h3><p>...</p></div>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.TCM.Steps",
  "value": "<steps><step id=\"1\"><description>步驟1</description><expectedResult>預期結果1</expectedResult></step></steps>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Common.Priority",
  "value": 2
}
```

## Spike 範本

### 研究 Spike

```json
{
  "op": "add",
  "path": "/fields/System.WorkItemType",
  "value": "Product Backlog Item"
},
{
  "op": "add",
  "path": "/fields/System.Title",
  "value": "SPIKE: [Research Topic]"
},
{
  "op": "add",
  "path": "/fields/System.Description",
  "value": "<div><h3>研究目標</h3><p>...</p><h3>研究問題</h3><ul><li>問題1</li></ul><h3>預期產出</h3><ul><li>技術報告</li><li>POC 程式碼</li></ul><h3>時間盒</h3><p>2 天</p></div>"
},
{
  "op": "add",
  "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
  "value": 2
},
{
  "op": "add",
  "path": "/fields/System.Tags",
  "value": "spike; research"
}
```

## 批量創建範例

### Python 範例：批量創建 Tasks

```python
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import json

# 配置
organization_url = "https://dev.azure.com/your-org"
personal_access_token = "your-pat"
project = "your-project"

# 建立連線
credentials = BasicAuthentication('', personal_access_token)
connection = Connection(base_url=organization_url, creds=credentials)
wit_client = connection.clients.get_work_item_tracking_client()

# Tasks 範本列表
tasks = [
    {
        "title": "實作使用者認證 API",
        "description": "<div><h3>實作細節</h3><p>使用 JWT 實作認證機制</p></div>",
        "remaining_work": 8,
        "tags": "backend; api; authentication"
    },
    {
        "title": "撰寫單元測試",
        "description": "<div><h3>測試範圍</h3><p>認證 API 單元測試</p></div>",
        "remaining_work": 4,
        "tags": "testing; unit-test"
    },
    {
        "title": "更新技術文檔",
        "description": "<div><h3>文檔內容</h3><p>更新 API 文檔</p></div>",
        "remaining_work": 2,
        "tags": "documentation"
    }
]

# 批量創建
created_tasks = []
for task_data in tasks:
    document = [
        {
            "op": "add",
            "path": "/fields/System.WorkItemType",
            "value": "Task"
        },
        {
            "op": "add",
            "path": "/fields/System.Title",
            "value": task_data["title"]
        },
        {
            "op": "add",
            "path": "/fields/System.Description",
            "value": task_data["description"]
        },
        {
            "op": "add",
            "path": "/fields/Microsoft.VSTS.Scheduling.RemainingWork",
            "value": task_data["remaining_work"]
        },
        {
            "op": "add",
            "path": "/fields/System.Tags",
            "value": task_data["tags"]
        }
    ]
    
    work_item = wit_client.create_work_item(
        document=document,
        project=project,
        type="Task"
    )
    
    created_tasks.append(work_item)
    print(f"Created Task #{work_item.id}: {work_item.fields['System.Title']}")

print(f"\n✅ 成功創建 {len(created_tasks)} 個 Tasks")
```

## Work Item 連結範本

### 階層連結（Parent-Child）

```python
# 連結 PBI 到 Feature
{
    "op": "add",
    "path": "/relations/-",
    "value": {
        "rel": "System.LinkTypes.Hierarchy-Reverse",
        "url": f"https://dev.azure.com/{organization}/{project}/_apis/wit/workItems/{parent_id}",
        "attributes": {
            "comment": "Child of Feature"
        }
    }
}
```

### 相關連結（Related）

```python
# 連結相關的 Work Items
{
    "op": "add",
    "path": "/relations/-",
    "value": {
        "rel": "System.LinkTypes.Related",
        "url": f"https://dev.azure.com/{organization}/{project}/_apis/wit/workItems/{related_id}",
        "attributes": {
            "comment": "Related work item"
        }
    }
}
```

### 依賴連結（Predecessor-Successor）

```python
# 設定前置依賴
{
    "op": "add",
    "path": "/relations/-",
    "value": {
        "rel": "System.LinkTypes.Dependency-Reverse",
        "url": f"https://dev.azure.com/{organization}/{project}/_apis/wit/workItems/{predecessor_id}",
        "attributes": {
            "comment": "Depends on this work item"
        }
    }
}
```

## 快速參考

### Work Item 狀態

| Work Item Type | 可用狀態 |
|----------------|----------|
| Feature | New, Active, Resolved, Closed, Removed |
| PBI | New, Approved, Committed, Done, Removed |
| Task | **New → To Do → In Progress → Done**, Removed |
| Bug | New, Active, Resolved, Closed |
| Test Case | Design, Ready, Closed |

> **⚠️ Task 狀態轉換規則（強制）**：Task 必須依序經過 `New → To Do → In Progress → Done`，禁止跳過任何中間狀態。建立時預設為 To Do，完成前必須先轉為 In Progress。

### 優先級說明

| 值 | 說明 |
|----|------|
| 0 | Critical - 最高優先級 |
| 1 | High - 高優先級 |
| 2 | Medium - 中等優先級 |
| 3 | Low - 低優先級 |

### Severity 級別（Bug）

| 值 | 說明 |
|----|------|
| 1 - Critical | 系統當機或資料遺失 |
| 2 - High | 主要功能無法使用 |
| 3 - Medium | 部分功能受影響 |
| 4 - Low | 輕微問題或美化 |

### 常用欄位參考

| 欄位路徑 | 說明 | 類型 |
|----------|------|------|
| System.Title | 標題 | string |
| System.Description | 描述 | html |
| System.State | 狀態 | string |
| System.AssignedTo | 指派給 | identity |
| System.AreaPath | 區域路徑 | string |
| System.IterationPath | 迭代路徑 | string |
| System.Tags | 標籤 | string (分號分隔) |
| Microsoft.VSTS.Scheduling.StoryPoints | 故事點數 | integer |
| Microsoft.VSTS.Scheduling.RemainingWork | 剩餘工作 | decimal |
| Microsoft.VSTS.Common.Priority | 優先級 | integer |
| Microsoft.VSTS.Common.Severity | 嚴重性 | string |
