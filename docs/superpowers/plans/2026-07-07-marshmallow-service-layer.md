# Marshmallow 輸入驗證 + Service Layer 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 Flask 電商 API 加入 Marshmallow 格式驗證層，並引入 Service Layer 分離業務邏輯與 HTTP 處理。

**Architecture:** Route 只做 HTTP（解析 request、回傳 response）；`@validate_body(Schema)` 裝飾器在進入 route 前驗證輸入格式；Service 處理所有業務邏輯與 DB 操作，失敗時 raise 自訂例外，由 error_handler 統一轉換為 HTTP 錯誤。

**Tech Stack:** Python 3, Flask 3, SQLAlchemy, marshmallow>=3.20.0, Flask-JWT-Extended

> **注意：** 此計畫不包含 pytest 單元測試（見 spec 第 10 節）。各任務以 curl 指令驗證行為正確性。

---

## 檔案結構

### 新增
```
app/
├── services/
│   ├── __init__.py           # 空檔案，讓 services 成為 package
│   ├── auth_service.py       # register, login 業務邏輯
│   ├── product_service.py    # 商品 CRUD 業務邏輯
│   ├── order_service.py      # 訂單建立（含樂觀鎖）、狀態更新
│   └── user_service.py       # 會員查詢、更新、停用
├── utils/
│   └── exceptions.py         # AppError, ConflictError, NotFoundError, BadRequestError, ForbiddenError, UnauthorizedError
├── blueprints/
│   ├── auth/schemas.py       # RegisterSchema, LoginSchema
│   ├── products/schemas.py   # CreateProductSchema, UpdateProductSchema
│   ├── orders/schemas.py     # CreateOrderSchema, OrderItemSchema, UpdateOrderStatusSchema
│   └── users/schemas.py      # UpdateUserSchema
```

### 修改
```
requirements.txt              # 新增 marshmallow>=3.20.0
app/utils/decorators.py       # 新增 validate_body 裝飾器
app/middleware/error_handler.py  # 新增 AppError handler
app/blueprints/auth/routes.py    # 改薄，委派給 auth_service
app/blueprints/products/routes.py  # 改薄，委派給 product_service
app/blueprints/orders/routes.py    # 改薄，委派給 order_service
app/blueprints/users/routes.py     # 改薄，委派給 user_service
```

---

## Task 1: 安裝 marshmallow

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 更新 requirements.txt**

將 `requirements.txt` 改為：
```
flask>=3.0.0
flask-sqlalchemy>=3.1.0
flask-migrate>=4.0.0
flask-jwt-extended>=4.6.0
werkzeug>=3.0.0
python-dotenv>=1.0.0
faker>=24.0.0
gunicorn>=21.0.0
psycopg2-binary>=2.9.11
marshmallow>=3.20.0
```

- [ ] **Step 2: 安裝**

```bash
pip install marshmallow>=3.20.0
```

Expected: `Successfully installed marshmallow-3.x.x`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add marshmallow dependency"
```

---

## Task 2: 建立自訂例外類別

**Files:**
- Create: `app/utils/exceptions.py`
- Modify: `app/middleware/error_handler.py`

- [ ] **Step 1: 建立 `app/utils/exceptions.py`**

```python
class AppError(Exception):
    def __init__(self, message, status_code):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ConflictError(AppError):
    def __init__(self, message):
        super().__init__(message, 409)


class NotFoundError(AppError):
    def __init__(self, message):
        super().__init__(message, 404)


class BadRequestError(AppError):
    def __init__(self, message):
        super().__init__(message, 400)


class ForbiddenError(AppError):
    def __init__(self, message):
        super().__init__(message, 403)


class UnauthorizedError(AppError):
    def __init__(self, message):
        super().__init__(message, 401)
```

- [ ] **Step 2: 更新 `app/middleware/error_handler.py`**

將整個檔案改為：
```python
from flask import jsonify
from app.utils.exceptions import AppError


