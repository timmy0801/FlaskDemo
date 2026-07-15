from app import db
from app.models.product import Product
from app.models.inventory_log import InventoryLog
from app.utils.pagination import clamp_per_page
from app.utils.exceptions import BadRequestError


def get_products(page, per_page, category):
    query = Product.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "products": [p.to_dict() for p in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page,
    }


def get_product(product_id):
    return Product.query.get_or_404(product_id).to_dict()


def create_product(data):
    product = Product(
        name=data["name"],
        description=data.get("description"),
        price=data["price"],
        stock=data.get("stock", 0),
        category=data.get("category"),
        image_url=data.get("image_url"),
    )
    db.session.add(product)
    db.session.commit()
    return product.to_dict()


def update_product(product_id, data):
    product = Product.query.get_or_404(product_id)
    for field in Product.UPDATABLE_FIELDS:
        if field in data:
            setattr(product, field, data[field])
    db.session.commit()
    return product.to_dict()


def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = False
    db.session.commit()


def get_inventory_logs(product_id, page, per_page):
    product = Product.query.get_or_404(product_id)
    per_page = clamp_per_page(per_page)
    pagination = (
        InventoryLog.query.filter_by(product_id=product.id)
        .order_by(InventoryLog.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return {
        "inventory_logs": [log.to_dict() for log in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page,
    }


def adjust_inventory(product_id, data):
    product = Product.query.get_or_404(product_id)
    action = data["action"]
    quantity_change = data["quantity_change"]

    if action == "restock" and quantity_change <= 0:
        raise BadRequestError("restock 的異動數量必須為正數")
    if action == "adjust" and quantity_change == 0:
        raise BadRequestError("adjust 的異動數量不可為 0")

    quantity_before = product.stock
    quantity_after = quantity_before + quantity_change
    if quantity_after < 0:
        raise BadRequestError("庫存不足，異動後不可為負數")

    product.stock = quantity_after
    product.version += 1

    log = InventoryLog(
        product_id=product.id,
        action=action,
        quantity_before=quantity_before,
        quantity_change=quantity_change,
        quantity_after=quantity_after,
        note=data.get("note"),
    )
    db.session.add(log)
    db.session.commit()
    return log.to_dict()
