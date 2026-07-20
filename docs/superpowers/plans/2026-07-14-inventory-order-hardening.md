# 測試基礎建設 + 庫存調整 API + 訂單取消回補 + 分頁上限 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為專案補上 pytest 測試基礎建設與既有功能的回歸測試，然後在此安全網之上新增「庫存補貨／人工調整 API」、修正「訂單狀態 PATCH 權限（使用者可取消自己的待處理訂單並回補庫存）」，並替所有分頁端點加上 `per_page` 上限。

**Architecture:** 沿用專案既有的 Route → Service → Model 分層。新功能一律：Marshmallow schema 驗證輸入格式，Service 處理業務邏輯與 DB 操作（含 `InventoryLog` 寫入），失敗時 raise `app/utils/exceptions.py` 中的自訂例外，由既有的 `error_handler` 統一轉成 HTTP 錯誤。測試使用 pytest + Flask test client，資料庫使用 SQLite in-memory。

**Tech Stack:** Python 3, Flask 3, SQLAlchemy, Marshmallow, Flask-JWT-Extended, pytest

**關鍵設計決策（已與使用者確認或依現有慣例決定，執行前請留意）：**
1. 「刪除訂單須加回庫存」= 重用既有 `PATCH /api/orders/<id>/status`，不新增 DELETE 路由。當訂單狀態被改為 `cancelled` 時（不論是使用者取消自己的訂單，或是 admin 手動改狀態），把該訂單所有品項的庫存加回去，並寫入 `InventoryLog(action='restock')`。
2. 一般使用者（非 admin）呼叫 `PATCH /status` 時：只能操作自己的訂單、只能把狀態改成 `cancelled`、且只有訂單目前狀態為 `pending` 時才允許取消（避免使用者取消已出貨/已送達的訂單）。admin 則不受此限制，可設定任何合法狀態。
3. 已知限制（本次不處理）：目前 `VALID_STATUSES` 沒有完整狀態機檢查，理論上 admin 可以把訂單從 `cancelled` 改回 `pending` 再改回 `cancelled`，導致庫存被回補兩次。這是既有設計就存在的缺口，不在本次需求範圍內，先不修正。
4. 分頁上限：新增 `app/utils/pagination.py`，`MAX_PER_PAGE = 100`，所有分頁端點（products / orders / users / 新增的 inventory-logs）一律 clamp 到 `[1, 100]`。

---

## 執行狀態（2026-07-15 覆核）

**Task 1-5 皆已實作並個別 commit：**

| Task | Commit |
|---|---|
| 1. pytest 測試基礎建設 | `556f131 feat:新增測試設定與smoke test` |
| 2. 既有功能回歸測試 | `02d0caf test:新增Integration test` |
| 3. 庫存補貨與人工調整 API | `570598b feat:新增庫存調整API` |
| 4. 訂單狀態 PATCH 權限修正 | `36944d6 modify:訂單狀態權限修正` |
| 5. per_page 上限 | `6344b34 feat:套用分頁功能在order,product,user service中` |

`pytest -v` 全部 35 個測試通過。實作與計畫的差異（皆為合理的實作選擇，非缺陷）：
- `DELETE /api/products/<id>` 改回傳 `204`（計畫原假設沿用既有的 `200`），對應測試已同步更新。

**⚠️ 覆核時發現一個計畫外的 bug，尚未修正：**

