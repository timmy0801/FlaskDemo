from functools import wraps
from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from marshmallow import ValidationError

def admin_required(fn):
    """限制只有 admin 角色可存取的裝飾器"""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt()
        if claims.get('role') != 'admin':
            return jsonify({'error': '權限不足，需要 admin 身分'}), 403
        return fn(*args, **kwargs)

    return wrapper


def validate_body(schema_class):
    """驗證JSON request body, 通過後以validated_data關鍵字參數傳入route"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args,**kwargs):
            data = request.get_json()
            schema = schema_class()
            try:
                validated = schema.load(data or {})
            except ValidationError as e:
                return jsonify({'errors': e.messages}), 400
            kwargs['validated_data'] = validated
            return fn(*args,**kwargs)
        return wrapper
    return decorator


def owner_or_admin_required(fn):
    """限制只有本人或 admin 可存取，適用於 URL 含 user_id 的 route"""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        current_user_id = int(get_jwt_identity())
        claims = get_jwt()
        url_user_id = kwargs.get('user_id')
        if claims.get('role') != 'admin' and url_user_id != current_user_id:
            return jsonify({'error': '無權限'}), 403
        return fn(*args, **kwargs)
    return wrapper