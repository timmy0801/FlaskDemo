def register_jwt_callbacks(jwt):

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        if jwt_payload.get('type') != 'refresh':
            return False

        from app.models.refresh_token import RefreshToken

        token = RefreshToken.query.filter_by(jti=jwt_payload['jti']).first()
        return token is None or token.revoked_at is not None
