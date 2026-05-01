# Capacity Planning 指南

完整的 Sprint 容量規劃方法，包含團隊容量計算、分配策略和優化技巧。

## 容量規劃基礎

### 什麼是 Sprint Capacity？

**Sprint Capacity（衝刺容量）** = 團隊在一個 Sprint 內可用於開發工作的總工時

**容量包含**:
- ✅ 開發時間
- ✅ 測試時間
- ✅ Code Review 時間
- ✅ 技術文檔時間

**容量不包含**:
- ❌ Scrum 儀式（Planning, Daily Standup, Review, Retro）
- ❌ 非計劃會議（臨時會議除非預期會發生）
- ❌ 訓練和學習（除非是 Sprint 計劃的一部分）
- ❌ 支援既有系統（除非明確計劃）

## 計算團隊容量

### 基本公式

```
團隊總容量 = Σ（每位成員的可用工時）
```

### 個人可用工時計算

```
個人可用工時 = 
    (工作天數 × 每日工時) 
    - 請假時數
    - Scrum活動時數
    - 預期會議時數
    - 專注度係數調整
```

### 詳細計算範例

**情境：2週 Sprint，5人團隊**

#### 步驟 1：計算基礎工時

```
Sprint 期間: 2023-03-01 到 2023-03-14 (10個工作日)
標準每日工時: 8 小時
基礎工時: 10 天 × 8 小時 = 80 小時/人
```

#### 步驟 2：扣除 Scrum 活動

| 活動 | 時間 | 說明 |
|------|------|------|
| Sprint Planning | 4h | Sprint 開始 |
| Daily Standup | 2.5h | 15分鐘 × 10天 |
| Sprint Review | 2h | Sprint 結束 |
| Sprint Retrospective | 1.5h | Sprint 結束 |
| **總計** | **10h** | |

```
扣除後: 80h - 10h = 70h/人
```

#### 步驟 3：扣除其他固定承諾

| 活動 | 時間 | 說明 |
|------|------|------|
| 部門週會 | 2h | 1小時 × 2週 |
| 技術分享會 | 1h | 每隔週一次 |
| 產品同步會 | 2h | 1小時 × 2週 |
| **總計** | **5h** | |

```
扣除後: 70h - 5h = 65h/人
```

#### 步驟 4：應用專注度係數

考慮日常中斷、緊急問題、Email處理等：

```
專注度係數: 0.85 (預期85%時間可專注於Sprint工作)
調整後: 65h × 0.85 = 55.25h ≈ 55h/人
```

#### 步驟 5：扣除個人請假

**團隊成員情況**：

| 成員 | 角色 | 可用工時 | 請假 | 最終容量 |
|------|------|----------|------|----------|
| Alice | Senior Dev | 55h | 0h | 55h |
| Bob | Dev | 55h | 16h (2天) | 39h |
| Carol | Dev | 55h | 0h | 55h |
| David | QA | 55h | 0h | 55h |
| Eve | DevOps | 55h | 8h (1天) | 47h |
| **總計** | - | **275h** | **24h** | **251h** |

### 容量計算工具

#### Python 腳本

