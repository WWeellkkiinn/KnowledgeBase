"""pdf2md.py — Convert PDF to Markdown via MinerU API.

Usage: python scripts/pdf2md.py <pdf_path> [--output-dir <dir>]
Output (stdout): {"md_path": "...", "sections": [...]}
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

MINERU_API = os.environ.get("KB_MINERU_LOCAL_URL", "http://localhost:8000")
POLL_INTERVAL = int(os.environ.get("KB_MINERU_POLL_INTERVAL", "5"))
POLL_TIMEOUT = int(os.environ.get("KB_MINERU_POLL_TIMEOUT", "600"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    parser.add_argument("--output-dir", default="papers")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path).resolve()
    if not pdf_path.exists():
        print(json.dumps({"error": f"File not found: {pdf_path}"}))
        sys.exit(1)

    output_dir = Path(args.output_dir) / _sanitize(pdf_path.stem)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{_sanitize(pdf_path.stem)}.md"

    if md_path.exists() and md_path.stat().st_size > 100:
        sections = _extract_sections(md_path)
        print(json.dumps({"md_path": str(md_path), "sections": sections}, ensure_ascii=False))
        return

    # Upload to MinerU
    with open(pdf_path, "rb") as f:
        resp = httpx.post(
            f"{MINERU_API}/tasks",
            files={"files": (pdf_path.name, f, "application/pdf")},
            data={"return_md": "true", "backend": "hybrid-auto-engine"},
            timeout=300,
        )
    resp.raise_for_status()
    data = resp.json()
    task_id = _get_task_id(data)
    if not task_id:
        print(json.dumps({"error": f"MinerU returned no task_id: {data}"}))
        sys.exit(1)

    # Poll
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        sr = httpx.get(f"{MINERU_API}/tasks/{task_id}", timeout=15)
        sr.raise_for_status()
        state = _get_state(sr.json())
        if state == "completed":
            break
        if state in ("failed", "error"):
            print(json.dumps({"error": f"MinerU task failed: {sr.json()}"}))
            sys.exit(1)
        print(f"[MinerU] {state}...", file=sys.stderr, flush=True)
    else:
        print(json.dumps({"error": f"MinerU timed out (>{POLL_TIMEOUT}s)"}))
        sys.exit(1)

    rr = httpx.get(f"{MINERU_API}/tasks/{task_id}/result", timeout=30)
    rr.raise_for_status()
    md_content = _extract_markdown(rr.json())
    if not md_content:
        print(json.dumps({"error": "MinerU returned empty Markdown"}))
        sys.exit(1)

    md_path.write_text(md_content, encoding="utf-8")
    sections = _extract_sections(md_path)
    print(json.dumps({"md_path": str(md_path), "sections": sections}, ensure_ascii=False))


def _get_task_id(data) -> str | None:
    if isinstance(data, list):
        data = data[0] if data else {}
    for k in ("task_id", "id"):
        if data.get(k):
            return str(data[k])
    return None


def _get_state(data) -> str:
    if isinstance(data, list):
        data = data[0] if data else {}
    for k in ("state", "status", "task_state"):
        if k in data:
            return str(data[k]).lower()
    return "unknown"


def _extract_markdown(result) -> str:
    if isinstance(result, list):
        result = result[0] if result else {}
    for file_result in result.get("results", {}).values():
        if isinstance(file_result, dict):
            md = file_result.get("md_content", "") or file_result.get("markdown", "")
            if isinstance(md, str) and md.strip():
                return md
    for key in ("markdown", "md_content", "content"):
        val = result.get(key, "")
        if isinstance(val, str) and val.strip():
            return val
    return ""


def _extract_sections(md_path: Path) -> list[dict]:
    sections = []
    with open(md_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            m = re.match(r"^(#{1,3})\s+(.+)", line.rstrip())
            if m:
                sections.append({
                    "id": len(sections),
                    "level": len(m.group(1)),
                    "title": m.group(2).strip(),
                    "line": lineno,
                })
    return sections


def _sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)[:120]


if __name__ == "__main__":
    main()
