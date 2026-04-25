#!/usr/bin/env python3
"""Download a PDF from a URL to a local file.

Usage:
    python scripts/download_pdf.py <url> <output_path>

Exit codes:
    0  success
    1  failure (reason printed to stderr)

Handler 优先级：nber → ssrn → generic（含 unpaywall fallback）
新增来源：在 scripts/downloaders/ 下新建模块，实现 can_handle + download，
然后在 _HANDLERS 列表中插入合适位置即可。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from downloaders import generic, nber, ssrn

_HANDLERS = [nber, ssrn, generic]


def download(url: str, output_path: str) -> tuple[bool, str]:
    for h in _HANDLERS:
        if h.can_handle(url):
            try:
                return h.download(url, output_path)
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"
    return False, "no handler matched"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: download_pdf.py <url> <output_path>", file=sys.stderr)
        sys.exit(1)
    ok, msg = download(sys.argv[1], sys.argv[2])
    print(msg, file=(sys.stdout if ok else sys.stderr))
    sys.exit(0 if ok else 1)
