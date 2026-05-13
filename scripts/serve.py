"""dev server 入口：`python scripts/serve.py`。

生产部署用其他方式（gunicorn 或 socketio.run），M1.5 范围内仅供开发。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app, socketio

if __name__ == "__main__":
    app = create_app()
    socketio.run(app, host="127.0.0.1", port=5000, debug=False, allow_unsafe_werkzeug=True)
