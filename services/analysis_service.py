"""AnalysisService —— 三阶段 LLM 流水线。

M1.3 最小抽离：通过 subprocess 调用 scripts/run_analysis_ui.py 的 --headless 模式，
保证 CLI 行为字节级等价。

`parse_refs` 是纯正则函数，在本模块内副本实现，避免触发
`scripts/run_analysis_ui.py` 的 `from search_refs import search` 链路，
那条链路会强制要求 `scripts/config.py`（含 API 密钥）。本副本与 scripts 中
原版必须保持同步。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from ._paths import ROOT

_ANALYSIS_CLI = ROOT / "scripts" / "run_analysis_ui.py"

# 与 scripts/run_analysis_ui.py:79 _REF_HEADING 保持同步
_REF_HEADING = re.compile(
    r'^###\s*\[?(\d+)\]?\.?\s*(.+?)\s+\((\d{4})\)\s*[—–-]\s*'
    r'(.+?)(?:\s*·\s*DOI:\s*(\S+))?\s*$',
    re.MULTILINE,
)


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
        timeout: float | None = None,
    ) -> int:
        """Run full pipeline on a markdown file. Returns exit code (0=ok).

        参数注入防护：argparse 会把 `--xxx` 当 flag，若 focus 由 HTTP 输入
        以 `-`/`--` 起头会被吃成 unknown flag。拒之。
        """
        if not focus or focus.startswith("-"):
            raise ValueError("focus 不能为空或以 '-' 开头")
        cmd = [sys.executable, str(_ANALYSIS_CLI), str(md_path), "--focus", focus]
        if output_dir is not None:
            cmd += ["--output-dir", str(output_dir)]
        if headless:
            cmd.append("--headless")
        if phase3_only:
            cmd.append("--phase3-only")
        try:
            proc = subprocess.run(cmd, timeout=timeout)
        except subprocess.TimeoutExpired:
            return -1
        return proc.returncode

    @staticmethod
    def parse_refs(text: str) -> list[dict]:
        """解析 analysis_refs.md 中的引用标题行为结构化条目。

        签名/字段与 scripts/run_analysis_ui.py:_parse_refs 完全一致。
        """
        out: list[dict] = []
        for m in _REF_HEADING.finditer(text):
            idx, authors, year, title, doi = m.groups()
            first = re.match(r'[A-Za-z]+', authors)
            out.append({
                "index": int(idx),
                "authors": authors.strip(),
                "year": year,
                "title": title.strip(),
                "doi": (doi or "").strip(),
                "first_author": (first.group(0).lower() if first else "unknown"),
            })
        return out
