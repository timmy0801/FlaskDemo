# API 文件（OpenAPI/Swagger）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 `apispec` + `flask-swagger-ui` 自動產生 OpenAPI 3.0 文件與互動式 Swagger UI，涵蓋全部既有端點，且不改動任何 route 的實際執行行為。

**Architecture:** 每個 Flask view function 的 docstring 寫一段 YAML（apispec 慣例），啟動時掃過 `app.view_functions` 呼叫 `spec.path(view=view)` 產生 OpenAPI path。Response Schema 純粹給文件用，不接進 `jsonify()` 的實際回應邏輯。設計依據：[docs/superpowers/specs/2026-07-17-openapi-docs-design.md](../specs/2026-07-17-openapi-docs-design.md)。

**Tech Stack:** apispec 6.10.0、apispec-webframeworks 1.2.0（`FlaskPlugin`）、flask-swagger-ui 5.32.8、Marshmallow 4.3.0

**技術細節（已在此環境用真實的 app + Flask test client 實測過，寫程式時直接照這些結論走）：**
- `apispec.ext.marshmallow.MarshmallowPlugin` 在 docstring YAML 裡用 `schema: XxxSchema`（class 名稱字串）就能自動解析、自動註冊到 `components.schemas`，**不需要**手動呼叫 `spec.components.schema(...)`。命名規則是自動去掉結尾的 `Schema`（例如 `UserResponseSchema` → 元件名稱 `UserResponse`，`$ref` 也會指向 `#/components/schemas/UserResponse`）。前提是這個 Schema class 所在的模組已經被 import 過（Marshmallow 有自己的全域 class registry）——本專案每個 blueprint 的 `schemas.py` 本來就會在 `routes.py` 被 import 時載入，所以只要 Response Schema 定義在對應 blueprint 的 `schemas.py`，`register_openapi(app)` 執行時一定找得到，不需要額外 import。
- 一個 docstring YAML 裡可以同時混用 `schema: XxxSchema`（字串簡寫，MarshmallowPlugin 解析）跟手寫的 `$ref: '#/components/schemas/Xxx'`（純 OpenAPI 語法），兩者都能正確解析，已實測過巢狀在 `properties` 裡的 `$ref` 也沒問題。
- `spec.path(view=view)` 對同一個 view function 重複呼叫多次（例如每個測試都會重新 `create_app()` 一次，`register_openapi` 就會重新掃一次）是安全的、不會報錯也不會重複累積，會直接覆蓋同一個 path key。這代表 `app/openapi.py` 裡的 `spec` 可以放心當成 module-level 單例，不用擔心測試套件跑多次 `create_app()` 會出錯。
- Flask 的 `<int:product_id>` 這種動態路由，`FlaskPlugin` 會正確轉成 OpenAPI 的 `{product_id}` 路徑參數格式（已實測 `/api/products/<int:product_id>` → `/api/products/{product_id}`）。
- 所有既有的 decorator（`jwt_required()`、`admin_required`、`validate_body`、`owner_or_admin_required`）都有用 `functools.wraps(fn)`（已確認 flask_jwt_extended 原始碼跟本專案的 `app/utils/decorators.py` 都是），所以 route function 的 docstring 會正確保留穿過所有裝飾器，`spec.path()` 抓得到。
- `flask-swagger-ui` 掛載的 blueprint，`GET /api/docs`（不帶結尾斜線）會回 308 redirect 到 `/api/docs/`；測試直接打 `/api/docs/`（帶斜線）拿到乾淨的 200，避免處理 redirect。

---

## Task 1: 基礎建設（APISpec + Swagger UI 骨架）

**Files:**
- Create: `app/openapi.py`
- Modify: `app/__init__.py`
- Modify: `requirements.txt`
- Test: `tests/test_openapi.py`

- [ ] **Step 1: 撰寫會失敗的測試 `tests/test_openapi.py`**

