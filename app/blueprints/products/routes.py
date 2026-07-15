from flask import request, jsonify

from app import db
from app.models.product import Product
from app.blueprints.products import products_bp
from app.blueprints.products.schemas import (
    CreateProductSchema,
    UpdateProductSchema,
    InventoryAdjustSchema,
)
from app.utils.decorators import admin_required, validate_body
from app.services import product_service


@products_bp.route("", methods=["GET"])
def get_products():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    category = request.args.get("category")
    q = request.args.get("q")
    sort_by = request.args.get("sort_by")
    order = request.args.get("order")

    return jsonify(product_service.get_products(page, per_page, category, q, sort_by, order))


@products_bp.route("/<int:product_id>", methods=["GET"])
def get_product(product_id):
    return jsonify(product_service.get_product(product_id))


@products_bp.route("", methods=["POST"])
@admin_required
@validate_body(CreateProductSchema)
def create_product(validated_data):
    product = product_service.create_product(validated_data)
    return jsonify({"message": "商品建立成功", "product": product}), 201


@products_bp.route("/<int:product_id>", methods=["PUT"])
@admin_required
@validate_body(UpdateProductSchema)
def update_product(product_id, validated_data):
    product = product_service.update_product(product_id, validated_data)
    return jsonify({"message": "商品更新成功", "product": product})


@products_bp.route("/<int:product_id>", methods=["DELETE"])
@admin_required
def delete_product(product_id):
    product_service.delete_product(product_id)
    return jsonify({"message": "商品已下架"}), 204


@products_bp.route("/<int:product_id>/inventory-logs", methods=["GET"])
@admin_required
def get_inventory_logs(product_id):
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    return jsonify(product_service.get_inventory_logs(product_id, page, per_page))


@products_bp.route("/<int:product_id>/inventory-logs", methods=["POST"])
@admin_required
@validate_body(InventoryAdjustSchema)
def adjust_inventory(product_id, validated_data):
    log = product_service.adjust_inventory(product_id, validated_data)
    return jsonify({"message": "庫存調整成功", "inventory_log": log}), 201
