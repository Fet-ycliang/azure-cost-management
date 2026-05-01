---
name: azdo-pipeline-monitor
description: |
  Azure DevOps Pipeline 監控與故障排除助手。監控建置狀態、分析失敗原因、追蹤部署進度。
  觸發詞: "check build", "pipeline status", "建置失敗", "部署狀態", "CI/CD monitor", "build logs"
---

# Azure DevOps Pipeline Monitor

自動化 CI/CD Pipeline 監控、故障診斷和效能分析。

## 核心功能

### 1. 建置狀態監控

即時監控 pipeline 執行狀態和建置結果。

**基本工作流程：**

```python
# 範例：監控建置狀態
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_pipelines_get_build_definitions
# - mcp_microsoft_azu_pipelines_get_builds
# - mcp_microsoft_azu_pipelines_get_build_status

async def monitor_build_status(project, definition_name=None, top=10):
    """
    監控建置狀態
    
    Args:
        project: 專案名稱
        definition_name: Pipeline 定義名稱（可選）
        top: 返回最近的建置數量
    
    Returns:
        建置狀態報告
    """
    # 1. 取得 pipeline 定義
    if definition_name:
        definitions = get_build_definitions(project, name=definition_name)
        definition_id = definitions[0].id
    else:
        definition_id = None
    
    # 2. 取得最近的建置
    builds = get_builds(
        project, 
        definition_id=definition_id,
        top=top,
        status_filter="all"
    )
    
    # 3. 分析建置狀態
    status_summary = {
        "succeeded": 0,
        "failed": 0,
        "in_progress": 0,
        "canceled": 0,
        "total": len(builds)
    }
    
    for build in builds:
        status = build.status.lower()
        if status in status_summary:
            status_summary[status] += 1
    
    # 4. 識別問題建置
    failed_builds = [b for b in builds if b.result == "failed"]
    
    # 5. 生成報告
    report = generate_status_report(builds, status_summary, failed_builds)
    
    return report
```

**監控指標：**
- ✅ **成功率** - 近期建置的成功百分比
- ⏱️ **平均時長** - 建置平均執行時間
- 🔄 **趨勢分析** - 成功率和時長的趨勢
- ⚠️ **失敗模式** - 常見失敗原因
- 📊 **佇列時間** - 建置等待時間

### 2. 建置失敗診斷

自動分析建置失敗的原因並提供修復建議。

**工作流程：**

```python
# 範例：診斷建置失敗
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_pipelines_get_build_status
# - mcp_microsoft_azu_pipelines_get_build_log
# - mcp_microsoft_azu_pipelines_get_build_log_by_id

async def diagnose_build_failure(project, build_id):
    """
    診斷建置失敗原因
    
    Args:
        project: 專案名稱
        build_id: 建置 ID
    
    Returns:
        失敗診斷報告
    """
    # 1. 取得建置詳細資訊
    build = get_build_status(project, build_id)
    
    # 2. 檢查建置結果
    if build.result != "failed":
        return "Build did not fail"
    
    # 3. 取得建置日誌
    logs = get_build_logs(project, build_id)
    
    # 4. 分析日誌找出錯誤
    errors = analyze_logs(logs)
    
    # 5. 分類錯誤類型
    error_categories = categorize_errors(errors)
    
    # 6. 提供修復建議
    suggestions = generate_fix_suggestions(error_categories)
    
    # 7. 生成診斷報告
    report = {
        "build_id": build_id,
        "failed_stage": identify_failed_stage(build),
        "error_summary": error_categories,
        "key_errors": errors[:5],  # 前 5 個關鍵錯誤
        "fix_suggestions": suggestions,
        "related_issues": find_similar_failures(project, errors)
    }
    
    return format_diagnostic_report(report)
```

**常見失敗類型：**

