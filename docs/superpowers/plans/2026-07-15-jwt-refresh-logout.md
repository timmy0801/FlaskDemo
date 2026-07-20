# JWT Refresh Token / 登出機制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓使用者登入後可以用 refresh token 換發新的 access token，不用每小時重新登入；並新增登出端點可以主動撤銷 refresh token。

**Architecture:** Access token 維持現況（1 小時、`Authorization: Bearer` header、JSON body）。Refresh token 走 httpOnly + CSRF 保護的 cookie，搭配一張 `refresh_tokens` DB 表記錄 jti/撤銷狀態，實作 rotation（每次換發都作廢舊的、發新的）與重放偵測（用已撤銷的 jti 換發 → 撤銷該使用者所有 refresh token）。撤銷檢查透過 Flask-JWT-Extended 的 `token_in_blocklist_loader`，只對 `type=='refresh'` 的 token 查 DB，access token 不受影響。設計依據：[docs/superpowers/specs/2026-07-15-jwt-refresh-logout-design.md](../specs/2026-07-15-jwt-refresh-logout-design.md)。

**Tech Stack:** Python 3, Flask 3, SQLAlchemy, Flask-JWT-Extended 4.7.4, pytest

**這是認證/安全相關功能**，實作階段建議由 `security-executor` 執行，而不是一般 executor 或主線程直接寫。

**重要技術細節（已在此環境驗證過，寫程式時務必照此假設）：**
- Flask-JWT-Extended 4.7.4 的預設值：refresh cookie 名稱 `refresh_token_cookie`、CSRF cookie 名稱 `csrf_refresh_token`、CSRF header 名稱 `X-CSRF-TOKEN`、`JWT_COOKIE_CSRF_PROTECT` 預設就是 `True`。
- Werkzeug 3.1 test client 的 `client.get_cookie(key, path=...)` 與 `client.set_cookie(key, value, path=...)`，如果 cookie 是用非預設 path（本專案設定 `JWT_REFRESH_COOKIE_PATH = "/api/auth"`）設定的，讀取/覆寫時**必須帶上一樣的 `path` 參數**，否則讀不到／會變成建立了另一個不同 path 的 cookie。已用實際的 Flask app + Werkzeug 3.1.8 test client 驗證過這個行為。
- `app/models/__init__.py` 會把所有 model 的 import 集中在一起；因為 Python import 一個 sub-module（例如 `app.models.user`）之前一定會先執行 package 的 `__init__.py`，只要專案裡任何地方 import 了 `app.models` 底下任何一個 model（現有程式碼在很多地方都有），`app/models/__init__.py` 就會被執行，連帶把新的 `RefreshToken` model 一起註冊進 `db.metadata`。**這是讓 `db.create_all()` 抓得到新表的關鍵**，Task 1 一定要把 `RefreshToken` 加進 `app/models/__init__.py`，不能省略。

---

## Task 1: 資料模型、Config、Blocklist Callback、測試輔助 fixture

**Files:**
- Create: `app/models/refresh_token.py`
- Modify: `app/models/__init__.py`
- Create: `app/utils/jwt_callbacks.py`
- Modify: `app/__init__.py`
- Modify: `config.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_refresh_token.py`

- [ ] **Step 1: 撰寫會失敗的測試 `tests/test_refresh_token.py`**

```python
from datetime import datetime, timedelta, timezone


def test_refresh_token_model_can_be_created(db):
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

    user = User(username='rtuser', email='rtuser@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    token = RefreshToken(
        jti='test-jti-123',
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.session.add(token)
    db.session.commit()

    saved = RefreshToken.query.filter_by(jti='test-jti-123').first()
    assert saved is not None
    assert saved.revoked_at is None
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_refresh_token.py -v
```

Expected: `FAILED`，`ModuleNotFoundError: No module named 'app.models.refresh_token'`

- [ ] **Step 3: 建立 `app/models/refresh_token.py`**

