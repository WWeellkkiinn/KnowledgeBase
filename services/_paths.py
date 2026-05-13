"""service 内部工具：sys.path 管理。

所有 service 在 import scripts/ 下旧模块前都应调用 `ensure_scripts_on_path()`，
集中处理去重，避免 sys.path 被多次插入相同条目。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
_SCRIPTS_STR = str(SCRIPTS)


def ensure_scripts_on_path() -> None:
    if _SCRIPTS_STR not in sys.path:
        sys.path.insert(0, _SCRIPTS_STR)
