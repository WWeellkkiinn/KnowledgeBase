"""SearchService —— 论文元数据 + PDF URL 搜索链。

委托给 `scripts.search_refs.search`（M1.3 最小抽离）。后续 milestone 再把
搜索链内部状态（_ss_last_call 等）搬进 instance。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


class SearchService:
    """搜索元数据 + PDF URL；尽量按 PLAN §4 M1.3 的接口对齐 Web 路由用法。"""

    def __init__(self, db_session=None) -> None:
        # db_session：M1.4+ 双写 citations / papers 时使用
        self.db_session = db_session

    def search(self, title: str, year: str = "", doi: str = "") -> dict:
        """Returns: {title, year, authors, doi, pdf_url, source}."""
        from search_refs import search as _search  # type: ignore
        return _search(title, year, doi)
