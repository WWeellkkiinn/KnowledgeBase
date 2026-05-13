"""DownloadService —— PDF 下载分发器。

委托给 `scripts.download_pdf.download`，handler 插件链（nber/ssrn/generic）保留原状。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


class DownloadService:
    def __init__(self, db_session=None) -> None:
        self.db_session = db_session

    def download(self, url: str, output_path: str) -> tuple[bool, str]:
        """Returns (success, message)."""
        from download_pdf import download as _download  # type: ignore
        return _download(url, output_path)
