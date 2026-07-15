from app.models.product import Product


def _create_product(db, name="商品", price=100, stock=10):
    product = Product(name=name, price=price, stock=stock, is_active=True)
    db.session.add(product)
    db.session.commit()
    return product


def _create_order(client, token, auth_header, product, quantity=2):
    resp = client.post(
        "/api/orders",
        json={"items": [{"product_id": product.id, "quantity": quantity}]},
        headers=auth_header(token),
    )
    return resp.json["order"]["id"]


def test_user_can_cancel_own_pending_order(
    client, db, normal_user_and_token, auth_header
):
    _, token = normal_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, token, auth_header, product, quantity=3)
    db.session.refresh(product)
    assert product.stock == 7

    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(token),
    )
    assert resp.status_code == 200
    assert resp.json["order"]["status"] == "cancelled"
    db.session.refresh(product)
    assert product.stock == 10


def test_user_cannot_cancel_others_order(
    client, db, normal_user_and_token, admin_user_and_token, auth_header
):
    _, user_token = normal_user_and_token
    _, admin_token = admin_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, admin_token, auth_header, product)
    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 403


def test_user_cannot_set_non_cancelled_status(
    client, db, normal_user_and_token, auth_header
):
    _, token = normal_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, token, auth_header, product)

    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "shipped"},
        headers=auth_header(token),
    )
    assert resp.status_code == 403


def test_user_cannot_cancel_non_pending_order(
    client, db, admin_user_and_token, normal_user_and_token, auth_header
):
    admin_user, admin_token = admin_user_and_token
    user, user_token = normal_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, user_token, auth_header, product)

    client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "paid"},
        headers=auth_header(admin_token),
    )

    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 400


def test_admin_cancelling_order_also_restocks(
    client, db, admin_user_and_token, auth_header
):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)
    order_id = _create_order(client, token, auth_header, product, quantity=4)

    db.session.refresh(product)
    assert product.stock == 6

    resp = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers=auth_header(token),
    )
    assert resp.status_code == 200

    db.session.refresh(product)
    assert product.stock == 10
