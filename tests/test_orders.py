from app.models.product import Product


def _create_product(db, name="商品", price=100.0, stock=10):
    product = Product(name=name, price=price, stock=stock, is_active=True)
    db.session.add(product)
    db.session.commit()
    return product


def test_create_order_deducts_stock(client, db, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    product = _create_product(db, stock=10)
    resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 3}]},
        headers=auth_header(token),
    )
    assert resp.status_code == 201
    db.session.refresh(product)
    assert product.stock == 7


def test_create_order_insufficient_stock_returns_400(
    client, db, normal_user_and_token, auth_header
):
    _, token = normal_user_and_token
    product = _create_product(db, stock=1)
    resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 5}]},
        headers=auth_header(token),
    )
    assert resp.status_code == 400


def test_user_cannot_view_others_order(
    client, db, normal_user_and_token, admin_user_and_token, auth_header
):
    _, user_token = normal_user_and_token
    _, admin_token = admin_user_and_token
    product = _create_product(db, stock=10)
    # User creates an order
    order_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 1}]},
        headers=auth_header(admin_token),
    )
    order_id = order_resp.get_json()["order"]["id"]
    # Admin tries to view the user's order
    resp = client.get(f"/api/orders/{order_id}", headers=auth_header(user_token))
    assert resp.status_code == 403


def test_admin_can_update_order_status(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)

    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 1}]},
        headers=auth_header(token),
    )
    order_id = create_resp.get_json()["order"]["id"]

    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "paid"},
        headers=auth_header(token),
    )
    assert resp.status_code == 200
    assert resp.get_json()["order"]["status"] == "paid"


def test_order_created_at_is_set_per_instance(db, normal_user_and_token):
    import time
    from app.models.order import Order

    user, _ = normal_user_and_token

    o1 = Order(user_id=user.id)
    db.session.add(o1)
    db.session.commit()

    time.sleep(0.01)

    o2 = Order(user_id=user.id)
    db.session.add(o2)
    db.session.commit()

    assert o1.created_at != o2.created_at


def test_cancelled_order_cannot_be_changed_to_pending(
    client, db, admin_user_and_token, auth_header
):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)

    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 1}]},
        headers=auth_header(token),
    )
    order_id = create_resp.get_json()["order"]["id"]

    # update order status to cancelled
    cancel_resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(token),
    )

    # Try to change the status back to pending
    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "pending"},
        headers=auth_header(token),
    )
    assert resp.status_code == 400


def test_pending_cannot_skip_to_shipped(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)

    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 1}]},
        headers=auth_header(token),
    )
    order_id = create_resp.get_json()["order"]["id"]

    # Try to change the status directly to shipped
    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "shipped"},
        headers=auth_header(token),
    )
    assert resp.status_code == 400


def test_delivered_cannot_be_cancelled(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)
    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 1}]},
        headers=auth_header(token),
    )
    order_id = create_resp.get_json()["order"]["id"]

    for status in ("paid", "shipped", "delivered"):
        client.patch(
            f"/api/orders/{order_id}/status",
            json={"status": status},
            headers=auth_header(token),
        )

    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(token),
    )
    assert resp.status_code == 400


def test_same_status_is_idempotent(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)
    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 1}]},
        headers=auth_header(token),
    )
    order_id = create_resp.get_json()["order"]["id"]

    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "pending"},
        headers=auth_header(token),
    )
    assert resp.status_code == 200


def test_double_cancel_does_not_restock_twice(
    client, db, admin_user_and_token, auth_header
):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)
    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 3}]},
        headers=auth_header(token),
    )
    order_id = create_resp.get_json()["order"]["id"]

    client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(token),
    )
    db.session.refresh(product)
    stock_after_first_cancel = product.stock

    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(token),
    )
    assert resp.status_code == 200
    db.session.refresh(product)
    assert product.stock == stock_after_first_cancel  # 沒有再回補


def test_full_order_lifecycle(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)
    create_resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": 1}]},
        headers=auth_header(token),
    )
    order_id = create_resp.get_json()["order"]["id"]

    for status in ("paid", "shipped", "delivered"):
        resp = client.patch(
            f"/api/orders/{order_id}/status",
            json={"status": status},
            headers=auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.get_json()["order"]["status"] == status
