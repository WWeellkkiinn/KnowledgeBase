"""DownloadService —— PDF 下载分发器。

委托给 `scripts.download_pdf.download`。

防御性校验：
- URL 仅允许 http(s)，挡掉 file://、gopher:// 等 SSRF 向量
- output_path 必须落在项目 papers/ 目录下，挡掉路径穿越
当前 M1.5 没有 HTTP 写入路由暴露此 service，但 M2+ 接入订阅/下载 API 时
这层校验先到位。
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from ._paths import ROOT, ensure_scripts_on_path

_ALLOWED_SCHEMES = {"http", "https"}
_PAPERS_DIR = (ROOT / "papers").resolve()


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(f"unsupported url scheme: {parsed.scheme!r}")
    if not parsed.netloc:
        raise ValueError("url missing host")


def _check_output(output_path: str) -> None:
    resolved = Path(output_path).resolve()
    try:
        resolved.relative_to(_PAPERS_DIR)
    except ValueError as e:
        raise ValueError(f"output_path must be under papers/: {output_path}") from e


class DownloadService:
    def __init__(self, db_session=None) -> None:
        self.db_session = db_session

    def download(self, url: str, output_path: str) -> tuple[bool, str]:
        _check_url(url)
        _check_output(output_path)
        ensure_scripts_on_path()
        from download_pdf import download as _download  # type: ignore
        return _download(url, output_path)
