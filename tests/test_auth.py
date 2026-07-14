def test_register_success(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "testnewuser",
            "email": "testnewuser@test.com",
            "password": "password1112",
        },
    )
    assert resp.status_code == 201
    assert resp.get_json()["user"]["email"] == "testnewuser@test.com"


def test_register_duplicate_email_returns_409(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "duplicate",
            "email": "dup@test.com",
            "password": "password1112",
        },
    )
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "duplicate2",
            "email": "dup@test.com",
            "password": "password1112",
        },
    )
    assert resp.status_code == 409


def test_login_with_wrong_password_returns_401(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "loginuser",
            "email": "login@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/auth/login", json={"email": "login@test.com", "password": "wrongpassword"}
    )
    assert resp.status_code == 401


def test_login_inactive_user_returns_403(client, db):
    from app.models.user import User

    user = User(
        username="inactive",
        email="inactive@test.com",
        role="user",
        is_active=False,
    )
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    resp = client.post(
        "/api/auth/login",
        json={"email": "inactive@test.com", "password": "password123"},
    )
    assert resp.status_code == 403


def test_me_requires_jwt(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