```python
def test_openapi_json_returns_valid_spec(client):
    resp = client.get('/api/openapi.json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['openapi'] == '3.0.3'
    assert data['info']['title']


def test_docs_page_returns_html(client):
    resp = client.get('/api/docs/')
    assert resp.status_code == 200
    assert 'text/html' in resp.content_type
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_openapi.py -v
```

Expected: 兩個都 `FAILED`（`/api/openapi.json`、`/api/docs/` 都還不存在，回 404）

- [ ] **Step 3: 安裝套件**

```bash
pip install apispec==6.10.0 apispec-webframeworks==1.2.0 flask-swagger-ui==5.32.8
```

- [ ] **Step 4: 更新 `requirements.txt`**

在檔案最後新增三行：

```
apispec==6.10.0
apispec-webframeworks==1.2.0
flask-swagger-ui==5.32.8
```

- [ ] **Step 5: 建立 `app/openapi.py`**

```python
from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from apispec_webframeworks.flask import FlaskPlugin
from flask import jsonify
from flask_swagger_ui import get_swaggerui_blueprint

spec = APISpec(
    title='Flask 電商後台 API',
    version='1.0.0',
    openapi_version='3.0.3',
    plugins=[FlaskPlugin(), MarshmallowPlugin()],
)

spec.components.security_scheme('bearerAuth', {
    'type': 'http',
    'scheme': 'bearer',
    'bearerFormat': 'JWT',
})
spec.components.security_scheme('cookieAuth', {
    'type': 'apiKey',
    'in': 'cookie',
    'name': 'refresh_token_cookie',
})
spec.components.security_scheme('csrfHeader', {
    'type': 'apiKey',
    'in': 'header',
    'name': 'X-CSRF-TOKEN',
})


def register_openapi(app):
    with app.test_request_context():
        for view in app.view_functions.values():
            if view.__doc__ and '---' in view.__doc__:
                spec.path(view=view)

    @app.route('/api/openapi.json')
    def openapi_json():
        return jsonify(spec.to_dict())

    swagger_ui_bp = get_swaggerui_blueprint(
        '/api/docs',
        '/api/openapi.json',
        config={'app_name': 'Flask 電商後台 API'},
    )
    app.register_blueprint(swagger_ui_bp, url_prefix='/api/docs')
```

- [ ] **Step 6: 更新 `app/__init__.py`**

把：

```python
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(orders_bp, url_prefix='/api/orders')
    app.register_blueprint(users_bp, url_prefix='/api/users')

    # 全域錯誤處理
```

改為：

```python
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(orders_bp, url_prefix='/api/orders')
    app.register_blueprint(users_bp, url_prefix='/api/users')

    # 註冊 OpenAPI 文件（必須在所有 blueprint 註冊完之後）
    from app.openapi import register_openapi
    register_openapi(app)

    # 全域錯誤處理
```

- [ ] **Step 7: 執行測試確認通過**

```bash
pytest tests/test_openapi.py -v
```

Expected: 兩個都 `PASSED`

- [ ] **Step 8: 執行完整測試套件**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [ ] **Step 9: Commit**

```bash
git add app/openapi.py app/__init__.py requirements.txt tests/test_openapi.py
git commit -m "feat: add apispec + swagger-ui scaffolding for OpenAPI docs"
```

---

## Task 2: Auth 端點文件

**Files:**
- Modify: `app/blueprints/auth/schemas.py`
- Modify: `app/blueprints/auth/routes.py`
- Test: `tests/test_openapi.py`

- [ ] **Step 1: 撰寫會失敗的測試**

在 `tests/test_openapi.py` 最後新增：

```python
def test_openapi_includes_auth_paths(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    assert '/api/auth/register' in paths
    assert '/api/auth/login' in paths
    assert '/api/auth/me' in paths
    assert '/api/auth/refresh' in paths
    assert '/api/auth/logout' in paths
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_openapi.py::test_openapi_includes_auth_paths -v
```