```python
from datetime import datetime, timedelta
from typing import List, Dict

class TeamMember:
    def __init__(self, name: str, role: str, hours_per_day: float = 8.0):
        self.name = name
        self.role = role
        self.hours_per_day = hours_per_day
        self.time_off_days = 0
        self.other_commitments_hours = 0
    
    def calculate_capacity(
        self,
        sprint_days: int,
        scrum_hours: float,
        focus_factor: float = 0.85
    ) -> float:
        """計算個人Sprint容量"""
        # 基礎工時
        base_hours = sprint_days * self.hours_per_day
        
        # 扣除請假
        time_off_hours = self.time_off_days * self.hours_per_day
        
        # 扣除固定活動
        available_hours = base_hours - time_off_hours - scrum_hours - self.other_commitments_hours
        
        # 應用專注度係數
        capacity = available_hours * focus_factor
        
        return max(0, capacity)  # 確保不為負數

class SprintCapacityPlanner:
    def __init__(self, sprint_days: int = 10):
        self.sprint_days = sprint_days
        self.team_members: List[TeamMember] = []
        self.scrum_hours = self._calculate_scrum_hours()
        self.focus_factor = 0.85
    
    def _calculate_scrum_hours(self) -> float:
        """計算Scrum活動總時數"""
        return (
            4.0 +  # Sprint Planning
            (self.sprint_days * 0.25) +  # Daily Standup (15分鐘)
            2.0 +  # Sprint Review
            1.5    # Sprint Retrospective
        )
    
    def add_member(self, member: TeamMember):
        """加入團隊成員"""
        self.team_members.append(member)
    
    def calculate_team_capacity(self) -> Dict:
        """計算團隊總容量"""
        capacities = []
        total_capacity = 0
        
        for member in self.team_members:
            capacity = member.calculate_capacity(
                self.sprint_days,
                self.scrum_hours,
                self.focus_factor
            )
            capacities.append({
                "name": member.name,
                "role": member.role,
                "capacity": capacity,
                "time_off": member.time_off_days
            })
            total_capacity += capacity
        
        return {
            "total_capacity_hours": total_capacity,
            "sprint_days": self.sprint_days,
            "scrum_hours": self.scrum_hours,
            "focus_factor": self.focus_factor,
            "members": capacities
        }
    
    def generate_report(self) -> str:
        """生成容量報告"""
        result = self.calculate_team_capacity()
        
        report = f"""
Sprint Capacity Report
{'='*60}

Sprint 期間: {self.sprint_days} 個工作日
Scrum 活動時數: {self.scrum_hours:.1f}h
專注度係數: {self.focus_factor:.0%}

團隊成員容量:
{'-'*60}
"""
        for member in result["members"]:
            time_off_note = f" (請假{member['time_off']}天)" if member['time_off'] > 0 else ""
            report += f"{member['name']:12} ({member['role']:10}): {member['capacity']:5.1f}h{time_off_note}\n"
        
        report += f"{'-'*60}\n"
        report += f"{'團隊總容量':12}: {result['total_capacity_hours']:.1f}h\n"
        report += f"{'='*60}\n"
        
        return report

# 使用範例
planner = SprintCapacityPlanner(sprint_days=10)

# 加入團隊成員
alice = TeamMember("Alice", "Senior Dev")
bob = TeamMember("Bob", "Dev")
bob.time_off_days = 2  # 請假2天

carol = TeamMember("Carol", "Dev")
david = TeamMember("David", "QA")
eve = TeamMember("Eve", "DevOps")
eve.time_off_days = 1  # 請假1天

planner.add_member(alice)
planner.add_member(bob)
planner.add_member(carol)
planner.add_member(david)
planner.add_member(eve)

# 生成報告
print(planner.generate_report())

# 輸出範例:
"""
Sprint Capacity Report
============================================================

Sprint 期間: 10 個工作日
Scrum 活動時數: 10.0h
專注度係數: 85%

團隊成員容量:
------------------------------------------------------------
Alice        (Senior Dev):  55.3h
Bob          (Dev       ):  39.1h (請假2天)
Carol        (Dev       ):  55.3h
David        (QA        ):  55.3h
Eve          (DevOps    ):  47.2h (請假1天)
------------------------------------------------------------
團隊總容量: 252.1h
============================================================
"""
```

## 容量分配策略

### 按技能分配

根據團隊成員的專長分配工作：

| 成員 | 技能 | 容量 | 分配類型 |
|------|------|------|----------|
| Alice | Backend (Expert) | 55h | 後端開發 (80%), Code Review (20%) |
| Bob | Frontend (Senior) | 39h | 前端開發 (90%), 文檔 (10%) |
| Carol | Full-stack | 55h | 前後端均分 (50%/50%) |
| David | QA (Expert) | 55h | 測試 (70%), 自動化 (30%) |
| Eve | DevOps | 47h | 基礎設施 (60%), CI/CD (40%) |

### 容量緩衝（Buffer）

保留一定比例的容量應對意外：

```
計劃容量 = 總容量 × (1 - 緩衝比例)

建議緩衝比例:
- 穩定團隊: 10-15%
- 新團隊: 20-25%
- 高風險Sprint: 25-30%
```

**範例**：
```
總容量: 251h
緩衝比例: 15%
計劃容量: 251h × 0.85 = 213.4h ≈ 213h

建議承諾: 213h 的工作量
```

### T型技能平衡

確保關鍵領域有足夠的備援：

```markdown
## 技能矩陣範例

|      | Backend | Frontend | QA | DevOps |
|------|---------|----------|-----|--------|
| Alice | ⚫⚫⚫ | ⚫⚪⚪ | ⚫⚪⚪ | ⚫⚪⚪ |
| Bob   | ⚫⚪⚪ | ⚫⚫⚫ | ⚫⚫⚪ | ⚫⚪⚪ |
| Carol | ⚫⚫⚪ | ⚫⚫⚪ | ⚫⚪⚪ | ⚫⚪⚪ |
| David | ⚫⚪⚪ | ⚫⚪⚪ | ⚫⚫⚫ | ⚫⚪⚪ |
| Eve   | ⚫⚪⚪ | ⚫⚪⚪ | ⚫⚫⚪ | ⚫⚫⚫ |

Legend: ⚫⚫⚫ Expert, ⚫⚫⚪ Proficient, ⚫⚪⚪ Basic

風險分析:
✅ Backend: 2個專家 (Alice, Carol)
✅ Frontend: 2個專家 (Bob, Carol)  
✅ QA: 2個高手 (David, Bob)
✅ DevOps: 1個專家 (Eve) - 注意風險！建議交叉訓練
```

