from flask import request, jsonify
from flask_jwt_extended import get_jwt

from app.blueprints.users import users_bp
from app.blueprints.users.schemas import UpdateUserSchema
from app.utils.decorators import admin_required, validate_body, owner_or_admin_required
from app.services import user_service


@users_bp.route('', methods=['GET'])
@admin_required
def get_users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    return jsonify(user_service.get_users(page, per_page))


@users_bp.route('/<int:user_id>', methods=['GET'])
@owner_or_admin_required
def get_user(user_id):
    return jsonify(user_service.get_user(user_id))


@users_bp.route('/<int:user_id>', methods=['PUT'])
@owner_or_admin_required
@validate_body(UpdateUserSchema)
def update_user(user_id, validated_data):
    claims = get_jwt()
    return jsonify({
        'message': '用戶資訊更新成功',
        'user': user_service.update_user(user_id, validated_data, claims)
    })


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@admin_required
def deactivate_user(user_id):
    user_service.deactivate_user(user_id)
    return jsonify({'message': '用戶帳號已停用'})