def register_error_handlers(app):

    @app.errorhandler(AppError)
    def handle_app_error(e):
        return jsonify({'error': e.message}), e.status_code

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({'error': '請求格式錯誤', 'detail': str(e)}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({'error': '未授權，請先登入'}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({'error': '權限不足'}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': '資源不存在'}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({'error': '不支援此 HTTP 方法'}), 405

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({'error': '伺服器內部錯誤'}), 500
```

- [ ] **Step 3: Commit**

```bash
git add app/utils/exceptions.py app/middleware/error_handler.py
git commit -m "feat: add custom AppError exception hierarchy and handler"
```

---

## Task 3: 新增 validate_body 裝飾器

**Files:**
- Modify: `app/utils/decorators.py`

- [ ] **Step 1: 更新 `app/utils/decorators.py`**

將整個檔案改為：
```python
from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from marshmallow import ValidationError


def admin_required(fn):
    """限制只有 admin 角色可存取的裝飾器"""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt()
        if claims.get('role') != 'admin':
            return jsonify({'error': '權限不足，需要 admin 身分'}), 403
        return fn(*args, **kwargs)

    return wrapper


def validate_body(schema_class):
    """驗證 JSON request body，通過後以 validated_data 關鍵字參數傳入 route"""
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

- [ ] **Step 2: 啟動伺服器，確認現有功能不受影響**

```bash
flask run
```

用 curl 測試現有 login（不帶 body）應得到 400：
```bash
curl -s -X POST http://localhost:5000/api/auth/login | python -m json.tool
```

Expected:
```json
{"error": "缺少必要欄位：email, password"}
```

（此時 routes 尚未改，行為不變是正常的）

- [ ] **Step 3: Commit**

```bash
git add app/utils/decorators.py
git commit -m "feat: add validate_body decorator for Marshmallow schema validation"
```

---

## Task 4: Auth — Schema + Service + Routes

**Files:**
- Create: `app/blueprints/auth/schemas.py`
- Create: `app/services/__init__.py`
- Create: `app/services/auth_service.py`
- Modify: `app/blueprints/auth/routes.py`

- [ ] **Step 1: 建立 `app/services/__init__.py`**

```python
```
（空檔案）

- [ ] **Step 2: 建立 `app/blueprints/auth/schemas.py`**

```python
from marshmallow import Schema, fields, validate


class RegisterSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=2, max=80))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=6))


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)
```

- [ ] **Step 3: 建立 `app/services/auth_service.py`**

```python
from flask_jwt_extended import create_access_token

from app import db
from app.models.user import User
from app.utils.exceptions import ConflictError, UnauthorizedError, ForbiddenError


def register(data):
    if User.query.filter_by(email=data['email']).first():
        raise ConflictError('此 Email 已被註冊')
    if User.query.filter_by(username=data['username']).first():
        raise ConflictError('此使用者名稱已被使用')

    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return user.to_dict()


def login(data):
    user = User.query.filter_by(email=data['email']).first()

    if not user or not user.check_password(data['password']):
        raise UnauthorizedError('Email 或密碼錯誤')

    if not user.is_active:
        raise ForbiddenError('帳號已被停用')

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={'role': user.role}
    )
    return {'access_token': access_token, 'user': user.to_dict()}
```

- [ ] **Step 4: 更新 `app/blueprints/auth/routes.py`**

```python
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.user import User
from app.blueprints.auth import auth_bp
from app.blueprints.auth.schemas import RegisterSchema, LoginSchema
from app.utils.decorators import validate_body
from app.services import auth_service


@auth_bp.route('/register', methods=['POST'])
@validate_body(RegisterSchema)
def register(validated_data):
    user = auth_service.register(validated_data)
    return jsonify({'message': '註冊成功', 'user': user}), 201


@auth_bp.route('/login', methods=['POST'])
@validate_body(LoginSchema)
def login(validated_data):
    result = auth_service.login(validated_data)
    return jsonify({'message': '登入成功', **result})


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())
```

- [ ] **Step 5: 手動驗證**

啟動 `flask run`，執行以下測試：

**5a. 格式驗證：密碼太短**
```bash
curl -s -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"tim","email":"tim@example.com","password":"123"}' | python -m json.tool
```
Expected:
```json
{"errors": {"password": ["Shorter than minimum length 6."]}}
```

**5b. 格式驗證：email 格式錯誤**
```bash
curl -s -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"tim","email":"not-an-email","password":"password123"}' | python -m json.tool
```
Expected:
```json
{"errors": {"email": ["Not a valid email address."]}}
```

**5c. 正常註冊**
```bash
curl -s -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"password123"}' | python -m json.tool
```
Expected: `201` 含 user 資料

**5d. 正常登入**
```bash
curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}' | python -m json.tool
```
Expected: `200` 含 access_token

- [ ] **Step 6: Commit**

```bash
git add app/services/__init__.py app/services/auth_service.py \
        app/blueprints/auth/schemas.py app/blueprints/auth/routes.py
git commit -m "feat: add auth schemas, auth_service, and slim auth routes"
```

---

## Task 5: Products — Schema + Service + Routes

**Files:**
- Create: `app/blueprints/products/schemas.py`
- Create: `app/services/product_service.py`
- Modify: `app/blueprints/products/routes.py`

- [ ] **Step 1: 建立 `app/blueprints/products/schemas.py`**

```python
from marshmallow import Schema, fields, validate


class CreateProductSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    price = fields.Float(required=True, validate=validate.Range(min=0.01))
    stock = fields.Int(load_default=0, validate=validate.Range(min=0))
    category = fields.Str(load_default=None)
    description = fields.Str(load_default=None)
    image_url = fields.Url(load_default=None)


class UpdateProductSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=200))
    price = fields.Float(validate=validate.Range(min=0.01))
    stock = fields.Int(validate=validate.Range(min=0))
    category = fields.Str()
    description = fields.Str()
    image_url = fields.Url()
    is_active = fields.Bool()
```

- [ ] **Step 2: 建立 `app/services/product_service.py`**

```python
from app import db
from app.models.product import Product


def get_products(page, per_page, category):
    query = Product.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        'products': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    }


def get_product(product_id):
    return Product.query.get_or_404(product_id).to_dict()


def create_product(data):
    product = Product(
        name=data['name'],
        description=data.get('description'),
        price=data['price'],
        stock=data.get('stock', 0),
        category=data.get('category'),
        image_url=data.get('image_url'),
    )
    db.session.add(product)
    db.session.commit()
    return product.to_dict()


def update_product(product_id, data):
    product = Product.query.get_or_404(product_id)
    for field in Product.UPDATABLE_FIELDS:
        if field in data:
            setattr(product, field, data[field])
    db.session.commit()
    return product.to_dict()


def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = False
    db.session.commit()
```

- [ ] **Step 3: 更新 `app/blueprints/products/routes.py`**

```python
from flask import request, jsonify

from app.blueprints.products import products_bp
from app.blueprints.products.schemas import CreateProductSchema, UpdateProductSchema
from app.utils.decorators import admin_required, validate_body
from app.services import product_service


@products_bp.route('', methods=['GET'])
def get_products():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    category = request.args.get('category')
    return jsonify(product_service.get_products(page, per_page, category))


@products_bp.route('/<int:product_id>', methods=['GET'])
def get_product(product_id):
    return jsonify(product_service.get_product(product_id))


@products_bp.route('', methods=['POST'])
@admin_required
@validate_body(CreateProductSchema)
def create_product(validated_data):
    product = product_service.create_product(validated_data)
    return jsonify({'message': '商品建立成功', 'product': product}), 201


@products_bp.route('/<int:product_id>', methods=['PUT'])
@admin_required
@validate_body(UpdateProductSchema)
def update_product(product_id, validated_data):
    product = product_service.update_product(product_id, validated_data)
    return jsonify({'message': '商品更新成功', 'product': product})


@products_bp.route('/<int:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    product_service.delete_product(product_id)
    return jsonify({'message': '商品已下架'})
```

- [ ] **Step 4: 手動驗證**

先取得 admin token：
```bash
TOKEN=$(curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

**4a. price 為負數應被拒絕**
```bash
curl -s -X POST http://localhost:5000/api/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"測試商品","price":-10}' | python -m json.tool
```
Expected:
```json
{"errors": {"price": ["Must be greater than or equal to 0.01."]}}
```

**4b. 正常建立商品**
```bash
curl -s -X POST http://localhost:5000/api/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"測試商品","price":99.9,"stock":100}' | python -m json.tool
```
Expected: `201` 含商品資料

- [ ] **Step 5: Commit**

```bash
git add app/blueprints/products/schemas.py app/services/product_service.py \
        app/blueprints/products/routes.py
git commit -m "feat: add product schemas, product_service, and slim product routes"
```

---

## Task 6: Orders — Schema + Service + Routes

**Files:**
- Create: `app/blueprints/orders/schemas.py`
- Create: `app/services/order_service.py`
- Modify: `app/blueprints/orders/routes.py`

- [ ] **Step 1: 建立 `app/blueprints/orders/schemas.py`**

```python
from marshmallow import Schema, fields, validate

VALID_STATUSES = ('pending', 'paid', 'shipped', 'delivered', 'cancelled')


class OrderItemSchema(Schema):
    product_id = fields.Int(required=True, validate=validate.Range(min=1))
    quantity = fields.Int(required=True, validate=validate.Range(min=1))


class CreateOrderSchema(Schema):
    items = fields.List(
        fields.Nested(OrderItemSchema),
        required=True,
        validate=validate.Length(min=1)
    )


class UpdateOrderStatusSchema(Schema):
    status = fields.Str(required=True, validate=validate.OneOf(VALID_STATUSES))
```

- [ ] **Step 2: 建立 `app/services/order_service.py`**

```python
from sqlalchemy.orm import joinedload

from app import db
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.inventory_log import InventoryLog
from app.utils.exceptions import (
    BadRequestError, ForbiddenError, NotFoundError, ConflictError
)

MAX_RETRY = 3


def get_orders(user_id, claims, page, per_page):
    query = Order.query.options(
        joinedload(Order.items).joinedload(OrderItem.product)
    ).order_by(Order.created_at.desc())

    if claims.get('role') != 'admin':
        query = query.filter_by(user_id=user_id)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        'orders': [o.to_dict() for o in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    }


def get_order(order_id, user_id, claims):
    order = Order.query.options(
        joinedload(Order.items).joinedload(OrderItem.product)
    ).get_or_404(order_id)

    if claims.get('role') != 'admin' and order.user_id != user_id:
        raise ForbiddenError('無權限查看此訂單')

    return order.to_dict()


def create_order(user_id, data):
    for attempt in range(MAX_RETRY):
        try:
            order = Order(user_id=user_id)
            db.session.add(order)
            logs = []

            for item_data in data['items']:
                product_id = item_data['product_id']
                qty = item_data['quantity']

                product = Product.query.get(product_id)
                if not product or not product.is_active:
                    db.session.rollback()
                    raise NotFoundError(f'商品 ID {product_id} 不存在或已下架')

                if product.stock < qty:
                    db.session.rollback()
                    raise BadRequestError(f'商品「{product.name}」庫存不足')

                stock_before = product.stock

                # 樂觀鎖：版本號不符則 updated_rows = 0
                updated_rows = Product.query.filter_by(
                    id=product.id,
                    version=product.version
                ).update({
                    'stock': product.stock - qty,
                    'version': product.version + 1
                })

                if updated_rows == 0:
                    db.session.rollback()
                    break  # 衝突，進入下一次重試

                order_item = OrderItem(
                    order=order,
                    product_id=product.id,
                    quantity=qty,
                    unit_price=product.price,
                )
                db.session.add(order_item)

                log = InventoryLog(
                    product_id=product.id,
                    action='deduct',
                    quantity_before=stock_before,
                    quantity_change=-qty,
                    quantity_after=stock_before - qty,
                    note='訂單建立扣除',
                )
                db.session.add(log)
                logs.append(log)

            else:
                # for 迴圈正常結束（無 break），所有商品處理成功
                db.session.flush()
                order.calculate_total()
                for log in logs:
                    log.order_id = order.id
                db.session.commit()
                return order.to_dict()

        except (NotFoundError, BadRequestError, ForbiddenError):
            raise  # 業務錯誤直接傳播，不重試
        except Exception as e:
            db.session.rollback()
            raise BadRequestError(f'訂單建立失敗：{str(e)}')

    raise ConflictError('庫存競爭衝突，請稍後再試')


def update_order_status(order_id, data, claims):
    if claims.get('role') != 'admin':
        raise ForbiddenError('只有 admin 可以更新訂單狀態')

    order = Order.query.get_or_404(order_id)
    order.status = data['status']
    db.session.commit()
    return order.to_dict()
```

- [ ] **Step 3: 更新 `app/blueprints/orders/routes.py`**

```python
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.blueprints.orders import orders_bp
from app.blueprints.orders.schemas import CreateOrderSchema, UpdateOrderStatusSchema
from app.utils.decorators import validate_body
from app.services import order_service


@orders_bp.route('', methods=['GET'])
@jwt_required()
def get_orders():
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    return jsonify(order_service.get_orders(user_id, claims, page, per_page))


@orders_bp.route('/<int:order_id>', methods=['GET'])
@jwt_required()
def get_order(order_id):
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    return jsonify(order_service.get_order(order_id, user_id, claims))


@orders_bp.route('', methods=['POST'])
@jwt_required()
@validate_body(CreateOrderSchema)
def create_order(validated_data):
    user_id = int(get_jwt_identity())
    order = order_service.create_order(user_id, validated_data)
    return jsonify({'message': '訂單建立成功', 'order': order}), 201


@orders_bp.route('/<int:order_id>/status', methods=['PATCH'])
@jwt_required()
@validate_body(UpdateOrderStatusSchema)
def update_order_status(order_id, validated_data):
    claims = get_jwt()
    order = order_service.update_order_status(order_id, validated_data, claims)
    return jsonify({'message': '訂單狀態已更新', 'order': order})
```

- [ ] **Step 4: 手動驗證**

取得 user token（用 seed 產生的任一用戶）：
```bash
USER_TOKEN=$(curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

**4a. quantity 為 0 應被拒絕**
```bash
curl -s -X POST http://localhost:5000/api/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{"items":[{"product_id":1,"quantity":0}]}' | python -m json.tool
```
Expected:
```json
{"errors": {"items": {"0": {"quantity": ["Must be greater than or equal to 1."]}}}}
```

**4b. 空 items 應被拒絕**
```bash
curl -s -X POST http://localhost:5000/api/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{"items":[]}' | python -m json.tool
```
Expected:
```json
{"errors": {"items": ["Shorter than minimum length 1."]}}
```

**4c. 正常建立訂單**
```bash
curl -s -X POST http://localhost:5000/api/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{"items":[{"product_id":1,"quantity":1}]}' | python -m json.tool
```
Expected: `201` 含訂單資料

- [ ] **Step 5: Commit**

```bash
git add app/blueprints/orders/schemas.py app/services/order_service.py \
        app/blueprints/orders/routes.py
git commit -m "feat: add order schemas, order_service, and slim order routes"
```

---

## Task 7: Users — Schema + Service + Routes

**Files:**
- Create: `app/blueprints/users/schemas.py`
- Create: `app/services/user_service.py`
- Modify: `app/blueprints/users/routes.py`

- [ ] **Step 1: 建立 `app/blueprints/users/schemas.py`**

```python
from marshmallow import Schema, fields, validate


class UpdateUserSchema(Schema):
    username = fields.Str(validate=validate.Length(min=2, max=80))
    password = fields.Str(validate=validate.Length(min=6))
    is_active = fields.Bool()
    role = fields.Str(validate=validate.OneOf(['user', 'admin']))
```

- [ ] **Step 2: 建立 `app/services/user_service.py`**

```python
from app import db
from app.models.user import User
from app.utils.exceptions import ConflictError


def get_users(page, per_page):
    pagination = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        'users': [u.to_dict() for u in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    }


def get_user(user_id):
    return User.query.get_or_404(user_id).to_dict()


def update_user(user_id, data, claims):
    user = User.query.get_or_404(user_id)

    if 'username' in data:
        existing = User.query.filter_by(username=data['username']).first()
        if existing and existing.id != user_id:
            raise ConflictError('此使用者名稱已被使用')
        user.username = data['username']

    if 'password' in data:
        user.set_password(data['password'])

    # is_active 和 role 僅限 admin 修改
    if claims.get('role') == 'admin':
        if 'is_active' in data:
            user.is_active = data['is_active']
        if 'role' in data:
            user.role = data['role']

    db.session.commit()
    return user.to_dict()


def deactivate_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
```

- [ ] **Step 3: 更新 `app/blueprints/users/routes.py`**

```python
from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.blueprints.users import users_bp
from app.blueprints.users.schemas import UpdateUserSchema
from app.utils.decorators import admin_required, validate_body
from app.services import user_service


def owner_or_admin_required(fn):
    """限制只有本人或 admin 可存取，適用於 URL 含 user_id 的 route"""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        current_user_id = int(get_jwt_identity())
        claims = get_jwt()
        url_user_id = kwargs.get('user_id')
        if claims.get('role') != 'admin' and url_user_id != current_user_id:
            return jsonify({'error': '無權限'}), 403
        return fn(*args, **kwargs)
    return wrapper


@users_bp.route('', methods=['GET'])
@admin_required
def get_users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    return jsonify(user_service.get_users(page, per_page))


@users_bp.route('/<int:user_id>', methods=['GET'])
@owner_or_admin_required
def get_user(user_id):
    return jsonify(user_service.get_user(user_id))


@users_bp.route('/<int:user_id>', methods=['PUT'])
@owner_or_admin_required
@validate_body(UpdateUserSchema)
def update_user(user_id, validated_data):
    claims = get_jwt()
    return jsonify({
        'message': '用戶資訊更新成功',
        'user': user_service.update_user(user_id, validated_data, claims)
    })


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@admin_required
def deactivate_user(user_id):
    user_service.deactivate_user(user_id)
    return jsonify({'message': '用戶帳號已停用'})
```

- [ ] **Step 4: 手動驗證**

**4a. 密碼太短應被拒絕**
```bash
ADMIN_TOKEN=$(curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X PUT http://localhost:5000/api/users/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"password":"123"}' | python -m json.tool
```
Expected:
```json
{"errors": {"password": ["Shorter than minimum length 6."]}}
```

**4b. role 非法值應被拒絕**
```bash
curl -s -X PUT http://localhost:5000/api/users/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"role":"superuser"}' | python -m json.tool
```
Expected:
```json
{"errors": {"role": ["Must be one of: user, admin."]}}
```

**4c. 正常更新 username**
```bash
curl -s -X PUT http://localhost:5000/api/users/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"username":"new_admin"}' | python -m json.tool
```
Expected: `200` 含更新後 user 資料

- [ ] **Step 5: Commit**

```bash
git add app/blueprints/users/schemas.py app/services/user_service.py \
        app/blueprints/users/routes.py
git commit -m "feat: add user schemas, user_service, and slim user routes"
```

---

## 完成後的目錄結構

```
app/
├── services/
│   ├── __init__.py
│   ├── auth_service.py
│   ├── product_service.py
│   ├── order_service.py
│   └── user_service.py
├── utils/
│   ├── decorators.py    ← 含 admin_required + validate_body
│   └── exceptions.py    ← 含 AppError 及子類別
├── blueprints/
│   ├── auth/
│   │   ├── routes.py    ← 薄 route
│   │   └── schemas.py
│   ├── products/
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── orders/
│   │   ├── routes.py
│   │   └── schemas.py
│   └── users/
│       ├── routes.py
│       └── schemas.py
└── middleware/
    └── error_handler.py ← 含 AppError handler
```
