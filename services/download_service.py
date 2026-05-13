"""DownloadService —— PDF 下载分发器。

委托给 `scripts.download_pdf.download`。
"""
from __future__ import annotations

from ._paths import ensure_scripts_on_path


class DownloadService:
    def __init__(self, db_session=None) -> None:
        self.db_session = db_session

    def download(self, url: str, output_path: str) -> tuple[bool, str]:
        ensure_scripts_on_path()
        from download_pdf import download as _download  # type: ignore
        return _download(url, output_path)