Expected: `FAILED`（這幾個 route 目前沒有 docstring，`register_openapi` 不會幫它們產生 path）

- [ ] **Step 3: 在 `app/blueprints/auth/schemas.py` 新增 Response Schema**

在檔案最後新增：

```python


class UserResponseSchema(Schema):
    id = fields.Int()
    username = fields.Str()
    email = fields.Str()
    role = fields.Str()
    is_active = fields.Bool()
    created_at = fields.DateTime()


class LoginResponseSchema(Schema):
    message = fields.Str()
    access_token = fields.Str()
    user = fields.Nested(UserResponseSchema)
```

- [ ] **Step 4: 更新 `app/blueprints/auth/routes.py`，把整個檔案改為**

```python
from flask import jsonify
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from app.models.user import User
from app.blueprints.auth import auth_bp
from app.blueprints.auth.schemas import RegisterSchema, LoginSchema
from app.services import auth_service
from app.utils.decorators import validate_body


@auth_bp.route('/register', methods=['POST'])
@validate_body(RegisterSchema)
def register(validated_data):
    """
    ---
    post:
      summary: 註冊新帳號
      tags: [Auth]
      requestBody:
        required: true
        content:
          application/json:
            schema: RegisterSchema
      responses:
        201:
          description: 註冊成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                  user:
                    $ref: '#/components/schemas/UserResponse'
        409:
          description: Email 或使用者名稱已被使用
    """
    user = auth_service.register(validated_data)
    return jsonify({'message': '註冊成功', 'user': user}), 201


@auth_bp.route('/login', methods=['POST'])
@validate_body(LoginSchema)
def login(validated_data):
    """
    ---
    post:
      summary: 登入取得 access token
      description: 成功登入後，除了 JSON 回應之外，也會用 Set-Cookie 設定一個 httpOnly 的 refresh token cookie。
      tags: [Auth]
      requestBody:
        required: true
        content:
          application/json:
            schema: LoginSchema
      responses:
        200:
          description: 登入成功
          content:
            application/json:
              schema: LoginResponseSchema
        401:
          description: Email 或密碼錯誤
        403:
          description: 帳號已被停用
    """
    result = auth_service.login(validated_data)
    response = jsonify({
        'message': '登入成功',
        'access_token': result['access_token'],
        'user': result['user'],
    })
    set_refresh_cookies(response, result['refresh_token'])
    return response


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """
    ---
    get:
      summary: 取得當前使用者資訊
      tags: [Auth]
      security:
        - bearerAuth: []
      responses:
        200:
          description: 使用者資訊
          content:
            application/json:
              schema: UserResponseSchema
        401:
          description: 未攜帶或無效的 access token
    """
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    ---
    post:
      summary: 用 refresh token 換發新的 access token
      description: 需要瀏覽器自動帶上 refresh_token_cookie，並額外帶 X-CSRF-TOKEN header（值來自 csrf_refresh_token cookie）。每次呼叫都會 rotate refresh token。
      tags: [Auth]
      security:
        - cookieAuth: []
          csrfHeader: []
      responses:
        200:
          description: 換發成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  access_token:
                    type: string
        401:
          description: refresh token 缺失、無效、或已被撤銷（重複使用已撤銷的 token 會連帶撤銷該使用者所有 session）
        403:
          description: 帳號已被停用
    """
    user_id = int(get_jwt_identity())
    jti = get_jwt()['jti']
    result = auth_service.refresh(user_id, jti)
    response = jsonify({'access_token': result['access_token']})
    set_refresh_cookies(response, result['refresh_token'])
    return response


@auth_bp.route('/logout', methods=['POST'])
@jwt_required(refresh=True)
def logout():
    """
    ---
    post:
      summary: 登出，撤銷目前的 refresh token
      description: 需要瀏覽器自動帶上 refresh_token_cookie，並額外帶 X-CSRF-TOKEN header。
      tags: [Auth]
      security:
        - cookieAuth: []
          csrfHeader: []
      responses:
        200:
          description: 登出成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
        401:
          description: refresh token 缺失或無效
    """
    jti = get_jwt()['jti']
    auth_service.logout(jti)
    response = jsonify({'message': '登出成功'})
    unset_jwt_cookies(response)
    return response
```

