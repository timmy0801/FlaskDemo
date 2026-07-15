from datetime import datetime, timezone

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token, get_jti

from app import db
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.utils.exceptions import ConflictError, UnauthorizedError, ForbiddenError


def register(data):
    if User.query.filter_by(email=data['email']).first():
        raise ConflictError('此 Email 已被註冊')
    if User.query.filter_by(username=data['username']).first():
        raise ConflictError('此使用者名稱已被使用')

    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return user.to_dict()


def login(data):
    user = User.query.filter_by(email=data['email']).first()
    if not user or not user.check_password(data['password']):
        raise UnauthorizedError('Email 或密碼錯誤')
    if not user.is_active:
        raise ForbiddenError('帳號已被停用')

    access_token = create_access_token(identity=str(user.id), additional_claims={'role': user.role})
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={'role': user.role})
    _store_refresh_token(refresh_token, user.id)

    return {'access_token': access_token, 'refresh_token': refresh_token, 'user': user.to_dict()}


def _store_refresh_token(raw_token, user_id):
    expires_at = datetime.now(timezone.utc) + current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
    db.session.add(RefreshToken(
        jti=get_jti(raw_token),
        user_id=user_id,
        expires_at=expires_at,
    ))
    db.session.commit()
