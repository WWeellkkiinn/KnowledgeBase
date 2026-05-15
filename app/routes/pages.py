"""SPA 静态托管：根路径返回 frontend/dist/index.html，未匹配的路径 fallback 到 index.html。

为生产化部署（公网通过 cpolar 隧道暴露）服务。前端打包后产物在 frontend/dist/。
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, make_response, send_from_directory

from app import limiter

bp = Blueprint("pages", __name__)

# frontend/dist 绝对路径：app/routes/pages.py → app/routes → app → 项目根 → frontend/dist
_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_DIST_RESOLVED = _DIST_DIR.resolve()


@bp.get("/health")
@limiter.exempt
def health():
    """无鉴权健康检查端点，给 cpolar 隧道/监控用。

    豁免限流：监控通常以秒级频率轮询，不能算进默认 120/min 配额。
    """
    return {"ok": True}


@bp.get("/", defaults={"path": ""})
@bp.get("/<path:path>")
def spa(path: str):
    if not _DIST_DIR.is_dir():
        abort(404, description="frontend not built; run `npm run build` in frontend/")
    # 已鉴权但路径以 api/ 或 socket.io/ 开头的请求落到这里 = 真正 404，
    # 不能让 SPA fallback 抓走（会让客户端把 index.html 当 JSON 解析）。
    if path.startswith("api/") or path.startswith("socket.io/"):
        abort(404)
    # 路径穿越加固：resolve 后必须仍位于 _DIST_DIR 之下，否则 404。
    if path:
        try:
            safe_path = (_DIST_DIR / path).resolve()
        except (OSError, ValueError):
            abort(404)
        if not safe_path.is_relative_to(_DIST_RESOLVED):
            abort(404)
        if safe_path.is_file():
            resp = make_response(send_from_directory(_DIST_DIR, path))
            if path.startswith("assets/"):
                # 带 hash 的资源，长期缓存
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                resp.headers["Cache-Control"] = "no-cache"
            return resp
    # SPA fallback：所有未命中的路径返回 index.html
    resp = make_response(send_from_directory(_DIST_DIR, "index.html"))
    resp.headers["Cache-Control"] = "no-cache"
    return resp
