from flask import jsonify
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_refresh_cookies,
)

from app.models.user import User
from app.blueprints.auth import auth_bp
from app.blueprints.auth.schemas import RegisterSchema, LoginSchema
from app.services import auth_service
from app.utils.decorators import validate_body


@auth_bp.route('/register', methods=['POST'])
@validate_body(RegisterSchema)
def register(validated_data):
    user = auth_service.register(validated_data)
    return jsonify({'message': '註冊成功', 'user': user}), 201


@auth_bp.route('/login', methods=['POST'])
@validate_body(LoginSchema)
def login(validated_data):
    result = auth_service.login(validated_data)
    response = jsonify({
        'message': '登入成功',
        'access_token': result['access_token'],
        'user': result['user'],
    })
    set_refresh_cookies(response, result['refresh_token'])
    return response


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    user_id = int(get_jwt_identity())
    jti = get_jwt()['jti']
    result = auth_service.refresh(user_id, jti)
    response = jsonify({'access_token': result['access_token']})
    set_refresh_cookies(response, result['refresh_token'])
    return response
