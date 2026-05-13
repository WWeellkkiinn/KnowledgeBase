"""ExpandService —— BFS 引用网络展开。

M1.3 最小抽离：内部委托给 `scripts.expand.expand`，保持原 manifest/graph 落盘行为。
后续 milestone 把 manifest/graph 替换为 DB 写入。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
        sys.path.insert(0, str(ROOT / "scripts"))
        from expand import expand  # type: ignore
        expand(root_pdf=root_pdf, focus=focus, max_depth=max_depth, max_breadth=max_breadth)
