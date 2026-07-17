from flask import request, jsonify
from flask_jwt_extended import get_jwt

from app.blueprints.users import users_bp
from app.blueprints.users.schemas import UpdateUserSchema
from app.utils.decorators import admin_required, validate_body, owner_or_admin_required
from app.services import user_service


@users_bp.route('', methods=['GET'])
@admin_required
def get_users():
    """
    ---
    get:
      summary: 取得所有會員
      tags: [Users]
      security:
        - bearerAuth: []
      parameters:
        - in: query
          name: page
          schema: {type: integer, default: 1}
        - in: query
          name: per_page
          schema: {type: integer, default: 20}
          description: 上限 100
      responses:
        200:
          description: 會員列表
          content:
            application/json:
              schema: UserListResponseSchema
        403:
          description: 權限不足，需要 admin 身分
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    return jsonify(user_service.get_users(page, per_page))


@users_bp.route('/<int:user_id>', methods=['GET'])
@owner_or_admin_required
def get_user(user_id):
    """
    ---
    get:
      summary: 取得單一會員
      tags: [Users]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: user_id
          required: true
          schema: {type: integer}
      responses:
        200:
          description: 會員資訊
          content:
            application/json:
              schema: UserResponseSchema
        403:
          description: 無權限（非本人也非 admin）
        404:
          description: 會員不存在
    """
    return jsonify(user_service.get_user(user_id))


@users_bp.route('/<int:user_id>', methods=['PUT'])
@owner_or_admin_required
@validate_body(UpdateUserSchema)
def update_user(user_id, validated_data):
    """
    ---
    put:
      summary: 更新會員資訊
      tags: [Users]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: user_id
          required: true
          schema: {type: integer}
      requestBody:
        required: true
        content:
          application/json:
            schema: UpdateUserSchema
      responses:
        200:
          description: 用戶資訊更新成功
          content:
            application/json:
              schema: UpdateUserResponseSchema
        400:
          description: 請求格式錯誤
        403:
          description: 無權限（非本人也非 admin）
        404:
          description: 會員不存在
        409:
          description: 使用者名稱已被使用
    """
    claims = get_jwt()
    return jsonify({
        'message': '用戶資訊更新成功',
        'user': user_service.update_user(user_id, validated_data, claims)
    })


@users_bp.route('/<int:user_id>', methods=['DELETE'])
@admin_required
def deactivate_user(user_id):
    """
    ---
    delete:
      summary: 停用帳號
      tags: [Users]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: user_id
          required: true
          schema: {type: integer}
      responses:
        200:
          description: 用戶帳號已停用
        403:
          description: 權限不足，需要 admin 身分
        404:
          description: 會員不存在
    """
    user_service.deactivate_user(user_id)
    return jsonify({'message': '用戶帳號已停用'})
