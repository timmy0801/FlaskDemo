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


def test_refresh_returns_new_access_token(client, db, csrf_header):
    from app.models.user import User

    user = User(username='refreshuser', email='refresh@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'refresh@test.com', 'password': 'password123'})

    resp = client.post('/api/auth/refresh', headers=csrf_header(client))
    assert resp.status_code == 200
    assert 'access_token' in resp.get_json()


def test_refresh_without_csrf_header_returns_401(client, db):
    from app.models.user import User

    user = User(username='nocsrfuser', email='nocsrf@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'nocsrf@test.com', 'password': 'password123'})

    resp = client.post('/api/auth/refresh')
    assert resp.status_code == 401


def test_refresh_without_cookie_returns_401(client):
    resp = client.post('/api/auth/refresh')
    assert resp.status_code == 401


def test_reused_refresh_token_revokes_all_sessions(client, db):
    from app.models.user import User
    from app.models.refresh_token import RefreshToken

    user = User(username='reuseuser', email='reuse@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'reuse@test.com', 'password': 'password123'})
    old_refresh_cookie = client.get_cookie('refresh_token_cookie', path='/api/auth')
    old_csrf_cookie = client.get_cookie('csrf_refresh_token', path='/')
    first_headers = {'X-CSRF-TOKEN': old_csrf_cookie.value}

    first_resp = client.post('/api/auth/refresh', headers=first_headers)
    assert first_resp.status_code == 200

    # 把 cookie jar 改回「舊的」refresh token，模擬 token 被偷後重複使用
    client.set_cookie('refresh_token_cookie', old_refresh_cookie.value, path='/api/auth')
    client.set_cookie('csrf_refresh_token', old_csrf_cookie.value, path='/')

    reused_resp = client.post('/api/auth/refresh', headers=first_headers)
    assert reused_resp.status_code == 401

    tokens = RefreshToken.query.filter_by(user_id=user.id).all()
    assert all(t.revoked_at is not None for t in tokens)


def test_refresh_rejected_for_deactivated_user(client, db, csrf_header):
    from app.models.user import User

    user = User(username='deactivateduser', email='deactivated@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'deactivated@test.com', 'password': 'password123'})

    user.is_active = False
    db.session.commit()

    resp = client.post('/api/auth/refresh', headers=csrf_header(client))
    assert resp.status_code == 403


def test_logout_revokes_token_and_clears_cookie(client, db, csrf_header):
    from app.models.user import User
    from app.models.refresh_token import RefreshToken

    user = User(username='logoutuser', email='logout@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'logout@test.com', 'password': 'password123'})

    resp = client.post('/api/auth/logout', headers=csrf_header(client))
    assert resp.status_code == 200

    tokens = RefreshToken.query.filter_by(user_id=user.id).all()
    assert all(t.revoked_at is not None for t in tokens)
    assert client.get_cookie('refresh_token_cookie', path='/api/auth') is None


def test_refresh_after_logout_returns_401(client, db, csrf_header):
    from app.models.user import User

    user = User(username='postlogoutuser', email='postlogout@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'postlogout@test.com', 'password': 'password123'})
    headers = csrf_header(client)
    client.post('/api/auth/logout', headers=headers)

    resp = client.post('/api/auth/refresh', headers=headers)
    assert resp.status_code == 401
