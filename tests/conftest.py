import pytest

from app import create_app, db as _db
from app.models.user import User


@pytest.fixture
def app():
    flask_app = create_app("testing")
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
        return {"Authorization": f"Bearer {token}"}

    return _make


def _create_user_and_login(client, db, email, password, role):
    user = User(username=email.split("@")[0], email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    token = resp.get_json()["access_token"]
    return user, token


@pytest.fixture
def admin_user_and_token(client, db):
    return _create_user_and_login(client, db, "admin@test.com", "admin1234", "admin")


@pytest.fixture
def normal_user_and_token(client, db):
    return _create_user_and_login(client, db, "user@test.com", "user12345", "user")


@pytest.fixture
def csrf_header():
    def _make(client):
        cookie = client.get_cookie("csrf_refresh_token", path="/api/auth")
        return {"X-CSRF-TOKEN": cookie.value} if cookie else {}
    return _make