```python
from datetime import datetime, timezone
from app import db


class RefreshToken(db.Model):
    __tablename__ = 'refresh_tokens'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: 更新 `app/models/__init__.py`**

```python
from app.models.user import User
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.inventory_log import InventoryLog
from app.models.refresh_token import RefreshToken
```

- [ ] **Step 5: 建立 `app/utils/jwt_callbacks.py`**

```python
def register_jwt_callbacks(jwt):

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        if jwt_payload.get('type') != 'refresh':
            return False

        from app.models.refresh_token import RefreshToken

        token = RefreshToken.query.filter_by(jti=jwt_payload['jti']).first()
        return token is None or token.revoked_at is not None
```

- [ ] **Step 6: 更新 `app/__init__.py`，註冊 callback**

把：

```python
    jwt.init_app(app)
```

改為：

```python
    jwt.init_app(app)

    from app.utils.jwt_callbacks import register_jwt_callbacks
    register_jwt_callbacks(jwt)
```

- [ ] **Step 7: 更新 `config.py`**

把整個檔案改為：

```python
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///ecommerce.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1 小時
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_REFRESH_COOKIE_PATH = "/api/auth"
    JWT_COOKIE_SAMESITE = "Strict"
    JWT_COOKIE_SECURE = False  # Dev/Testing 沒有 HTTPS


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    JWT_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = 300  # 測試時設置為 5 分鐘


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
```

- [ ] **Step 8: 在 `tests/conftest.py` 新增 `csrf_header` fixture**

在檔案最後新增：

```python

@pytest.fixture
def csrf_header():
    def _make(client):
        cookie = client.get_cookie("csrf_refresh_token", path="/api/auth")
        return {"X-CSRF-TOKEN": cookie.value} if cookie else {}
    return _make
```

- [ ] **Step 9: 執行測試確認通過**

```bash
pytest tests/test_refresh_token.py -v
```

Expected: `PASSED`

- [ ] **Step 10: 執行完整測試套件，確認 Config 變更沒有破壞既有功能**

```bash
pytest -v
```

Expected: 全部 `PASSED`（`JWT_TOKEN_LOCATION` 加入 `cookies`、開啟 `JWT_COOKIE_CSRF_PROTECT` 不影響既有只用 header 的 `@jwt_required()`／`@admin_required()` 路由，因為 CSRF 檢查只在 token 是從 cookie 讀出來時才會觸發）

- [ ] **Step 11: Commit**

```bash
git add app/models/refresh_token.py app/models/__init__.py app/utils/jwt_callbacks.py \
        app/__init__.py config.py tests/conftest.py tests/test_refresh_token.py
