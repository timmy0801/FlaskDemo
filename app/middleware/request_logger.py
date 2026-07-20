import time
import uuid
from flask import request, g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request


def register_hooks(app):

    @app.before_request
    def before_request():
        g.start_time = time.time()
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    @app.after_request
    def after_request(response):
        duration_ms = round((time.time() - g.start_time) * 1000, 2)
        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except Exception:
            pass
        response.headers["X-Request-ID"] = g.request_id
        app.logger.info(
            "request_log",
            extra={
                "request_id": g.request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
                "ip": request.remote_addr,
            },
        )
        return response
