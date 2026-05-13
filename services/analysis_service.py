"""AnalysisService —— 三阶段 LLM 流水线。

M1.3 最小抽离：通过 subprocess 调用 scripts/run_analysis_ui.py 的 --headless 模式，
保证 CLI 行为字节级等价。Phase 2 解析能力以静态方法暴露（被搜索/扩展复用）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_ANALYSIS_CLI = ROOT / "scripts" / "run_analysis_ui.py"


class AnalysisService:
    def __init__(self, db_session=None) -> None:
        self.db_session = db_session

    def analyze(
        self,
        md_path: Path,
        focus: str,
        output_dir: Path | None = None,
        headless: bool = True,
        phase3_only: bool = False,
    ) -> int:
        """Run full pipeline on a markdown file. Returns exit code (0=ok)."""
        cmd = [sys.executable, str(_ANALYSIS_CLI), str(md_path), "--focus", focus]
        if output_dir is not None:
            cmd += ["--output-dir", str(output_dir)]
        if headless:
            cmd.append("--headless")
        if phase3_only:
            cmd.append("--phase3-only")
        proc = subprocess.run(cmd)
        return proc.returncode

    @staticmethod
    def parse_refs(text: str) -> list[dict]:
        """Static helper to parse `analysis_refs.md` content into structured refs."""
        sys.path.insert(0, str(ROOT / "scripts"))
        from run_analysis_ui import _parse_refs  # type: ignore
        return _parse_refs(text)
