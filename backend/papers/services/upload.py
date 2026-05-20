"""Upload pipeline service helpers."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


def compute_sha1(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk), b""):
            h.update(buf)
    return h.hexdigest()


def extract_title_from_md(md_path: Path) -> str | None:
    try:
        with open(md_path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^#\s+(.+)$", line.strip())
                if m:
                    candidate = m.group(1).strip()
                    if candidate and len(candidate) > 4:
                        return candidate
    except OSError:
        return None
    return None
