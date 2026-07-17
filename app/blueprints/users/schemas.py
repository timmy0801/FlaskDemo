from marshmallow import Schema, fields, validate

from app.blueprints.auth.schemas import UserResponseSchema


class UpdateUserSchema(Schema):
    username = fields.Str(validate=validate.Length(min=2, max=80))
    password = fields.Str(validate=validate.Length(min=6))
    is_active = fields.Bool()
    role = fields.Str(validate=validate.OneOf(['user', 'admin']))


class UserListResponseSchema(Schema):
    users = fields.List(fields.Nested(UserResponseSchema))
    total = fields.Int()
    pages = fields.Int()
    current_page = fields.Int()


class UpdateUserResponseSchema(Schema):
    message = fields.Str()
    user = fields.Nested(UserResponseSchema)
