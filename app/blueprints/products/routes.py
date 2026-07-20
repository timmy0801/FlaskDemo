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
    """
    ---
    get:
      summary: 取得商品列表
      tags: [Products]
      parameters:
        - in: query
          name: q
          schema: {type: string}
          description: 依商品名稱關鍵字搜尋（不分大小寫、包含比對）
        - in: query
          name: category
          schema: {type: string}
        - in: query
          name: sort_by
          schema: {type: string, enum: [price, created_at]}
          description: 未帶或無效值時預設 created_at
        - in: query
          name: order
          schema: {type: string, enum: [asc, desc]}
          description: 未帶或無效值時預設 desc
        - in: query
          name: page
          schema: {type: integer, default: 1}
        - in: query
          name: per_page
          schema: {type: integer, default: 10}
          description: 上限 100
      responses:
        200:
          description: 商品列表
          content:
            application/json:
              schema: ProductListResponseSchema
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    category = request.args.get("category")
    q = request.args.get("q")
    sort_by = request.args.get("sort_by")
    order = request.args.get("order")

    return jsonify(
        product_service.get_products(page, per_page, category, q, sort_by, order)
    )


@products_bp.route("/<int:product_id>", methods=["GET"])
def get_product(product_id):
    """
    ---
    get:
      summary: 取得單一商品
      tags: [Products]
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
      responses:
        200:
          description: 商品資訊
          content:
            application/json:
              schema: ProductResponseSchema
        404:
          description: 商品不存在
    """
    return jsonify(product_service.get_product(product_id))


@products_bp.route("", methods=["POST"])
@admin_required
@validate_body(CreateProductSchema)
def create_product(validated_data):
    """
    ---
    post:
      summary: 新增商品
      tags: [Products]
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema: CreateProductSchema
      responses:
        201:
          description: 商品建立成功
          content:
            application/json:
              schema: CreateProductResponseSchema
        400:
          description: 請求格式錯誤
        403:
          description: 權限不足，需要 admin 身分
    """
    product = product_service.create_product(validated_data)
    return jsonify({"message": "商品建立成功", "product": product}), 201


@products_bp.route("/<int:product_id>", methods=["PUT"])
@admin_required
@validate_body(UpdateProductSchema)
def update_product(product_id, validated_data):
    """
    ---
    put:
      summary: 更新商品
      tags: [Products]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
      requestBody:
        required: true
        content:
          application/json:
            schema: UpdateProductSchema
      responses:
        200:
          description: 商品更新成功
          content:
            application/json:
              schema: UpdateProductResponseSchema
        400:
          description: 請求格式錯誤
        403:
          description: 權限不足，需要 admin 身分
        404:
          description: 商品不存在
    """
    product = product_service.update_product(product_id, validated_data)
    return jsonify({"message": "商品更新成功", "product": product})


@products_bp.route("/<int:product_id>", methods=["DELETE"])
@admin_required
def delete_product(product_id):
    """
    ---
    delete:
      summary: 下架商品（軟刪除）
      tags: [Products]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
      responses:
        204:
          description: 商品已下架
        403:
          description: 權限不足，需要 admin 身分
        404:
          description: 商品不存在
    """
    product_service.delete_product(product_id)
    return "", 204


@products_bp.route("/<int:product_id>/inventory-logs", methods=["GET"])
@admin_required
def get_inventory_logs(product_id):
    """
    ---
    get:
      summary: 取得商品的庫存異動紀錄
      tags: [Products]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
        - in: query
          name: page
          schema: {type: integer, default: 1}
        - in: query
          name: per_page
          schema: {type: integer, default: 20}
      responses:
        200:
          description: 庫存異動紀錄列表
          content:
            application/json:
              schema: InventoryLogListResponseSchema
        403:
          description: 權限不足，需要 admin 身分
        404:
          description: 商品不存在
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    return jsonify(product_service.get_inventory_logs(product_id, page, per_page))


@products_bp.route("/<int:product_id>/inventory-logs", methods=["POST"])
@admin_required
@validate_body(InventoryAdjustSchema)
def adjust_inventory(product_id, validated_data):
    """
    ---
    post:
      summary: 補貨（restock）或人工調整庫存（adjust）
      tags: [Products]
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: product_id
          required: true
          schema: {type: integer}
      requestBody:
        required: true
        content:
          application/json:
            schema: InventoryAdjustSchema
      responses:
        201:
          description: 庫存調整成功
          content:
            application/json:
              schema: AdjustInventoryResponseSchema
        400:
          description: 請求格式錯誤，或異動數量不合法／會導致庫存為負數
        403:
          description: 權限不足，需要 admin 身分
        404:
          description: 商品不存在
    """
    log = product_service.adjust_inventory(product_id, validated_data)
    return jsonify({"message": "庫存調整成功", "inventory_log": log}), 201
