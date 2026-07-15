from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager

from config import config_map

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


def create_app(env='default'):
    app = Flask(__name__)
    app.config.from_object(config_map[env])

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    from app.utils.jwt_callbacks import register_jwt_callbacks
    register_jwt_callbacks(jwt)

    # 註冊 Middleware（Before / After Request）
    from app.middleware.request_logger import register_hooks
    register_hooks(app)

    # 註冊 Blueprint
    from app.blueprints.auth import auth_bp
    from app.blueprints.products import products_bp
    from app.blueprints.orders import orders_bp
    from app.blueprints.users import users_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(orders_bp, url_prefix='/api/orders')
    app.register_blueprint(users_bp, url_prefix='/api/users')

    # 全域錯誤處理
    from app.middleware.error_handler import register_error_handlers
    register_error_handlers(app)

    # 註冊 CLI 指令
    from app.commands import register_commands
    register_commands(app)

    return app
