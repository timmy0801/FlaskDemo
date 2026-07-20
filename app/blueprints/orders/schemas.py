from marshmallow import Schema, fields, validate

VALID_STATUSES = ("pending", "paid", "shipped", "delivered", "cancelled")


class OrderItemSchema(Schema):
    product_id = fields.Int(required=True, validate=validate.Range(min=1))
    quantity = fields.Int(required=True, validate=validate.Range(min=1))


class CreateOrderSchema(Schema):
    items = fields.List(
        fields.Nested(OrderItemSchema), required=True, validate=validate.Length(min=1)
    )


class UpdateOrderStatusSchema(Schema):
    status = fields.Str(required=True, validate=validate.OneOf(VALID_STATUSES))


class OrderItemResponseSchema(Schema):
    id = fields.Int()
    product_id = fields.Int()
    product_name = fields.Str(allow_none=True)
    quantity = fields.Int()
    unit_price = fields.Decimal(as_string=True)
    subtotal = fields.Decimal(as_string=True)


class OrderResponseSchema(Schema):
    id = fields.Int()
    user_id = fields.Int()
    status = fields.Str()
    total_amount = fields.Decimal(as_string=True)
    items = fields.List(fields.Nested(OrderItemResponseSchema))
    created_at = fields.DateTime()


class OrderListResponseSchema(Schema):
    orders = fields.List(fields.Nested(OrderResponseSchema))
    total = fields.Int()
    pages = fields.Int()
    current_page = fields.Int()


class CreateOrderResponseSchema(Schema):
    message = fields.Str()
    order = fields.Nested(OrderResponseSchema)


class UpdateOrderStatusResponseSchema(Schema):
    message = fields.Str()
    order = fields.Nested(OrderResponseSchema)
