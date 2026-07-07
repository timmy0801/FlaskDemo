from marshmallow import Schema, fields, validate

class CreateProductSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1,max=200))
    price = fields.Float(required=True, validate=validate.Range(min=0.01))
    stock = fields.Int(load_default=0, validate=validate.Range(min=0))
    category = fields.Str(load_default=None)
    description = fields.Str(load_default=None)
    image_url = fields.Url(load_default=None)

class UpdateProductSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1,max=200))
    price = fields.Float(validate=validate.Range(min=0.01))
    stock = fields.Int(validate=validate.Range(min=0))
    category = fields.Str()
    description = fields.Str()
    image_url = fields.Url()
    is_active = fields.Bool()