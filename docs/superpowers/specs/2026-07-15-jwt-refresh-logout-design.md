# JWT Refresh Token / 登出機制 Design

**Status:** Approved
**Date:** 2026-07-15

## 背景與目標

目前 `POST /api/auth/login` 只發一個 1 小時效期的 access token（`config.py:12` `JWT_ACCESS_TOKEN_EXPIRES = 3600`），過期後使用者只能重新輸入帳密登入，也沒有「登出」端點可以主動讓 token 失效。本次新增：
1. Refresh token 機制，讓使用者不用每小時重新登入
2. 登出端點，可以撤銷 refresh token

**Client 假設：** 主要消費者是瀏覽器 SPA 前端。

## 核心設計決策

1. **Access token 維持現況**：1 小時效期、走 `Authorization: Bearer` header、JSON body 回傳（`login`/`refresh` 都回）。既有的 `@jwt_required()`／`@admin_required()`／所有既有測試不受影響。
2. **Refresh token 走 httpOnly cookie**：30 天效期，`httpOnly + Secure(production) + SameSite=Strict`，cookie path 限定在 `/api/auth`（只有這個路徑下的請求會帶到這個 cookie）。**絕不**在 JSON response body 中回傳 refresh token 明文——否則等於繞過 httpOnly 保護。
3. **CSRF 防護**：用 Flask-JWT-Extended 內建的 `JWT_COOKIE_CSRF_PROTECT`（不手刻）。設定後，`set_refresh_cookies()` 會額外設一個「JS 可讀」的 CSRF cookie，前端要把值複製到 `X-CSRF-TOKEN` header 才能呼叫 `/refresh`、`/logout`。
4. **Rotation + 竊用偵測**：每次呼叫 `/refresh` 換發新 access token 時，同時撤銷目前這個 refresh token（標記 `revoked_at`）、發一組新的（新 jti）。如果偵測到「已撤銷的 jti 被重複使用」→ 視為 token 被偷，撤銷該使用者名下所有 refresh token（強制所有裝置登出）。
5. **撤銷檢查只查 refresh token，不查 access token**：用 Flask-JWT-Extended 的 `token_in_blocklist_loader`，對 `type != 'refresh'` 的 token 直接回傳 `False`（不查 DB），維持「access token 到期前都有效，不用每次 API 請求多一次 DB 查詢」的既有取捨。
6. **Refresh 時重新檢查 `is_active`**：若使用者在拿到 refresh token 之後被 admin 停用帳號，`/refresh` 要擋下來，不能讓已停用帳號一直用舊 refresh token 換新 access token。

## 資料模型

**新增：** `app/models/refresh_token.py`

```python
class RefreshToken(db.Model):
    __tablename__ = 'refresh_tokens'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
```

不需要 `to_dict()`——這張表只做內部撤銷/查核用，從不透過 API 回傳。

**Migration：** 這次計畫只會用 `db.create_all()` 讓測試套件過（pytest 用 in-memory SQLite，每次都重建 schema），不會在計畫裡自動跑 `flask db migrate`（因為需要連到 `.env` 設定的實際 Postgres，這個環境不一定連得到）。計畫最後會提醒手動執行：

```bash
flask db migrate -m "add refresh_tokens table"
flask db upgrade
```

## API 變更

### `POST /api/auth/login`（修改）

行為不變（仍回 `{"message":..., "access_token":..., "user":...}`），但額外：
- 呼叫 `create_refresh_token()` 產生 refresh token
- 寫入一筆 `RefreshToken` 紀錄
- 用 `set_refresh_cookies(response, refresh_token)` 把 refresh token 設成 httpOnly cookie（連同 CSRF cookie 一起設）

### `POST /api/auth/refresh`（新增）

- `@jwt_required(refresh=True)`：從 cookie 讀 refresh token，驗證簽章/效期，並觸發 `token_in_blocklist_loader` 查撤銷狀態
- CSRF 保護自動套用（POST 屬於受保護方法）
- Service 邏輯：
  1. 查 `RefreshToken` 是否存在且未撤銷 → 若已撤銷或不存在，視為重用攻擊，撤銷該 user 名下所有 refresh token，回 401
  2. 檢查 `user.is_active`，False 則回 403
  3. 撤銷目前這個 jti（`revoked_at = now`）
  4. 發新的 access token + 新的 refresh token（新 jti），寫入新紀錄
  5. Response：JSON 回新的 `access_token`；`set_refresh_cookies()` 更新 cookie

### `POST /api/auth/logout`（新增）

- `@jwt_required(refresh=True)`：同樣從 cookie 讀 refresh token
- Service 邏輯：撤銷目前這個 jti
- Response：`unset_jwt_cookies(response)` 清掉 cookie，回 `{"message": "登出成功"}`

## Config 變更

```python
class Config:
    ...
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 維持 1 小時
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_REFRESH_COOKIE_PATH = '/api/auth'
    JWT_COOKIE_SAMESITE = 'Strict'
    JWT_COOKIE_SECURE = False  # Dev/Testing 沒有 HTTPS


class ProductionConfig(Config):
    DEBUG = False
    JWT_COOKIE_SECURE = True
```

`TestingConfig` 不覆寫 `JWT_COOKIE_CSRF_PROTECT`——測試也要驗證 CSRF 保護真的有效，不能為了省事關掉安全機制。

## Blocklist Callback

**新增：** `app/utils/jwt_callbacks.py`

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

在 `app/__init__.py` 的 `jwt.init_app(app)` 之後呼叫 `register_jwt_callbacks(jwt)`。

## 測試計畫

**測試環境的特殊處理：** Flask 測試 client 的 cookie jar 會在同一個 `client` fixture 的多次呼叫間自動保留 cookie（包含 `Path` 限定的 refresh cookie）。CSRF header 需要測試程式自己從 cookie jar 讀出 CSRF cookie 值，組成 `X-CSRF-TOKEN` header 帶入 `/refresh`、`/logout` 請求。

- 登入成功會設定 refresh cookie
- 用有效 refresh cookie + 正確 CSRF header 呼叫 `/refresh` → 200，拿到新 access token，refresh cookie 也換新
- `/refresh` 沒帶 CSRF header → 401（CSRF 防護生效）
- 用同一個 refresh token 呼叫 `/refresh` 兩次（模擬重放）→ 第二次應回 401，且該使用者名下所有 refresh token 都被撤銷（用第一次拿到的新 refresh token 再打一次 `/refresh` 也應該失敗）
- 帳號被停用後，用該帳號原本的 refresh token 呼叫 `/refresh` → 403
- `/logout` 成功撤銷目前 refresh token，之後再用同一個 token 呼叫 `/refresh` → 401
- 沒有 refresh cookie 呼叫 `/refresh`／`/logout` → 401
- 既有的 `/api/auth/login`、`/api/auth/me`、以及所有既有測試（`test_auth.py` 等）行為不變，全部維持通過

## 已知限制（不在本次範圍）

- 沒有「查看/撤銷指定裝置的 session 列表」這種帳號管理 UI，只有「撤銷單一 token」與「竊用偵測時撤銷全部」兩種操作
- `refresh_tokens` 表不會自動清理過期資料（沒有定期清除 job），長期執行資料量會累積，之後有需要再加 cleanup 機制
