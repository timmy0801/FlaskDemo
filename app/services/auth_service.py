from flask_jwt_extended import create_access_token

from app import db
from app.models.user import User
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
    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={'role': user.role}
    )
    return {'access_token': access_token, 'user': user.to_dict()}