| 類型 | 描述 | 常見原因 |
|------|------|----------|
| 🔴 **編譯錯誤** | 程式碼無法編譯 | 語法錯誤、相依問題 |
| 🟡 **測試失敗** | 單元測試或整合測試失敗 | 邏輯錯誤、環境問題 |
| 🟠 **連線錯誤** | 無法連接外部服務 | 網路問題、認證失敗 |
| 🟣 **逾時** | 建置執行時間過長 | 效能問題、資源不足 |
| 🔵 **設定錯誤** | Pipeline 設定有誤 | YAML 語法錯誤、變數未定義 |
| ⚫ **資源不足** | 記憶體或磁碟空間不足 | 資源配置問題 |

### 3. Pipeline 執行追蹤

追蹤 pipeline 的完整執行過程和各階段狀態。

**工作流程：**

```python
# 範例：追蹤 Pipeline 執行
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_pipelines_get_run
# - mcp_microsoft_azu_pipelines_list_runs

async def track_pipeline_execution(project, pipeline_id, run_id=None):
    """
    追蹤 Pipeline 執行狀態
    
    Args:
        project: 專案名稱
        pipeline_id: Pipeline ID
        run_id: 特定的執行 ID（可選）
    
    Returns:
        執行追蹤報告
    """
    if run_id:
        # 追蹤特定執行
        run = get_pipeline_run(project, pipeline_id, run_id)
        stages = get_run_stages(run)
        
        report = {
            "run_id": run_id,
            "status": run.state,
            "result": run.result,
            "started": run.created_date,
            "duration": calculate_duration(run),
            "stages": format_stages(stages),
            "current_stage": identify_current_stage(stages)
        }
    else:
        # 追蹤最近的執行
        runs = list_pipeline_runs(project, pipeline_id, top=5)
        report = format_runs_summary(runs)
    
    return report
```

**執行階段追蹤：**
- 🟢 **佇列中** (Queued) - 等待執行
- 🔵 **執行中** (Running) - 正在執行
- ✅ **成功** (Succeeded) - 執行成功
- ❌ **失敗** (Failed) - 執行失敗
- ⚠️ **部分成功** (PartiallySucceeded) - 部分階段失敗
- ⏸️ **已取消** (Canceled) - 手動取消

### 4. 部署監控

監控多環境部署流程和狀態。

**工作流程：**

```python
# 範例：監控部署狀態
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_pipelines_get_builds
# - mcp_microsoft_azu_pipelines_update_build_stage

async def monitor_deployment(project, environment="production"):
    """
    監控部署狀態
    
    Args:
        project: 專案名稱
        environment: 目標環境（dev, staging, production）
    
    Returns:
        部署狀態報告
    """
    # 1. 取得部署 pipeline 的建置
    builds = get_builds(
        project,
        tags=[f"deploy-{environment}"],
        status_filter="inProgress,completed"
    )
    
    # 2. 分析部署狀態
    deployment_status = {
        "environment": environment,
        "latest_deployment": None,
        "in_progress": [],
        "recent_history": []
    }
    
    for build in builds:
        if build.status == "inProgress":
            deployment_status["in_progress"].append(build)
        elif not deployment_status["latest_deployment"]:
            deployment_status["latest_deployment"] = build
        else:
            deployment_status["recent_history"].append(build)
    
    # 3. 計算部署指標
    metrics = calculate_deployment_metrics(builds, environment)
    
    # 4. 生成報告
    report = format_deployment_report(deployment_status, metrics)
    
    return report
```

**部署指標：**
- 📈 **部署頻率** - 每日/每週部署次數
- ⏱️ **前置時間** - 從 commit 到部署的時間
- ✅ **成功率** - 部署成功的百分比
- 🔄 **回滾率** - 需要回滾的部署百分比
- ⚡ **平均恢復時間** (MTTR) - 失敗後恢復所需時間

### 5. 效能分析

分析 pipeline 效能並識別優化機會。

**工作流程：**

