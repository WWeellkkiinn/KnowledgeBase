"""Pdf2MdService —— PDF → Markdown 转换。

底层调用 scripts/pdf2md.py（subprocess，stdout 末尾输出 JSON）。
stdout 末尾允许有非 JSON 噪声（如日志、警告），扫描从后往前找首条可解析 JSON。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ._paths import ROOT

_PDF2MD = ROOT / "scripts" / "pdf2md.py"


class Pdf2MdService:
    def __init__(self, db_session=None) -> None:
        self.db_session = db_session

    def convert(self, pdf_path: Path, output_dir: Path | None = None) -> dict:
        """Run pdf2md.py and return parsed JSON dict.

        Returns: {"md_path": str, "sections": [...]} on success;
                 {"error": str} on failure.
        """
        cmd = [sys.executable, str(_PDF2MD), str(pdf_path)]
        if output_dir is not None:
            cmd += ["--output-dir", str(output_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0:
            return {"error": proc.stderr.strip() or f"exit {proc.returncode}"}

        # 从后往前找首条可解析 JSON。pdf2md 在 stdout 末尾输出结果，但允许
        # 同 stream 上有非 JSON 噪声（如 logging.warning 错落到 stdout）。
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