## 容量監控

### Sprint Burndown（燃盡圖）

追蹤剩餘工作量：

```
理想燃盡速率 = 總容量 / Sprint天數

每日更新:
- 剩餘工作 (Remaining Work)
- 完成工作 (Completed Work)
- 理想線 (Ideal Line)
```

#### 燃盡圖範例數據

```python
sprint_data = {
    "total_capacity": 213,  # 小時
    "sprint_days": 10,
    "daily_tracking": [
        {"day": 1, "remaining": 213, "completed": 0},
        {"day": 2, "remaining": 190, "completed": 23},
        {"day": 3, "remaining": 168, "completed": 45},
        {"day": 4, "remaining": 150, "completed": 63},
        {"day": 5, "remaining": 128, "completed": 85},
        # Weekend break
        {"day": 8, "remaining": 105, "completed": 108},
        {"day": 9, "remaining": 78, "completed": 135},
        {"day": 10, "remaining": 45, "completed": 168},
    ]
}

# 計算理想線
ideal_rate = sprint_data["total_capacity"] / sprint_data["sprint_days"]
for day_data in sprint_data["daily_tracking"]:
    day_data["ideal"] = sprint_data["total_capacity"] - (ideal_rate * day_data["day"])
```

### Capacity Utilization（容量使用率）

監控容量分配效率：

```python
def calculate_utilization(planned_hours: float, actual_hours: float) -> dict:
    """計算容量使用率"""
    utilization = (actual_hours / planned_hours) * 100 if planned_hours > 0 else 0
    
    # 評估
    if utilization < 70:
        status = "Under-utilized（使用不足）"
        recommendation = "增加承諾或重新評估容量"
    elif 70 <= utilization <= 95:
        status = "Optimal（最佳）"
        recommendation = "維持當前節奏"
    elif 95 < utilization <= 110:
        status = "High（高使用率）"
        recommendation = "注意團隊負荷"
    else:
        status = "Over-utilized（過度使用）"
        recommendation = "減少承諾或增加資源"
    
    return {
        "utilization": f"{utilization:.1f}%",
        "status": status,
        "recommendation": recommendation
    }

# 範例
result = calculate_utilization(planned_hours=213, actual_hours=205)
print(result)
# 輸出: {'utilization': '96.2%', 'status': 'High', 'recommendation': '注意團隊負荷'}
```

### 每日容量追蹤

在 Daily Standup 更新：

```markdown
## Daily Standup 容量檢查

**問題**：
1. 昨天完成了什麼? → 更新 Completed Work
2. 今天計劃做什麼? → 確認分配
3. 有什麼阻礙? → 調整容量預期

**更新 Task**：
- Remaining Work（剩餘工作）
- Completed Work（完成工作）

**檢查點**：
- 是否按計劃進度?
- 需要重新分配工作嗎?
- 有人負荷過重或過輕嗎?
```

## 容量優化技巧

### 1. 減少Context Switching（減少上下文切換）

```markdown
❌ 避免:
- 同時處理多個 PBI
- 頻繁切換不同類型的任務

✅ 推薦:
- 一次專注一個 PBI
- 批次處理相似任務（如：所有 code review 一起做）
- Work In Progress (WIP) 限制：每人最多2個活躍任務
```

### 2. Pair Programming 考量

```
Pair Programming 容量計算:
- 2個人 × 4小時 = 4小時產出（不是8小時）
- 但品質更高，bug更少
- 適合：複雜功能、知識傳遞、新成員培訓
```

### 3. 技術債務時間盒

預留容量處理技術債務：

```
建議分配:
- 70% 新功能開發
- 20% Bug修復和維護
- 10% 技術債務和改善

範例（213h總容量）:
- 新功能: 149h
- Bug修復: 43h
- 技術債務: 21h
```

### 4. 學習和成長時間

```
預留時間給團隊成長:
- 每Sprint 5-10% 容量
- 用於：技術研究、新工具學習、技能提升

範例：213h × 5% = 10.6h ≈ 11h
相當於每人每Sprint 2-3小時的學習時間
```

## 特殊情況處理

### 長假期間的Sprint

```markdown
## 範例：包含3天連假的Sprint

標準2週Sprint: 10工作日
扣除連假: 10 - 3 = 7工作日

選項1: 縮短Sprint
- 只規劃7天的Sprint
- 容量相應減少

選項2: 延長Sprint
- 延長為3週Sprint
- 容量計算需考慮更多變數

選項3: 正常進行但降低承諾
- 仍為2週Sprint
- 但承諾減少30%

建議: 選項1（縮短Sprint保持節奏）
```

