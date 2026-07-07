from marshmallow import Schema, fields, validate

VALID_STATUSES = ('pending', 'paid', 'shipped', 'delivered', 'cancelled')


class OrderItemSchema(Schema):
    product_id = fields.Int(required=True, validate=validate.Range(min=1))
    quantity = fields.Int(required=True, validate=validate.Range(min=1))


class CreateOrderSchema(Schema):
    items = fields.List(
        fields.Nested(OrderItemSchema),
        required=True,
        validate=validate.Length(min=1)
    )


class UpdateOrderStatusSchema(Schema):
    status = fields.Str(required=True, validate=validate.OneOf(VALID_STATUSES))
