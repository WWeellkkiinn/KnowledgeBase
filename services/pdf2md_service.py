"""Pdf2MdService —— PDF → Markdown 转换。

底层调用 scripts/pdf2md.py（subprocess 形态，主程序返回 JSON 到 stdout）。
保留 subprocess 调用方式以保 CLI 等价；后续 milestone 可改为直接 import。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PDF2MD = ROOT / "scripts" / "pdf2md.py"


class Pdf2MdService:
    def __init__(self, db_session=None) -> None:
        self.db_session = db_session

    def convert(self, pdf_path: Path, output_dir: Path | None = None) -> dict:
        """Run pdf2md.py subprocess and parse last-line JSON output.

        Returns: {"md_path": str, "sections": [...]} or {"error": str}.
        """
        cmd = [sys.executable, str(_PDF2MD), str(pdf_path)]
        if output_dir is not None:
            cmd += ["--output-dir", str(output_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0:
            return {"error": proc.stderr.strip() or f"exit {proc.returncode}"}
        # 取最后一行 JSON（pdf2md.py 在 stderr 打进度，stdout 仅 JSON 结果）
        last = (proc.stdout.strip().splitlines() or [""])[-1]
        try:
            return json.loads(last)
        except json.JSONDecodeError:
            return {"error": f"non-JSON stdout: {last[:200]}"}
