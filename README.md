# Flask 電商後台 API

以 Flask 打造的電商後台 RESTful API，展示 Blueprint 模組化、SQLAlchemy ORM、JWT 驗證等實務技術。

## 技術棧

- **Flask 3** - Web 框架
- **SQLAlchemy + Flask-Migrate** - ORM 與資料庫版本控制
- **Marshmallow** - 請求格式驗證
- **Flask-JWT-Extended** - JWT 身份驗證（access token + httpOnly cookie 的 refresh token，含 CSRF 防護與 token rotation）
- **SQLite**（開發）/ 可替換為 PostgreSQL（生產）
- **Faker** - 假資料產生
- **pytest** - 測試

## 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定環境變數

複製 `.env` 並修改 Secret Key：

```bash
cp .env .env.local
```

### 3. 初始化資料庫

```bash
flask db init
flask db migrate -m "initial migration"
flask db upgrade
```

### 4. 填入測試假資料

```bash
flask seed
# 可指定數量
flask seed --users 20 --products 100
```

### 5. 啟動開發伺服器

```bash
flask run
```

API 服務將在 `http://localhost:5000` 啟動。

### 6. 執行測試

```bash
pytest
# 顯示每個測試名稱
pytest -v
```

測試使用獨立的 in-memory SQLite（`testing` config），不會動到開發用的資料庫。

---

## API 端點

### 驗證 `/api/auth`

| 方法 | 路徑 | 說明 | 驗證 |
|------|------|------|------|
| POST | `/register` | 註冊新帳號 | 無 |
| POST | `/login` | 登入取得 access token；同時會設定一個 httpOnly 的 refresh token cookie | 無 |
| GET | `/me` | 取得當前使用者資訊 | Access token |
| POST | `/refresh` | 用 refresh token 換發新的 access token（同時 rotate refresh token） | Refresh token cookie + CSRF header |
| POST | `/logout` | 撤銷目前的 refresh token、清除 cookie | Refresh token cookie + CSRF header |

**Access token** 效期 1 小時，走 `Authorization: Bearer <token>` header，login/refresh 的 JSON 回應都會回傳。

**Refresh token** 效期 30 天，透過 `Set-Cookie` 存成 httpOnly cookie（`refresh_token_cookie`，只在 `/api/auth` 路徑下會被送出），**不會**出現在任何 JSON 回應裡。呼叫 `/refresh`、`/logout` 時，除了瀏覽器自動帶的 cookie 之外，還要額外帶一個 `X-CSRF-TOKEN` header，值來自登入時一起設定的、JS 可讀的 `csrf_refresh_token` cookie（CSRF double-submit 防護，由 Flask-JWT-Extended 內建處理，不用自己刻）。

每次呼叫 `/refresh` 都會作廢舊的 refresh token、換發一組新的（rotation）；如果偵測到「已經作廢的 refresh token 被重複使用」，會視為 token 被偷，直接撤銷該使用者名下所有 refresh token（強制所有裝置登出）。

### 商品 `/api/products`

| 方法 | 路徑 | 說明 | 驗證 |
|------|------|------|------|
| GET | `/` | 取得商品列表（分頁、分類篩選、關鍵字搜尋、排序） | 無 |
| GET | `/<id>` | 取得單一商品 | 無 |
| POST | `/` | 新增商品 | Admin |
| PUT | `/<id>` | 更新商品 | Admin |
| DELETE | `/<id>` | 下架商品（軟刪除） | Admin |
| GET | `/<id>/inventory-logs` | 取得該商品的庫存異動紀錄（分頁） | Admin |
| POST | `/<id>/inventory-logs` | 補貨（`restock`）或人工調整庫存（`adjust`） | Admin |

`GET /` 支援的 query string：

| 參數 | 說明 |
|------|------|
| `q` | 依商品名稱關鍵字搜尋（不分大小寫、包含比對） |
| `category` | 依分類篩選 |
| `sort_by` | `price` 或 `created_at`，其他值/未帶 → 預設 `created_at` |
| `order` | `asc` 或 `desc`，其他值/未帶 → 預設 `desc`（最新上架優先） |
| `page` / `per_page` | 分頁，`per_page` 上限 100 |

### 訂單 `/api/orders`

| 方法 | 路徑 | 說明 | 驗證 |
|------|------|------|------|
| GET | `/` | 取得訂單列表（Admin 看全部，一般使用者只看自己的） | JWT |
| GET | `/<id>` | 取得單一訂單（本人或 Admin） | JWT |
| POST | `/` | 建立新訂單（會扣庫存、寫入庫存異動紀錄） | JWT |
| PATCH | `/<id>/status` | 更新訂單狀態：Admin 可設定任意合法狀態；一般使用者只能把自己「pending」狀態的訂單改成 `cancelled`（取消後會自動把庫存加回去） | JWT |

### 會員 `/api/users`

| 方法 | 路徑 | 說明 | 驗證 |
|------|------|------|------|
| GET | `/` | 取得所有會員（分頁，上限 100） | Admin |
| GET | `/<id>` | 取得單一會員 | JWT（本人或 Admin）|
| PUT | `/<id>` | 更新會員資訊 | JWT（本人或 Admin）|
| DELETE | `/<id>` | 停用帳號 | Admin |

---

## 專案結構

Route 只做 HTTP 解析/回應，業務邏輯都在 `services/`；輸入格式驗證用 Marshmallow schema，業務例外統一由 `middleware/error_handler.py` 轉成 HTTP 錯誤。

```
flask-ecommerce-api/
├── app/
│   ├── __init__.py          # Flask App 初始化、Blueprint 註冊、JWT callback 註冊
│   ├── commands.py          # CLI 指令（seed、init-db）
│   ├── blueprints/
│   │   ├── auth/            # 登入、註冊、refresh、logout（routes.py + schemas.py）
│   │   ├── products/        # 商品 CRUD、庫存調整、搜尋排序
│   │   ├── orders/          # 訂單建立/查詢/狀態變更
│   │   └── users/           # 會員管理
│   ├── models/
│   │   ├── user.py
│   │   ├── product.py
│   │   ├── order.py          # Order、OrderItem
│   │   ├── inventory_log.py  # 庫存異動紀錄（deduct/restock/adjust）
│   │   └── refresh_token.py  # refresh token 撤銷狀態追蹤
│   ├── services/            # 業務邏輯（auth/product/order/user_service.py）
│   ├── utils/
│   │   ├── decorators.py     # admin_required、validate_body、owner_or_admin_required
│   │   ├── exceptions.py     # AppError 及子類別
│   │   ├── jwt_callbacks.py  # refresh token 撤銷檢查（token_in_blocklist_loader）
│   │   └── pagination.py     # per_page 上限
│   └── middleware/
│       ├── request_logger.py  # 請求 Log（Before/After Request）
│       └── error_handler.py   # 全域錯誤處理
├── migrations/               # Flask-Migrate 版本控制
├── tests/                    # pytest 測試套件
├── config.py                 # 環境設定
├── run.py                    # 啟動入口
├── requirements.txt
└── .env
```

## 測試帳號（執行 seed 後）

| 帳號 | 密碼 | 角色 |
|------|------|------|
| admin@example.com | admin123 | Admin |
| （其他由 Faker 產生） | password123 | User |
