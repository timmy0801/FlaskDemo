from app import db
from app.models.user import User
from app.utils.exceptions import ConflictError
from app.utils.pagination import clamp_per_page


def get_users(page, per_page):
    per_page = clamp_per_page(per_page)
    pagination = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        "users": [u.to_dict() for u in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page,
    }


def get_user(user_id):
    return User.query.filter_by(id=user_id).first_or_404().to_dict()


def update_user(user_id, data, claims):
    user = User.query.filter_by(id=user_id).first_or_404()

    if "username" in data:
        existing = User.query.filter_by(username=data["username"]).first()
        if existing and existing.id != user_id:
            raise ConflictError("此使用者名稱已被使用")
        user.username = data["username"]

    if "password" in data:
        user.set_password(data["password"])

    # is_active 和 role 僅限 admin 修改
    if claims.get("role") == "admin":
        if "is_active" in data:
            user.is_active = data["is_active"]
        if "role" in data:
            user.role = data["role"]

    db.session.commit()
    return user.to_dict()


def deactivate_user(user_id):
    user = User.query.filter_by(id=user_id).first_or_404()
    user.is_active = False
    db.session.commit()
