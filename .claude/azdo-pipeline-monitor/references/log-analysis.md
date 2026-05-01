# Pipeline 日誌分析指南

此文件提供分析 Azure DevOps Pipeline 日誌的模式、技巧和常見問題解決方案。

## 🔍 日誌分析基礎

### 日誌結構

Azure Pipeline 日誌通常包含：
```
##[section]Starting: {Job/Task Name}
==============================================================================
Task         : {TaskName}
Description  : {Description}
Version      : {Version}
==============================================================================
{Task Output}
##[section]Finishing: {Job/Task Name}
```

### 關鍵標記

| 標記 | 含義 | 嚴重程度 |
|------|------|---------|
| `##[error]` | 錯誤訊息 | 高 |
| `##[warning]` | 警告訊息 | 中 |
| `##[debug]` | 除錯訊息 | 低 |
| `##[command]` | 執行的命令 | 資訊 |
| `##[section]` | 階段分隔 | 資訊 |

## 🐛 常見錯誤模式

### 1. 編譯錯誤

**模式識別**:
```regex
error CS\d+:|error C\d+:|SyntaxError:|TypeError:|CompilationError
```

**範例日誌**:
```
src/main.py:25:10: error: Syntax Error
    def calculate_total()
        ^
SyntaxError: invalid syntax
```

**診斷步驟**:
1. 定位錯誤的檔案和行號
2. 檢查最近的程式碼變更
3. 本地重現錯誤
4. 檢查相依版本是否一致

**常見原因**:
- 語法錯誤
- 缺少相依套件
- 版本不相容
- 環境變數未設定

### 2. 測試失敗

**模式識別**:
```regex
FAILED|Test.*failed|AssertionError|Test case.*failed
```

**範例日誌**:
```
FAILED tests/test_user.py::test_create_user - AssertionError: 
Expected: 201
Actual: 400
```

**診斷步驟**:
1. 識別失敗的測試案例
2. 檢查錯誤訊息和堆疊追蹤
3. 確認測試資料和環境
4. 本地執行失敗的測試

**常見原因**:
- 邏輯錯誤
- 測試資料問題
- 環境差異
- 不穩定的測試 (flaky test)

### 3. 相依套件問題

**模式識別**:
```regex
Could not find|Package not found|ModuleNotFoundError|ImportError
```

**範例日誌**:
```
ERROR: Could not find a version that satisfies the requirement 
    package-name==1.2.3 (from versions: 1.0.0, 1.1.0, 1.2.0)
ERROR: No matching distribution found for package-name==1.2.3
```

**診斷步驟**:
1. 檢查套件名稱和版本
2. 驗證套件來源可用性
3. 檢查相依衝突
4. 確認網路連線

**常見原因**:
- 套件版本不存在
- 套件來源無法訪問
- 相依衝突
- 網路問題

### 4. 權限錯誤

**模式識別**:
```regex
Permission denied|Access denied|Unauthorized|403|401
```

**範例日誌**:
```
##[error]fatal: Authentication failed for 'https://github.com/repo.git/'
##[error]remote: Permission to repo.git denied to user.
```

**診斷步驟**:
1. 檢查認證設定
2. 驗證 Service Connection
3. 確認權限配置
4. 檢查 token 有效期

**常見原因**:
- Token 過期
- 權限不足
- Service Connection 配置錯誤
- 防火牆或網路限制

### 5. 逾時錯誤

**模式識別**:
```regex
timeout|timed out|TimeoutError|Operation canceled
```

**範例日誌**:
```
##[error]The job running on agent Agent-01 ran longer than the maximum time 
of 60 minutes. Canceling the job and stop the agent.
```

**診斷步驟**:
1. 識別逾時的階段
2. 檢查任務執行時間趨勢
3. 分析效能瓶頸
4. 評估是否需要增加逾時限制

**常見原因**:
- 效能問題
- 網路延遲
- 資源不足
- 配置的逾時時間過短

### 6. 資源不足

**模式識別**:
```regex
Out of memory|OOM|Disk.*full|No space left
```

**範例日誌**:
```
##[error]java.lang.OutOfMemoryError: Java heap space
##[error]Error: Process completed with exit code 137.
```

**診斷步驟**:
1. 檢查資源使用情況
2. 分析記憶體或磁碟使用趨勢
3. 優化資源使用
4. 調整 agent pool 配置

**常見原因**:
- 記憶體洩漏
- 過大的測試資料
- 快取累積
- Agent 資源配置不足

### 7. Matrix job 被連帶取消

**模式識別**:
```regex
The operation was canceled|Operation canceled|conclusion\": \"cancelled\"
```

**範例日誌**:
```
##[error]The operation was canceled.
```

**診斷步驟**:
1. 不要把 `cancelled` job 當成第一現場；先回頭找同一個 run 裡最早的 `failure` job
2. 若是 matrix workflow，檢查是否開了 `strategy.fail-fast`
3. 比對同一時間其他 sibling jobs，找出誰先失敗
4. 若是 GitHub Actions，也檢查是否有 `concurrency.cancel-in-progress`、手動取消或 environment approval 被中止

