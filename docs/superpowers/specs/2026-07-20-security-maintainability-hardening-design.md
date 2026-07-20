# 安全性與可維護性強化 Design

**Status:** Approved
**Date:** 2026-07-20

## 背景與目標

專案經過 6 輪 superpowers 迭代後（Marshmallow/Service Layer → 測試/庫存/分頁 → JWT refresh → 搜尋排序 → OpenAPI → Rate Limiting），功能面已相當完整。本次聚焦在「安全底線」與「可維護性」的強化，不新增業務功能，不改動既有 spec 中刻意不做的項目。

### 本次要解決的問題

1. **生產環境可能用弱預設金鑰啟動**：`config.py` 的 `SECRET_KEY` / `JWT_SECRET_KEY` 在環境變數缺失時 fallback 到 `"dev-secret-key"` / `"dev-jwt-secret-key"`，若部署時漏設，等於用可預測金鑰簽發 JWT。
2. **400 錯誤回應洩漏內部細節**：`error_handler.py` 的 `handle_bad_request` 直接 `str(e)` 回傳給 client，可能暴露框架解析細節或內部路徑。
3. **204 回應帶 body**：`DELETE /api/products/<id>` 回 204 但附帶 JSON body，違反 HTTP 語意（RFC 9110: 204 response MUST NOT contain content）。
4. **金額用 Float 有精度漂移風險**：`Product.price`、`OrderItem.unit_price`、`Order.total_amount` 皆為 `db.Float`，多筆金額加總會產生浮點誤差（例如 `19.99 × 3 = 59.970000000000006`），電商核心資料不應有此風險。
5. **資料完整性只靠應用層**：quantity > 0、stock >= 0、status/action 合法值等約束僅在 Marshmallow schema 與 service 層檢查，若有程式繞過（CLI、migration script、直接 DB 操作），資料可能不一致。
6. **請求日誌缺乏追蹤能力**：目前只記 method/path/status/duration，缺 request ID、user ID、IP，故障追蹤成本高。

### 不在本次範圍（維持既有 spec 決策）

| 項目                       | 原因                                        | 來源                           |
| -------------------------- | ------------------------------------------- | ------------------------------ |
| Rate limit 改 Redis        | 原 spec 刻意選擇 in-memory，demo 專案可接受 | rate-limiting-design           |
| 完整訂單狀態機             | 原 spec 刻意延後                            | inventory-order-hardening plan |
| Refresh token 過期清理     | 原 spec 記錄為未來工作                      | jwt-refresh-logout-design      |
| 搜尋 LIKE 萬用字元跳脫     | 原 spec 確認不構成安全性問題                | product-search-sort-design     |
| Response schema 執行期驗證 | 原 spec 設計為文件用途                      | openapi-docs-design            |
| Login 帳號噴射攻擊防護     | 原 spec 刻意延後                            | rate-limiting-design           |

---

## 設計決策

### 決策 1：生產環境強制 Secrets

**做法：** `ProductionConfig` 直接用 `os.environ["SECRET_KEY"]`（不帶預設值），缺值時 Python 會拋 `KeyError`，Flask 啟動失敗。

**理由：**

- 比在 `create_app()` 裡加 if-check 更簡單、更早失敗（class body 載入時就爆）
- Development / Testing config 繼承 `Config`（保留預設值），不受影響
- 不需要額外的套件或環境檢測邏輯

**影響範圍：** 僅 `config.py`，零行為變更

### 決策 2：BadRequest 回應移除內部細節

**做法：** `handle_bad_request` 對外固定回 `{"error": "請求格式錯誤"}`，原始 `str(e)` 改寫到 `app.logger.debug()`。

**理由：**

- OWASP 建議不應在錯誤回應中暴露框架內部訊息
- debug 級別日誌在開發時仍可查看，生產環境可透過 log level 控制
- 既有測試不會斷言 `detail` 欄位（已確認）

**影響範圍：** 僅 `app/middleware/error_handler.py`

### 決策 3：204 回應改為空 body

**做法：** `return '', 204`，不回 JSON。

**替代方案（不採用）：** 改成 `200 + {"message": "商品已下架"}`。不採用是因為 DELETE 回 204 是 REST 慣例，且既有的 OpenAPI 文件已標記 204。