git commit -m "feat: add RefreshToken model, JWT cookie config, and revocation blocklist callback"
```

---

## Task 2: 登入時簽發並儲存 refresh token

**Files:**
- Modify: `app/services/auth_service.py`
- Modify: `app/blueprints/auth/routes.py`
- Test: `tests/test_refresh_token.py`

- [ ] **Step 1: 撰寫會失敗的測試**

在 `tests/test_refresh_token.py` 最後新增：

```python
def test_login_sets_refresh_cookie_and_stores_token(client, db):
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

    user = User(username='cookieuser', email='cookieuser@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    resp = client.post('/api/auth/login', json={'email': 'cookieuser@test.com', 'password': 'password123'})
    assert resp.status_code == 200
    assert 'refresh_token_cookie' in resp.headers.get('Set-Cookie', '')

    tokens = RefreshToken.query.filter_by(user_id=user.id).all()
    assert len(tokens) == 1
    assert tokens[0].revoked_at is None


def test_login_response_does_not_leak_refresh_token_in_json(client, db):
    from app.models.user import User

    user = User(username='noleakuser', email='noleak@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    resp = client.post('/api/auth/login', json={'email': 'noleak@test.com', 'password': 'password123'})
    assert 'refresh_token' not in resp.get_json()
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_refresh_token.py -v -k "login_sets_refresh or does_not_leak"
```

Expected: `FAILED`（目前登入不會設 refresh cookie，也不會寫入 `RefreshToken`）

- [ ] **Step 3: 更新 `app/services/auth_service.py`**

把整個檔案改為：

```python
from datetime import datetime, timezone

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token, get_jti

from app import db
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.utils.exceptions import ConflictError, UnauthorizedError, ForbiddenError


def register(data):
    if User.query.filter_by(email=data['email']).first():
        raise ConflictError('此 Email 已被註冊')
    if User.query.filter_by(username=data['username']).first():
        raise ConflictError('此使用者名稱已被使用')

    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return user.to_dict()


def login(data):
    user = User.query.filter_by(email=data['email']).first()
    if not user or not user.check_password(data['password']):
        raise UnauthorizedError('Email 或密碼錯誤')
    if not user.is_active:
        raise ForbiddenError('帳號已被停用')

    access_token = create_access_token(identity=str(user.id), additional_claims={'role': user.role})
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={'role': user.role})
    _store_refresh_token(refresh_token, user.id)

    return {'access_token': access_token, 'refresh_token': refresh_token, 'user': user.to_dict()}


def _store_refresh_token(raw_token, user_id):
    expires_at = datetime.now(timezone.utc) + current_app.config['JWT_REFRESH_TOKEN_EXPIRES']
    db.session.add(RefreshToken(
        jti=get_jti(raw_token),
        user_id=user_id,
        expires_at=expires_at,
    ))
    db.session.commit()
```

- [ ] **Step 4: 更新 `app/blueprints/auth/routes.py`**

把整個檔案改為：

```python
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, set_refresh_cookies

from app.models.user import User
from app.blueprints.auth import auth_bp
from app.blueprints.auth.schemas import RegisterSchema, LoginSchema
from app.services import auth_service
from app.utils.decorators import validate_body


@auth_bp.route('/register', methods=['POST'])
@validate_body(RegisterSchema)
def register(validated_data):
    user = auth_service.register(validated_data)
    return jsonify({'message': '註冊成功', 'user': user}), 201


@auth_bp.route('/login', methods=['POST'])
@validate_body(LoginSchema)
def login(validated_data):
    result = auth_service.login(validated_data)
    response = jsonify({
        'message': '登入成功',
        'access_token': result['access_token'],
        'user': result['user'],
    })
    set_refresh_cookies(response, result['refresh_token'])
    return response


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())
```

（移除了原本 import 但沒用到的 `request` 與 `create_access_token`）

- [ ] **Step 5: 執行測試確認通過**

```bash
pytest tests/test_refresh_token.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 6: 執行完整測試套件**

```bash
pytest -v
```

Expected: 全部 `PASSED`（`tests/test_auth.py` 的既有測試不受影響，因為 JSON 回應格式沒變）

- [ ] **Step 7: Commit**

```bash
git add app/services/auth_service.py app/blueprints/auth/routes.py tests/test_refresh_token.py
git commit -m "feat: issue and persist refresh token on login"
```

---

## Task 3: `/api/auth/refresh` 端點（rotation + 重放偵測 + is_active 檢查）

**Files:**
- Modify: `app/services/auth_service.py`
- Modify: `app/blueprints/auth/routes.py`
- Test: `tests/test_refresh_token.py`

- [ ] **Step 1: 撰寫會失敗的測試**

在 `tests/test_refresh_token.py` 最後新增：

