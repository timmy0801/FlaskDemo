from datetime import datetime, timezone
from app import db


class RefreshToken(db.Model):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        db.Index("ix_refresh_tokens_user_revoked", "user_id", "revoked_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
