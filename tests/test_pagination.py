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
        db.session.add(Product(name=f"商品{i}", price=10.0, stock=1, is_active=True))
    db.session.commit()

    resp = client.get(f"/api/products?per_page={MAX_PER_PAGE + 50}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["products"]) == MAX_PER_PAGE
    assert body["total"] == MAX_PER_PAGE + 20


def test_user_list_per_page_is_capped(client, admin_user_and_token, auth_header, db):
    from app.models.user import User

    for i in range(MAX_PER_PAGE + 5):
        u = User(username=f"user{i}", email=f"user{i}@test.com", role="user")
        u.set_password("password123")
        db.session.add(u)
    db.session.commit()

    _, token = admin_user_and_token
    resp = client.get(
        f"/api/users?per_page={MAX_PER_PAGE + 50}", headers=auth_header(token)
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["users"]) == MAX_PER_PAGE
