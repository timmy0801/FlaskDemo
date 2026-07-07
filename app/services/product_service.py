from app import db
from app.models.product import Product


def get_products(page, per_page, category):
    query = Product.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        'products': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    }


def get_product(product_id):
    return Product.query.get_or_404(product_id).to_dict()


def create_product(data):
    product = Product(
        name=data['name'],
        description=data.get('description'),
        price=data['price'],
        stock=data.get('stock', 0),
        category=data.get('category'),
        image_url=data.get('image_url'),
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
