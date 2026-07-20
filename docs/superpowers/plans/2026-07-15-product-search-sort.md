# 商品搜尋與排序 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 `GET /api/products` 加上關鍵字搜尋（比對商品名稱）與排序（價格、上架時間，各支援 asc/desc），沿用既有的寬鬆 query string 風格（無效值 fallback 到預設，不回 400）。

**Architecture:** Route 從 query string 讀取 `q`、`sort_by`、`order` 三個新參數，原封不動傳給 Service；Service 負責組出對應的 SQLAlchemy filter/order_by。設計依據：[docs/superpowers/specs/2026-07-15-product-search-sort-design.md](../specs/2026-07-15-product-search-sort-design.md)。

**Tech Stack:** Python 3, Flask 3, SQLAlchemy, pytest

**前置修正：** 開發過程中發現 `app/models/product.py` 的 `created_at`／`updated_at` 欄位用 `default=datetime.now(timezone.utc)`（沒有包成 lambda），這個寫法在 SQLAlchemy 裡會在「模組被 import 時」只算一次，之後所有 Product 都會拿到同一個固定時間戳，而不是「每次新增資料時」各自算一次。這會讓「依上架時間排序」這個功能失去意義（所有商品的 `created_at` 幾乎都相同）。這個 bug 直接擋到本次要做的排序功能，所以 Task 1 先修這個，Task 2 才做搜尋/排序本身。（註：`order.py`、`user.py` 也有同樣的寫法問題，但不影響本次功能，這次不動，之後有需要再處理。）

---

## Task 1: 修正 `Product.created_at`／`updated_at` 預設值改為每筆各自產生

**Files:**
- Modify: `app/models/product.py`
- Test: `tests/test_products.py`

- [x] **Step 1: 撰寫會失敗的測試**

在 `tests/test_products.py` 最後新增：

```python
def test_product_created_at_is_set_per_instance(db):
    import time
    from app.models.product import Product

    p1 = Product(name='A', price=10, stock=1)
    db.session.add(p1)
    db.session.commit()

    time.sleep(0.01)

    p2 = Product(name='B', price=10, stock=1)
    db.session.add(p2)
    db.session.commit()

    assert p1.created_at != p2.created_at
```

- [x] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_products.py::test_product_created_at_is_set_per_instance -v
```

Expected: `FAILED`，`p1.created_at == p2.created_at`（兩筆資料拿到同一個固定時間戳）

- [x] **Step 3: 修正 `app/models/product.py`**

把第 17-18 行：

```python
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
```

改為：

```python
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

- [x] **Step 4: 執行測試確認通過**

```bash
pytest tests/test_products.py::test_product_created_at_is_set_per_instance -v
```

Expected: `PASSED`

- [x] **Step 5: 執行完整測試套件，確認沒有破壞既有功能**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [x] **Step 6: Commit**

```bash
git add app/models/product.py tests/test_products.py
git commit -m "fix: evaluate Product.created_at/updated_at default per-row instead of at import time"
```

---

## Task 2: 商品搜尋與排序

**Files:**
- Modify: `app/services/product_service.py`
- Modify: `app/blueprints/products/routes.py`
- Test: `tests/test_products.py`

- [x] **Step 1: 撰寫會失敗的測試**

在 `tests/test_products.py` 最後新增：

