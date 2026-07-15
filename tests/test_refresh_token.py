from datetime import datetime, timedelta, timezone


def test_refresh_token_model_can_be_created(db):
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

    user = User(username='rtuser', email='rtuser@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    token = RefreshToken(
        jti='test-jti-123',
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.session.add(token)
    db.session.commit()

    saved = RefreshToken.query.filter_by(jti='test-jti-123').first()
    assert saved is not None
    assert saved.revoked_at is None


def test_login_sets_refresh_cookie_and_stores_token(client, db):
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

    user = User(username='cookieuser', email='cookieuser@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    resp = client.post('/api/auth/login', json={'email': 'cookieuser@test.com', 'password': 'password123'})
    assert resp.status_code == 200
    assert 'refresh_token_cookie' in resp.headers.get('Set-Cookie', '')

    tokens = RefreshToken.query.filter_by(user_id=user.id).all()
    assert len(tokens) == 1
    assert tokens[0].revoked_at is None


def test_login_response_does_not_leak_refresh_token_in_json(client, db):
    from app.models.user import User

    user = User(username='noleakuser', email='noleak@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    resp = client.post('/api/auth/login', json={'email': 'noleak@test.com', 'password': 'password123'})
    assert 'refresh_token' not in resp.get_json()
