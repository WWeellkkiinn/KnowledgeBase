"""Pdf2MdService —— PDF → Markdown 转换。

provider 切换（环境变量 KB_PDF2MD_PROVIDER）：
  - "mineru-cloud"（默认）：调 services.pdf2md_cloud，走 mineru.net 公网 API
  - "local"：保留旧路径，subprocess 调 scripts/pdf2md.py（局域网 MinerU）

云端方案支持 `on_progress(step, msg)` 回调以推送 socket 进度。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from ._paths import ROOT

_PDF2MD = ROOT / "scripts" / "pdf2md.py"
_log = logging.getLogger(__name__)


class Pdf2MdService:
    def __init__(self, db_session=None) -> None:
        self.db_session = db_session

    def convert(
        self,
        pdf_path: Path,
        output_dir: Path | None = None,
        timeout: float | None = 600.0,
        *,
        on_progress: Optional[Callable[[str, str], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> dict:
        """PDF → Markdown，返回 {"md_path", "sections"} 或 {"error"}。

        output_dir 必填：云端 / 本地两路实现都按 stem 分目录写盘；
        若为 None 调用方不同 PDF 会互相覆盖 md，故 fail-fast。
        """
        provider = (os.environ.get("KB_PDF2MD_PROVIDER") or "mineru-cloud").strip().lower()
        if output_dir is None:
            return {"error": "output_dir is required (per-paper dir to avoid md collisions)"}

        if provider == "mineru-cloud":
            from .pdf2md_cloud import convert as _cloud_convert
            return _cloud_convert(
                pdf_path, Path(output_dir),
                on_progress=on_progress,
                timeout=timeout or 600.0,
                stop_event=stop_event,
            )

        # 回退：subprocess 调本地 pdf2md.py
        if on_progress is not None:
            try:
                on_progress("pdf2md.subprocess", "调用本地 MinerU…")
            except Exception:
                pass
        cmd = [sys.executable, str(_PDF2MD), str(pdf_path)]
        if output_dir is not None:
            cmd += ["--output-dir", str(output_dir)]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"timeout after {timeout}s"}
        if proc.returncode != 0:
            return {"error": proc.stderr.strip() or f"exit {proc.returncode}"}

        lines = proc.stdout.strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return {"error": f"no JSON found in stdout (last 200 chars): {proc.stdout[-200:]}"}