```python
# 範例：Pipeline 效能分析
# 需使用的 MCP 工具：
# - mcp_microsoft_azu_pipelines_get_builds
# - mcp_microsoft_azu_pipelines_get_build_log

async def analyze_pipeline_performance(project, definition_id, days=30):
    """
    分析 Pipeline 效能
    
    Args:
        project: 專案名稱
        definition_id: Pipeline 定義 ID
        days: 分析的天數範圍
    
    Returns:
        效能分析報告
    """
    # 1. 取得指定期間的建置
    since_date = datetime.now() - timedelta(days=days)
    builds = get_builds(
        project,
        definition_id=definition_id,
        min_time=since_date
    )
    
    # 2. 計算效能指標
    metrics = {
        "total_builds": len(builds),
        "avg_duration": calculate_avg_duration(builds),
        "median_duration": calculate_median_duration(builds),
        "p95_duration": calculate_percentile_duration(builds, 95),
        "queue_time": calculate_avg_queue_time(builds),
        "success_rate": calculate_success_rate(builds)
    }
    
    # 3. 識別瓶頸
    bottlenecks = identify_bottlenecks(builds)
    
    # 4. 生成優化建議
    recommendations = generate_optimization_recommendations(metrics, bottlenecks)
    
    # 5. 趨勢分析
    trends = analyze_trends(builds, days)
    
    report = {
        "metrics": metrics,
        "bottlenecks": bottlenecks,
        "recommendations": recommendations,
        "trends": trends
    }
    
    return format_performance_report(report)
```

**優化建議：**
- ⚡ **並行執行** - 識別可並行的任務
- 💾 **快取優化** - 改善相依套件快取
- 🎯 **縮小範圍** - 針對變更執行特定測試
- 🔧 **資源調整** - 調整 agent pool 配置
- 📦 **映像優化** - 使用更輕量的容器映像

## 監控儀表板

### 即時狀態面板

```markdown
# Pipeline 即時狀態

## 🔴 失敗的建置
- [Build #12345] main - feat/login-api (失敗於測試階段)
- [Build #12344] develop - fix/payment-bug (編譯錯誤)

## 🔵 進行中的建置
- [Build #12346] main - release/v2.1.0 (部署階段 - 3/5)
- [Build #12347] develop - chore/update-deps (測試階段 - 2/3)

## ✅ 最近成功
- [Build #12343] main - feat/dashboard (25 分鐘前)
- [Build #12342] develop - docs/api-update (1 小時前)

## 📊 今日統計
- 總建置數: 47
- 成功率: 85% (40/47)
- 平均時長: 12.5 分鐘
- 最長建置: 25 分鐘
```

### 趨勢分析圖表

```markdown
# 建置趨勢 (最近 7 天)

## 成功率趨勢
Day 1: ████████░░ 80%
Day 2: ██████████ 100%
Day 3: █████████░ 90%
Day 4: ███████░░░ 70%
Day 5: █████████░ 90%
Day 6: ██████████ 100%
Day 7: ████████░░ 85%

## 每日建置數
Day 1: ████████████████ 48
Day 2: ███████████ 35
Day 3: ██████████████ 42
Day 4: █████████████████ 52
Day 5: ████████████ 38
Day 6: ██████████ 30
Day 7: ███████████████ 47
```

## 告警設定

### 告警規則

```python
# 範例：設定告警規則
ALERT_RULES = {
    "build_failure": {
        "condition": "consecutive_failures >= 3",
        "action": "notify_team",
        "severity": "high"
    },
    "long_duration": {
        "condition": "duration > avg_duration * 2",
        "action": "notify_owner",
        "severity": "medium"
    },
    "low_success_rate": {
        "condition": "success_rate_24h < 0.7",
        "action": "notify_leads",
        "severity": "high"
    },
    "deployment_failure": {
        "condition": "deployment_failed AND environment == 'production'",
        "action": "notify_oncall",
        "severity": "critical"
    }
}
```

## 最佳實踐

