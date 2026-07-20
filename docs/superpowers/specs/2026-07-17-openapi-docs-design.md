# API 文件（OpenAPI/Swagger）Design

**Status:** Approved
**Date:** 2026-07-17

## 背景與目標

目前這支 API 沒有任何機器可讀或互動式的文件，只有 `README.md` 手寫的端點表格（剛更新過，但每次加新端點都要記得手動同步）。目標是加上自動產生的 OpenAPI 3.0 文件 + Swagger UI，且不改動任何現有 route 的實際行為。

## 技術驗證（已在此環境實測，不是憑經驗猜的）

用 `apispec` (6.10.0) + `apispec-webframeworks` (1.2.0，提供 `FlaskPlugin`) + `apispec.ext.marshmallow.MarshmallowPlugin`，實際對 `app.blueprints.products.schemas.CreateProductSchema` 跟一個真實的 Flask view function（`products.create_product`）跑過完整流程：註冊 schema → 幫 view 加上 YAML docstring → `spec.path(view=view)` → 成功產生出正確的 `$ref` 到 schema 的 OpenAPI path JSON。確認這套工具鏈跟專案目前的 Flask 3.1.3 / marshmallow 4.3.0 相容，沒有版本衝突。

## 核心設計決策

1. **工具**：`apispec` + `apispec-webframeworks`（`FlaskPlugin`）+ `MarshmallowPlugin` + `flask-swagger-ui`。不用 `flask-smorest`——後者需要把所有 route 從 function-based 改寫成 class-based `MethodView`，改動範圍太大，不符合「只加文件、不動行為」的目標。
2. **運作方式**：每個 Flask view function 的 docstring 寫一段 YAML（`summary`、`tags`、`security`、`requestBody`、`responses`），啟動時（或建立 spec 的當下）呼叫 `spec.path(view=view_func)` 讀取這段 YAML 產生對應的 OpenAPI path。Route 程式碼本身完全不變，只是多了 docstring。
3. **Response Schema 純粹是文件用途，不接進執行路徑**：新增對應回應形狀的 Marshmallow Schema（例如 `UserResponseSchema` 對照 `User.to_dict()`），但 route 依然是 `jsonify(model.to_dict())`，不會改成 `Schema().dump(...)`。這樣整個功能是純加法，不會影響任何現有回應的實際內容或行為，也不需要重新驗證既有的行為測試。
4. **服務端點**：
   - `GET /api/openapi.json`：回傳 `spec.to_dict()` 的 JSON
   - `GET /api/docs`：Swagger UI 頁面，用 `flask_swagger_ui.get_swaggerui_blueprint()` 掛載，指向 `/api/openapi.json`
5. **認證表示法**：
   - 一般端點（`@jwt_required()`／`@admin_required()`／`@owner_or_admin_required`）：`bearerAuth`（`type: http, scheme: bearer, bearerFormat: JWT`）
   - `/api/auth/refresh`、`/api/auth/logout`：`cookieAuth`（`type: apiKey, in: cookie, name: refresh_token_cookie`）+ `csrfHeader`（`type: apiKey, in: header, name: X-CSRF-TOKEN`），兩者都要求（`security: [{cookieAuth: [], csrfHeader: []}]`）
6. **不需要驗證登入狀態就能看文件**：`/api/docs`、`/api/openapi.json` 不加任何 `@jwt_required()`，公開瀏覽（這是純文件端點，不是資料端點）。

## 檔案配置

**新增：**
- `app/openapi.py`：
  - 建立 `APISpec` 物件（title/version/openapi_version/plugins/security schemes）
  - `register_openapi(app)` function：掃過 `app.view_functions`，對每個有 apispec YAML docstring 的 view 呼叫 `spec.path(view=view)`；註冊 `/api/openapi.json` route；用 `flask_swagger_ui.get_swaggerui_blueprint()` 掛載 `/api/docs`
  - 在 `app/__init__.py` 的 `create_app()` 裡，**所有 blueprint 都註冊完之後**呼叫 `register_openapi(app)`（一定要在 blueprint 註冊之後，因為要掃 `app.view_functions`，而且要對每個 endpoint 都是「已經在 app.url_map 上」的狀態，`FlaskPlugin` 才能正確解析出 URL）

**修改：**
- `app/blueprints/auth/schemas.py`：新增 `UserResponseSchema`、`LoginResponseSchema`
- `app/blueprints/products/schemas.py`：新增 `ProductResponseSchema`、`ProductListResponseSchema`、`InventoryLogResponseSchema`、`InventoryLogListResponseSchema`
- `app/blueprints/orders/schemas.py`：新增 `OrderResponseSchema`、`OrderItemResponseSchema`、`OrderListResponseSchema`
- `app/blueprints/users/schemas.py`：新增 `UserListResponseSchema`（`UserResponseSchema` 從 auth 那邊複用，import 過去）
- 四個 blueprint 的 `routes.py`：每個 route function 補上 YAML docstring
- `app/__init__.py`：呼叫 `register_openapi(app)`
- `requirements.txt`：新增 `apispec`、`apispec-webframeworks`、`flask-swagger-ui`

## 測試計畫

- `GET /api/openapi.json` 回 200，內容是合法 JSON，且 `openapi` 欄位存在
- spec 的 `paths` 裡包含所有主要端點（例如 `/api/products`、`/api/orders/{order_id}/status`、`/api/auth/refresh` 都要出現）
- `GET /api/docs` 回 200，回應是 HTML（Swagger UI 頁面）
- 既有的 54+ 個測試全部維持通過（因為 route 行為完全沒變，這是驗證「純加法沒有破壞任何東西」的關鍵）

## 已知限制（不在本次範圍）

- Response Schema 只是文件用途，不會在執行期強制驗證回應格式；如果之後 `to_dict()` 的欄位跟 Response Schema 兜不起來，文件會跟實際回應不同步，需要人工留意（沒有自動化機制防止兩者漂移）
- 沒有幫文件加版本號管理（例如 `/api/v1/docs`），目前 API 本身也沒有版本化，維持現況
