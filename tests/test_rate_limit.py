def test_login_rate_limited_after_5_attempts_same_email(client, db):
    from app.models.user import User

    user = User(username='ratelimituser', email='ratelimit@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    for _ in range(5):
        resp = client.post(
            '/api/auth/login',
            json={'email': 'ratelimit@test.com', 'password': 'wrongpassword'},
        )
        assert resp.status_code == 401

    resp = client.post(
        '/api/auth/login',
        json={'email': 'ratelimit@test.com', 'password': 'wrongpassword'},
    )
    assert resp.status_code == 429
    assert resp.get_json() == {'error': '請求過於頻繁，請稍後再試'}


def test_login_rate_limit_is_per_email_not_just_per_ip(client, db):
    from app.models.user import User

    for email in ('user_a@test.com', 'user_b@test.com'):
        user = User(username=email.split('@')[0], email=email, role='user')
        user.set_password('password123')
        db.session.add(user)
    db.session.commit()

    for _ in range(5):
        client.post(
            '/api/auth/login',
            json={'email': 'user_a@test.com', 'password': 'wrongpassword'},
        )

    blocked_resp = client.post(
        '/api/auth/login',
        json={'email': 'user_a@test.com', 'password': 'wrongpassword'},
    )
    assert blocked_resp.status_code == 429

    other_email_resp = client.post(
        '/api/auth/login',
        json={'email': 'user_b@test.com', 'password': 'password123'},
    )
    assert other_email_resp.status_code == 200


def test_register_rate_limited_after_5_attempts_same_ip(client):
    for i in range(5):
        resp = client.post(
            '/api/auth/register',
            json={
                'username': f'rluser{i}',
                'email': f'rluser{i}@test.com',
                'password': 'password123',
            },
        )
        assert resp.status_code == 201

    resp = client.post(
        '/api/auth/register',
        json={
            'username': 'rluser5',
            'email': 'rluser5@test.com',
            'password': 'password123',
        },
    )
    assert resp.status_code == 429
    assert resp.get_json() == {'error': '請求過於頻繁，請稍後再試'}
