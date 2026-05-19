"""Flask app factory（PLAN.md §4 M1.5）。

最小骨架：REST 蓝图 + 占位首页 + Socket.IO 实例（M1.6 真正绑事件）。
单用户场景，默认监听 127.0.0.1:5000；CORS 仅放行 Vite dev server。
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets
import sys
import threading

from flask import Flask, Response, abort, g, request
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
from werkzeug.middleware.proxy_fix import ProxyFix

from database import SessionLocal, init_sqlite


# CORS allowlist 支持环境变量覆盖；默认放行 Vite dev 的 localhost 与 127.0.0.1。
# 公网部署时通过 KB_CORS_ORIGINS=https://你的域名 覆盖（多值用逗号分隔）。
_DEFAULT_CORS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_CORS = os.environ.get("KB_CORS_ORIGINS")
_CORS_LIST = [s.strip() for s in _CORS.split(",") if s.strip()] if _CORS else _DEFAULT_CORS

socketio = SocketIO(cors_allowed_origins=_CORS_LIST, async_mode="threading")

# 公网部署速率限制：按客户端 IP 配额，重端点用 @limiter.limit 单独覆盖。
# 上游反向代理（nginx 等）透传真实公网 IP 到 X-Forwarded-For，get_remote_address 已识别。
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
    init_sqlite()
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
    # MAX_CONTENT_LENGTH 设为最大需求（默认 60MB，覆盖 50MB 上传 + multipart 头）。
    # 单独的"非上传路径仍按 256KB 限"策略由 before_request `_limit_non_upload_body` 实现，
    # 把 DoS 面收回到 256KB —— 仅 /papers/upload 享受 60MB 配额。
    _upload_cap = 60 * 1024 * 1024
    _raw_max = os.environ.get("KB_MAX_CONTENT_LENGTH", str(_upload_cap))
    try:
        app.config["MAX_CONTENT_LENGTH"] = int(_raw_max)
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning(
            "invalid KB_MAX_CONTENT_LENGTH=%r, fallback to %d bytes",
            _raw_max, _upload_cap,
        )
        app.config["MAX_CONTENT_LENGTH"] = _upload_cap
    app.config.update(config or {})

    # 非上传路径的请求体上限：DoS 面收紧到 256KB。
    _NON_UPLOAD_BODY_LIMIT = 256 * 1024
    _UPLOAD_PATH = "/api/papers/upload"

    # 多 worker 守卫：flask-limiter memory:// 与 _digest_lock(threading.Lock) 均假定
    # 单 worker，gunicorn/uwsgi 多 worker 下计数与锁会失效。
    # 检测策略：
    #   1) sys.modules 里出现 gunicorn / uwsgi 模块 —— 命令行 `gunicorn -w N` 启动
    #      时 worker 进程加载 app 必经此路径，无法绕过；
    #   2) 兜底再看 SERVER_SOFTWARE / GUNICORN_CMD_ARGS env，覆盖反代/容器场景。
    # 绕过路径（已知且安全）：socketio.run / scripts/serve.py 通过 `import app` 直接
    # 创建单进程实例，gunicorn 模块未加载，环境变量也未设，不触发守卫。
    if os.environ.get("KB_ALLOW_MULTI_WORKER") != "1":
        _server_software = os.environ.get("SERVER_SOFTWARE", "").lower()
        _gunicorn_args = os.environ.get("GUNICORN_CMD_ARGS", "")
        _multi_worker_detected = (
            "gunicorn" in sys.modules
            or "uwsgi" in sys.modules
            or "gunicorn" in _server_software
            or "uwsgi" in _server_software
            or bool(_gunicorn_args)
        )
        if _multi_worker_detected:
            raise RuntimeError(
                "Detected gunicorn/uwsgi multi-worker env but rate limiter uses "
                "memory:// and locks are in-process; set KB_ALLOW_MULTI_WORKER=1 "
                "to override after switching to a shared storage backend."
            )
        else:
            logging.getLogger(__name__).warning(
                "single-worker assumption: memory:// limiter & threading locks; "
                "do NOT run under gunicorn/uwsgi multi-worker without KB_ALLOW_MULTI_WORKER=1"
            )

    # 公网通过反向代理（nginx）转发到 app:5000，真实客户端 IP 在 X-Forwarded-For。
    # 仅当显式启用时挂 ProxyFix，避免本地 dev 信任任意 header 导致 IP 伪造。
    if os.environ.get("KB_TRUST_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Flask 生产模式默认 logger level=WARNING；XFF sentinel 用 INFO 写日志，
    # 需要抬级别并保证至少挂一个 handler（gunicorn 之外的入口可能没默认 handler，
    # 此时 INFO 日志会被丢弃）。
    if app.logger.level == 0 or app.logger.level > logging.INFO:
        app.logger.setLevel(logging.INFO)
    if not app.logger.handlers:
        app.logger.addHandler(logging.StreamHandler())

    # XFF sentinel 一次性记录：用 threading.Event 做原子 "test-and-set"，
    # 避免 dict 读写在多线程下出现重复打印或丢失。
    _xff_logged = threading.Event()

    # limiter 必须在 before_request 鉴权之前 init，确保 401 路径也计入默认限流，
    # 防止攻击者无限重试爆破 Bearer token。
    # gzip / brotli 压缩：默认对 JSON 等可压缩 MIME 启用。
    # MIN_SIZE 1024：小响应（health/stats 等几百字节 JSON）跳过压缩省 CPU
    # LEVEL 4：比默认 6 快 ~30%，压缩率仅差 1-2%，对中等大小 JSON 性价比更高
    app.config.setdefault("COMPRESS_MIN_SIZE", 1024)
    app.config.setdefault("COMPRESS_LEVEL", 4)
    app.config.setdefault("COMPRESS_MIMETYPES", [
        "application/json",
        "application/javascript",
        "text/html",
        "text/css",
        "text/plain",
        "text/javascript",
        "text/xml",
        "image/svg+xml",
    ])
    Compress(app)

    limiter.init_app(app)

    @app.before_request
    def _limit_non_upload_body():
        """非上传路径按 256KB 早拒绝，不让 60MB 大包侵蚀 JSON 端点。

        仅在 Content-Length 已知时拦；chunked transfer 走默认 MAX_CONTENT_LENGTH。
        """
        if request.path == _UPLOAD_PATH:
            return
        cl = request.content_length
        if cl is not None and cl > _NON_UPLOAD_BODY_LIMIT:
            return Response(
                '{"error":"request body too large for this endpoint"}',
                status=413, mimetype="application/json",
            )

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

    @app.after_request
    def _log_xff_once(resp: Response) -> Response:
        # 放在鉴权之后（after_request 一定在 before_request 全过之后才运行），
        # 且只在非 401 响应里记录，避免未鉴权探测请求也写日志被攻击者刷屏。
        # 用 Event.is_set/set 保证多线程下只触发一次。
        if resp.status_code == 401 or _xff_logged.is_set():
            return resp
        if not _xff_logged.is_set():
            # set() 返回 None，无 test-and-set 原子原语；多线程下偶有重复打印
            # 不影响功能（远比丢失安全）。设置后续 if 立即生效。
            _xff_logged.set()
            raw_xff = request.headers.get("X-Forwarded-For", "<absent>")
            # 防日志注入：截断 + 剥离 CR/LF + 控制字符替换为 '?'
            xff = raw_xff[:64].replace("\r", "").replace("\n", "")
            xff = "".join(c if (c == "\t" or 32 <= ord(c) < 127) else "?" for c in xff)
            remote = (request.remote_addr or "<unknown>")[:64]
            remote = "".join(
                c if (c == "\t" or 32 <= ord(c) < 127) else "?" for c in remote
            )
            app.logger.info(
                "XFF sentinel: X-Forwarded-For=%s, Remote-IP=%s, trust_proxy=%s",
                xff, remote, os.environ.get("KB_TRUST_PROXY") == "1",
            )
        return resp

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
        # 强制类（嗅探/点击劫持/Referer）：直接赋值，避免被上游/蓝图弱化。
        # 这些头没有合法的"路由级豁免"诉求，统一强制更安全。
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # 策略类（CSP）：用 setdefault，允许未来 docs/swagger 等特殊路由按需放宽
        # （它们通常需要 inline script / 远程 CDN），由具体路由自负安全责任。
        # CSP 收紧：
        # - img-src 去掉 https:，防止 XSS 通过 <img src=https://attacker/?token=...> 外发
        # - connect-src 去掉 ws:/wss:，Socket.IO 同源即可，不需要外站 ws
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'",
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
        from services.scheduler_service import start_scheduler
        start_scheduler()
        _start_journal_backfill()

    # 上传后台 worker：单进程单线程消费 tasks.type="upload_pipeline"。
    # 多 worker 进程下 fetch_next 无 SELECT FOR UPDATE 会重复领取同一任务，
    # 因此当 KB_ALLOW_MULTI_WORKER=1 时直接不启动 worker（必须有人显式跑独立 worker 进程）。
    # 测试场景：KB_DISABLE_UPLOAD_WORKER=1 跳过（避免 fixture 残留线程）。
    if (
        os.environ.get("KB_DISABLE_UPLOAD_WORKER") != "1"
        and os.environ.get("KB_ALLOW_MULTI_WORKER") != "1"
    ):
        from services.upload_worker import start_worker as _start_upload_worker
        _start_upload_worker()
    elif os.environ.get("KB_ALLOW_MULTI_WORKER") == "1":
        logging.getLogger(__name__).warning(
            "KB_ALLOW_MULTI_WORKER=1 → upload-worker NOT started in this process; "
            "run a single dedicated worker process for type=upload_pipeline tasks."
        )

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
