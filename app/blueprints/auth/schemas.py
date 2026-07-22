from marshmallow import Schema, fields, validate


class RegisterSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=2, max=80))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8))


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)


class UserResponseSchema(Schema):
    id = fields.Int()
    username = fields.Str()
    email = fields.Str()
    role = fields.Str()
    is_active = fields.Bool()
    created_at = fields.DateTime()


class LoginResponseSchema(Schema):
    message = fields.Str()
    access_token = fields.Str()
    user = fields.Nested(UserResponseSchema)


class RegisterResponseSchema(Schema):
    message = fields.Str()
    user = fields.Nested(UserResponseSchema)
