from sqlalchemy.orm import joinedload

from app import db
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.inventory_log import InventoryLog
from app.utils.exceptions import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    ConflictError,
)
from app.utils.pagination import clamp_per_page

MAX_RETRY = 3


def get_orders(user_id, claims, page, per_page):
    per_page = clamp_per_page(per_page)
    query = Order.query.options(
        joinedload(Order.items).joinedload(OrderItem.product)
    ).order_by(Order.created_at.desc())

    if claims.get("role") != "admin":
        query = query.filter_by(user_id=user_id)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "orders": [o.to_dict() for o in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page,
    }


def get_order(order_id, user_id, claims):
    order = (
        Order.query.options(joinedload(Order.items).joinedload(OrderItem.product))
        .filter_by(id=order_id)
        .first_or_404()
    )

    if claims.get("role") != "admin" and order.user_id != user_id:
        raise ForbiddenError("無權限查看此訂單")

    return order.to_dict()


def create_order(user_id, data):
    for attempt in range(MAX_RETRY):
        try:
            order = Order(user_id=user_id)
            db.session.add(order)
            logs = []

            for item_data in data["items"]:
                product_id = item_data["product_id"]
                qty = item_data["quantity"]

                product = db.session.get(Product, product_id)
                if not product or not product.is_active:
                    db.session.rollback()
                    raise NotFoundError(f"商品 ID {product_id} 不存在或已下架")

                if product.stock < qty:
                    db.session.rollback()
                    raise BadRequestError(f"商品「{product.name}」庫存不足")

                stock_before = product.stock

                # 樂觀鎖：版本號不符則 updated_rows = 0
                updated_rows = Product.query.filter_by(
                    id=product.id, version=product.version
                ).update({"stock": product.stock - qty, "version": product.version + 1})

                if updated_rows == 0:
                    db.session.rollback()
                    break  # 衝突，進入下一次重試

                order_item = OrderItem(
                    order=order,
                    product_id=product.id,
                    quantity=qty,
                    unit_price=product.price,
                )
                db.session.add(order_item)

                log = InventoryLog(
                    product_id=product.id,
                    action="deduct",
                    quantity_before=stock_before,
                    quantity_change=-qty,
                    quantity_after=stock_before - qty,
                    note="訂單建立扣除",
                )
                db.session.add(log)
                logs.append(log)

            else:
                # for 迴圈正常結束（無 break），所有商品處理成功
                db.session.flush()
                order.calculate_total()
                for log in logs:
                    log.order_id = order.id
                db.session.commit()
                return order.to_dict()

        except (NotFoundError, BadRequestError, ForbiddenError):
            raise  # 業務錯誤直接傳播，不重試

    raise ConflictError("庫存競爭衝突，請稍後再試")


def update_order_status(order_id, data, user_id, claims):
    order = (
        Order.query.options(joinedload(Order.items).joinedload(OrderItem.product))
        .filter_by(id=order_id)
        .first_or_404()
    )
    new_status = data["status"]
    is_admin = claims.get("role") == "admin"
    if not is_admin:
        if order.user_id != user_id:
            raise ForbiddenError("無權限修改此訂單狀態")
        if order.status != "pending":
            raise BadRequestError("只能取消待處理的訂單")
        if new_status != "cancelled":
            raise ForbiddenError("只能將訂單狀態改為 cancelled")

    if new_status == "cancelled" and order.status != "cancelled":
        _restock_order_items(order)
    order.status = new_status
    db.session.commit()
    return order.to_dict()


def _restock_order_items(order):
    for item in order.items:
        product = item.product
        quantity_before = product.stock
        product.stock = quantity_before + item.quantity
        product.version += 1
        db.session.add(
            InventoryLog(
                product_id=product.id,
                action="restock",
                quantity_before=quantity_before,
                quantity_change=item.quantity,
                quantity_after=product.stock,
                note=f"訂單取消, 庫存回補 (訂單 ID: {order.id})",
            )
        )
