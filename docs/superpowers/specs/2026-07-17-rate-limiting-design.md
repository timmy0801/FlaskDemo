# Rate Limiting Design

**Status:** Approved
**Date:** 2026-07-17

## 背景與目標

`/api/auth/login`、`/api/auth/register` 目前沒有任何請求頻率限制，容易被暴力破解密碼或灌大量假帳號。目標是替這兩個端點加上 rate limiting，不影響其他端點。

## 技術驗證（已在此環境實測）

用 `Flask-Limiter`（安裝時解析到 4.1.1）在一個模擬 `login` route 的最小 Flask app 上實測：
- 自訂 `key_func` 組合 `IP + email`（從 `request.get_json()` 讀 email），連續打同一個 email 5 次，第 4、5 次正確被擋（429），換一個 email（同 IP）馬上又能打通——確認「同 IP 多使用者互不影響」的設計目標成立。
- 自訂 `@app.errorhandler(429)` 能正確攔截 Flask-Limiter 拋出的例外，改寫成專案既有的 `{"error": "..."}` JSON 格式。
- `pip install --dry-run flask-limiter` 對現有的 Flask 3.1.3 / marshmallow 4.3.0 環境沒有版本衝突。

## 核心設計決策

1. **只保護 `/api/auth/login` 與 `/api/auth/register`**，其他端點都需要有效 JWT 或 admin 權限才能呼叫，被濫用風險低很多，不在這次範圍內。
2. **`login`：`5 次/分鐘`，key 為 `IP + email` 組合**（`f'{get_remote_address()}:{email}'`）。理由：純 IP-based 會讓同一個 IP 後面的其他使用者（公司網路、NAT）被一個帳號的爆破攻擊連坐鎖住；用 `IP+email` 組合可以讓限制精準命中「同一來源打同一個帳號」，不影響同 IP 打不同帳號的正常使用者。
   - 已知取捨：這個 key 策略對「同一 IP 大量嘗試『不同』帳號」（帳號列舉/噴射攻擊）的防護較弱，因為每個 (IP, email) 組合都有自己獨立的計數。這次先不處理，之後如果有這類攻擊的實際需求，可以另外疊加一層純 IP-based 的全域限制。
3. **`register`：`5 次/小時`，key 為純 IP**。理由：register 沒有「保護既有帳號不被爆破」的需求，這裡真正要防的是「同一來源短時間內灌大量假帳號」，純 IP-based 剛好對症。
4. **儲存後端：in-memory（`storage_uri="memory://"`）**，不引入 Redis。已知限制：如果之後 production 用 gunicorn 多 worker process 部署，每個 worker 會有自己獨立的計數器，實際限制效果會變成「門檻 × worker 數」而不是精確的全域限制。這次先接受這個誤差（demo 專案、目前本來就是單 process 的 `flask run`），不現在額外引入 Redis。
5. **429 回應格式**：自訂 `@app.errorhandler(429)`，統一改成 `{"error": "請求過於頻繁，請稍後再試"}`，跟現有 `error_handler.py` 裡其他 handler 的風格一致（不用 Flask-Limiter 預設的錯誤訊息格式）。
6. **物件生命週期**：仿照專案既有的 `db`/`migrate`/`jwt` pattern——在 `app/__init__.py` 建立模組層級的 `limiter = Limiter(key_func=get_remote_address)`（沒有綁定 app），`create_app()` 裡呼叫 `limiter.init_app(app)`。`login`/`register` 的 `@limiter.limit(...)` decorator 在 blueprint 模組被 import 時就會套用（在 `limiter.init_app()` 執行之前），這是 Flask-Limiter officially 支援的 app-factory 用法，跟這個專案其他 Flask extension 的初始化方式一致。

## 檔案配置

**修改：**
- `requirements.txt`：新增 `flask-limiter`
- `app/__init__.py`：新增模組層級 `limiter = Limiter(key_func=get_remote_address)`；`create_app()` 裡呼叫 `limiter.init_app(app)`（放在 `jwt.init_app(app)` 附近即可，跟 blueprint 註冊順序無關，因為 decorator 在 import 當下就已經掛好了，`init_app` 只是把 limiter 跟這個 app instance 綁定，不影響 decorator 是否生效）
- `app/middleware/error_handler.py`：新增 `@app.errorhandler(429)` handler
- `app/blueprints/auth/routes.py`：`login`、`register` 各自加上 `@limiter.limit(...)`（`login` 額外指定自訂 `key_func`）

**Decorator 順序**（rate limit 檢查要在 body 驗證之前執行，避免浪費運算在會被拒絕的請求上）：
```python
@auth_bp.route('/login', methods=['POST'])
@limiter.limit('5 per minute', key_func=login_rate_limit_key)
@validate_body(LoginSchema)
def login(validated_data):
    ...
```

`login_rate_limit_key` 這個 function 定義在 `app/blueprints/auth/routes.py` 裡（不需要额外的檔案），直接 `request.get_json(silent=True)` 讀 email——這跟 `validate_body` decorator 各自呼叫一次 `request.get_json()` 沒有效能疑慮，因為 Flask 本身會 cache 解析結果，不會真的重複解析兩次。

## 測試計畫

**測試環境的特殊處理（已修正）：** 原本以為 Flask-Limiter 的 in-memory storage 是跨整個測試進程共用的全域狀態，需要在 conftest 手動 reset。實際寫這份 spec 的過程中用「每次都重新 `create_app()`，重用同一個已經在 blueprint 裡被 decorate 過的 view function，不呼叫任何 reset」的方式連續模擬了 3 輪（完全比照這個專案 `tests/conftest.py` 的 `app` fixture 每個測試都重新 `create_app("testing")` 的模式），對 `login`（自訂 `IP+email` key）跟 `register`（純 IP key）都測過：**每一輪都獨立重新從 0 開始計數，完全沒有跨輪次污染**，不需要額外的 reset 步驟。這個結論比原本的假設更好——不需要在 conftest 加任何東西。

- 連續打 `login` 超過 5 次（同一組 email/IP）→ 第 6 次開始回 429，格式是 `{"error": "..."}`
- 換一個 email（模擬同 IP 不同使用者）→ 不受前一個 email 的計數影響，正常回應
- 連續打 `register` 超過 5 次（同 IP，不同 email）→ 第 6 次開始回 429（因為 register 是純 IP-based，不看 email）
- 未超過門檻時，行為完全不變（既有的 register/login 測試應該維持全部通過，不需要因為加了 rate limit 而受影響——因為現有測試套件裡同一個 email/IP 的登入/註冊呼叫次數都遠低於 5 次的門檻）

## 已知限制（不在本次範圍）

- 沒有處理「同一 IP 大量嘗試不同帳號」的帳號列舉/噴射攻擊防護（見決策 2 的取捨說明）
- In-memory storage 在多 worker 部署下的限制不精確（見決策 4）
- 沒有做「超過門檻後逐步拉長鎖定時間」（progressive backoff）這種更進階的機制，固定時間窗口重置
