import time
from flask import request, g


def register_hooks(app):

    @app.before_request
    def before_request():
        g.start_time = time.time()

    @app.after_request
    def after_request(response):
        duration_ms = round((time.time() - g.start_time) * 1000, 2)
        app.logger.info(
            f'{request.method} {request.path} → {response.status_code} ({duration_ms}ms)'
        )
        return response