- [ ] **Step 5: 執行測試確認通過**

```bash
pytest tests/test_openapi.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 6: 執行完整測試套件**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [ ] **Step 7: Commit**

```bash
git add app/blueprints/auth/schemas.py app/blueprints/auth/routes.py tests/test_openapi.py
git commit -m "docs: add OpenAPI documentation for auth endpoints"
```

---

## Task 3: Products 端點文件

**Files:**
- Modify: `app/blueprints/products/schemas.py`
- Modify: `app/blueprints/products/routes.py`
- Test: `tests/test_openapi.py`

- [ ] **Step 1: 撰寫會失敗的測試**

在 `tests/test_openapi.py` 最後新增：

```python
def test_openapi_includes_product_paths(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    assert '/api/products' in paths
    assert '/api/products/{product_id}' in paths
    assert '/api/products/{product_id}/inventory-logs' in paths
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_openapi.py::test_openapi_includes_product_paths -v
```

Expected: `FAILED`

- [ ] **Step 3: 在 `app/blueprints/products/schemas.py` 新增 Response Schema**

在檔案最後新增：

```python


class ProductResponseSchema(Schema):
    id = fields.Int()
    name = fields.Str()
    description = fields.Str(allow_none=True)
    price = fields.Float()
    stock = fields.Int()
    category = fields.Str(allow_none=True)
    image_url = fields.Str(allow_none=True)
    is_active = fields.Bool()
    created_at = fields.DateTime()


class ProductListResponseSchema(Schema):
    products = fields.List(fields.Nested(ProductResponseSchema))
    total = fields.Int()
    pages = fields.Int()
    current_page = fields.Int()


class InventoryLogResponseSchema(Schema):
    id = fields.Int()
    product_id = fields.Int()
    order_id = fields.Int(allow_none=True)
    action = fields.Str()
    quantity_before = fields.Int()
    quantity_change = fields.Int()
    quantity_after = fields.Int()
    note = fields.Str(allow_none=True)
    created_at = fields.DateTime()


class InventoryLogListResponseSchema(Schema):
    inventory_logs = fields.List(fields.Nested(InventoryLogResponseSchema))
    total = fields.Int()
    pages = fields.Int()
    current_page = fields.Int()
```

- [ ] **Step 4: 更新 `app/blueprints/products/routes.py`，把整個檔案改為**

```python
from flask import request, jsonify

from app import db
from app.models.product import Product
from app.blueprints.products import products_bp
from app.blueprints.products.schemas import (
    CreateProductSchema,
    UpdateProductSchema,
    InventoryAdjustSchema,
)
from app.utils.decorators import admin_required, validate_body
from app.services import product_service


@products_bp.route("", methods=["GET"])
def get_products():
    """
    ---
    get:
      summary: 取得商品列表
      tags: [Products]
      parameters:
        - in: query
          name: q
          schema: {type: string}
          description: 依商品名稱關鍵字搜尋（不分大小寫、包含比對）
        - in: query
          name: category
          schema: {type: string}
        - in: query
          name: sort_by
          schema: {type: string, enum: [price, created_at]}
          description: 未帶或無效值時預設 created_at
        - in: query
          name: order
          schema: {type: string, enum: [asc, desc]}
          description: 未帶或無效值時預設 desc
        - in: query
          name: page
          schema: {type: integer, default: 1}
        - in: query
          name: per_page
          schema: {type: integer, default: 10}
          description: 上限 100
      responses:
        200:
          description: 商品列表
          content:
            application/json:
              schema: ProductListResponseSchema
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    category = request.args.get("category")
    q = request.args.get("q")
    sort_by = request.args.get("sort_by")
    order = request.args.get("order")

    return jsonify(product_service.get_products(page, per_page, category, q, sort_by, order))


@products_bp.route("/<int:product_id>", methods=["GET"])
def get_product(product_id):
    """
    ---
    get:
      summary: 取得單一商品
      tags: [Products]
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
      responses:
        200:
          description: 商品資訊
          content:
            application/json:
              schema: ProductResponseSchema
        404:
          description: 商品不存在
    """
    return jsonify(product_service.get_product(product_id))


@products_bp.route("", methods=["POST"])
@admin_required
@validate_body(CreateProductSchema)
def create_product(validated_data):
    """
    ---
    post:
      summary: 新增商品
      tags: [Products]
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema: CreateProductSchema
      responses:
        201:
          description: 商品建立成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  message: {type: string}
                  product:
                    $ref: '#/components/schemas/ProductResponse'
        403:
          description: 權限不足，需要 admin 身分
    """
    product = product_service.create_product(validated_data)
    return jsonify({"message": "商品建立成功", "product": product}), 201


@products_bp.route("/<int:product_id>", methods=["PUT"])
@admin_required
@validate_body(UpdateProductSchema)
def update_product(product_id, validated_data):
    """
    ---
    put:
      summary: 更新商品
      tags: [Products]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
      requestBody:
        required: true
        content:
          application/json:
            schema: UpdateProductSchema
      responses:
        200:
          description: 商品更新成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  message: {type: string}
                  product:
                    $ref: '#/components/schemas/ProductResponse'
        403:
          description: 權限不足，需要 admin 身分
        404:
          description: 商品不存在
    """
    product = product_service.update_product(product_id, validated_data)
    return jsonify({"message": "商品更新成功", "product": product})


@products_bp.route("/<int:product_id>", methods=["DELETE"])
@admin_required
def delete_product(product_id):
    """
    ---
    delete:
      summary: 下架商品（軟刪除）
      tags: [Products]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
      responses:
        204:
          description: 商品已下架
        403:
          description: 權限不足，需要 admin 身分
        404:
          description: 商品不存在
    """
    product_service.delete_product(product_id)
    return jsonify({"message": "商品已下架"}), 204


@products_bp.route("/<int:product_id>/inventory-logs", methods=["GET"])
@admin_required
def get_inventory_logs(product_id):
    """
    ---
    get:
      summary: 取得商品的庫存異動紀錄
      tags: [Products]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
        - in: query
          name: page
          schema: {type: integer, default: 1}
        - in: query
          name: per_page
          schema: {type: integer, default: 20}
      responses:
        200:
          description: 庫存異動紀錄列表
          content:
            application/json:
              schema: InventoryLogListResponseSchema
        403:
          description: 權限不足，需要 admin 身分
        404:
          description: 商品不存在
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    return jsonify(product_service.get_inventory_logs(product_id, page, per_page))


@products_bp.route("/<int:product_id>/inventory-logs", methods=["POST"])
@admin_required
@validate_body(InventoryAdjustSchema)
def adjust_inventory(product_id, validated_data):
    """
    ---
    post:
      summary: 補貨（restock）或人工調整庫存（adjust）
      tags: [Products]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
      requestBody:
        required: true
        content:
          application/json:
            schema: InventoryAdjustSchema
      responses:
        201:
          description: 庫存調整成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  message: {type: string}
                  inventory_log:
                    $ref: '#/components/schemas/InventoryLogResponse'
        400:
          description: 異動數量不合法或會導致庫存為負數
        403:
          description: 權限不足，需要 admin 身分
        404:
          description: 商品不存在
    """
    log = product_service.adjust_inventory(product_id, validated_data)
    return jsonify({"message": "庫存調整成功", "inventory_log": log}), 201
```

- [ ] **Step 5: 執行測試確認通過**

```bash
pytest tests/test_openapi.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 6: 執行完整測試套件**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [ ] **Step 7: Commit**

```bash
git add app/blueprints/products/schemas.py app/blueprints/products/routes.py tests/test_openapi.py
git commit -m "docs: add OpenAPI documentation for product endpoints"
```

---

## Task 4: Orders 端點文件

**Files:**
- Modify: `app/blueprints/orders/schemas.py`
- Modify: `app/blueprints/orders/routes.py`
- Test: `tests/test_openapi.py`

- [ ] **Step 1: 撰寫會失敗的測試**

在 `tests/test_openapi.py` 最後新增：

```python
def test_openapi_includes_order_paths(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    assert '/api/orders' in paths
    assert '/api/orders/{order_id}' in paths
    assert '/api/orders/{order_id}/status' in paths
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_openapi.py::test_openapi_includes_order_paths -v
```

Expected: `FAILED`

- [ ] **Step 3: 在 `app/blueprints/orders/schemas.py` 新增 Response Schema**

在檔案最後新增：

```python


class OrderItemResponseSchema(Schema):
    id = fields.Int()
    product_id = fields.Int()
    product_name = fields.Str(allow_none=True)
    quantity = fields.Int()
    unit_price = fields.Float()
    subtotal = fields.Float()


class OrderResponseSchema(Schema):
    id = fields.Int()
    user_id = fields.Int()
    status = fields.Str()
    total_amount = fields.Float()
    items = fields.List(fields.Nested(OrderItemResponseSchema))
    created_at = fields.DateTime()


class OrderListResponseSchema(Schema):
    orders = fields.List(fields.Nested(OrderResponseSchema))
    total = fields.Int()
    pages = fields.Int()
    current_page = fields.Int()
```

- [ ] **Step 4: 更新 `app/blueprints/orders/routes.py`，把整個檔案改為**

```python
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.blueprints.orders import orders_bp
from app.blueprints.orders.schemas import CreateOrderSchema, UpdateOrderStatusSchema
from app.utils.decorators import validate_body
from app.services import order_service


@orders_bp.route("", methods=["GET"])
@jwt_required()
def get_orders():
    """
    ---
    get:
      summary: 取得訂單列表
      description: Admin 看全部訂單，一般使用者只看自己的訂單。
      tags: [Orders]
      security:
        - bearerAuth: []
      parameters:
        - in: query
          name: page
          schema: {type: integer, default: 1}
        - in: query
          name: per_page
          schema: {type: integer, default: 20}
      responses:
        200:
          description: 訂單列表
          content:
            application/json:
              schema: OrderListResponseSchema
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    return jsonify(order_service.get_orders(user_id, claims, page, per_page))


@orders_bp.route("/<int:order_id>", methods=["GET"])
@jwt_required()
def get_order(order_id):
    """
    ---
    get:
      summary: 取得單一訂單
      tags: [Orders]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: order_id
          required: true
          schema: {type: integer}
      responses:
        200:
          description: 訂單資訊
          content:
            application/json:
              schema: OrderResponseSchema
        403:
          description: 無權限查看此訂單
        404:
          description: 訂單不存在
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    return jsonify(order_service.get_order(order_id, user_id, claims))


@orders_bp.route("", methods=["POST"])
@jwt_required()
@validate_body(CreateOrderSchema)
def create_order(validated_data):
    """
    ---
    post:
      summary: 建立新訂單
      description: 會依序扣除各商品庫存並寫入庫存異動紀錄；若庫存不足或商品不存在會回錯誤。
      tags: [Orders]
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema: CreateOrderSchema
      responses:
        201:
          description: 訂單建立成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  message: {type: string}
                  order:
                    $ref: '#/components/schemas/OrderResponse'
        400:
          description: 商品庫存不足
        404:
          description: 商品不存在或已下架
        409:
          description: 庫存競爭衝突，請稍後再試
    """
    user_id = int(get_jwt_identity())
    order = order_service.create_order(user_id, validated_data)
    return jsonify({"message": "訂單建立成功", "order": order}), 201


@orders_bp.route("/<int:order_id>/status", methods=["PATCH"])
@jwt_required()
@validate_body(UpdateOrderStatusSchema)
def update_order_status(order_id, validated_data):
    """
    ---
    patch:
      summary: 更新訂單狀態
      description: Admin 可設定任意合法狀態；一般使用者只能把自己「pending」狀態的訂單改成 cancelled，取消時會自動把庫存加回去。
      tags: [Orders]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: order_id
          required: true
          schema: {type: integer}
      requestBody:
        required: true
        content:
          application/json:
            schema: UpdateOrderStatusSchema
      responses:
        200:
          description: 訂單狀態已更新
          content:
            application/json:
              schema:
                type: object
                properties:
                  message: {type: string}
                  order:
                    $ref: '#/components/schemas/OrderResponse'
        400:
          description: 只有待處理（pending）的訂單可以取消
        403:
          description: 無權限修改此訂單狀態
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    order = order_service.update_order_status(order_id, validated_data, user_id, claims)
    return jsonify({"message": "訂單狀態已更新", "order": order})
```

- [ ] **Step 5: 執行測試確認通過**

```bash
pytest tests/test_openapi.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 6: 執行完整測試套件**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [ ] **Step 7: Commit**

```bash
git add app/blueprints/orders/schemas.py app/blueprints/orders/routes.py tests/test_openapi.py
git commit -m "docs: add OpenAPI documentation for order endpoints"
```

---

## Task 5: Users 端點文件 + 最終驗證

**Files:**
- Modify: `app/blueprints/users/schemas.py`
- Modify: `app/blueprints/users/routes.py`
- Test: `tests/test_openapi.py`

- [ ] **Step 1: 撰寫會失敗的測試**

在 `tests/test_openapi.py` 最後新增：

```python
def test_openapi_includes_user_paths(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    assert '/api/users' in paths
    assert '/api/users/{user_id}' in paths


def test_openapi_spec_covers_all_blueprints(client):
    resp = client.get('/api/openapi.json')
    paths = resp.get_json()['paths']
    expected = [
        '/api/auth/register', '/api/auth/login', '/api/auth/me',
        '/api/auth/refresh', '/api/auth/logout',
        '/api/products', '/api/products/{product_id}',
        '/api/products/{product_id}/inventory-logs',
        '/api/orders', '/api/orders/{order_id}', '/api/orders/{order_id}/status',
        '/api/users', '/api/users/{user_id}',
    ]
    for path in expected:
        assert path in paths, f'{path} missing from OpenAPI spec'
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_openapi.py -v -k "user_paths or all_blueprints"
```

Expected: `FAILED`（users 的 route 還沒加文件）

- [ ] **Step 3: 在 `app/blueprints/users/schemas.py` 新增 Response Schema，把整個檔案改為**

```python
from marshmallow import Schema, fields, validate

from app.blueprints.auth.schemas import UserResponseSchema


class UpdateUserSchema(Schema):
    username = fields.Str(validate=validate.Length(min=2, max=80))
    password = fields.Str(validate=validate.Length(min=6))
    is_active = fields.Bool()
    role = fields.Str(validate=validate.OneOf(['user', 'admin']))


class UserListResponseSchema(Schema):
    users = fields.List(fields.Nested(UserResponseSchema))
    total = fields.Int()
    pages = fields.Int()
    current_page = fields.Int()
```

- [ ] **Step 4: 更新 `app/blueprints/users/routes.py`，把整個檔案改為**

```python
from flask import request, jsonify
from flask_jwt_extended import get_jwt

from app.blueprints.users import users_bp
from app.blueprints.users.schemas import UpdateUserSchema
from app.utils.decorators import admin_required, validate_body, owner_or_admin_required
from app.services import user_service


@users_bp.route('', methods=['GET'])
@admin_required
def get_users():
    """
    ---
    get:
      summary: 取得所有會員
      tags: [Users]
      security:
        - bearerAuth: []
      parameters:
        - in: query
          name: page
          schema: {type: integer, default: 1}
        - in: query
          name: per_page
          schema: {type: integer, default: 20}
          description: 上限 100
      responses:
        200:
          description: 會員列表
          content:
            application/json:
              schema: UserListResponseSchema
        403:
          description: 權限不足，需要 admin 身分
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    return jsonify(user_service.get_users(page, per_page))


@users_bp.route('/<int:user_id>', methods=['GET'])
@owner_or_admin_required
def get_user(user_id):
    """
    ---
    get:
      summary: 取得單一會員
      tags: [Users]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: user_id
          required: true
          schema: {type: integer}
      responses:
        200:
          description: 會員資訊
          content:
            application/json:
              schema: UserResponseSchema
        403:
          description: 無權限（非本人也非 admin）
    """
    return jsonify(user_service.get_user(user_id))


@users_bp.route('/<int:user_id>', methods=['PUT'])
@owner_or_admin_required
@validate_body(UpdateUserSchema)
def update_user(user_id, validated_data):
    """
    ---
    put:
      summary: 更新會員資訊
      tags: [Users]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: user_id
          required: true
          schema: {type: integer}
      requestBody:
        required: true
        content:
          application/json:
            schema: UpdateUserSchema
      responses:
        200:
          description: 用戶資訊更新成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  message: {type: string}
                  user:
                    $ref: '#/components/schemas/UserResponse'
        403:
          description: 無權限（非本人也非 admin）
        409:
          description: 使用者名稱已被使用
    """
    claims = get_jwt()
    return jsonify({
        'message': '用戶資訊更新成功',
        'user': user_service.update_user(user_id, validated_data, claims)
    })


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@admin_required
def deactivate_user(user_id):
    """
    ---
    delete:
      summary: 停用帳號
      tags: [Users]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: user_id
          required: true
          schema: {type: integer}
      responses:
        200:
          description: 用戶帳號已停用
        403:
          description: 權限不足，需要 admin 身分
    """
    user_service.deactivate_user(user_id)
    return jsonify({'message': '用戶帳號已停用'})
```

- [ ] **Step 5: 執行測試確認通過**

```bash
pytest tests/test_openapi.py -v
```

Expected: 全部 `PASSED`（含 `test_openapi_spec_covers_all_blueprints`）

- [ ] **Step 6: 執行完整測試套件**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [ ] **Step 7: 手動確認 Swagger UI 實際可用**

```bash
flask run
```

瀏覽器開 `http://localhost:5000/api/docs/`，確認頁面正常顯示、可以展開各個端點、Schema 區塊有列出。

- [ ] **Step 8: Commit**

```bash
git add app/blueprints/users/schemas.py app/blueprints/users/routes.py tests/test_openapi.py
git commit -m "docs: add OpenAPI documentation for user endpoints"
```

---

## 完成後的變更總覽

```
app/
├── openapi.py                       (new: APISpec + security schemes + register_openapi)
├── __init__.py                      (呼叫 register_openapi)
└── blueprints/
    ├── auth/
    │   ├── schemas.py               (+UserResponseSchema, +LoginResponseSchema)
    │   └── routes.py                (5 個 route 補 docstring)
    ├── products/
    │   ├── schemas.py               (+ProductResponseSchema 等 4 個)
    │   └── routes.py                (7 個 route 補 docstring)
    ├── orders/
    │   ├── schemas.py               (+OrderResponseSchema 等 3 個)
    │   └── routes.py                (4 個 route 補 docstring)
    └── users/
        ├── schemas.py               (+UserListResponseSchema)
        └── routes.py                (4 個 route 補 docstring)
requirements.txt                     (+apispec, +apispec-webframeworks, +flask-swagger-ui)
tests/
└── test_openapi.py                  (new: 8 個測試)
```

完成後可以訪問：
- `GET /api/docs/` — Swagger UI 互動文件
- `GET /api/openapi.json` — 原始 OpenAPI 3.0 spec
