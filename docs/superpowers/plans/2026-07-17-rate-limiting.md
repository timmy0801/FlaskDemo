# Rate Limiting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 替 `/api/auth/login`、`/api/auth/register` 加上請求頻率限制，防止暴力破解密碼與大量灌假帳號，不影響其他端點。

**Architecture:** 用 `Flask-Limiter`，仿照專案既有的 `db`/`migrate`/`jwt` pattern，在 `app/__init__.py` 建立模組層級的 `limiter` 物件並在 `create_app()` 裡 `init_app`。`login` 用 `IP+email` 組合當限流 key（避免同 IP 下一個帳號被打導致其他人連坐被鎖），`register` 用純 IP。超過限制回 429，用自訂 error handler 統一成專案既有的 `{"error": "..."}` 格式。設計依據：[docs/superpowers/specs/2026-07-17-rate-limiting-design.md](../specs/2026-07-17-rate-limiting-design.md)。

**Tech Stack:** Flask-Limiter 4.1.1

**⚠️ 這個 branch 要從 `main` 重新切 worktree，不要疊在 `feature/openapi-docs` 上面**（那個 branch 還沒併回 main，兩個功能應該保持獨立）。

**技術細節（已在此環境實測過，寫程式時直接照這些結論走）：**
- `flask-limiter` 安裝到這個環境會解析到 `4.1.1`（`pip install --dry-run` 確認過跟現有的 Flask 3.1.3 / marshmallow 4.3.0 沒有版本衝突）。
- **不需要在測試裡手動 reset limiter 的計數器。** 原本以為 in-memory storage 是跨整個測試進程共用的全域狀態，需要在 `tests/conftest.py` 的 `app` fixture 裡加 `limiter.reset()`。但實際模擬「每次都重新 `create_app()`，重用同一個已經在 blueprint 裡被 decorate 過的 view function」（完全比照 `tests/conftest.py` 的 `app` fixture 每個測試都重新 `create_app("testing")` 的模式）連續測了 3 輪，對 `login`（自訂 `IP+email` key）跟 `register`（純 IP key）都確認：**每一輪都是全新的、從 0 開始的計數，完全沒有跨測試污染**。所以這份計畫不需要碰 `tests/conftest.py`。
- 429 的 error handler 要用 `werkzeug.exceptions.TooManyRequests` 這個類別（跟 `app/middleware/error_handler.py` 裡其他 handler 用 werkzeug exception 類別的風格一致，不是用裸的整數 `429`），已實測確認 Flask-Limiter 拋出的例外會被這個 handler 正確攔截。
- `@limiter.limit(...)` decorator 要放在 `@validate_body(...)` 上面（更靠近 `@xxx_bp.route(...)`），這樣限流檢查會在請求進到 body 驗證邏輯**之前**先執行——被擋掉的請求不會浪費運算去解析/驗證 body。

---

## Task 1: Flask-Limiter 基礎建設 + login/register 限流

**Files:**
- Modify: `requirements.txt`
- Modify: `app/__init__.py`
- Modify: `app/middleware/error_handler.py`
- Modify: `app/blueprints/auth/routes.py`
- Test: `tests/test_rate_limit.py`

- [ ] **Step 1: 撰寫會失敗的測試 `tests/test_rate_limit.py`**

```python
def test_login_rate_limited_after_5_attempts_same_email(client, db):
    from app.models.user import User

    user = User(username='ratelimituser', email='ratelimit@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    for _ in range(5):
        resp = client.post(
            '/api/auth/login',
            json={'email': 'ratelimit@test.com', 'password': 'wrongpassword'},
        )
        assert resp.status_code == 401

    resp = client.post(
        '/api/auth/login',
        json={'email': 'ratelimit@test.com', 'password': 'wrongpassword'},
    )
    assert resp.status_code == 429
    assert resp.get_json() == {'error': '請求過於頻繁，請稍後再試'}


def test_login_rate_limit_is_per_email_not_just_per_ip(client, db):
    from app.models.user import User

    for email in ('user_a@test.com', 'user_b@test.com'):
        user = User(username=email.split('@')[0], email=email, role='user')
        user.set_password('password123')
        db.session.add(user)
    db.session.commit()

    for _ in range(5):
        client.post(
            '/api/auth/login',
            json={'email': 'user_a@test.com', 'password': 'wrongpassword'},
        )

    blocked_resp = client.post(
        '/api/auth/login',
        json={'email': 'user_a@test.com', 'password': 'wrongpassword'},
    )
    assert blocked_resp.status_code == 429

    other_email_resp = client.post(
        '/api/auth/login',
        json={'email': 'user_b@test.com', 'password': 'password123'},
    )
    assert other_email_resp.status_code == 200


def test_register_rate_limited_after_5_attempts_same_ip(client):
    for i in range(5):
        resp = client.post(
            '/api/auth/register',
            json={
                'username': f'rluser{i}',
                'email': f'rluser{i}@test.com',
                'password': 'password123',
            },
        )
        assert resp.status_code == 201

    resp = client.post(
        '/api/auth/register',
        json={
            'username': 'rluser5',
            'email': 'rluser5@test.com',
            'password': 'password123',
        },
    )
    assert resp.status_code == 429
    assert resp.get_json() == {'error': '請求過於頻繁，請稍後再試'}
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_rate_limit.py -v
```