**常見原因**:
- matrix 其中一個 job 先失敗，觸發 fail-fast
- 有人手動取消 run
- concurrency policy 把舊 run 中止
- 等待 approval / environment gate 時被終止

### 8. Container image ref 大小寫或命名非法

**模式識別**:
```regex
invalid tag|invalid reference format|repository name must be lowercase
```

**範例日誌**:
```
ERROR: failed to build: invalid tag "ghcr.io/Fet-ycliang/mcp-dotnet-samples/todo-list:latest": repository name must be lowercase
```

**診斷步驟**:
1. 檢查 image ref 是否混入大寫 owner / repo、`refs/heads/*`、空白或特殊字元
2. 比對 `docker/metadata-action` 產出的 tag 與後面手動補的 `latest` / version tag，確認是否使用了不同來源
3. 若 workflow 同時做 attestation，確認 `subject-name` 也沿用同一個 normalized image name
4. 對 GitHub Actions / GHCR，避免直接用原始 `${{ github.repository }}` 組最終 image ref；先轉小寫一次再重複使用

**常見原因**:
- `${{ github.repository }}` 保留原始大小寫
- branch 名稱未先正規化就直接拿來組 tag
- `metadata-action` 已經小寫，但手動追加的 `latest` / version tag 還在用原始值
- 同一條 pipeline 的 image name / attestation subject 來源不一致

### 9. MCP Registry publish 403（fork 發佈 upstream namespace）

**模式識別**:
```regex
publish failed: server returned status 403|You do not have permission to publish this server|Attempting to publish: io\.github\.
```

**範例日誌**:
```
Error: publish failed: server returned status 403: {"detail":"You do not have permission to publish this server. You have permission to publish: io.github.Fet-ycliang/*. Attempting to publish: io.github.microsoft/awesome-copilot."}
```

**診斷步驟**:
1. 先看 `server.json` 的 `name`，確認實際要 publish 的 MCP Registry namespace
2. 比對目前 repo 是否為官方來源；fork repo 通常只有 `io.github.<fork-owner>/*` 權限
3. 檢查 workflow 是否把 `mcp-publisher login/publish`、metadata sync、server.json rewrite 這類 upstream-only 步驟限制在官方 repo
4. 若是 fork，只保留 build/push GHCR image；不要自動 publish 到 upstream namespace，也不要讓 hourly schedule 持續重跑這類步驟

**常見原因**:
- `awesome-copilot/server.json` 指向 upstream namespace（例如 `io.github.microsoft/awesome-copilot`）
- fork 沒有該 namespace 的 MCP Registry publish 權限
- reusable workflow 沒有區分官方 repo 與 fork repo
- schedule workflow 在 fork 上照常執行，反覆撞同一個 403

## 📊 日誌分析技巧

### 1. 快速定位錯誤

```python
def find_errors_in_log(log_content):
    """
    從日誌中快速提取錯誤訊息
    """
    import re
    
    error_patterns = {
        'build_error': r'##\[error\](.+)',
        'test_failure': r'FAILED (.+?) - (.+)',
        'exception': r'(\w+Error|Exception): (.+)',
        'exit_code': r'exit code (\d+)'
    }
    
    errors = {}
    for error_type, pattern in error_patterns.items():
        matches = re.findall(pattern, log_content, re.MULTILINE)
        if matches:
            errors[error_type] = matches
    
    return errors
```

### 2. 提取關鍵資訊

```python
def extract_build_summary(log_content):
    """
    提取建置摘要資訊
    """
    summary = {
        'duration': None,
        'exit_code': None,
        'errors': [],
        'warnings': [],
        'failed_tasks': []
    }
    
    # 提取執行時長
    duration_match = re.search(r'Total time: (.+)', log_content)
    if duration_match:
        summary['duration'] = duration_match.group(1)
    
    # 提取錯誤和警告
    summary['errors'] = re.findall(r'##\[error\](.+)', log_content)
    summary['warnings'] = re.findall(r'##\[warning\](.+)', log_content)
    
    # 提取失敗的任務
    failed_tasks = re.findall(
        r'##\[error\]Task (.+?) failed', 
        log_content
    )
    summary['failed_tasks'] = failed_tasks
    
    return summary
```

### 3. 比較日誌差異

```python
def compare_build_logs(successful_log, failed_log):
    """
    比較成功和失敗的建置日誌以識別差異
    """
    differences = {
        'new_errors': [],
        'new_warnings': [],
        'changed_outputs': []
    }
    
    # 提取錯誤
    success_errors = set(re.findall(r'##\[error\](.+)', successful_log))
    failed_errors = set(re.findall(r'##\[error\](.+)', failed_log))
    
    # 找出新增的錯誤
    differences['new_errors'] = list(failed_errors - success_errors)
    
    return differences
```

## 🔧 自動化分析腳本

### 錯誤分類器

