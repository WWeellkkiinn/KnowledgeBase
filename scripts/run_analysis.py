"""run_analysis.py — Run one paper through Ollama and save full conversation log.

Usage: python scripts/run_analysis.py <md_path> --focus <focus> [--output-dir <dir>]
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx

OLLAMA_BASE = "http://<ollama-host>:13811/v1"
MODEL = "supergemma4-26b"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """\
你是一名学术文献调研助手。用户会给你一篇论文的 Markdown 全文，你需要：
1. 定位与关注重点最相关的章节
2. 用中文总结该章节核心内容（200字以内）
3. 列出该章节中所有引用的文献编号或作者年份标记

规则：
- 全程使用中文回复
- 总结严格不超过200字
- 引用列表每行一条，格式：作者(年份) 或 [编号]
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("md_path")
    parser.add_argument("--focus", required=True)
    parser.add_argument("--output-dir", default="papers")
    args = parser.parse_args()

    md_path = Path(args.md_path)
    if not md_path.exists():
        print(f"ERROR: {md_path} not found"); sys.exit(1)

    md_text = md_path.read_text(encoding="utf-8")
    output_dir = Path(args.output_dir) / md_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    print(f"论文: {md_path.name}", flush=True)
    print(f"关注重点: {args.focus}", flush=True)
    print(f"日志: {log_path}", flush=True)
    print("─" * 60, flush=True)

    # Build messages with paper content as stable prefix
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"<论文全文>\n{md_text}\n</论文全文>\n\n关注重点：{args.focus}\n\n请执行上述三个步骤。"},
    ]

    log_entries = []

    def log(entry: dict):
        log_entries.append(entry)
        log_path.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in log_entries),
            encoding="utf-8",
        )

    log({"type": "session_start", "timestamp": datetime.now().isoformat(),
         "model": MODEL, "focus": args.focus, "md_path": str(md_path)})
    log({"type": "user_message", "content": messages[1]["content"][:200] + "..."})

    # Call Ollama Responses API
    print("🤖 正在分析...", flush=True)
    client = httpx.Client(timeout=300)
    resp = client.post(
        f"{OLLAMA_BASE}/responses",
        headers={"Authorization": "Bearer ollama", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "input": [{"role": m["role"], "content": m["content"]} for m in messages],
            "max_output_tokens": MAX_TOKENS,
            "stream": False,
        },
    )
    resp.raise_for_status()
    data = resp.json()

    # Extract text output
    output_text = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    output_text += c.get("text", "")

    # Clean Gemma special tokens
    output_text = re.sub(r"(<channel\|>|<\|[^>]*\|?>|\bthought\b)", "", output_text).strip()

    log({"type": "assistant_message", "content": output_text,
         "usage": data.get("usage", {})})

    print(f"\n🤖 模型回复：\n{output_text}", flush=True)
    print("\n" + "─" * 60, flush=True)

    # Save analysis.md
    analysis_path = output_dir / "analysis.md"
    analysis_path.write_text(
        f"# {md_path.stem}\n\n"
        f"**关注重点**：{args.focus}\n\n"
        f"## 关注重点分析\n\n{output_text}\n\n"
        f"## 引用文献概览\n\n",
        encoding="utf-8",
    )

    # Run extract_refs
    import subprocess
    print("📚 提取引用文献...", flush=True)
    r = subprocess.run(
        [sys.executable, "scripts/extract_refs.py", str(md_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    refs = []
    if r.returncode == 0:
        try:
            refs = json.loads(r.stdout)
        except Exception:
            pass

    # Search metadata for each ref
    enriched_refs = []
    for ref in refs:
        title = ref.get("title", "")
        year  = ref.get("year", "")
        print(f"  🔍 {title[:50]}...", flush=True)
        sr = subprocess.run(
            [sys.executable, "scripts/search_refs.py", title, "--year", year],
            capture_output=True, text=True, encoding="utf-8",
        )
        if sr.returncode == 0:
            try:
                meta = json.loads(sr.stdout)
                ref.update({k: meta[k] for k in ("doi", "pdf_url", "authors", "year") if meta.get(k)})
            except Exception:
                pass
        ref.setdefault("relevance", "")
        enriched_refs.append(ref)

    log({"type": "refs_extracted", "count": len(enriched_refs), "refs": enriched_refs})
    print(f"找到 {len(enriched_refs)} 条引用文献", flush=True)

    # Append refs overview to analysis.md
    overview = "\n".join(
        f"- [{r['index']}] {r.get('authors','')[:30]} ({r.get('year','')}) — {r.get('title','')[:60]}"
        for r in enriched_refs
    )
    with open(analysis_path, "a", encoding="utf-8") as f:
        f.write(overview + "\n")

    # Save refs.json
    refs_path = output_dir / "refs.json"
    refs_path.write_text(json.dumps(enriched_refs, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save todo_download.txt
    todo_path = output_dir / "todo_download.txt"
    lines = [
        f"[{r['index']}] {r['title']} | {r.get('doi') or '—'} | {r.get('pdf_url') or 'NOT_FOUND'}"
        for r in enriched_refs
    ]
    todo_path.write_text("\n".join(lines), encoding="utf-8")

    log({"type": "session_complete", "outputs": {
        "analysis": str(analysis_path),
        "refs": str(refs_path),
        "todo": str(todo_path),
        "log": str(log_path),
    }})

    print(f"\n✅ 完成，输出：", flush=True)
    print(f"  analysis.md  → {analysis_path}", flush=True)
    print(f"  refs.json    → {refs_path} ({len(refs)} 条)", flush=True)
    print(f"  todo_download.txt → {todo_path}", flush=True)
    print(f"  session log  → {log_path}", flush=True)


if __name__ == "__main__":
    main()
