from marshmallow import Schema, fields, validate


class CreateProductSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    price = fields.Float(required=True, validate=validate.Range(min=0.01))
    stock = fields.Int(load_default=0, validate=validate.Range(min=0))
    category = fields.Str(load_default=None)
    description = fields.Str(load_default=None)
    image_url = fields.Url(load_default=None)


class UpdateProductSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=200))
    price = fields.Float(validate=validate.Range(min=0.01))
    stock = fields.Int(validate=validate.Range(min=0))
    category = fields.Str()
    description = fields.Str()
    image_url = fields.Url()
    is_active = fields.Bool()


class InventoryAdjustSchema(Schema):
    action = fields.Str(required=True, validate=validate.OneOf(["restock", "adjust"]))
    quantity_change = fields.Int(required=True)
    note = fields.Str(load_default=None, validate=validate.Length(max=250))


class ProductResponseSchema(Schema):
    id = fields.Int()
    name = fields.Str()
    description = fields.Str(allow_none=True)
    price = fields.Float()
    stock = fields.Int()
    category = fields.Str(allow_none=True)
    image_url = fields.Str(allow_none=True)
    is_active = fields.Bool()
    created_at = fields.DateTime()


class ProductListResponseSchema(Schema):
    products = fields.List(fields.Nested(ProductResponseSchema))
    total = fields.Int()
    pages = fields.Int()
    current_page = fields.Int()


class InventoryLogResponseSchema(Schema):
    id = fields.Int()
    product_id = fields.Int()
    order_id = fields.Int(allow_none=True)
    action = fields.Str()
    quantity_before = fields.Int()
    quantity_change = fields.Int()
    quantity_after = fields.Int()
    note = fields.Str(allow_none=True)
    created_at = fields.DateTime()


class InventoryLogListResponseSchema(Schema):
    inventory_logs = fields.List(fields.Nested(InventoryLogResponseSchema))
    total = fields.Int()
    pages = fields.Int()
    current_page = fields.Int()


class CreateProductResponseSchema(Schema):
    message = fields.Str()
    product = fields.Nested(ProductResponseSchema)


class UpdateProductResponseSchema(Schema):
    message = fields.Str()
    product = fields.Nested(ProductResponseSchema)


class AdjustInventoryResponseSchema(Schema):
    message = fields.Str()
    inventory_log = fields.Nested(InventoryLogResponseSchema)
