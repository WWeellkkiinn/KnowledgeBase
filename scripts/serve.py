"""应用入口：`python scripts/serve.py`。

`socketio.run()` 单进程模式：限速器 `memory://` 与 TaskQueue 单 worker 守卫均
依赖此假设；Docker Compose 默认即此入口。**不要**改用 gunicorn 多 worker
（除非配 `KB_ALLOW_MULTI_WORKER=1` 并独立跑 worker 进程）。

默认启用订阅调度器（M2.3）；测试场景下走 create_app() 直接调用不会启 scheduler。
绑定地址通过 `KB_BIND_HOST` 覆盖（容器内默认 0.0.0.0，本地开发默认 127.0.0.1）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 默认在 dev server 路径开启调度器；用户可通过显式设环境变量为 "0" 关闭。
os.environ.setdefault("KB_ENABLE_SCHEDULER", "1")

from app import create_app, socketio  # noqa: E402

if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("KB_BIND_HOST", "127.0.0.1")
    socketio.run(app, host=host, port=5000, debug=False, allow_unsafe_werkzeug=True)
