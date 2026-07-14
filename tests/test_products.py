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