```python
def test_search_by_keyword_matches_product_name(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    client.post('/api/products', json={'name': '木製椅子', 'price': 100}, headers=auth_header(token))
    client.post('/api/products', json={'name': '藍牙耳機', 'price': 200}, headers=auth_header(token))

    resp = client.get('/api/products?q=椅子')
    assert resp.status_code == 200
    names = [p['name'] for p in resp.get_json()['products']]
    assert names == ['木製椅子']


def test_search_by_keyword_no_match_returns_empty(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    client.post('/api/products', json={'name': '木製椅子', 'price': 100}, headers=auth_header(token))

    resp = client.get('/api/products?q=不存在的關鍵字xyz')
    assert resp.status_code == 200
    assert resp.get_json()['products'] == []


def test_sort_by_price_ascending(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    client.post('/api/products', json={'name': '商品貴', 'price': 300}, headers=auth_header(token))
    client.post('/api/products', json={'name': '商品便宜', 'price': 50}, headers=auth_header(token))
    client.post('/api/products', json={'name': '商品中等', 'price': 150}, headers=auth_header(token))

    resp = client.get('/api/products?sort_by=price&order=asc')
    prices = [p['price'] for p in resp.get_json()['products']]
    assert prices == sorted(prices)


def test_sort_by_price_descending(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    client.post('/api/products', json={'name': '商品貴', 'price': 300}, headers=auth_header(token))
    client.post('/api/products', json={'name': '商品便宜', 'price': 50}, headers=auth_header(token))
    client.post('/api/products', json={'name': '商品中等', 'price': 150}, headers=auth_header(token))

    resp = client.get('/api/products?sort_by=price&order=desc')
    prices = [p['price'] for p in resp.get_json()['products']]
    assert prices == sorted(prices, reverse=True)


def test_sort_by_created_at_ascending_returns_oldest_first(client, admin_user_and_token, auth_header):
    import time
    _, token = admin_user_and_token
    client.post('/api/products', json={'name': '先建立', 'price': 10}, headers=auth_header(token))
    time.sleep(0.01)
    client.post('/api/products', json={'name': '後建立', 'price': 10}, headers=auth_header(token))

    resp = client.get('/api/products?sort_by=created_at&order=asc')
    names = [p['name'] for p in resp.get_json()['products']]
    assert names == ['先建立', '後建立']


def test_default_sort_is_newest_first(client, admin_user_and_token, auth_header):
    import time
    _, token = admin_user_and_token
    client.post('/api/products', json={'name': '先建立', 'price': 10}, headers=auth_header(token))
    time.sleep(0.01)
    client.post('/api/products', json={'name': '後建立', 'price': 10}, headers=auth_header(token))

    resp = client.get('/api/products')
    names = [p['name'] for p in resp.get_json()['products']]
    assert names == ['後建立', '先建立']


def test_invalid_sort_params_fallback_to_default_instead_of_400(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    client.post('/api/products', json={'name': '商品', 'price': 10}, headers=auth_header(token))

    resp = client.get('/api/products?sort_by=not_a_field&order=sideways')
    assert resp.status_code == 200


def test_search_and_category_filter_combine(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    client.post('/api/products', json={'name': '木製椅子', 'price': 100, 'category': '家居用品'},
                headers=auth_header(token))
    client.post('/api/products', json={'name': '塑膠椅子', 'price': 80, 'category': '運動休閒'},
                headers=auth_header(token))

    resp = client.get('/api/products?q=椅子&category=家居用品')
    names = [p['name'] for p in resp.get_json()['products']]
    assert names == ['木製椅子']
```

- [x] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_products.py -v -k "search_by_keyword or sort_by or default_sort or invalid_sort or search_and_category"
```

Expected: 全部 `FAILED` 或斷言不符（目前 `get_products` 不接受 `q`/`sort_by`/`order` 參數，route 也還沒讀取）

- [x] **Step 3: 更新 `app/services/product_service.py`**

把檔案開頭到 `get_products` 定義前的部分改為：

```python
from app import db
from app.models.product import Product
from app.models.inventory_log import InventoryLog
from app.utils.pagination import clamp_per_page
from app.utils.exceptions import BadRequestError

SORTABLE_FIELDS = {
    'price': Product.price,
    'created_at': Product.created_at,
}
```

把 `get_products` 函式改為：

```python
def get_products(page, per_page, category, q=None, sort_by=None, order=None):
    per_page = clamp_per_page(per_page)
    query = Product.query.filter_by(is_active=True)

    if category:
        query = query.filter_by(category=category)

    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))

    column = SORTABLE_FIELDS.get(sort_by, Product.created_at)
    query = query.order_by(column.asc() if order == 'asc' else column.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        'products': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    }
```

- [x] **Step 4: 更新 `app/blueprints/products/routes.py`**

把 `get_products` route 改為：

```python
@products_bp.route("", methods=["GET"])
def get_products():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    category = request.args.get("category")
    q = request.args.get("q")
    sort_by = request.args.get("sort_by")
    order = request.args.get("order")

    return jsonify(product_service.get_products(page, per_page, category, q, sort_by, order))
```

- [x] **Step 5: 執行測試確認全部通過**

```bash
pytest tests/test_products.py -v
```

Expected: 全部 `PASSED`

- [x] **Step 6: 執行完整測試套件，確認沒有破壞既有功能**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [x] **Step 7: Commit**

```bash
git add app/services/product_service.py app/blueprints/products/routes.py tests/test_products.py
git commit -m "feat: add keyword search and price/created_at sorting to product listing"
```

---

## 完成後的變更總覽

```
app/
├── models/
│   └── product.py            (修正 created_at/updated_at 預設值為每筆各自產生)
├── services/
│   └── product_service.py    (+SORTABLE_FIELDS, get_products 新增 q/sort_by/order 參數)
└── blueprints/
    └── products/
        └── routes.py         (get_products route 讀取 q/sort_by/order query string)
tests/
└── test_products.py          (+9 個新測試)
```
