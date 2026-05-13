"""Flask app factory（PLAN.md §4 M1.5）。

最小骨架：REST 蓝图 + 占位首页 + Socket.IO 实例（M1.6 真正绑事件）。
单用户场景，默认监听 127.0.0.1:5000；CORS 仅放行 Vite dev server。
"""
from __future__ import annotations

import os
import secrets

from flask import Flask, g
from flask_socketio import SocketIO

from database import SessionLocal


# CORS allowlist 支持环境变量覆盖；默认放行 Vite dev 的 localhost 与 127.0.0.1。
_DEFAULT_CORS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_CORS = os.environ.get("KB_CORS_ORIGINS")
_CORS_LIST = [s.strip() for s in _CORS.split(",")] if _CORS else _DEFAULT_CORS

socketio = SocketIO(cors_allowed_origins=_CORS_LIST, async_mode="threading")


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    # SECRET_KEY 必须设置：flask-socketio polling transport 与未来 Flask session
    # 都依赖；优先读环境变量，开发期 fallback 到随机 key（重启后失效，符合 dev 预期）。
    app.config["SECRET_KEY"] = os.environ.get("KB_SECRET_KEY") or secrets.token_hex(32)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.config.update(config or {})

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

    return app


__all__ = ["create_app", "socketio"]