**影響範圍：** `app/blueprints/products/routes.py`、對應測試

### 決策 4：金額改 Numeric(12, 2)

**做法：** `Product.price`、`OrderItem.unit_price`、`Order.total_amount` 全部從 `db.Float` 改為 `db.Numeric(12, 2)`。

**精度選擇：**

- `12` 位總長、`2` 位小數 → 最大值 9,999,999,999.99（百億級，電商足夠）
- 選 2 位小數而非 4 位，因為目前所有商品價格與 Schema 驗證都是到小數點後兩位

**序列化策略：**

- `to_dict()` 中用 `float(self.price)` 轉換，保持 JSON 回應與既有格式一致（數字型別而非字串）
- Marshmallow schema 的 response fields 維持 `fields.Float()`（不改成 `fields.Decimal`），因為 response schema 僅供 OpenAPI 文件用（原 spec 決策），不接進序列化邏輯

**Migration：**

- 透過 `flask db migrate` 自動產生
- SQLite（開發/測試）的 Numeric 實際上仍是 REAL，精度改善有限；但 PostgreSQL（生產）會正確使用 NUMERIC 型別

**影響範圍：** `app/models/product.py`、`app/models/order.py`、migration file、測試

### 決策 5：補 DB Check Constraint 與索引

**做法：** 透過 `__table_args__` 加 `CheckConstraint`。

| Model        | 約束                                                                             |
| ------------ | -------------------------------------------------------------------------------- |
| Product      | `price > 0`、`stock >= 0`                                                        |
| Order        | `status IN ('pending','paid','shipped','delivered','cancelled')`                 |
| OrderItem    | `quantity > 0`、`unit_price >= 0`                                                |
| InventoryLog | `action IN ('deduct','restock','adjust')`                                        |
| RefreshToken | 複合索引 `(user_id, revoked_at)`（加速「撤銷某使用者所有 token」的 UPDATE 查詢） |

**已知限制：**

- SQLite 在 ALTER TABLE 時不支援新增 CHECK constraint（只有 CREATE TABLE 時生效），所以 migration 對既有的 SQLite 開發資料庫不會真的生效。但 `db.create_all()`（測試環境）和 PostgreSQL migration 會正確套用。
- 不加 `created_at` 的 default 值 constraint（太瑣碎，ORM 層處理即可）

**影響範圍：** 4 個 model 檔案、migration file

### 決策 6：結構化請求日誌

**做法：**

- `before_request` 產生 `g.request_id`（優先讀 `X-Request-ID` header，沒有則自動產生 UUID4）
- `after_request` 用 `app.logger.info()` 的 `extra` 參數帶入結構化欄位
- Response header 回傳 `X-Request-ID`（方便 client 端對照）
- 嘗試用 `verify_jwt_in_request(optional=True)` 取得 user_id（失敗則為 None，不影響非認證端點）

**不做的事：**

- 不引入 `python-json-logger` 之類的套件（維持零新依賴原則）
- 不改動 Flask 預設的 log formatter（那是部署層面的決策）

**影響範圍：** 僅 `app/middleware/request_logger.py`

---

## 測試計畫

| Task               | 驗證方式                                                             |
| ------------------ | -------------------------------------------------------------------- |
| 1. 強制 Secrets    | 手動測 `FLASK_ENV=production flask run` 缺值會失敗；pytest 全過      |
| 2. 400 移除 detail | 既有測試通過（不斷言 detail 欄位）                                   |
| 3. 204 空 body     | 更新 `test_products.py` 中斷言 204 的測試，不嘗試解析 body           |
| 4. Numeric 金額    | 新增精度測試（`19.99 × 3 == 59.97`）；既有金額相關測試全過           |
| 5. DB 約束         | 既有測試資料皆合法，全過；可選：新增「寫入非法資料被 DB 擋下」的測試 |
| 6. 結構化日誌      | 既有測試全過（after_request hook 不影響回應內容）                    |

---

## 執行順序

Task 1 → 2 → 3（低風險，可快速完成）→ Task 4（含 migration，獨立 commit）→ Task 5（含 migration，獨立 commit）→ Task 6（獨立 commit）
