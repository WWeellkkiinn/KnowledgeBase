"""Flask app factory（PLAN.md §4 M1.5）。

最小骨架：REST 蓝图 + 占位首页 + Socket.IO 实例（M1.6 真正绑事件）。
单用户场景，默认监听 127.0.0.1:5000；CORS 仅放行 Vite dev server。
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets

from flask import Flask, Response, abort, g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
from werkzeug.middleware.proxy_fix import ProxyFix

from database import SessionLocal


# CORS allowlist 支持环境变量覆盖；默认放行 Vite dev 的 localhost 与 127.0.0.1。
# 公网部署时通过 KB_CORS_ORIGINS=https://你的cpolar.cn 覆盖（多值用逗号分隔）。
_DEFAULT_CORS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_CORS = os.environ.get("KB_CORS_ORIGINS")
_CORS_LIST = [s.strip() for s in _CORS.split(",") if s.strip()] if _CORS else _DEFAULT_CORS

socketio = SocketIO(cors_allowed_origins=_CORS_LIST, async_mode="threading")

# 公网部署速率限制：按客户端 IP 配额，重端点用 @limiter.limit 单独覆盖。
# cpolar 隧道透传真实公网 IP 到 X-Forwarded-For，get_remote_address 已识别。
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120 per minute"],
    storage_uri="memory://",
)


# 鉴权白名单：未带 token 也可访问的 path。
# 设计：浏览器 HTML 导航请求（GET 任意 SPA 路由）没法带 Authorization 头，
# 必须放行让 index.html 加载，再由前端 JS 从 localStorage 取 token 调 /api/*。
# 因此规则是：所有非 /api/* 且非 /socket.io/* 的 GET 都豁免鉴权，
# API 端点和 Socket.IO 仍走严格 Bearer 校验。
_AUTH_PROTECTED_PREFIXES = ("/api/", "/socket.io/")


def _is_auth_exempt(method: str, path: str) -> bool:
    # 任何受保护前缀（API / Socket.IO）都要走鉴权
    if path.startswith(_AUTH_PROTECTED_PREFIXES):
        return False
    # 其它路径如果是 GET（HTML 导航 / 静态资源），放行让 SPA 自行处理
    return method == "GET"


def _unauthorized() -> Response:
    """构造带 WWW-Authenticate 头的 401 响应（RFC 6750）。"""
    resp = Response(
        '{"error":"unauthorized"}',
        status=401,
        mimetype="application/json",
    )
    resp.headers["WWW-Authenticate"] = 'Bearer realm="KnowledgeBase"'
    return resp


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    # SECRET_KEY 必须设置：flask-socketio polling transport 与未来 Flask session
    # 都依赖；优先读环境变量，开发期 fallback 到随机 key（重启后失效，符合 dev 预期）。
    app.config["SECRET_KEY"] = os.environ.get("KB_SECRET_KEY") or secrets.token_hex(32)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    # 默认不启动 APScheduler（避免测试场景下意外起线程）；正式入口 scripts/serve.py
    # 显式打开 KB_ENABLE_SCHEDULER=1
    app.config["KB_ENABLE_SCHEDULER"] = (
        os.environ.get("KB_ENABLE_SCHEDULER") == "1"
    )
    # 公网部署时单请求体上限，防止大包打爆内存（默认 256KB；上传走专门端点另议）。
    # 非数字值时回退默认，避免启动崩溃。
    _raw_max = os.environ.get("KB_MAX_CONTENT_LENGTH", str(256 * 1024))
    try:
        app.config["MAX_CONTENT_LENGTH"] = int(_raw_max)
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning(
            "invalid KB_MAX_CONTENT_LENGTH=%r, fallback to 256KB", _raw_max
        )
        app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    app.config.update(config or {})

    # 公网通过 cpolar 隧道转发到 127.0.0.1，真实客户端 IP 在 X-Forwarded-For。
    # 仅当显式启用时挂 ProxyFix，避免本地 dev 信任任意 header 导致 IP 伪造。
    if os.environ.get("KB_TRUST_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # limiter 必须在 before_request 鉴权之前 init，确保 401 路径也计入默认限流，
    # 防止攻击者无限重试爆破 Bearer token。
    limiter.init_app(app)

    @app.before_request
    def _require_bearer_token():
        """全局 Bearer 鉴权：未设 KB_API_TOKEN 时为 dev mode 全放行；
        设了之后除白名单外所有路径都必须带 Authorization: Bearer <token>。"""
        expected = os.environ.get("KB_API_TOKEN")
        if not expected:
            return  # 本地 dev：未配置即放行
        if _is_auth_exempt(request.method, request.path):
            return
        auth = request.headers.get("Authorization", "")
        # HTTP scheme 大小写不敏感（RFC 7235 §2.1）：用 split 解析
        parts = auth.split(None, 1)
        provided = ""
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided = parts[1].strip()
        if not provided or not hmac.compare_digest(provided, expected):
            return _unauthorized()

    @app.errorhandler(401)
    def _handle_401(_err):
        """兜底：任何 abort(401) 也带上 WWW-Authenticate。"""
        return _unauthorized()

    @app.after_request
    def _security_headers(resp: Response) -> Response:
        """全局安全响应头：MIME sniff / clickjacking / Referer / CSP。

        style-src 必须含 'unsafe-inline'（Vite 打包后 CSS 含 inline style）；
        script-src 不放 'unsafe-inline'，避免 XSS 注入脚本执行。
        """
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "img-src 'self' data: https:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; "
                "connect-src 'self' ws: wss:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'"
            ),
        )
        return resp

    @app.before_request
    def _open_session():
        g.db = SessionLocal()

    @app.teardown_request
    def _close_session(exc=None):
        """teardown 只负责 rollback + close。

        路由写入必须显式 `g.db.commit()`；M1.5 当前路由全部只读，所以这里不再
        隐式提交，避免后续路由捕获异常返回 200 时把脏写入意外落库。
        """
        db = g.pop("db", None)
        if db is None:
            return
        try:
            if exc is not None:
                db.rollback()
        finally:
            db.close()

    from .routes.api import bp as api_bp
    from .routes.pages import bp as pages_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(pages_bp)

    socketio.init_app(app)
    # 注册 socket handlers
    from .sockets import progress as _progress  # noqa: F401

    if app.config.get("KB_ENABLE_SCHEDULER"):
        from services.subscription_service import start_scheduler
        start_scheduler()
        _start_journal_backfill()

    return app


def _start_journal_backfill() -> None:
    """启动后台线程，对核心论文中有 DOI 但无期刊的条目调 OpenAlex 补全。"""
    import threading as _threading

    def _run() -> None:
        import logging as _logging
        _log = _logging.getLogger(__name__)
        try:
            from services.journal_service import JournalService
            svc = JournalService()
            session = SessionLocal()
            try:
                svc.bootstrap_from_seed(session)
                session.commit()  # seed 独立提交，与 backfill 事务隔离
                result = svc.backfill_journals(session)
                _log.info("journal backfill: %s", result)
            finally:
                session.close()
        except Exception:
            _log.exception("journal backfill thread failed")

    _threading.Thread(target=_run, daemon=True, name="journal-backfill").start()


__all__ = ["create_app", "socketio"]
