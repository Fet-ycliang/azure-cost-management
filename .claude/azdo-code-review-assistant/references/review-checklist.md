# Pull Request 審查檢查清單

完整的 PR 審查檢查清單，確保程式碼品質和一致性。

## 🔍 審查前準備

### 審查者準備
- [ ] 了解 PR 的上下文和目的
- [ ] 檢查關聯的 work items
- [ ] 確認自己有足夠的領域知識
- [ ] 預留足夠的審查時間
- [ ] 切換到正確的心態（建設性、客觀）

### 作者準備
- [ ] 已進行自我審查
- [ ] 所有測試都通過
- [ ] 已修復所有 linter 警告
- [ ] PR 描述完整且清晰
- [ ] 已更新相關文檔

## 📋 程式碼審查檢查清單

### 1. 正確性 (Correctness)

- [ ] **邏輯正確** - 程式碼實現了預期的功能
- [ ] **邊界條件** - 正確處理邊界情況
- [ ] **錯誤處理** - 適當的錯誤處理和例外管理
- [ ] **資料驗證** - 輸入資料經過驗證
- [ ] **並行安全** - 多執行緒環境下的安全性
- [ ] **記憶體管理** - 無記憶體洩漏風險
- [ ] **算法效率** - 使用適當的演算法和資料結構

**常見問題**:
```python
# ❌ 沒有檢查空值
def process_user(user):
    return user.name.upper()  # 如果 user 是 None 會報錯

# ✅ 正確的檢查
def process_user(user):
    if user is None:
        return None
    return user.name.upper() if user.name else ""
```

### 2. 設計 (Design)

- [ ] **單一職責** - 函數/類別有明確的單一職責
- [ ] **開放封閉** - 對擴展開放，對修改封閉
- [ ] **依賴注入** - 使用依賴注入而非硬編碼
- [ ] **抽象程度** - 適當的抽象層次
- [ ] **介面設計** - 清晰簡潔的 API 設計
- [ ] **可擴展性** - 容易擴展新功能
- [ ] **可測試性** - 程式碼容易測試

**範例**:
```python
# ❌ 違反單一職責
class UserManager:
    def create_user(self, data):
        # 驗證資料
        # 儲存到資料庫
        # 發送歡迎郵件
        # 記錄日誌
        pass

# ✅ 分離職責
class UserValidator:
    def validate(self, data): pass

class UserRepository:
    def save(self, user): pass

class EmailService:
    def send_welcome_email(self, user): pass

class UserManager:
    def __init__(self, validator, repository, email_service):
        self.validator = validator
        self.repository = repository
        self.email_service = email_service
    
    def create_user(self, data):
        self.validator.validate(data)
        user = self.repository.save(data)
        self.email_service.send_welcome_email(user)
        return user
```

### 3. 可讀性 (Readability)

- [ ] **命名清晰** - 變數、函數、類別名稱具有描述性
- [ ] **適當註解** - 解釋「為什麼」而非「是什麼」
- [ ] **程式碼結構** - 邏輯分組和適當的空行
- [ ] **魔術數字** - 使用常數代替魔術數字
- [ ] **函數長度** - 函數不超過 50 行（建議）
- [ ] **嵌套深度** - 避免過深的嵌套（建議 <4 層）
- [ ] **一致性** - 遵循專案的程式碼風格

**範例**:
```python
# ❌ 不清晰的命名和魔術數字
def calc(x, y, t):
    if t == 1:
        return x * 0.9
    elif t == 2:
        return x * 0.8
    return x

# ✅ 清晰的命名和常數
class DiscountType:
    STANDARD = 1
    PREMIUM = 2

STANDARD_DISCOUNT = 0.9
PREMIUM_DISCOUNT = 0.8

def calculate_discounted_price(original_price, quantity, discount_type):
    """計算折扣後的價格"""
    if discount_type == DiscountType.STANDARD:
        return original_price * STANDARD_DISCOUNT
    elif discount_type == DiscountType.PREMIUM:
        return original_price * PREMIUM_DISCOUNT
    return original_price
```

### 4. 效能 (Performance)

- [ ] **時間複雜度** - 使用高效的演算法
- [ ] **空間複雜度** - 合理的記憶體使用
- [ ] **資料庫查詢** - 避免 N+1 查詢問題
- [ ] **快取策略** - 適當使用快取
- [ ] **資源管理** - 正確關閉連線和釋放資源
- [ ] **批次處理** - 適當使用批次操作
- [ ] **非同步處理** - 耗時操作使用非同步

**範例**:
```python
# ❌ N+1 查詢問題
def get_users_with_orders(user_ids):
    users = []
    for user_id in user_ids:
        user = db.query(User).filter(User.id == user_id).first()
        user.orders = db.query(Order).filter(Order.user_id == user_id).all()
        users.append(user)
    return users

# ✅ 使用 JOIN 一次查詢
def get_users_with_orders(user_ids):
    return db.query(User).filter(
        User.id.in_(user_ids)
    ).options(
        joinedload(User.orders)
    ).all()
```

### 5. 安全性 (Security)

- [ ] **輸入驗證** - 所有使用者輸入都經過驗證
- [ ] **SQL 注入** - 使用參數化查詢
- [ ] **XSS 防護** - 適當的輸出編碼
- [ ] **CSRF 防護** - 使用 CSRF tokens
- [ ] **認證授權** - 正確的權限檢查
- [ ] **敏感資料** - 不記錄敏感資訊
- [ ] **加密** - 敏感資料適當加密
- [ ] **相依套件** - 無已知安全漏洞

