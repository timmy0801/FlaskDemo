from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.blueprints.orders import orders_bp
from app.blueprints.orders.schemas import CreateOrderSchema, UpdateOrderStatusSchema
from app.utils.decorators import validate_body
from app.services import order_service


@orders_bp.route('', methods=['GET'])
@jwt_required()
def get_orders():
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    return jsonify(order_service.get_orders(user_id, claims, page, per_page))


@orders_bp.route('/<int:order_id>', methods=['GET'])
@jwt_required()
def get_order(order_id):
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    return jsonify(order_service.get_order(order_id, user_id, claims))


@orders_bp.route('', methods=['POST'])
@jwt_required()
@validate_body(CreateOrderSchema)
def create_order(validated_data):
    user_id = int(get_jwt_identity())
    order = order_service.create_order(user_id, validated_data)
    return jsonify({'message': '訂單建立成功', 'order': order}), 201


@orders_bp.route('/<int:order_id>/status', methods=['PATCH'])
@jwt_required()
@validate_body(UpdateOrderStatusSchema)
def update_order_status(order_id, validated_data):
    claims = get_jwt()
    order = order_service.update_order_status(order_id, validated_data, claims)
    return jsonify({'message': '訂單狀態已更新', 'order': order})
