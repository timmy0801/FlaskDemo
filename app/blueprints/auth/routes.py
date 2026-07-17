from flask import jsonify
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from app.models.user import User
from app.blueprints.auth import auth_bp
from app.blueprints.auth.schemas import RegisterSchema, LoginSchema
from app.services import auth_service
from app.utils.decorators import validate_body


@auth_bp.route('/register', methods=['POST'])
@validate_body(RegisterSchema)
def register(validated_data):
    """
    ---
    post:
      summary: 註冊新帳號
      description: Email 與使用者名稱必須是唯一的，重複註冊會被拒絕。
      tags: [Auth]
      requestBody:
        required: true
        content:
          application/json:
            schema: RegisterSchema
      responses:
        201:
          description: 註冊成功
          content:
            application/json:
              schema: RegisterResponseSchema
        400:
          description: 請求格式錯誤
        409:
          description: Email 或使用者名稱已被使用
    """
    user = auth_service.register(validated_data)
    return jsonify({'message': '註冊成功', 'user': user}), 201


@auth_bp.route('/login', methods=['POST'])
@validate_body(LoginSchema)
def login(validated_data):
    """
    ---
    post:
      summary: 登入取得 access token
      description: 成功登入後，除了 JSON 回應之外，也會用 Set-Cookie 設定一個 httpOnly 的 refresh token cookie。
      tags: [Auth]
      requestBody:
        required: true
        content:
          application/json:
            schema: LoginSchema
      responses:
        200:
          description: 登入成功
          content:
            application/json:
              schema: LoginResponseSchema
        400:
          description: 請求格式錯誤
        401:
          description: Email 或密碼錯誤
        403:
          description: 帳號已被停用
    """
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
    """
    ---
    get:
      summary: 取得當前使用者資訊
      tags: [Auth]
      security:
        - bearerAuth: []
      responses:
        200:
          description: 使用者資訊
          content:
            application/json:
              schema: UserResponseSchema
        401:
          description: 未攜帶或無效的 access token
        404:
          description: 使用者不存在
    """
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    ---
    post:
      summary: 用 refresh token 換發新的 access token
      description: 需要瀏覽器自動帶上 refresh_token_cookie，並額外帶 X-CSRF-TOKEN header（值來自 csrf_refresh_token cookie）。每次呼叫都會 rotate refresh token。
      tags: [Auth]
      security:
        - cookieAuth: []
          csrfHeader: []
      responses:
        200:
          description: 換發成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  access_token:
                    type: string
        401:
          description: refresh token 缺失、無效、或已被撤銷（重複使用已撤銷的 token 會連帶撤銷該使用者所有 session）
        403:
          description: 帳號已被停用
    """
    user_id = int(get_jwt_identity())
    jti = get_jwt()['jti']
    result = auth_service.refresh(user_id, jti)
    response = jsonify({'access_token': result['access_token']})
    set_refresh_cookies(response, result['refresh_token'])
    return response


@auth_bp.route('/logout', methods=['POST'])
@jwt_required(refresh=True)
def logout():
    """
    ---
    post:
      summary: 登出，撤銷目前的 refresh token
      description: 需要瀏覽器自動帶上 refresh_token_cookie，並額外帶 X-CSRF-TOKEN header。
      tags: [Auth]
      security:
        - cookieAuth: []
          csrfHeader: []
      responses:
        200:
          description: 登出成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
        401:
          description: refresh token 缺失或無效
    """
    jti = get_jwt()['jti']
    auth_service.logout(jti)
    response = jsonify({'message': '登出成功'})
    unset_jwt_cookies(response)
    return response
