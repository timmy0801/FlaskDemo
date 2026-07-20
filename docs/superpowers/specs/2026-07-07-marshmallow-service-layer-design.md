# Marshmallow 輸入驗證 + Service Layer 設計文件

**日期：** 2026-07-07  
**專案：** Flask 電商後台 API  
**範疇：** 加入 Marshmallow 輸入驗證，並引入 Service Layer 架構

---

## 1. 背景與目標

### 現有問題
目前所有 Blueprint route 直接處理 `request.get_json()`，缺乏結構化驗證：
- 只檢查欄位是否存在，無型別、格式、範圍驗證
- `price` 可傳負數、`quantity` 可傳 0 或負數
- email 格式未驗證、密碼無最低長度限制
- 業務邏輯（DB 查詢、庫存扣除）與 HTTP 處理混在同一個函式

### 目標
1. 加入 Marshmallow 格式驗證層，所有輸入在進入業務邏輯前先通過 Schema 驗證
2. 引入 Service Layer，將業務邏輯從 route 中分離
3. 統一錯誤處理機制，透過自訂例外自動映射 HTTP status code

---

## 2. 整體架構

```
HTTP Request
     │
     ▼
┌─────────────┐
│   Route     │  只做 HTTP：解析 request、呼叫 service、回傳 response
│  (blueprint)│
└──────┬──────┘
       │ @validate_body(Schema) 攔截，驗證失敗直接回傳 400
       ▼
┌─────────────┐
│   Schema    │  格式/型別驗證：email 格式、price > 0、密碼長度...
│ (blueprint) │
└──────┬──────┘
       │ 驗證通過，validated_data 傳入 service
       ▼
┌─────────────┐
│   Service   │  業務邏輯：唯一性檢查、庫存驗證、樂觀鎖、DB 操作
│(app/services)│  失敗時 raise 自訂例外
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Model    │  SQLAlchemy ORM（不改動）
└─────────────┘
```

---

## 3. 檔案結構變更

### 新增檔案

```
app/
├── services/
│   ├── auth_service.py
│   ├── product_service.py
│   ├── order_service.py
│   └── user_service.py
├── utils/
│   └── exceptions.py             ← 自訂例外類別
├── blueprints/
│   ├── auth/
│   │   └── schemas.py
│   ├── products/
│   │   └── schemas.py
│   ├── orders/
│   │   └── schemas.py
│   └── users/
│       └── schemas.py
```

### 修改檔案

| 檔案 | 變更說明 |
|------|---------|
| `requirements.txt` | 新增 `marshmallow>=3.20.0` |
| `app/utils/decorators.py` | 新增 `validate_body` 裝飾器 |
| `app/middleware/error_handler.py` | 新增 `AppError` 捕捉 handler |
| `app/blueprints/auth/routes.py` | 改薄，委派給 auth_service |
| `app/blueprints/products/routes.py` | 改薄，委派給 product_service |
| `app/blueprints/orders/routes.py` | 改薄，委派給 order_service |
| `app/blueprints/users/routes.py` | 改薄，委派給 user_service |

---

## 4. Schema 驗證規則

### Auth（`app/blueprints/auth/schemas.py`）

| Schema | 欄位 | 型別 | 規則 |
|--------|------|------|------|
| `RegisterSchema` | `username` | String | 必填，長度 2–80 |
| | `email` | Email | 必填，email 格式 |
| | `password` | String | 必填，最少 6 字元 |
| `LoginSchema` | `email` | Email | 必填 |
| | `password` | String | 必填 |

### Products（`app/blueprints/products/schemas.py`）

| Schema | 欄位 | 型別 | 規則 |
|--------|------|------|------|
| `CreateProductSchema` | `name` | String | 必填，長度 1–200 |
| | `price` | Float | 必填，> 0 |
| | `stock` | Integer | 選填，>= 0，預設 0 |
| | `category` | String | 選填 |
| | `description` | String | 選填 |
| | `image_url` | URL | 選填，合法 URL 格式 |
| `UpdateProductSchema` | 同上 | | 全部選填，獨立 class |