[app/services/order_service.py:130](app/services/order_service.py#L130)

```python
if new_status == "cancelled" and order.status != "cancelld":
```

`"cancelld"` 是拼字錯誤（應為 `"cancelled"`）。因為這個字串永遠不會等於真正的訂單狀態，這個判斷式其實恆為 `True`，等於「防止重複回補庫存」的防護完全沒作用 —— 只要對同一張已經是 `cancelled` 的訂單再打一次 `PATCH /status {"status":"cancelled"}`（目前只有 admin 能重複打，因為使用者只能在 `pending` 狀態下取消），就會再回補一次庫存，庫存數字會被灌水。目前測試沒有覆蓋「對已取消訂單重複取消」這個案例，所以沒被抓到。建議修正為 `order.status != "cancelled"`，並補一個回歸測試（對同一張訂單呼叫兩次 cancel，第二次庫存不應再增加）。

---

## Task 1: pytest 測試基礎建設

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_smoke.py`

- [x] **Step 1: 在 `requirements.txt` 加入 pytest**

在檔案最後新增一行（用 UTF-8 存檔，取代原本疑似 UTF-16 編碼的內容）：

```
pytest>=8.0.0
```

- [x] **Step 2: 安裝 pytest**

```bash
pip install pytest>=8.0.0
```

Expected: `Successfully installed pytest-8.x.x`

- [x] **Step 3: 在 `config.py` 新增 `TestingConfig`**

在 `class ProductionConfig(Config):` 區塊之後、`config_map = {` 之前插入：

```python
class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    JWT_SECRET_KEY = 'test-jwt-secret-key'
```

並把 `config_map` 改為：

```python
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
```

- [x] **Step 4: 建立 `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [x] **Step 5: 建立空的 `tests/__init__.py`**

```python
```

- [x] **Step 6: 建立 `tests/conftest.py`**

```python
import pytest

from app import create_app, db as _db
from app.models.user import User


@pytest.fixture
def app():
    flask_app = create_app('testing')
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def auth_header():
    def _make(token):
        return {'Authorization': f'Bearer {token}'}
    return _make


def _create_user_and_login(client, db, email, password, role):
    user = User(username=email.split('@')[0], email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    resp = client.post('/api/auth/login', json={'email': email, 'password': password})
    token = resp.get_json()['access_token']
    return user, token


@pytest.fixture
def admin_user_and_token(client, db):
    return _create_user_and_login(client, db, 'admin@test.com', 'admin1234', 'admin')


@pytest.fixture
def normal_user_and_token(client, db):
    return _create_user_and_login(client, db, 'user@test.com', 'user12345', 'user')
```

- [x] **Step 7: 建立煙霧測試 `tests/test_smoke.py`**

```python
def test_get_products_returns_empty_list(client):
    resp = client.get('/api/products')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['products'] == []
    assert data['total'] == 0


def test_admin_fixture_can_login(client, admin_user_and_token):
    user, token = admin_user_and_token
    resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.get_json()['role'] == 'admin'
```

- [x] **Step 8: 執行測試，確認基礎建設可用**

```bash
pytest tests/test_smoke.py -v
```

Expected: 2 個測試皆為 `PASSED`

- [x] **Step 9: Commit**

```bash
git add requirements.txt config.py pytest.ini tests/__init__.py tests/conftest.py tests/test_smoke.py
git commit -m "test: add pytest infrastructure with app/client/db fixtures"
```

---

## Task 2: 既有功能回歸測試（auth / products / orders / users）

> 這些是既有功能，此任務目的是補上「安全網」而非驅動新程式碼，因此步驟只需「寫測試 → 執行確認全部 PASS」，不需要先確認 FAIL。

**Files:**
- Create: `tests/test_auth.py`
- Create: `tests/test_products.py`
- Create: `tests/test_orders.py`
- Create: `tests/test_users.py`

- [x] **Step 1: 建立 `tests/test_auth.py`**

```python
def test_register_success(client):
    resp = client.post('/api/auth/register', json={
        'username': 'newuser',
        'email': 'newuser@test.com',
        'password': 'password123',
    })
    assert resp.status_code == 201
    assert resp.get_json()['user']['email'] == 'newuser@test.com'


def test_register_duplicate_email_returns_409(client):
    client.post('/api/auth/register', json={
        'username': 'dup1', 'email': 'dup@test.com', 'password': 'password123',
    })
    resp = client.post('/api/auth/register', json={
        'username': 'dup2', 'email': 'dup@test.com', 'password': 'password123',
    })
    assert resp.status_code == 409


def test_login_wrong_password_returns_401(client):
    client.post('/api/auth/register', json={
        'username': 'loginuser', 'email': 'login@test.com', 'password': 'password123',
    })
    resp = client.post('/api/auth/login', json={
        'email': 'login@test.com', 'password': 'wrongpass',
    })
    assert resp.status_code == 401


def test_login_inactive_user_returns_403(client, db):
    from app.models.user import User
    user = User(username='inactive', email='inactive@test.com', role='user', is_active=False)
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    resp = client.post('/api/auth/login', json={
        'email': 'inactive@test.com', 'password': 'password123',
    })
    assert resp.status_code == 403


def test_me_requires_jwt(client):
    resp = client.get('/api/auth/me')
    assert resp.status_code == 401
```

- [x] **Step 2: 建立 `tests/test_products.py`**

```python
def test_create_product_requires_admin(client, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    resp = client.post('/api/products', json={'name': '測試商品', 'price': 100},
                        headers=auth_header(token))
    assert resp.status_code == 403


def test_admin_can_create_product(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    resp = client.post('/api/products', json={'name': '測試商品', 'price': 100, 'stock': 10},
                        headers=auth_header(token))
    assert resp.status_code == 201
    body = resp.get_json()['product']
    assert body['name'] == '測試商品'
    assert body['stock'] == 10


def test_get_product_404_for_missing_id(client):
    resp = client.get('/api/products/999')
    assert resp.status_code == 404


def test_soft_deleted_product_excluded_from_list(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    create_resp = client.post('/api/products', json={'name': '將下架商品', 'price': 50},
                               headers=auth_header(token))
    product_id = create_resp.get_json()['product']['id']

    delete_resp = client.delete(f'/api/products/{product_id}', headers=auth_header(token))
    assert delete_resp.status_code == 200

    list_resp = client.get('/api/products')
    ids = [p['id'] for p in list_resp.get_json()['products']]
    assert product_id not in ids
```

- [x] **Step 3: 建立 `tests/test_orders.py`**

```python
from app.models.product import Product


def _create_product(db, name='商品', price=100.0, stock=10):
    product = Product(name=name, price=price, stock=stock, is_active=True)
    db.session.add(product)
    db.session.commit()
    return product


def test_create_order_deducts_stock(client, db, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    product = _create_product(db, stock=10)

    resp = client.post('/api/orders', json={'items': [{'product_id': product.id, 'quantity': 3}]},
                        headers=auth_header(token))
    assert resp.status_code == 201

    db.session.refresh(product)
    assert product.stock == 7


def test_create_order_insufficient_stock_returns_400(client, db, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    product = _create_product(db, stock=1)

    resp = client.post('/api/orders', json={'items': [{'product_id': product.id, 'quantity': 5}]},
                        headers=auth_header(token))
    assert resp.status_code == 400


def test_user_cannot_view_others_order(client, db, normal_user_and_token, admin_user_and_token, auth_header):
    admin_user, admin_token = admin_user_and_token
    user, user_token = normal_user_and_token
    product = _create_product(db, stock=10)

    create_resp = client.post('/api/orders', json={'items': [{'product_id': product.id, 'quantity': 1}]},
                               headers=auth_header(admin_token))
    order_id = create_resp.get_json()['order']['id']

    resp = client.get(f'/api/orders/{order_id}', headers=auth_header(user_token))
    assert resp.status_code == 403


def test_admin_can_update_order_status(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)

    create_resp = client.post('/api/orders', json={'items': [{'product_id': product.id, 'quantity': 1}]},
                               headers=auth_header(token))
    order_id = create_resp.get_json()['order']['id']

    resp = client.patch(f'/api/orders/{order_id}/status', json={'status': 'paid'},
                         headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.get_json()['order']['status'] == 'paid'
```

- [x] **Step 4: 建立 `tests/test_users.py`**

```python
def test_list_users_requires_admin(client, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    resp = client.get('/api/users', headers=auth_header(token))
    assert resp.status_code == 403


def test_admin_can_list_users(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    resp = client.get('/api/users', headers=auth_header(token))
    assert resp.status_code == 200


def test_owner_can_update_own_profile(client, normal_user_and_token, auth_header):
    user, token = normal_user_and_token
    resp = client.put(f'/api/users/{user.id}', json={'username': 'renamed'},
                       headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.get_json()['user']['username'] == 'renamed'


def test_non_owner_cannot_update_others_profile(client, normal_user_and_token, admin_user_and_token, auth_header):
    admin_user, admin_token = admin_user_and_token
    user, user_token = normal_user_and_token

    resp = client.put(f'/api/users/{admin_user.id}', json={'username': 'hijacked'},
                       headers=auth_header(user_token))
    assert resp.status_code == 403
```

- [x] **Step 5: 執行全部測試**

```bash
pytest -v
```

Expected: `tests/test_auth.py`、`tests/test_products.py`、`tests/test_orders.py`、`tests/test_users.py` 全部 `PASSED`

- [x] **Step 6: Commit**

```bash
git add tests/test_auth.py tests/test_products.py tests/test_orders.py tests/test_users.py
git commit -m "test: add regression tests for auth, products, orders, users"
```

---

## Task 3: 商品庫存補貨與人工調整 API

**Files:**
- Create: `app/utils/pagination.py`
- Modify: `app/blueprints/products/schemas.py`
- Modify: `app/services/product_service.py`
- Modify: `app/blueprints/products/routes.py`
- Test: `tests/test_inventory.py`

- [x] **Step 1: 建立 `app/utils/pagination.py`**

```python
MAX_PER_PAGE = 100


def clamp_per_page(per_page, max_per_page=MAX_PER_PAGE):
    return max(1, min(per_page, max_per_page))
```

- [x] **Step 2: 撰寫會失敗的測試 `tests/test_inventory.py`**

```python
from app.models.product import Product
from app.models.inventory_log import InventoryLog


def _create_product(db, name='商品', price=100.0, stock=10):
    product = Product(name=name, price=price, stock=stock, is_active=True)
    db.session.add(product)
    db.session.commit()
    return product


def test_restock_requires_admin(client, db, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    product = _create_product(db, stock=5)

    resp = client.post(f'/api/products/{product.id}/inventory-logs',
                        json={'action': 'restock', 'quantity_change': 10},
                        headers=auth_header(token))
    assert resp.status_code == 403


def test_admin_can_restock_product(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=5)

    resp = client.post(f'/api/products/{product.id}/inventory-logs',
                        json={'action': 'restock', 'quantity_change': 20, 'note': '廠商補貨'},
                        headers=auth_header(token))
    assert resp.status_code == 201
    log = resp.get_json()['inventory_log']
    assert log['quantity_before'] == 5
    assert log['quantity_after'] == 25
    assert log['action'] == 'restock'

    db.session.refresh(product)
    assert product.stock == 25


def test_restock_with_non_positive_quantity_returns_400(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=5)

    resp = client.post(f'/api/products/{product.id}/inventory-logs',
                        json={'action': 'restock', 'quantity_change': -1},
                        headers=auth_header(token))
    assert resp.status_code == 400


def test_admin_can_adjust_product_down(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)

    resp = client.post(f'/api/products/{product.id}/inventory-logs',
                        json={'action': 'adjust', 'quantity_change': -3, 'note': '盤點損耗'},
                        headers=auth_header(token))
    assert resp.status_code == 201
    assert resp.get_json()['inventory_log']['quantity_after'] == 7

    db.session.refresh(product)
    assert product.stock == 7


def test_adjust_below_zero_returns_400(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=2)

    resp = client.post(f'/api/products/{product.id}/inventory-logs',
                        json={'action': 'adjust', 'quantity_change': -5},
                        headers=auth_header(token))
    assert resp.status_code == 400


def test_get_inventory_logs_returns_history(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)

    client.post(f'/api/products/{product.id}/inventory-logs',
                json={'action': 'restock', 'quantity_change': 5},
                headers=auth_header(token))

    resp = client.get(f'/api/products/{product.id}/inventory-logs', headers=auth_header(token))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['total'] == 1
    assert body['inventory_logs'][0]['action'] == 'restock'
```

- [x] **Step 3: 執行測試確認會失敗（路由尚未存在）**

```bash
pytest tests/test_inventory.py -v
```

Expected: 全部 `FAILED`，錯誤為 404（路由不存在）

- [x] **Step 4: 在 `app/blueprints/products/schemas.py` 新增 `InventoryAdjustSchema`**

在檔案最後新增：

```python

class InventoryAdjustSchema(Schema):
    action = fields.Str(required=True, validate=validate.OneOf(['restock', 'adjust']))
    quantity_change = fields.Int(required=True)
    note = fields.Str(load_default=None, validate=validate.Length(max=255))
```

- [x] **Step 5: 在 `app/services/product_service.py` 新增庫存相關函式**

把檔案開頭的 import 改為：

```python
from app import db
from app.models.product import Product
from app.models.inventory_log import InventoryLog
from app.utils.exceptions import BadRequestError
from app.utils.pagination import clamp_per_page
```

在檔案最後新增：

```python

def get_inventory_logs(product_id, page, per_page):
    product = Product.query.get_or_404(product_id)
    per_page = clamp_per_page(per_page)
    pagination = InventoryLog.query.filter_by(product_id=product.id).order_by(
        InventoryLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    return {
        'inventory_logs': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    }


def adjust_inventory(product_id, data):
    product = Product.query.get_or_404(product_id)
    action = data['action']
    quantity_change = data['quantity_change']

    if action == 'restock' and quantity_change <= 0:
        raise BadRequestError('restock 的異動數量必須為正數')
    if action == 'adjust' and quantity_change == 0:
        raise BadRequestError('adjust 的異動數量不可為 0')

    quantity_before = product.stock
    quantity_after = quantity_before + quantity_change
    if quantity_after < 0:
        raise BadRequestError('庫存不足，異動後不可為負數')

    product.stock = quantity_after
    product.version += 1

    log = InventoryLog(
        product_id=product.id,
        action=action,
        quantity_before=quantity_before,
        quantity_change=quantity_change,
        quantity_after=quantity_after,
        note=data.get('note'),
    )
    db.session.add(log)
    db.session.commit()
    return log.to_dict()
```

- [x] **Step 6: 更新 `app/blueprints/products/routes.py`**

移除檔案開頭沒用到的 `from math import prod`（第 1 行），並把 import 區塊改為：

```python
from flask import request, jsonify

from app import db
from app.models.product import Product
from app.blueprints.products import products_bp
from app.blueprints.products.schemas import CreateProductSchema, UpdateProductSchema, InventoryAdjustSchema
from app.utils.decorators import admin_required, validate_body
from app.services import product_service
```

在檔案最後新增兩個路由：

```python

@products_bp.route('/<int:product_id>/inventory-logs', methods=['GET'])
@admin_required
def get_inventory_logs(product_id):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    return jsonify(product_service.get_inventory_logs(product_id, page, per_page))


@products_bp.route('/<int:product_id>/inventory-logs', methods=['POST'])
@admin_required
@validate_body(InventoryAdjustSchema)
def adjust_inventory(product_id, validated_data):
    log = product_service.adjust_inventory(product_id, validated_data)
    return jsonify({'message': '庫存調整成功', 'inventory_log': log}), 201
```

- [x] **Step 7: 執行測試確認全部通過**

```bash
pytest tests/test_inventory.py -v
```

Expected: 全部 `PASSED`

- [x] **Step 8: 執行完整測試套件，確認沒有破壞既有功能**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [x] **Step 9: Commit**

```bash
git add app/utils/pagination.py app/blueprints/products/schemas.py app/services/product_service.py \
        app/blueprints/products/routes.py tests/test_inventory.py
git commit -m "feat: add inventory restock/adjust API backed by InventoryLog"
```

---

## Task 4: 訂單狀態 PATCH 權限修正（使用者可取消自己的待處理訂單）+ 取消時回補庫存

**Files:**
- Modify: `app/services/order_service.py`
- Modify: `app/blueprints/orders/routes.py`
- Test: `tests/test_order_cancel.py`

- [x] **Step 1: 撰寫會失敗的測試 `tests/test_order_cancel.py`**

```python
from app.models.product import Product


def _create_product(db, name='商品', price=100.0, stock=10):
    product = Product(name=name, price=price, stock=stock, is_active=True)
    db.session.add(product)
    db.session.commit()
    return product


def _create_order(client, token, auth_header, product, quantity=2):
    resp = client.post('/api/orders', json={'items': [{'product_id': product.id, 'quantity': quantity}]},
                        headers=auth_header(token))
    return resp.get_json()['order']['id']


def test_user_can_cancel_own_pending_order(client, db, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, token, auth_header, product, quantity=3)

    db.session.refresh(product)
    assert product.stock == 7

    resp = client.patch(f'/api/orders/{order_id}/status', json={'status': 'cancelled'},
                         headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.get_json()['order']['status'] == 'cancelled'

    db.session.refresh(product)
    assert product.stock == 10


def test_user_cannot_cancel_others_order(client, db, normal_user_and_token, admin_user_and_token, auth_header):
    admin_user, admin_token = admin_user_and_token
    user, user_token = normal_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, admin_token, auth_header, product)

    resp = client.patch(f'/api/orders/{order_id}/status', json={'status': 'cancelled'},
                         headers=auth_header(user_token))
    assert resp.status_code == 403


def test_user_cannot_set_non_cancelled_status(client, db, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, token, auth_header, product)

    resp = client.patch(f'/api/orders/{order_id}/status', json={'status': 'shipped'},
                         headers=auth_header(token))
    assert resp.status_code == 403


def test_user_cannot_cancel_non_pending_order(client, db, admin_user_and_token, normal_user_and_token, auth_header):
    admin_user, admin_token = admin_user_and_token
    user, user_token = normal_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, user_token, auth_header, product)

    client.patch(f'/api/orders/{order_id}/status', json={'status': 'paid'},
                 headers=auth_header(admin_token))

    resp = client.patch(f'/api/orders/{order_id}/status', json={'status': 'cancelled'},
                         headers=auth_header(user_token))
    assert resp.status_code == 400


def test_admin_cancelling_order_also_restocks(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, token, auth_header, product, quantity=4)

    db.session.refresh(product)
    assert product.stock == 6

    resp = client.patch(f'/api/orders/{order_id}/status', json={'status': 'cancelled'},
                         headers=auth_header(token))
    assert resp.status_code == 200

    db.session.refresh(product)
    assert product.stock == 10
```

- [x] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_order_cancel.py -v
```

Expected: 大部分 `FAILED`（目前非 admin 呼叫一律回 403，且沒有回補庫存邏輯）

- [x] **Step 3: 更新 `app/services/order_service.py` 的 `update_order_status`**

把現有的 `update_order_status` 函式（第 111-118 行）整段替換為：

```python
def update_order_status(order_id, data, user_id, claims):
    order = Order.query.options(
        joinedload(Order.items).joinedload(OrderItem.product)
    ).filter_by(id=order_id).first_or_404()

    new_status = data['status']
    is_admin = claims.get('role') == 'admin'

    if not is_admin:
        if order.user_id != user_id:
            raise ForbiddenError('無權限修改此訂單')
        if new_status != 'cancelled':
            raise ForbiddenError('使用者僅能取消訂單')
        if order.status != 'pending':
            raise BadRequestError('只有待處理（pending）的訂單可以取消')

    if new_status == 'cancelled' and order.status != 'cancelled':
        _restock_order_items(order)

    order.status = new_status
    db.session.commit()
    return order.to_dict()


def _restock_order_items(order):
    for item in order.items:
        product = item.product
        quantity_before = product.stock
        product.stock = quantity_before + item.quantity
        product.version += 1
        db.session.add(InventoryLog(
            product_id=product.id,
            order_id=order.id,
            action='restock',
            quantity_before=quantity_before,
            quantity_change=item.quantity,
            quantity_after=product.stock,
            note='訂單取消，庫存回補',
        ))
```

- [x] **Step 4: 更新 `app/blueprints/orders/routes.py` 的 `update_order_status` route**

把現有的 route（第 37-43 行）整段替換為：

```python
@orders_bp.route('/<int:order_id>/status', methods=['PATCH'])
@jwt_required()
@validate_body(UpdateOrderStatusSchema)
def update_order_status(order_id, validated_data):
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    order = order_service.update_order_status(order_id, validated_data, user_id, claims)
    return jsonify({'message': '訂單狀態已更新', 'order': order})
```

- [x] **Step 5: 執行測試確認全部通過**

```bash
pytest tests/test_order_cancel.py -v
```

Expected: 全部 `PASSED`

- [x] **Step 6: 執行完整測試套件**

```bash
pytest -v
```

Expected: 全部 `PASSED`（含 Task 2 中 `test_admin_can_update_order_status`，此測試把狀態改為 `paid`，不會觸發回補邏輯，應維持通過）

- [x] **Step 7: Commit**

```bash
git add app/services/order_service.py app/blueprints/orders/routes.py tests/test_order_cancel.py
git commit -m "feat: allow user to cancel own pending order and restock inventory on cancellation"
```

---

## Task 5: 分頁 `per_page` 加上上限

**Files:**
- Modify: `app/services/product_service.py`
- Modify: `app/services/order_service.py`
- Modify: `app/services/user_service.py`
- Test: `tests/test_pagination.py`

- [x] **Step 1: 撰寫會失敗的測試 `tests/test_pagination.py`**

```python
from app.models.product import Product
from app.utils.pagination import clamp_per_page, MAX_PER_PAGE


def test_clamp_per_page_caps_large_value():
    assert clamp_per_page(9999) == MAX_PER_PAGE


def test_clamp_per_page_floors_non_positive_value():
    assert clamp_per_page(0) == 1
    assert clamp_per_page(-5) == 1


def test_clamp_per_page_keeps_value_within_range():
    assert clamp_per_page(10) == 10


def test_product_list_per_page_is_capped(client, db):
    for i in range(MAX_PER_PAGE + 20):
        db.session.add(Product(name=f'商品{i}', price=10.0, stock=1, is_active=True))
    db.session.commit()

    resp = client.get(f'/api/products?per_page={MAX_PER_PAGE + 50}')
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body['products']) == MAX_PER_PAGE
    assert body['total'] == MAX_PER_PAGE + 20


def test_user_list_per_page_is_capped(client, admin_user_and_token, auth_header, db):
    from app.models.user import User
    for i in range(MAX_PER_PAGE + 5):
        u = User(username=f'user{i}', email=f'user{i}@test.com', role='user')
        u.set_password('password123')
        db.session.add(u)
    db.session.commit()

    _, token = admin_user_and_token
    resp = client.get(f'/api/users?per_page={MAX_PER_PAGE + 50}', headers=auth_header(token))
    assert resp.status_code == 200
    assert len(resp.get_json()['users']) == MAX_PER_PAGE
```

- [x] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_pagination.py -v
```

Expected: `test_clamp_per_page_*` 這三個單元測試應 `PASSED`（`clamp_per_page` 已在 Task 3 建立好了）；`test_product_list_per_page_is_capped` 與 `test_user_list_per_page_is_capped` 應 `FAILED`（Service 尚未呼叫 `clamp_per_page`，會回傳超過 `MAX_PER_PAGE` 筆）

- [x] **Step 3: 在 `app/services/product_service.py` 的 `get_products` 套用上限**

把 `get_products` 函式改為：

```python
def get_products(page, per_page, category):
    per_page = clamp_per_page(per_page)
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
```

- [x] **Step 4: 在 `app/services/order_service.py` 套用上限**

在檔案開頭的 import 加入：

```python
from app.utils.pagination import clamp_per_page
```

把 `get_orders` 函式改為：

```python
def get_orders(user_id, claims, page, per_page):
    per_page = clamp_per_page(per_page)
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
```

- [x] **Step 5: 在 `app/services/user_service.py` 套用上限**

在檔案開頭的 import 加入：

```python
from app.utils.pagination import clamp_per_page
```

把 `get_users` 函式改為：

```python
def get_users(page, per_page):
    per_page = clamp_per_page(per_page)
    pagination = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        'users': [u.to_dict() for u in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    }
```

- [x] **Step 6: 執行測試確認全部通過**

```bash
pytest tests/test_pagination.py -v
```

Expected: 全部 `PASSED`

- [x] **Step 7: 執行完整測試套件，確認整個專案沒有回歸**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [x] **Step 8: Commit**

```bash
git add app/services/product_service.py app/services/order_service.py app/services/user_service.py \
        tests/test_pagination.py
git commit -m "feat: cap per_page at 100 across products, orders, and users pagination"
```

---

## 完成後新增/修改的檔案總覽

```
requirements.txt                        (+pytest)
config.py                               (+TestingConfig)
pytest.ini                              (new)
tests/
├── __init__.py                         (new)
├── conftest.py                         (new)
├── test_smoke.py                       (new)
├── test_auth.py                        (new)
├── test_products.py                    (new)
├── test_orders.py                      (new)
├── test_users.py                       (new)
├── test_inventory.py                   (new)
├── test_order_cancel.py                (new)
└── test_pagination.py                  (new)
app/
├── utils/
│   └── pagination.py                   (new: clamp_per_page, MAX_PER_PAGE)
├── blueprints/
│   ├── products/
│   │   ├── schemas.py                  (+InventoryAdjustSchema)
│   │   └── routes.py                   (+GET/POST inventory-logs, 移除死 import)
│   └── orders/
│       └── routes.py                   (update_order_status 傳入 user_id)
└── services/
    ├── product_service.py              (+get_inventory_logs, +adjust_inventory, per_page clamp)
    ├── order_service.py                (update_order_status 權限與回補邏輯, per_page clamp)
    └── user_service.py                 (per_page clamp)
```
