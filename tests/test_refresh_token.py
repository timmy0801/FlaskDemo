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
