from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.blueprints.orders import orders_bp
from app.blueprints.orders.schemas import CreateOrderSchema, UpdateOrderStatusSchema
from app.utils.decorators import validate_body
from app.services import order_service


@orders_bp.route("", methods=["GET"])
@jwt_required()
def get_orders():
    """
    ---
    get:
      summary: 取得訂單列表
      description: Admin 看全部訂單，一般使用者只看自己的訂單。
      tags: [Orders]
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
          description: 訂單列表
          content:
            application/json:
              schema: OrderListResponseSchema
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    return jsonify(order_service.get_orders(user_id, claims, page, per_page))


@orders_bp.route("/<int:order_id>", methods=["GET"])
@jwt_required()
def get_order(order_id):
    """
    ---
    get:
      summary: 取得單一訂單
      tags: [Orders]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: order_id
          required: true
          schema: {type: integer}
      responses:
        200:
          description: 訂單資訊
          content:
            application/json:
              schema: OrderResponseSchema
        403:
          description: 無權限查看此訂單
        404:
          description: 訂單不存在
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    return jsonify(order_service.get_order(order_id, user_id, claims))


@orders_bp.route("", methods=["POST"])
@jwt_required()
@validate_body(CreateOrderSchema)
def create_order(validated_data):
    """
    ---
    post:
      summary: 建立新訂單
      description: 會依序扣除各商品庫存並寫入庫存異動紀錄；若庫存不足或商品不存在會回錯誤。
      tags: [Orders]
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema: CreateOrderSchema
      responses:
        201:
          description: 訂單建立成功
          content:
            application/json:
              schema: CreateOrderResponseSchema
        400:
          description: 請求格式錯誤，或商品庫存不足
        404:
          description: 商品不存在或已下架
        409:
          description: 庫存競爭衝突，請稍後再試
    """
    user_id = int(get_jwt_identity())
    order = order_service.create_order(user_id, validated_data)
    return jsonify({"message": "訂單建立成功", "order": order}), 201


@orders_bp.route("/<int:order_id>/status", methods=["PATCH"])
@jwt_required()
@validate_body(UpdateOrderStatusSchema)
def update_order_status(order_id, validated_data):
    """
    ---
    patch:
      summary: 更新訂單狀態
      description: Admin 可設定任意合法狀態；一般使用者只能把自己「pending」狀態的訂單改成 cancelled，取消時會自動把庫存加回去。
      tags: [Orders]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: order_id
          required: true
          schema: {type: integer}
      requestBody:
        required: true
        content:
          application/json:
            schema: UpdateOrderStatusSchema
      responses:
        200:
          description: 訂單狀態已更新
          content:
            application/json:
              schema: UpdateOrderStatusResponseSchema
        400:
          description: 請求格式錯誤，或只有待處理（pending）的訂單可以取消
        403:
          description: 無權限修改此訂單狀態
        404:
          description: 訂單不存在
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    order = order_service.update_order_status(order_id, validated_data, user_id, claims)
    return jsonify({"message": "訂單狀態已更新", "order": order})
