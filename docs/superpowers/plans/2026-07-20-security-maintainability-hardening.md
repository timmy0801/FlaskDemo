# 安全性與可維護性強化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 補強專案的安全底線與可維護性：生產環境強制 secrets、移除錯誤回應中的內部細節外洩、修正 204 回應語意、金額型別改 Decimal 避免精度漂移、補 DB 層約束與索引、結構化請求日誌。

**Architecture:** 沿用既有 Route → Service → Model 分層，不新增模組，僅強化既有程式碼的安全性與正確性。

**Tech Stack:** Python 3, Flask 3, SQLAlchemy, Flask-Migrate, pytest

**與既有 spec 的關係：**

- 不改動 rate limit 儲存後端（維持 memory，原 spec 刻意取捨）
- 不新增完整訂單狀態機（原 spec 刻意不做）
- 不動 refresh token 清理機制（原 spec 延後處理）

---

## Task 1: 生產環境強制 Secret Key

**Files:**

- Modify: `config.py`
- Modify: `app/__init__.py`
- Modify: `run.py`

- [x] **Step 1: 修改 `ProductionConfig` + `create_app` runtime 檢查**

實際做法（與原 plan 略有差異）：`ProductionConfig` 不在 class body 讀 `os.environ[]`（避免 import 時影響其他環境），改在 `create_app()` 中當 `env == "production"` 時檢查 `SECRET_KEY` / `JWT_SECRET_KEY` 非空，缺值或空值拋 `RuntimeError`。同時在 `run.py` 頂部先 `load_dotenv()` 確保 `FLASK_ENV` 在 `create_app()` 呼叫前就已載入。

- [x] **Step 2: 確認 development / testing config 不受影響**

`pytest -v` → 66 passed

- [x] **Step 3: 手動驗證 production 缺值時行為**

`FLASK_ENV=production` + `SECRET_KEY=` (空值) → `RuntimeError: SECRET_KEY must be set and non-empty in production`

- [ ] **Step 4: Commit**

---

## Task 2: 移除 BadRequest 錯誤回應中的內部細節

**Files:**

- Modify: `app/middleware/error_handler.py`

- [x] **Step 1: 修改 `handle_bad_request`，不再對外回傳 `str(e)`**

已移除 `detail` 欄位，對外固定回 `{"error": "請求格式錯誤"}`。

- [x] **Step 2: 執行測試確認無破壞**

`pytest -v` → 66 passed

- [ ] **Step 3: Commit**

---

## Task 3: 修正商品下架 204 回應語意

**Files:**

- Modify: `app/blueprints/products/routes.py`
- Modify: `tests/test_products.py`（若有斷言 status_code 204 + body 的測試需同步更新）

- [x] **Step 1: 改為回傳空 body 的 204**

已改為 `return "", 204`。

- [x] **Step 2: 同步更新測試（若有斷言 response body）**

已確認測試只斷言 `status_code == 204`。

- [x] **Step 3: 執行測試**

`pytest -v` → 66 passed

- [ ] **Step 4: Commit**

---

## Task 4: 金額欄位改 Decimal（Numeric）

**Files:**

- Modify: `app/models/product.py`
- Modify: `app/models/order.py`
- Modify: `app/blueprints/products/schemas.py`
- Modify: `app/blueprints/orders/schemas.py`
- Modify: `app/services/product_service.py`（若有 float 相關邏輯）
- Create: migration file（透過 `flask db migrate`）
- Modify: `tests/test_orders.py`（補精度測試）

- [x] **Step 1: 修改 `app/models/product.py`**

已改 `price` 為 `db.Numeric(12, 2)`。

- [x] **Step 2: 修改 `app/models/order.py`**

已改 `total_amount` 與 `unit_price` 為 `db.Numeric(12, 2)`。

- [x] **Step 3: 更新 Schema 中金額欄位**

維持 `fields.Float`（Response schema 僅供 OpenAPI 文件用途，原 spec 決策）。

- [x] **Step 4: 確認 `to_dict()` 序列化正確**

`OrderItem.to_dict()` 已用 `float(self.unit_price)` / `float(self.subtotal)` 轉換。

- [x] **Step 5: 產生 migration**

Migration `8d4300d425e5` 已產生（同時包含 Numeric 型別變更與 Task 5 的約束/索引）。

- [ ] **Step 6: 補精度測試（可選）**

- [x] **Step 7: 執行完整測試套件**

`pytest -v` → 66 passed

- [ ] **Step 8: Commit**

---

## Task 5: 補 DB 層約束與索引

**Files:**

- Modify: `app/models/product.py`
- Modify: `app/models/order.py`
- Modify: `app/models/inventory_log.py`
- Modify: `app/models/refresh_token.py`
- Create: migration file

- [x] **Step 1: `app/models/product.py` 補 CheckConstraint**

已加 `ck_product_price_positive` (`price >= 0`) 與 `ck_product_stock_non_negative` (`stock >= 0`)。

- [x] **Step 2: `app/models/order.py` 補 CheckConstraint**

Order: `ck_order_total_amount_non_negative` + `ck_order_status_valid`。
OrderItem: `ck_orderitem_quantity_positive` + `ck_orderitem_price_non_negative`。

- [x] **Step 3: `app/models/inventory_log.py` 補 CheckConstraint**

已加 `ck_inventorylog_action_valid`。

- [x] **Step 4: `app/models/refresh_token.py` 補複合索引**

已加 `ix_refresh_tokens_user_revoked` (`user_id`, `revoked_at`)。

- [x] **Step 5: 產生 migration**

Migration `8d4300d425e5`（與 Task 4 合併在同一份 migration 中）。

- [x] **Step 6: 執行完整測試**

`pytest -v` → 66 passed

- [ ] **Step 7: Commit**

---

## Task 6: 結構化請求日誌

**Files:**

- Modify: `app/middleware/request_logger.py`

- [x] **Step 1: 加入 request_id 與結構化欄位**

已改為含 `uuid`、`X-Request-ID` header、`verify_jwt_in_request(optional=True)` 取 user_id、結構化 `extra` 欄位的版本。

- [x] **Step 2: 執行測試確認無破壞**

`pytest -v` → 66 passed

- [ ] **Step 3: Commit**

---

## 完成後的變更總覽

```
config.py                              (production 強制 secrets)
app/
├── middleware/
│   ├── error_handler.py               (移除 detail 外洩)
│   └── request_logger.py              (結構化日誌)
├── blueprints/
│   └── products/
│       └── routes.py                  (204 空 body)
├── models/
│   ├── product.py                     (Numeric + CheckConstraint)
│   ├── order.py                       (Numeric + CheckConstraint)
│   ├── inventory_log.py              (CheckConstraint)
│   └── refresh_token.py              (複合索引)
└── blueprints/
    ├── products/schemas.py            (Decimal fields)
    └── orders/schemas.py              (Decimal fields)
migrations/versions/
├── xxxx_change_float_to_numeric.py
└── xxxx_add_check_constraints.py
tests/
├── test_products.py                   (204 斷言更新)
└── test_orders.py                     (+精度測試)
```

計畫已建立在 [docs/superpowers/plans/2026-07-20-security-maintainability-hardening.md](docs/superpowers/plans/2026-07-20-security-maintainability-hardening.md)。