```python
def test_refresh_returns_new_access_token(client, db, csrf_header):
    from app.models.user import User

    user = User(username='refreshuser', email='refresh@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'refresh@test.com', 'password': 'password123'})

    resp = client.post('/api/auth/refresh', headers=csrf_header(client))
    assert resp.status_code == 200
    assert 'access_token' in resp.get_json()


def test_refresh_without_csrf_header_returns_401(client, db):
    from app.models.user import User

    user = User(username='nocsrfuser', email='nocsrf@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'nocsrf@test.com', 'password': 'password123'})

    resp = client.post('/api/auth/refresh')
    assert resp.status_code == 401


def test_refresh_without_cookie_returns_401(client):
    resp = client.post('/api/auth/refresh')
    assert resp.status_code == 401


def test_reused_refresh_token_revokes_all_sessions(client, db):
    from app.models.user import User
    from app.models.refresh_token import RefreshToken

    user = User(username='reuseuser', email='reuse@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'reuse@test.com', 'password': 'password123'})
    old_refresh_cookie = client.get_cookie('refresh_token_cookie', path='/api/auth')
    old_csrf_cookie = client.get_cookie('csrf_refresh_token', path='/api/auth')
    first_headers = {'X-CSRF-TOKEN': old_csrf_cookie.value}

    first_resp = client.post('/api/auth/refresh', headers=first_headers)
    assert first_resp.status_code == 200

    # 把 cookie jar 改回「舊的」refresh token，模擬 token 被偷後重複使用
    client.set_cookie('refresh_token_cookie', old_refresh_cookie.value, path='/api/auth')
    client.set_cookie('csrf_refresh_token', old_csrf_cookie.value, path='/api/auth')

    reused_resp = client.post('/api/auth/refresh', headers=first_headers)
    assert reused_resp.status_code == 401

    tokens = RefreshToken.query.filter_by(user_id=user.id).all()
    assert all(t.revoked_at is not None for t in tokens)


def test_refresh_rejected_for_deactivated_user(client, db, csrf_header):
    from app.models.user import User

    user = User(username='deactivateduser', email='deactivated@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'deactivated@test.com', 'password': 'password123'})

    user.is_active = False
    db.session.commit()

    resp = client.post('/api/auth/refresh', headers=csrf_header(client))
    assert resp.status_code == 403
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_refresh_token.py -v -k "refresh_returns or refresh_without or reused or deactivated"
```

Expected: 大部分 `FAILED`（`/api/auth/refresh` 路由還不存在，回 404）

- [ ] **Step 3: 在 `app/services/auth_service.py` 新增 `refresh` 函式**

在檔案最後新增：

```python

def refresh(user_id, jti):
    token_record = RefreshToken.query.filter_by(jti=jti).first()

    if token_record is None or token_record.revoked_at is not None:
        RefreshToken.query.filter_by(user_id=user_id, revoked_at=None).update(
            {'revoked_at': datetime.now(timezone.utc)}
        )
        db.session.commit()
        raise UnauthorizedError('Refresh token 無效，請重新登入')

    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        raise ForbiddenError('帳號已被停用')

    token_record.revoked_at = datetime.now(timezone.utc)

    access_token = create_access_token(identity=str(user_id), additional_claims={'role': user.role})
    new_refresh_token = create_refresh_token(identity=str(user_id), additional_claims={'role': user.role})
    _store_refresh_token(new_refresh_token, user_id)

    db.session.commit()
    return {'access_token': access_token, 'refresh_token': new_refresh_token}
```

- [ ] **Step 4: 在 `app/blueprints/auth/routes.py` 新增 `/refresh` route**

把 import 區塊改為：

```python
from flask import jsonify
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_refresh_cookies,
)

from app.models.user import User
from app.blueprints.auth import auth_bp
from app.blueprints.auth.schemas import RegisterSchema, LoginSchema
from app.services import auth_service
from app.utils.decorators import validate_body
```

在檔案最後新增：

```python

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    user_id = int(get_jwt_identity())
    jti = get_jwt()['jti']
    result = auth_service.refresh(user_id, jti)
    response = jsonify({'access_token': result['access_token']})
    set_refresh_cookies(response, result['refresh_token'])
    return response
```

- [ ] **Step 5: 執行測試確認全部通過**