### Orders（`app/blueprints/orders/schemas.py`）

| Schema | 欄位 | 型別 | 規則 |
|--------|------|------|------|
| `CreateOrderSchema` | `items` | List[OrderItemSchema] | 必填，至少 1 筆 |
| `OrderItemSchema` | `product_id` | Integer | 必填，>= 1 |
| | `quantity` | Integer | 必填，>= 1 |
| `UpdateOrderStatusSchema` | `status` | String | 必填，限 pending/paid/shipped/delivered/cancelled |

### Users（`app/blueprints/users/schemas.py`）

| Schema | 欄位 | 型別 | 規則 |
|--------|------|------|------|
| `UpdateUserSchema` | `username` | String | 選填，長度 2–80 |
| | `password` | String | 選填，最少 6 字元 |
| | `is_active` | Boolean | 選填（service 層確認 admin 才生效） |
| | `role` | String | 選填，限 `user`/`admin`（service 層確認 admin 才生效） |

---

## 5. 自訂例外（`app/utils/exceptions.py`）

```python
class AppError(Exception):
    def __init__(self, message, status_code):
        self.message = message
        self.status_code = status_code

class ConflictError(AppError):    # 409
class NotFoundError(AppError):    # 404
class BadRequestError(AppError):  # 400
class ForbiddenError(AppError):   # 403
```

`error_handler.py` 新增 handler：
```python
@app.errorhandler(AppError)
def handle_app_error(e):
    return jsonify({'error': e.message}), e.status_code
```

---

## 6. validate_body 裝飾器（`app/utils/decorators.py`）

```python
def validate_body(schema_class):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            data = request.get_json()
            schema = schema_class()
            try:
                validated = schema.load(data or {})
            except ValidationError as err:
                return jsonify({'errors': err.messages}), 400
            kwargs['validated_data'] = validated
            return fn(*args, **kwargs)
        return wrapper
    return decorator
```

驗證失敗回應範例：
```json
{
  "errors": {
    "email": ["Not a valid email address."],
    "password": ["Shorter than minimum length 6."]
  }
}
```

---

## 7. Service 函式簽名

```python
# auth_service.py
def register(data: dict) -> dict          # 回傳 user.to_dict()
def login(data: dict) -> dict             # 回傳 {access_token, user}

# product_service.py
def get_products(page, per_page, category) -> dict
def get_product(product_id) -> dict
def create_product(data: dict) -> dict
def update_product(product_id, data: dict) -> dict
def delete_product(product_id) -> None

# order_service.py
def get_orders(user_id, claims, page, per_page) -> dict
def get_order(order_id, user_id, claims) -> dict
def create_order(user_id, data: dict) -> dict   # 含樂觀鎖邏輯
def update_order_status(order_id, data: dict, claims: dict) -> dict

# user_service.py
def get_users(page, per_page) -> dict
def get_user(user_id) -> dict
def update_user(user_id, data: dict, claims: dict) -> dict
def deactivate_user(user_id) -> None
```

---

## 8. Route 改寫範例

**Before（auth/routes.py register）：**
```python
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or not all(k in data for k in ('username', 'email', 'password')):
        return jsonify({'error': '缺少必要欄位'}), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': '此 Email 已被註冊'}), 409
    # ... DB 操作 ...
```

**After：**
```python
@auth_bp.route('/register', methods=['POST'])
@validate_body(RegisterSchema)
def register(validated_data):
    user = auth_service.register(validated_data)
    return jsonify({'message': '註冊成功', 'user': user}), 201
```

---

## 9. 裝飾器堆疊順序

需要同時使用 JWT 驗證與 body 驗證的 route，裝飾器順序如下：

```python
@owner_or_admin_required   # 外層：先驗身份
@validate_body(UpdateUserSchema)  # 內層：再驗資料
def update_user(user_id, validated_data):
    ...
```

Python 裝飾器由外到內執行，確保身份驗證失敗時不會觸發 body 解析。

---

## 10. 不在本次範疇

- 查詢參數（`page`、`per_page`、`category`）的 Schema 驗證
- Service 單元測試
- Model 層異動
