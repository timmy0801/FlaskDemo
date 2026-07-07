from flask import jsonify
from app.utils.exceptions import AppError
from werkzeug.exceptions import NotFound, MethodNotAllowed, BadRequest, Unauthorized, Forbidden, InternalServerError


def register_error_handlers(app):

    @app.errorhandler(AppError)
    def handle_app_error(e):
        return jsonify({'error': e.message}), e.status_code

    @app.errorhandler(BadRequest)
    def handle_bad_request(e):
        return jsonify({'error': '請求格式錯誤','detail':str(e)}), 400

    @app.errorhandler(Unauthorized)
    def handle_unauthorized(e):
        return jsonify({'error': '未授權，請先登入'}), 401

    @app.errorhandler(Forbidden)
    def handle_forbidden(e):
        return jsonify({'error': '權限不足'}), 403

    @app.errorhandler(NotFound)
    def handle_not_found(e):
        return jsonify({'error': '資源不存在'}), 404

    @app.errorhandler(MethodNotAllowed)
    def handle_method_not_allowed(e):
        return jsonify({'error': '不支援此 HTTP 方法'}), 405


    @app.errorhandler(InternalServerError)
    def internal_error(e):
        return jsonify({'error': '伺服器內部錯誤'}), 500
    