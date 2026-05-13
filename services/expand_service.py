"""ExpandService —— BFS 引用网络展开。

M1.3 最小抽离：内部委托给 `scripts.expand.expand`。
"""
from __future__ import annotations

from pathlib import Path

from ._paths import ensure_scripts_on_path


class ExpandService:
    def __init__(self, db_session=None) -> None:
        self.db_session = db_session

    def run(
        self,
        root_pdf: Path,
        focus: str,
        max_depth: int = 1,
        max_breadth: int | None = None,
    ) -> None:
        ensure_scripts_on_path()
        from expand import expand  # type: ignore
        expand(root_pdf=root_pdf, focus=focus, max_depth=max_depth, max_breadth=max_breadth)
