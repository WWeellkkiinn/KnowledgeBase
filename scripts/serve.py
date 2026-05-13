"""dev server 入口：`python scripts/serve.py`。

生产部署用其他方式（gunicorn 或 socketio.run），M1.5+M2.3 范围内仅供开发。
默认启用订阅调度器（M2.3）；测试场景下走 create_app() 直接调用不会启 scheduler。
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
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)