### 多專案團隊成員

```python
# 成員分配給多個專案
member_allocation = {
    "name": "Alice",
    "total_capacity": 55,
    "allocations": [
        {"project": "Project A", "percentage": 70, "hours": 38.5},
        {"project": "Project B", "percentage": 30, "hours": 16.5}
    ]
}

# 每個Sprint規劃時只計算該專案分配的容量
project_a_capacity = 38.5  # 小時
```

### 新成員加入

```markdown
## 新成員生產力曲線

Week 1-2: 30% 生產力（學習環境、工具、流程）
Week 3-4: 50% 生產力（開始貢獻，需要指導）
Week 5-8: 70% 生產力（獨立工作，偶爾需要協助）
Week 9+: 90% 生產力（接近全速）

容量調整範例:
新成員（第3週）: 55h × 0.5 = 27.5h
加上老成員指導成本: -5h × 2人 = -10h
淨增加容量: 27.5h - 10h = 17.5h
```

## 容量規劃檢查清單

### Sprint Planning 前

- [ ] 確認Sprint起迄日期
- [ ] 收集所有成員的請假資訊
- [ ] 識別固定會議和承諾
- [ ] 檢視上個Sprint的容量使用率
- [ ] 準備容量計算工具/試算表

### Sprint Planning 中

- [ ] 計算並分享團隊總容量
- [ ] 考慮技能分配平衡
- [ ] 預留適當緩衝
- [ ] 確認每個人的工作量合理
- [ ] 記錄容量假設和調整

### Sprint 期間

- [ ] 每日更新 Remaining Work
- [ ] 監控燃盡圖趨勢
- [ ] 識別並處理瓶頸
- [ ] 必要時重新分配工作
- [ ] 記錄容量變化（臨時請假、緊急任務等）

### Sprint 結束

- [ ] 比較計劃vs實際容量
- [ ] 分析容量使用率
- [ ] 識別容量估算偏差的原因
- [ ] 更新下個Sprint的容量係數
- [ ] 文檔化學習點

## Azure DevOps 容量設定

### 配置團隊容量

```
Azure DevOps → Boards → Sprints → Capacity

每個成員設定:
1. Capacity per day (每日容量): 6小時
   (8小時 - Scrum活動 - 其他會議 - 專注度調整)

2. Days off (請假日): 標記請假日期

3. Activity (活動類型分配):
   - Development: 60%
   - Testing: 20%
   - Design: 10%
   - Documentation: 10%
```

### 產生容量報告

使用 Azure DevOps Analytics：

```
查詢範例:
- Team Capacity vs. Work
- Capacity by Activity
- Daily Capacity Burn
- Sprint Burndown
```

## 容量規劃範本

### Excel/Google Sheets 範本

```
Column A: 成員名稱
Column B: 角色
Column C: Sprint天數
Column D: 每日工時
Column E: 請假天數
Column F: Scrum活動（小時）
Column G: 其他會議（小時）
Column H: 專注度係數
Column I: 計算容量 = (C*D - E*D - F - G) * H

Row 底部: SUM(Column I) = 團隊總容量
```

### 會議記錄範本

```markdown
# Sprint X Capacity Planning

**Sprint**: Sprint X (YYYY-MM-DD to YYYY-MM-DD)
**Team**: [Team Name]
**Planned by**: [Scrum Master/Team]

## 容量摘要
- **Sprint 天數**: 10天
- **團隊總容量**: 213小時
- **緩衝 (15%)**: 32小時
- **可承諾容量**: 181小時

## 成員容量

| 成員 | 角色 | 請假 | 容量(h) | 分配重點 |
|------|------|------|---------|----------|
| Alice | Senior Dev | 0天 | 55h | Backend APIs |
| Bob | Dev | 2天 | 39h | Frontend |
| Carol | Dev | 0天 | 55h | Full-stack |
| David | QA | 0天 | 55h | Testing |
| Eve | DevOps | 1天 | 47h | CI/CD |

## 容量分配

| 類別 | 小時 | 百分比 |
|------|------|--------|
| 新功能開發 | 127h | 70% |
| Bug修復 | 36h | 20% |
| 技術債務 | 18h | 10% |
| **總計** | **181h** | **100%** |

## 假設和風險
- 假設: 無臨時中斷或緊急事項
- 風險: Eve是唯一的DevOps專家
- 緩解: 交叉訓練Carol學習基本DevOps

## 核准
- [ ] Team reviewed and agreed
- [ ] Product Owner aware of capacity constraints
```

## 參考資源

- **Scrum Guide** - 官方容量規劃指南
- **Agile Capacity Planning** - Mike Cohn's best practices
- **Team Velocity and Capacity** - Azure DevOps documentation
- **Focus Factor Research** - 生產力研究數據