**範例**:
```python
# ❌ SQL 注入風險
def get_user(username):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return db.execute(query)

# ✅ 使用參數化查詢
def get_user(username):
    query = "SELECT * FROM users WHERE username = :username"
    return db.execute(query, {"username": username})

# ❌ 記錄敏感資料
logger.info(f"User login: {username}, password: {password}")

# ✅ 不記錄敏感資料
logger.info(f"User login attempt: {username}")
```

### 6. 測試 (Testing)

- [ ] **測試覆蓋** - 新程式碼有適當的測試
- [ ] **測試品質** - 測試有意義且不脆弱
- [ ] **邊界測試** - 包含邊界條件的測試
- [ ] **錯誤測試** - 測試錯誤情況
- [ ] **整合測試** - 必要時包含整合測試
- [ ] **測試可讀性** - 測試程式碼清晰易懂
- [ ] **測試獨立性** - 測試之間相互獨立

**測試結構**:
```python
# ✅ 清晰的測試結構 (Arrange-Act-Assert)
def test_calculate_discounted_price():
    # Arrange - 準備測試資料
    original_price = 100
    discount_type = DiscountType.STANDARD
    expected_price = 90
    
    # Act - 執行被測試的功能
    result = calculate_discounted_price(original_price, 1, discount_type)
    
    # Assert - 驗證結果
    assert result == expected_price

def test_calculate_discounted_price_with_invalid_type():
    # 測試錯誤情況
    with pytest.raises(ValueError):
        calculate_discounted_price(100, 1, "invalid_type")
```

### 7. 文檔 (Documentation)

- [ ] **API 文檔** - 公開 API 有完整文檔
- [ ] **Docstrings** - 函數有適當的 docstrings
- [ ] **README 更新** - 必要時更新 README
- [ ] **變更說明** - PR 描述清楚說明變更
- [ ] **TODO 處理** - 必要的 TODOs 已記錄
- [ ] **設定文檔** - 新設定項目有文檔
- [ ] **遷移指南** - 重大變更有遷移指南

**Docstring 範例**:
```python
def calculate_discount(
    price: float,
    discount_percent: float,
    min_price: float = 0.0
) -> float:
    """
    計算折扣後的價格。
    
    Args:
        price: 原始價格。必須為正數。
        discount_percent: 折扣百分比 (0-100)。
        min_price: 最低價格限制。折扣後價格不會低於此值。
    
    Returns:
        折扣後的價格。
    
    Raises:
        ValueError: 如果價格為負數或折扣百分比不在 0-100 範圍內。
    
    Examples:
        >>> calculate_discount(100, 10)
        90.0
        >>> calculate_discount(100, 50, min_price=60)
        60.0
    """
    if price < 0:
        raise ValueError("Price must be non-negative")
    if not 0 <= discount_percent <= 100:
        raise ValueError("Discount percent must be between 0 and 100")
    
    discounted = price * (1 - discount_percent / 100)
    return max(discounted, min_price)
```

## 🎯 特定技術檢查

### Python

- [ ] 使用 Type Hints
- [ ] 遵循 PEP 8
- [ ] 使用 with 語句管理資源
- [ ] 適當使用列表推導式
- [ ] 避免可變預設參數
- [ ] 使用 logging 而非 print

### JavaScript/TypeScript

- [ ] 使用 TypeScript 類型
- [ ] 避免 var，使用 const/let
- [ ] 適當的 async/await 使用
- [ ] 錯誤邊界處理
- [ ] 避免記憶體洩漏
- [ ] 使用 ES6+ 語法

### SQL

- [ ] 使用索引優化查詢
- [ ] 避免 SELECT *
- [ ] 使用參數化查詢
- [ ] 適當使用 JOIN
- [ ] 考慮查詢效能

### API 設計

- [ ] RESTful 原則
- [ ] 適當的 HTTP 狀態碼
- [ ] API 版本控制
- [ ] 錯誤回應格式一致
- [ ] 分頁處理
- [ ] 速率限制考慮

## 📝 審查評論指南

### 評論分類

使用標籤分類評論：
- `[MUST]` - 必須修改才能合併
- `[SUGGEST]` - 建議修改但非必須
- `[QUESTION]` - 需要澄清的問題
- `[PRAISE]` - 正面回饋
- `[NOTE]` - 資訊性評論

### 評論範例

**好的評論**:
```
[MUST] 此處存在 SQL 注入風險
建議使用參數化查詢:
db.execute("SELECT * FROM users WHERE id = :id", {"id": user_id})
```

```
[SUGGEST] 考慮提取這個邏輯到獨立函數以提高可讀性
這樣也更容易測試
```

```
[PRAISE] 很好的錯誤處理！清楚的錯誤訊息將有助於除錯
```

**避免的評論**:
```
❌ 這個程式碼很糟糕
❌ 為什麼要這樣寫？
❌ 改成我的方式
```

## ⏱️ 審查時間指南

- **小型 PR (<100 行)**: 15-30 分鐘
- **中型 PR (100-400 行)**: 30-60 分鐘
- **大型 PR (>400 行)**: 應拆分或安排專門時間

## ✅ 審查完成檢查

- [ ] 所有檢查項目已確認
- [ ] 評論清晰且具建設性
- [ ] 已測試關鍵路徑（如可能）
- [ ] 已檢查相關文檔
- [ ] 做出明確的審查決定（批准/請求變更/評論）

## 📚 參考資源

- [Google Code Review Guidelines](https://google.github.io/eng-practices/review/)
- [Conventional Comments](https://conventionalcomments.org/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
