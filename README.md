# Flask 電商後台 API

以 Flask 打造的電商後台 RESTful API，展示 Blueprint 模組化、SQLAlchemy ORM、JWT 驗證等實務技術。

## 技術棧

- **Flask 3** - Web 框架
- **SQLAlchemy + Flask-Migrate** - ORM 與資料庫版本控制
- **Flask-JWT-Extended** - JWT 身份驗證
- **SQLite**（開發）/ 可替換為 PostgreSQL（生產）
- **Faker** - 假資料產生

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

---

## API 端點

### 驗證 `/api/auth`

| 方法 | 路徑 | 說明 | 驗證 |
|------|------|------|------|
| POST | `/register` | 註冊新帳號 | 無 |
| POST | `/login` | 登入取得 JWT Token | 無 |
| GET | `/me` | 取得當前使用者資訊 | JWT |

### 商品 `/api/products`

| 方法 | 路徑 | 說明 | 驗證 |
|------|------|------|------|
| GET | `/` | 取得商品列表（分頁、分類篩選） | 無 |
| GET | `/<id>` | 取得單一商品 | 無 |
| POST | `/` | 新增商品 | Admin |
| PUT | `/<id>` | 更新商品 | Admin |
| DELETE | `/<id>` | 下架商品（軟刪除） | Admin |

### 訂單 `/api/orders`

| 方法 | 路徑 | 說明 | 驗證 |
|------|------|------|------|
| GET | `/` | 取得訂單列表（Admin 看全部） | JWT |
| GET | `/<id>` | 取得單一訂單 | JWT |
| POST | `/` | 建立新訂單 | JWT |
| PATCH | `/<id>/status` | 更新訂單狀態 | Admin |

### 會員 `/api/users`

| 方法 | 路徑 | 說明 | 驗證 |
|------|------|------|------|
| GET | `/` | 取得所有會員 | Admin |
| GET | `/<id>` | 取得單一會員 | JWT（本人或 Admin）|
| PUT | `/<id>` | 更新會員資訊 | JWT（本人或 Admin）|
| DELETE | `/<id>` | 停用帳號 | Admin |

---

## 專案結構

```
flask-ecommerce-api/
├── app/
│   ├── __init__.py          # Flask App 初始化、Blueprint 註冊
│   ├── commands.py          # CLI 指令（seed、init-db）
│   ├── blueprints/
│   │   ├── auth/            # 登入、註冊
│   │   ├── products/        # 商品 CRUD
│   │   ├── orders/          # 訂單管理
│   │   └── users/           # 會員管理
│   ├── models/
│   │   ├── user.py
│   │   ├── product.py
│   │   └── order.py
│   └── middleware/
│       ├── request_logger.py  # 請求 Log（Before/After Request）
│       └── error_handler.py   # 全域錯誤處理
├── migrations/              # Flask-Migrate 版本控制
├── config.py                # 環境設定
├── run.py                   # 啟動入口
├── requirements.txt
└── .env
```

## 測試帳號（執行 seed 後）

| 帳號 | 密碼 | 角色 |
|------|------|------|
| admin@example.com | admin123 | Admin |
| （其他由 Faker 產生） | password123 | User |