1. **主動監控** - 定期檢查 pipeline 健康狀態，不要等到問題發生
2. **快速回饋** - 保持建置時間在合理範圍內（建議 <15 分鐘）
3. **清晰日誌** - 確保日誌有足夠資訊但不過於冗長
4. **失敗通知** - 建置失敗時立即通知相關人員
5. **歷史追蹤** - 保留建置歷史以分析趨勢
6. **自動重試** - 對暫時性失敗（如網路問題）啟用自動重試
7. **資源管理** - 合理配置 agent pool 避免資源瓶頸
8. **安全掃描** - 整合安全掃描工具到 pipeline
9. **效能基準** - 建立效能基準線並持續監控
10. **定期審查** - 定期審查和優化 pipeline 設定

## 故障排除指南

### 常見問題診斷

| 問題 | 可能原因 | 解決方案 |
|------|----------|----------|
| 建置卡在佇列 | Agent 資源不足 | 增加 agent 或檢查 agent 健康狀態 |
| 間歇性失敗 | 不穩定的測試 | 識別並修復 flaky tests |
| 建置時間過長 | 低效的任務或缺乏快取 | 優化任務順序，啟用快取 |
| 認證失敗 | Token 過期或權限不足 | 更新 service connection |
| 相依套件問題 | 套件來源不可用 | 使用內部 feed 或鏡像 |

### 診斷步驟

1. **檢查建置狀態** - 確認失敗的階段
2. **查看日誌** - 分析錯誤訊息
3. **比較歷史** - 對比成功和失敗的建置
4. **隔離問題** - 在本地重現問題
5. **檢查變更** - 審查最近的程式碼或設定變更
6. **驗證環境** - 確認環境設定正確
7. **測試修復** - 在分支上測試解決方案

## 參考文件

| 文件 | 內容 |
|------|------|
| [references/alert-rules.md](references/alert-rules.md) | 詳細的告警規則設定 |
| [references/log-analysis.md](references/log-analysis.md) | 日誌分析模式和技巧 |
| [references/optimization-guide.md](references/optimization-guide.md) | Pipeline 優化完整指南 |
| [references/metrics-definitions.md](references/metrics-definitions.md) | 所有指標的定義和計算方法 |

## 使用範例

### 範例 1：檢查最新建置

```plaintext
User: 檢查 main 分支的最新建置狀態

Agent 執行流程：
1. 取得 main 分支的 pipeline
2. 查詢最新建置
3. 顯示狀態、時長、結果
4. 如果失敗，提供失敗原因和日誌連結
```

### 範例 2：診斷失敗

```plaintext
User: Build #12345 失敗了，幫我診斷原因

Agent 執行流程：
1. 取得建置詳細資訊
2. 下載並分析日誌
3. 識別錯誤類型
4. 提供修復建議
5. 搜尋類似的歷史問題
```

### 範例 3：效能報告

```plaintext
User: 產生最近一個月的 pipeline 效能報告

Agent 執行流程：
1. 收集最近 30 天的建置數據
2. 計算各項效能指標
3. 識別趨勢和異常
4. 生成視覺化報告
5. 提供優化建議
```

### 範例 4：部署監控

```plaintext
User: 生產環境的部署狀態如何？

Agent 執行流程：
1. 查詢生產環境的部署 pipeline
2. 顯示最新部署資訊
3. 檢查是否有進行中的部署
4. 提供最近的部署歷史
5. 顯示相關指標（成功率、頻率等）
```

## 整合建議

- **Slack/Teams 通知** - 建置失敗時自動發送通知
- **儀表板** - 使用 Azure Dashboard 或 Grafana 視覺化指標
- **Email 摘要** - 每日或每週發送建置摘要報告
- **Webhook** - 整合外部監控系統
- **自動化修復** - 對已知問題實施自動修復腳本
- **容量規劃** - 根據使用趨勢規劃 agent pool 容量
