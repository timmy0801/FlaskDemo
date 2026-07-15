def register_jwt_callbacks(jwt):

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        if jwt_payload.get('type') != 'refresh':
            return False

        from app.models.refresh_token import RefreshToken

        token = RefreshToken.query.filter_by(jti=jwt_payload['jti']).first()
        # Block only refresh tokens whose jti has no DB record (e.g. forged/
        # cleaned-up). A revoked-but-present token is intentionally allowed past
        # the decorator so auth_service.refresh() can run reuse detection and
        # revoke all of the user's sessions (theft response). If the loader also
        # blocked revoked tokens, @jwt_required(refresh=True) would 401 first and
        # that cascade would never fire. auth_service.refresh()/logout() still
        # enforce revoked -> 401 at the service layer.
        return token is None