```bash
pytest tests/test_refresh_token.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 6: 執行完整測試套件**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [ ] **Step 7: Commit**

```bash
git add app/services/auth_service.py app/blueprints/auth/routes.py tests/test_refresh_token.py
git commit -m "feat: add /api/auth/refresh with token rotation and reuse detection"
```

---

## Task 4: `/api/auth/logout` 端點

**Files:**
- Modify: `app/services/auth_service.py`
- Modify: `app/blueprints/auth/routes.py`
- Test: `tests/test_refresh_token.py`

- [ ] **Step 1: 撰寫會失敗的測試**

在 `tests/test_refresh_token.py` 最後新增：

```python
def test_logout_revokes_token_and_clears_cookie(client, db, csrf_header):
    from app.models.user import User
    from app.models.refresh_token import RefreshToken

    user = User(username='logoutuser', email='logout@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'logout@test.com', 'password': 'password123'})

    resp = client.post('/api/auth/logout', headers=csrf_header(client))
    assert resp.status_code == 200

    tokens = RefreshToken.query.filter_by(user_id=user.id).all()
    assert all(t.revoked_at is not None for t in tokens)
    assert client.get_cookie('refresh_token_cookie', path='/api/auth') is None


def test_refresh_after_logout_returns_401(client, db, csrf_header):
    from app.models.user import User

    user = User(username='postlogoutuser', email='postlogout@test.com', role='user')
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()

    client.post('/api/auth/login', json={'email': 'postlogout@test.com', 'password': 'password123'})
    headers = csrf_header(client)
    client.post('/api/auth/logout', headers=headers)

    resp = client.post('/api/auth/refresh', headers=headers)
    assert resp.status_code == 401
```

- [ ] **Step 2: 執行測試確認會失敗**

```bash
pytest tests/test_refresh_token.py -v -k "logout"
```

Expected: `FAILED`（`/api/auth/logout` 路由還不存在，回 404）

- [ ] **Step 3: 在 `app/services/auth_service.py` 新增 `logout` 函式**

在檔案最後新增：

```python

def logout(jti):
    token_record = RefreshToken.query.filter_by(jti=jti).first()
    if token_record and token_record.revoked_at is None:
        token_record.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
```

- [ ] **Step 4: 在 `app/blueprints/auth/routes.py` 新增 `/logout` route**

把 import 區塊改為：

```python
from flask import jsonify
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    get_jwt,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from app.models.user import User
from app.blueprints.auth import auth_bp
from app.blueprints.auth.schemas import RegisterSchema, LoginSchema
from app.services import auth_service
from app.utils.decorators import validate_body
```

在檔案最後新增：

```python

@auth_bp.route('/logout', methods=['POST'])
@jwt_required(refresh=True)
def logout():
    jti = get_jwt()['jti']
    auth_service.logout(jti)
    response = jsonify({'message': '登出成功'})
    unset_jwt_cookies(response)
    return response
```

- [ ] **Step 5: 執行測試確認全部通過**

```bash
pytest tests/test_refresh_token.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 6: 執行完整測試套件，確認整個專案沒有回歸**

```bash
pytest -v
```

Expected: 全部 `PASSED`

- [ ] **Step 7: Commit**

```bash
git add app/services/auth_service.py app/blueprints/auth/routes.py tests/test_refresh_token.py
git commit -m "feat: add /api/auth/logout to revoke refresh token"
```

---

## 完成後需要手動處理的事（不在自動化步驟內）

這個環境沒有連到 `.env` 設定的實際 Postgres，所以計畫沒有自動產生 migration。全部 Task 完成後，需要在有連線到真正開發用資料庫的環境手動執行：

```bash
flask db migrate -m "add refresh_tokens table"
flask db upgrade
```

## 完成後的變更總覽

```
app/
├── models/
│   ├── refresh_token.py      (new)
│   └── __init__.py           (+RefreshToken import)
├── utils/
│   └── jwt_callbacks.py      (new: token_in_blocklist_loader)
├── services/
│   └── auth_service.py       (+refresh, +logout, login 改為同時發 refresh token)
├── blueprints/
│   └── auth/
│       └── routes.py         (+POST /refresh, +POST /logout, login 改設 refresh cookie)
└── __init__.py                (註冊 jwt_callbacks)
config.py                      (+JWT cookie/CSRF/refresh 相關設定)
tests/
├── conftest.py                (+csrf_header fixture)
└── test_refresh_token.py      (new: 12 個測試)
```
