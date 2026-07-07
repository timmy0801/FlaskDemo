from marshmallow import Schema, fields, validate


class UpdateUserSchema(Schema):
    username = fields.Str(validate=validate.Length(min=2, max=80))
    password = fields.Str(validate=validate.Length(min=6))
    is_active = fields.Bool()
    role = fields.Str(validate=validate.OneOf(['user', 'admin']))
