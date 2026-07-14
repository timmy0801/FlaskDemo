def test_get_products_returns_empty_list(client):
    resp = client.get("/api/products")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["products"] == []
    assert data["total"] == 0


def test_admin_fixture_can_login(client, admin_user_and_token):
    user, token = admin_user_and_token
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "admin"
