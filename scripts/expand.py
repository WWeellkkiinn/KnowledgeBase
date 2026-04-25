"""expand.py — 递归展开引用网络。

对 root PDF 跑 pdf2md + Phase 1-3，然后按 --max-depth 对其下载到的 refs/*.pdf 递归同样流程。
去重、断点续跑、网络图持久化均靠 papers/_manifest.json + network.json。

用法：
    python scripts/expand.py <root_pdf> --focus <focus> [--max-depth 1] [--max-breadth N]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PAPERS_DIR = ROOT / "papers"
MANIFEST_PATH = PAPERS_DIR / "_manifest.json"
GRAPH_PATH = ROOT / "network.json"

sys.path.insert(0, str(SCRIPTS))
from run_analysis_ui import _parse_refs  # noqa: E402


def _load_json(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"WARN: {p} 损坏，重置: {e}", file=sys.stderr)
    return default


def _atomic_write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _run_pdf2md(pdf_path: Path) -> Path | None:
    """调 pdf2md 子进程。成功返回 .md 路径，失败返回 None。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "pdf2md.py"), str(pdf_path),
         "--output-dir", str(PAPERS_DIR)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not out:
        err = (proc.stderr or "").strip()[-500:]
        print(f"  [pdf2md] rc={proc.returncode}  {err}", file=sys.stderr)
        return None
    last = out.splitlines()[-1]
    try:
        data = json.loads(last)
    except json.JSONDecodeError:
        print(f"  [pdf2md] 无法解析输出: {last[:200]}", file=sys.stderr)
        return None
    if "error" in data:
        print(f"  [pdf2md] {data['error']}", file=sys.stderr)
        return None
    return Path(data["md_path"])


def _run_analysis(md_path: Path, focus: str) -> bool:
    """调 run_analysis_ui --headless。stdout/stderr 透传给用户看进度。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "run_analysis_ui.py"),
         str(md_path), "--focus", focus, "--headless",
         "--output-dir", str(PAPERS_DIR)],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return proc.returncode == 0


_TITLE_LINE = re.compile(r"^#\s+(.+?)\s*$")


def _parse_title(analysis_insight_md: Path) -> str:
    """从 analysis_insight.md 首行 `# Title` 提取标题。"""
    if not analysis_insight_md.exists():
        return ""
    for line in analysis_insight_md.read_text(encoding="utf-8").splitlines()[:10]:
        m = _TITLE_LINE.match(line)
        if m:
            return m.group(1).strip()
    return ""


def _add_edge(graph: dict, src: str, dst: str, meta: dict | None):
    edge = {"from": src, "to": dst}
    if meta:
        edge.update(meta)
    # 去重：按 (from, to, index) 三元组
    key = (edge["from"], edge["to"], edge.get("index"))
    for existing in graph["edges"]:
        if (existing["from"], existing["to"], existing.get("index")) == key:
            return
    graph["edges"].append(edge)


def expand(root_pdf: Path, focus: str, max_depth: int, max_breadth: int | None):
    manifest = _load_json(MANIFEST_PATH, {"analyzed": {}})
    graph = _load_json(GRAPH_PATH, {"nodes": {}, "edges": []})

    queue: list[tuple[Path, int, str | None, dict | None]] = [(root_pdf, 0, None, None)]
    processed = 0
    while queue:
        pdf, depth, parent, edge_meta = queue.pop(0)
        stem = pdf.stem
        print(f"\n[depth={depth}] {stem}")

        prior = manifest["analyzed"].get(stem)
        cached = bool(prior and prior.get("analyzed") and prior.get("path"))
        if cached:
            print("  命中 manifest（已成功），跳过分析")
            if parent:
                _add_edge(graph, parent, stem, edge_meta)
                _atomic_write_json(GRAPH_PATH, graph)
            if depth >= max_depth:
                continue
            out_dir = ROOT / prior["path"]
        else:
            if prior:
                print(f"  上次失败（{prior.get('error', 'analysis_failed')}），重试")

            # Step 1: pdf2md（若入参已是 .md 则跳过，直接复用）
            if pdf.suffix.lower() == ".md":
                md_path: Path | None = pdf
            else:
                md_path = _run_pdf2md(pdf)
            if md_path is None:
                manifest["analyzed"][stem] = {
                    "path": None, "depth": depth, "parent": parent,
                    "analyzed": False, "error": "pdf2md_failed",
                }
                graph["nodes"][stem] = {"title": stem, "depth": depth, "analyzed": False,
                                        "error": "pdf2md_failed"}
                if parent:
                    _add_edge(graph, parent, stem, edge_meta)
                _atomic_write_json(MANIFEST_PATH, manifest)
                _atomic_write_json(GRAPH_PATH, graph)
                continue

            out_dir = md_path.parent

            # Step 2: Phase 1-3
            ok = _run_analysis(md_path, focus)

            title = _parse_title(out_dir / "analysis_insight.md") or stem
            graph["nodes"][stem] = {
                "title": title,
                "path": str(out_dir.relative_to(ROOT)).replace("\\", "/"),
                "depth": depth,
                "analyzed": ok,
            }
            if parent:
                _add_edge(graph, parent, stem, edge_meta)
            manifest["analyzed"][stem] = {
                "path": str(out_dir.relative_to(ROOT)).replace("\\", "/"),
                "depth": depth,
                "parent": parent,
                "analyzed": ok,
            }
            _atomic_write_json(MANIFEST_PATH, manifest)
            _atomic_write_json(GRAPH_PATH, graph)
            processed += 1

            if not ok or depth >= max_depth:
                continue

        # Step 3: 入队 refs
        refs_md = out_dir / "analysis_refs.md"
        refs_dir = out_dir / "refs"
        if not refs_md.exists() or not refs_dir.exists():
            continue
        parsed = _parse_refs(refs_md.read_text(encoding="utf-8"))
        by_idx = {r["index"]: r for r in parsed}
        pdfs = sorted(refs_dir.glob("*.pdf"))
        if max_breadth is not None:
            pdfs = pdfs[:max_breadth]
        for ref_pdf in pdfs:
            try:
                idx = int(ref_pdf.stem.split("_", 1)[0])
            except ValueError:
                continue
            meta = by_idx.get(idx, {})
            queue.append((ref_pdf, depth + 1, stem, {
                "index": idx,
                "title": meta.get("title", ""),
            }))

    print(f"\n完成。本次新分析 {processed} 篇。")
    print(f"  manifest: {MANIFEST_PATH.relative_to(ROOT)}")
    print(f"  graph:    {GRAPH_PATH.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root_pdf", help="起点 PDF 路径（也接受 .md，跳过 pdf2md 直接分析）")
    ap.add_argument("--focus", required=True, help="关注重点（递归中不变）")
    ap.add_argument("--max-depth", type=int, default=1,
                    help="递归深度。root=0；默认 1（root + 一层 refs）")
    ap.add_argument("--max-breadth", type=int, default=None,
                    help="每篇论文最多展开的 refs 数（按文件名排序）")
    args = ap.parse_args()

    root_pdf = Path(args.root_pdf).resolve()
    if not root_pdf.exists():
        print(f"ERROR: {root_pdf} not found", file=sys.stderr)
        sys.exit(1)
    expand(root_pdf, args.focus, args.max_depth, args.max_breadth)


if __name__ == "__main__":
    main()
