def test_create_product_requires_admin(client, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    resp = client.post(
        "/api/products",
        json={
            "name": "測試商品",
            "price": 100,
        },
        headers=auth_header(token),
    )
    assert resp.status_code == 403


def test_admin_can_create_product(client, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    resp = client.post(
        "/api/products",
        json={
            "name": "測試商品",
            "price": 100,
            "stock": 10,
        },
        headers=auth_header(token),
    )
    assert resp.status_code == 201
    data = resp.get_json()["product"]
    assert data["name"] == "測試商品"
    assert data["stock"] == 10


def test_get_product_404_for_missing_id(client):
    resp = client.get("/api/products/999")
    assert resp.status_code == 404


def test_soft_deleted_product_excluded_from_list(
    client, admin_user_and_token, auth_header
):
    _, token = admin_user_and_token
    # Create a product
    resp = client.post(
        "/api/products",
        json={
            "name": "下架商品",
            "price": 50,
            "stock": 10,
        },
        headers=auth_header(token),
    )
    product_id = resp.get_json()["product"]["id"]

    # Delete the product
    delete_resp = client.delete(
        f"/api/products/{product_id}", headers=auth_header(token)
    )
    assert delete_resp.status_code == 204
    # Check that the product is not in the list
    list_resp = client.get("/api/products")
    ids = [p["id"] for p in list_resp.get_json()["products"]]
    assert product_id not in ids


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