Expected: 全部 `FAILED`（目前沒有任何限流機制，第 6 次呼叫會正常處理，不會回 429）

- [ ] **Step 3: 更新 `requirements.txt`**

在檔案最後新增一行：

```
flask-limiter==4.1.1
```

- [ ] **Step 4: 安裝套件**

```bash
pip install flask-limiter==4.1.1
```

- [ ] **Step 5: 更新 `app/__init__.py`**

把：

```python
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
```

改為：

```python
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import config_map

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, storage_uri='memory://')


def create_app(env='default'):
    app = Flask(__name__)
    app.config.from_object(config_map[env])

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
```

- [ ] **Step 6: 更新 `app/middleware/error_handler.py`**

把 import 那行：

```python
from werkzeug.exceptions import NotFound, MethodNotAllowed, BadRequest, Unauthorized, Forbidden, InternalServerError
```

改為：

```python
from werkzeug.exceptions import (
    NotFound,
    MethodNotAllowed,
    BadRequest,
    Unauthorized,
    Forbidden,
    InternalServerError,
    TooManyRequests,
)
```

在 `handle_forbidden` 之後、`handle_not_found` 之前新增：

```python

    @app.errorhandler(TooManyRequests)
    def handle_too_many_requests(e):
        return jsonify({'error': '請求過於頻繁，請稍後再試'}), 429
```

- [ ] **Step 7: 更新 `app/blueprints/auth/routes.py`**

把 import 區塊改為：

```python
from flask import jsonify, request
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_refresh_cookies,
    unset_jwt_cookies,
)
from flask_limiter.util import get_remote_address

from app import limiter
from app.models.user import User
from app.blueprints.auth import auth_bp
from app.blueprints.auth.schemas import RegisterSchema, LoginSchema
from app.services import auth_service
from app.utils.decorators import validate_body


def _login_rate_limit_key():
    data = request.get_json(silent=True) or {}
    return f'{get_remote_address()}:{data.get("email", "")}'
```

把：

```python
@auth_bp.route('/register', methods=['POST'])
@validate_body(RegisterSchema)
def register(validated_data):
```

改為：

```python
@auth_bp.route('/register', methods=['POST'])
@limiter.limit('5 per hour')
@validate_body(RegisterSchema)
def register(validated_data):
```

把：

```python
@auth_bp.route('/login', methods=['POST'])
@validate_body(LoginSchema)
def login(validated_data):
```

改為：

```python
@auth_bp.route('/login', methods=['POST'])
@limiter.limit('5 per minute', key_func=_login_rate_limit_key)
@validate_body(LoginSchema)
def login(validated_data):
```

- [ ] **Step 8: 執行測試確認通過**

```bash
pytest tests/test_rate_limit.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 9: 執行完整測試套件，確認沒有破壞既有功能**

```bash
pytest -v
```

Expected: 全部 `PASSED`（既有的 `test_auth.py`、`tests/conftest.py` 裡的 `admin_user_and_token`/`normal_user_and_token` fixture 都遠低於 5 次的門檻，且每個測試各自 `create_app()` 互相隔離，不會被這次改動影響）

- [ ] **Step 10: Commit**

```bash
git add requirements.txt app/__init__.py app/middleware/error_handler.py app/blueprints/auth/routes.py tests/test_rate_limit.py
git commit -m "feat: add rate limiting to login and register endpoints"
```

---

## 完成後的變更總覽

```
app/
├── __init__.py                    (+limiter 物件、+limiter.init_app(app))
├── middleware/
│   └── error_handler.py           (+429 handler)
└── blueprints/
    └── auth/
        └── routes.py              (+_login_rate_limit_key, login/register 加 @limiter.limit)
requirements.txt                   (+flask-limiter==4.1.1)
tests/
└── test_rate_limit.py             (new: 3 個測試)
```

## 已知限制（不在本次範圍，設計階段已記錄）

- 沒有處理「同一 IP 大量嘗試不同帳號」的帳號列舉/噴射攻擊防護
- In-memory storage 在 production 多 gunicorn worker 部署下，實際限制效果會是「門檻 × worker 數」，不是精確的全域限制
- 沒有 progressive backoff，固定時間窗口重置
