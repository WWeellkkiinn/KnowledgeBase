"""SearchService —— 论文元数据 + PDF URL 搜索链。

委托给 `scripts.search_refs.search`（M1.3 最小抽离）。
"""
from __future__ import annotations

from ._paths import ensure_scripts_on_path


class SearchService:
    def __init__(self, db_session=None) -> None:
        self.db_session = db_session

    def search(self, title: str, year: str = "", doi: str = "") -> dict:
        """Returns: {title, year, authors, doi, pdf_url, source}."""
        ensure_scripts_on_path()
        from search_refs import search as _search  # type: ignore
        return _search(title, year, doi)
