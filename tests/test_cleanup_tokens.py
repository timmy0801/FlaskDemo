from datetime import datetime, timedelta, timezone
from click.testing import CliRunner


def test_cleanup_deletes_expired_tokens(app, db):
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

    user = User(username="cleanupuser", email="cleanup@test.com", role="user")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    # 已過期的 token
    expired = RefreshToken(
        jti="expired-jti",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    # 未過期的 token
    active = RefreshToken(
        jti="active-jti",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=29),
    )
    db.session.add_all([expired, active])
    db.session.commit()

    runner = CliRunner()
    result = runner.invoke(app.cli, ["cleanup-tokens"])
    assert result.exit_code == 0
    assert "1" in result.output  # 刪除了 1 筆

    assert RefreshToken.query.filter_by(jti="expired-jti").first() is None
    assert RefreshToken.query.filter_by(jti="active-jti").first() is not None


def test_cleanup_dry_run_does_not_delete(app, db):
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

    user = User(username="dryrunuser", email="dryrun@test.com", role="user")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    expired = RefreshToken(
        jti="dryrun-jti",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.session.add(expired)
    db.session.commit()

    runner = CliRunner()
    result = runner.invoke(app.cli, ["cleanup-tokens", "--dry-run"])
    assert result.exit_code == 0

    assert RefreshToken.query.filter_by(jti="dryrun-jti").first() is not None
