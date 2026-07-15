from app.models.product import Product
from app.models.inventory_log import InventoryLog


def _create_product(db, name="商品", price=100.0, stock=10):
    product = Product(name=name, price=price, stock=stock, is_active=True)
    db.session.add(product)
    db.session.commit()
    return product


def test_restock_requires_admin(client, db, normal_user_and_token, auth_header):
    _, token = normal_user_and_token
    product = _create_product(db, stock=5)

    resp = client.post(
        f"/api/products/{product.id}/inventory-logs",
        json={"action": "restock", "quantity_change": 10},
        headers=auth_header(token),
    )
    assert resp.status_code == 403


def test_admin_can_restock_product(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=5)

    resp = client.post(
        f"/api/products/{product.id}/inventory-logs",
        json={"action": "restock", "quantity_change": 20, "note": "廠商補貨"},
        headers=auth_header(token),
    )
    assert resp.status_code == 201
    log = resp.get_json()["inventory_log"]
    assert log["quantity_before"] == 5
    assert log["quantity_after"] == 25
    assert log["action"] == "restock"

    db.session.refresh(product)
    assert product.stock == 25


def test_restock_with_non_positive_quantity_returns_400(
    client, db, admin_user_and_token, auth_header
):
    _, token = admin_user_and_token
    product = _create_product(db, stock=5)

    resp = client.post(
        f"/api/products/{product.id}/inventory-logs",
        json={"action": "restock", "quantity_change": -1},
        headers=auth_header(token),
    )
    assert resp.status_code == 400


def test_admin_can_adjust_product_down(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)

    resp = client.post(
        f"/api/products/{product.id}/inventory-logs",
        json={"action": "adjust", "quantity_change": -3, "note": "盤點損耗"},
        headers=auth_header(token),
    )
    assert resp.status_code == 201
    assert resp.get_json()["inventory_log"]["quantity_after"] == 7

    db.session.refresh(product)
    assert product.stock == 7


def test_adjust_below_zero_returns_400(client, db, admin_user_and_token, auth_header):
    _, token = admin_user_and_token
    product = _create_product(db, stock=2)

    resp = client.post(
        f"/api/products/{product.id}/inventory-logs",
        json={"action": "adjust", "quantity_change": -5},
        headers=auth_header(token),
    )
    assert resp.status_code == 400


def test_get_inventory_logs_returns_history(
    client, db, admin_user_and_token, auth_header
):
    _, token = admin_user_and_token
    product = _create_product(db, stock=10)

    client.post(
        f"/api/products/{product.id}/inventory-logs",
        json={"action": "restock", "quantity_change": 5},
        headers=auth_header(token),
    )

    resp = client.get(
        f"/api/products/{product.id}/inventory-logs", headers=auth_header(token)
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["inventory_logs"][0]["action"] == "restock"