```python
class LogErrorClassifier:
    """日誌錯誤分類器"""
    
    ERROR_CATEGORIES = {
        'compilation': {
            'patterns': [
                r'error CS\d+:',
                r'SyntaxError:',
                r'CompilationError'
            ],
            'severity': 'high',
            'suggestions': [
                '檢查最近的程式碼變更',
                '確認所有相依套件已安裝',
                '本地重現編譯錯誤'
            ]
        },
        'testing': {
            'patterns': [
                r'FAILED tests/',
                r'AssertionError',
                r'Test.*failed'
            ],
            'severity': 'high',
            'suggestions': [
                '檢查失敗的測試案例',
                '確認測試資料正確',
                '在本地執行測試'
            ]
        },
        'network': {
            'patterns': [
                r'Connection.*refused',
                r'timeout',
                r'Could not resolve host'
            ],
            'severity': 'medium',
            'suggestions': [
                '檢查網路連線',
                '確認服務可用性',
                '檢查防火牆設定'
            ]
        },
        'authentication': {
            'patterns': [
                r'Authentication failed',
                r'Permission denied',
                r'401|403'
            ],
            'severity': 'high',
            'suggestions': [
                '檢查認證憑證',
                '驗證權限設定',
                '確認 token 未過期'
            ]
        },
        'resources': {
            'patterns': [
                r'Out of memory',
                r'Disk.*full',
                r'No space left'
            ],
            'severity': 'high',
            'suggestions': [
                '清理磁碟空間',
                '增加記憶體配置',
                '檢查資源洩漏'
            ]
        }
    }
    
    def classify(self, log_content):
        """
        分類日誌中的錯誤
        
        Returns:
            dict: 分類結果包含類別、嚴重程度和建議
        """
        results = []
        
        for category, config in self.ERROR_CATEGORIES.items():
            for pattern in config['patterns']:
                matches = re.findall(pattern, log_content, re.IGNORECASE)
                if matches:
                    results.append({
                        'category': category,
                        'severity': config['severity'],
                        'matches': matches[:5],  # 只顯示前 5 個
                        'suggestions': config['suggestions']
                    })
                    break  # 找到匹配後跳出
        
        return results
```

### 使用範例

```python
# 分析日誌
classifier = LogErrorClassifier()
log_content = """
##[error]FAILED tests/test_api.py::test_create_user - AssertionError
##[error]Connection to database timed out
##[warning]Deprecation warning in module X
"""

results = classifier.classify(log_content)

for result in results:
    print(f"類別: {result['category']}")
    print(f"嚴重程度: {result['severity']}")
    print(f"匹配: {result['matches']}")
    print(f"建議: {', '.join(result['suggestions'])}")
    print()
```

## 📈 日誌趨勢分析

### 追蹤錯誤頻率

```python
def analyze_error_trends(builds_logs, days=30):
    """
    分析錯誤趨勢
    
    Returns:
        dict: 每種錯誤類型的出現頻率
    """
    classifier = LogErrorClassifier()
    trends = {}
    
    for build_date, log in builds_logs:
        errors = classifier.classify(log)
        for error in errors:
            category = error['category']
            if category not in trends:
                trends[category] = []
            trends[category].append(build_date)
    
    # 計算每種錯誤的頻率
    frequency = {}
    for category, dates in trends.items():
        frequency[category] = {
            'count': len(dates),
            'first_seen': min(dates),
            'last_seen': max(dates),
            'avg_per_day': len(dates) / days
        }
    
    return frequency
```

## 🎯 最佳實踐

### 1. 日誌記錄準則

**好的日誌**:
```python
# ✅ 清晰且包含上下文
logger.info(f"Processing user {user_id} - Step 1: Validation")
logger.info(f"Database query took {duration}ms")
logger.error(f"Failed to send email to {email}: {error}")
```

**避免的日誌**:
```python
# ❌ 過於簡略
logger.info("Processing")
logger.error("Error")

# ❌ 過於冗長
logger.debug(f"Variable x = {x}, Variable y = {y}, ...")
```

### 2. 結構化日誌

使用結構化格式便於分析：
```python
import json

log_entry = {
    "timestamp": "2024-02-18T10:30:00Z",
    "level": "ERROR",
    "category": "database",
    "message": "Connection timeout",
    "context": {
        "user_id": 12345,
        "operation": "fetch_orders",
        "duration": 30000
    }
}

logger.error(json.dumps(log_entry))
```

### 3. 錯誤碼系統

建立錯誤碼以便快速識別：
```python
ERROR_CODES = {
    "DB001": "Database connection failed",
    "API002": "External API timeout",
    "AUTH003": "Authentication failed",
    "VAL004": "Input validation failed"
}

logger.error(f"[DB001] {ERROR_CODES['DB001']}: {details}")
```

## 📚 參考工具

- **Log Analytics**: Azure Monitor Log Analytics
- **日誌處理**: `grep`, `awk`, `sed`
- **分析工具**: ELK Stack, Splunk
- **可視化**: Grafana, Kibana

## 🔗 相關資源

- [Azure Pipeline 日誌格式文檔](https://docs.microsoft.com/azure/devops/pipelines/troubleshooting)
- [正則表達式測試工具](https://regex101.com/)
- [日誌最佳實踐](https://www.loggly.com/ultimate-guide/python-logging-basics/)
