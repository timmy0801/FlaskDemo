from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from apispec_webframeworks.flask import FlaskPlugin
from flask import jsonify
from flask_swagger_ui import get_swaggerui_blueprint

spec = APISpec(
    title='Flask 電商後台 API',
    version='1.0.0',
    openapi_version='3.0.3',
    plugins=[FlaskPlugin(), MarshmallowPlugin()],
)

spec.components.security_scheme('bearerAuth', {
    'type': 'http',
    'scheme': 'bearer',
    'bearerFormat': 'JWT',
})
spec.components.security_scheme('cookieAuth', {
    'type': 'apiKey',
    'in': 'cookie',
    'name': 'refresh_token_cookie',
})
spec.components.security_scheme('csrfHeader', {
    'type': 'apiKey',
    'in': 'header',
    'name': 'X-CSRF-TOKEN',
})


def register_openapi(app):
    with app.test_request_context():
        for view in app.view_functions.values():
            if view.__doc__ and '---' in view.__doc__:
                spec.path(view=view)

    @app.route('/api/openapi.json')
    def openapi_json():
        return jsonify(spec.to_dict())

    swagger_ui_bp = get_swaggerui_blueprint(
        '/api/docs',
        '/api/openapi.json',
        config={'app_name': 'Flask 電商後台 API'},
    )
    app.register_blueprint(swagger_ui_bp, url_prefix='/api/docs')
