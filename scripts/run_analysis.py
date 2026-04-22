"""run_analysis.py — Agentic loop: LLM actively reads sections and judges references.

Usage: python scripts/run_analysis.py <md_path> --focus <focus> [--output-dir <dir>]

Loop tools:
  [TOOL: list_sections]               → chapter list
  [TOOL: read_section] {"id": N}      → section text (≤2000 chars)
  [TOOL: search_ref] {"title": "...","year": "..."} → metadata
  [TOOL: finish] {"analysis": "...","refs": [...]}  → done
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx

OLLAMA_BASE = "http://<ollama-host>:13811/v1"
MODEL = "gemma4-31b"
TIMEOUT = 300
MAX_ITER = 8
MAX_CONSEC_FAILURES = 3
SECTION_CHAR_LIMIT = 2000

SYSTEM_PROMPT = """\
你是学术文献调研助手。每次回复只输出一个工具调用，格式严格如下，不加任何其他文字：

[TOOL: list_sections]
[TOOL: read_section] {"id": <整数>}
[TOOL: search_ref] {"title": "<标题>", "year": "<年份>"}
[TOOL: finish] {"analysis": "<中文，≤500字>", "refs": [{"index": <整数>, "relevance": "high"|"medium"|"low", "reason": "<≤50字>"}]}

工作策略：
1. 先调用 list_sections 获取章节列表
2. 根据关注重点选择最相关的 1-2 个章节调用 read_section
3. 对章节中出现的重要引用调用 search_ref（≤5 次）
4. 调用 finish 输出分析结论和引用评级

refs 只需包含与关注重点相关的引用，不需要穷举所有引用。\
"""

TOOL_CALL_RE = re.compile(r'\[TOOL:\s*(\w+)\]\s*(\{.*\})?', re.DOTALL)
VALID_RELEVANCE = {"high", "medium", "low"}


# ── LLM ──────────────────────────────────────────────────────────────────────

def call_llm(messages: list[dict]) -> str:
    client = httpx.Client(timeout=TIMEOUT)
    resp = client.post(
        f"{OLLAMA_BASE}/chat/completions",
        headers={"Authorization": "Bearer ollama"},
        json={"model": MODEL, "messages": messages, "stream": False, "temperature": 0.1},
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    # Clean Gemma special tokens
    text = re.sub(r'(<channel\|>|<\|[^>]*\|?>|\bthought\b)', '', text)
    text = text.replace('\ufffd', '')
    text = re.sub(r'(.)\1{20,}', r'\1\1\1', text)
    return text.strip()


def call_llm_with_retry(messages: list[dict], log: callable) -> str | None:
    for attempt in range(2):
        try:
            return call_llm(messages)
        except httpx.TimeoutException:
            log({"type": "warn", "msg": f"LLM timeout (attempt {attempt + 1}/2)"})
    return None


# ── Tool parsing ──────────────────────────────────────────────────────────────

def parse_tool_call(text: str) -> tuple[str, dict] | None:
    m = TOOL_CALL_RE.search(text)
    if not m:
        return None
    name = m.group(1).strip()
    args_str = (m.group(2) or "{}").strip()
    args_str = re.sub(r',\s*([}\]])', r'\1', args_str)  # trailing commas
    try:
        args = json.loads(args_str)
    except json.JSONDecodeError:
        args = {}
    return name, args


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_list_sections(md_text: str) -> str:
    sections = []
    for i, line in enumerate(md_text.splitlines()):
        m = re.match(r'^(#{1,3})\s+(.+)', line)
        if m:
            sections.append({
                "id": len(sections),
                "level": len(m.group(1)),
                "title": m.group(2).strip(),
                "line": i + 1,
            })
    return json.dumps(sections, ensure_ascii=False)


def tool_read_section(md_text: str, section_id: int) -> str:
    lines = md_text.splitlines()
    headings = [i for i, l in enumerate(lines) if re.match(r'^#{1,3}\s+', l)]
    if section_id < 0 or section_id >= len(headings):
        return f"[ERROR] section_id {section_id} 超出范围（共 {len(headings)} 个章节）"
    start = headings[section_id]
    end = headings[section_id + 1] if section_id + 1 < len(headings) else len(lines)
    content = "\n".join(lines[start:end])
    truncated = content[:SECTION_CHAR_LIMIT]
    if len(content) > SECTION_CHAR_LIMIT:
        truncated += f"\n[截断，原长 {len(content)} 字符]"
    return truncated


def tool_search_ref(title: str, year: str, cache: dict) -> str:
    key = f"{title[:50].lower()}|{year}"
    if key in cache:
        return json.dumps(cache[key], ensure_ascii=False)
    try:
        r = subprocess.run(
            [sys.executable, "scripts/search_refs.py", title, "--year", str(year)],
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        meta = json.loads(r.stdout) if r.returncode == 0 else {}
    except Exception:
        meta = {}
    cache[key] = meta
    return json.dumps(meta, ensure_ascii=False)


# ── finish parsing ────────────────────────────────────────────────────────────

def parse_finish(args: dict) -> tuple[str, list[dict]]:
    analysis = str(args.get("analysis", ""))
    refs_raw = args.get("refs", [])
    if not isinstance(refs_raw, list):
        return analysis, []
    validated = []
    for item in refs_raw:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        relevance = item.get("relevance", "low")
        if relevance not in VALID_RELEVANCE:
            relevance = "low"
        reason = str(item.get("reason", ""))[:100]
        validated.append({"index": idx, "relevance": relevance, "reason": reason})
    return analysis, validated


# ── Output writers ────────────────────────────────────────────────────────────

def write_outputs(output_dir: Path, md_stem: str, focus: str,
                  analysis: str, enriched_refs: list[dict],
                  parse_failed: bool, raw_log: list[dict]):
    output_dir.mkdir(parents=True, exist_ok=True)

    # analysis.md
    warning = ("> [WARNING] finish 未收到或解析失败，analysis/relevance 可能为空。"
               "见 parse_debug.txt\n\n") if parse_failed else ""
    overview = "\n".join(
        f"- [{r['index']}] {r.get('authors','')[:30]} ({r.get('year','')}) — "
        f"{r.get('title','')[:60]} [{r.get('relevance','')}]"
        for r in enriched_refs
    )
    (output_dir / "analysis.md").write_text(
        f"# {md_stem}\n\n**关注重点**：{focus}\n\n"
        f"{warning}"
        f"## 深度分析\n\n{analysis}\n\n"
        f"## 引用文献概览\n\n{overview}\n",
        encoding="utf-8",
    )

    # refs.json
    (output_dir / "refs.json").write_text(
        json.dumps(enriched_refs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # todo_download.txt — 只包含 high 相关引用（与 run_analysis_ui.py 保持一致）
    high_refs = [r for r in enriched_refs if r.get("relevance") == "high"]
    lines = [
        f"[{r['index']}] {r['title']} | {r.get('doi') or '—'} | {r.get('pdf_url') or 'NOT_FOUND'}"
        for r in high_refs
    ]
    (output_dir / "todo_download.txt").write_text("\n".join(lines), encoding="utf-8")

    # session log (full conversation for debug)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = output_dir / f"session_{ts}.jsonl"
    log_path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in raw_log),
        encoding="utf-8",
    )

    if parse_failed:
        (output_dir / "parse_debug.txt").write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in raw_log),
            encoding="utf-8",
        )

    return log_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("md_path")
    parser.add_argument("--focus", required=True)
    parser.add_argument("--output-dir", default="papers")
    args = parser.parse_args()

    md_path = Path(args.md_path)
    if not md_path.exists():
        print(f"ERROR: {md_path} not found")
        sys.exit(1)

    md_text = md_path.read_text(encoding="utf-8")
    focus = args.focus
    output_dir = Path(args.output_dir) / md_path.stem

    raw_log: list[dict] = []

    def log(entry: dict):
        raw_log.append(entry)
        # Print tool-call events to console for visibility
        t = entry.get("type", "")
        if t == "tool_call":
            print(f"  → [{entry['tool']}] {json.dumps(entry.get('args',{}), ensure_ascii=False)[:80]}")
        elif t == "tool_result":
            preview = entry.get("content", "")[:120].replace('\n', ' ')
            print(f"    ← {preview}")
        elif t == "warn":
            print(f"  ⚠ {entry['msg']}")
        elif t == "llm_response":
            preview = entry.get("content", "")[:120].replace('\n', ' ')
            print(f"  🤖 {preview!r}")

    log({"type": "session_start", "timestamp": datetime.now().isoformat(),
         "model": MODEL, "focus": focus, "md_path": str(md_path)})

    print(f"论文: {md_path.name}")
    print(f"关注重点: {focus}")
    print(f"模型: {MODEL}")
    print("─" * 60)

    # Pre-extract all refs (for metadata enrichment after loop)
    print("📚 提取引用文献...")
    r = subprocess.run(
        [sys.executable, "scripts/extract_refs.py", str(md_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    all_refs: list[dict] = []
    if r.returncode == 0:
        try:
            all_refs = json.loads(r.stdout)
        except Exception:
            pass
    log({"type": "refs_extracted", "count": len(all_refs)})
    print(f"  找到 {len(all_refs)} 条引用文献")

    # Agentic loop
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"论文路径: {md_path.name}\n关注重点: {focus}\n请开始分析。"},
    ]
    log({"type": "user_message", "content": messages[-1]["content"]})

    search_cache: dict = {}
    analysis = ""
    rated_refs: list[dict] = []
    parse_failed = True
    consec_failures = 0

    print("\n🔄 开始 Agentic Loop")
    for iteration in range(1, MAX_ITER + 1):
        print(f"\n轮 {iteration}/{MAX_ITER}:")

        text = call_llm_with_retry(messages, log)
        if text is None:
            log({"type": "warn", "msg": f"轮{iteration} 连续超时，跳过"})
            consec_failures += 1
            if consec_failures >= MAX_CONSEC_FAILURES:
                print("  连续超时次数过多，退出 loop")
                break
            continue

        log({"type": "llm_response", "iteration": iteration, "content": text})

        result = parse_tool_call(text)
        if result is None:
            log({"type": "warn", "msg": f"轮{iteration} 工具调用解析失败"})
            consec_failures += 1
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "请只输出一个工具调用，格式：[TOOL: 工具名] {参数}"})
            log({"type": "correction_sent"})
            if consec_failures >= MAX_CONSEC_FAILURES:
                print("  连续解析失败次数过多，退出 loop")
                break
            continue

        consec_failures = 0
        tool_name, tool_args = result
        log({"type": "tool_call", "iteration": iteration, "tool": tool_name, "args": tool_args})

        # Execute tool
        if tool_name == "list_sections":
            tool_result = tool_list_sections(md_text)

        elif tool_name == "read_section":
            section_id = tool_args.get("id", 0)
            try:
                section_id = int(section_id)
            except (TypeError, ValueError):
                section_id = 0
            tool_result = tool_read_section(md_text, section_id)

        elif tool_name == "search_ref":
            title = str(tool_args.get("title", ""))
            year = str(tool_args.get("year", ""))
            tool_result = tool_search_ref(title, year, search_cache)

        elif tool_name == "finish":
            analysis, rated_refs = parse_finish(tool_args)
            log({"type": "finish", "analysis_len": len(analysis), "refs_count": len(rated_refs)})
            print(f"  ✓ finish: analysis={len(analysis)}字, refs={len(rated_refs)}条")
            parse_failed = False
            break

        else:
            tool_result = f"[ERROR] 未知工具: {tool_name}"

        log({"type": "tool_result", "tool": tool_name, "content": tool_result})

        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": f"[TOOL_RESULT: {tool_name}]\n{tool_result}"})

    if parse_failed:
        log({"type": "warn", "msg": "loop 结束未收到 finish，降级保存"})
        print("\n⚠ 未收到 finish，降级保存原始 log")

    # Enrich all_refs with rated_refs and search metadata
    print("\n🔍 补充引用元数据...")
    rated_map = {r["index"]: r for r in rated_refs}

    enriched: list[dict] = []
    for ref in all_refs:
        idx = ref.get("index")
        rated = rated_map.get(idx, {})
        ref["relevance"] = rated.get("relevance", "")
        ref["reason"] = rated.get("reason", "")

        # Search metadata if not already in cache
        title = ref.get("title", "")
        year = str(ref.get("year", ""))
        key = f"{title[:50].lower()}|{year}"
        if key not in search_cache and title:
            print(f"  🔍 {title[:50]}...")
            tool_search_ref(title, year, search_cache)
        if key in search_cache:
            meta = search_cache[key]
            for k in ("doi", "pdf_url", "authors", "year"):
                if meta.get(k) and not ref.get(k):
                    ref[k] = meta[k]

        enriched.append(ref)

    log({"type": "enrichment_complete", "count": len(enriched)})

    # Write outputs
    log_path = write_outputs(output_dir, md_path.stem, focus,
                             analysis, enriched, parse_failed, raw_log)

    print(f"\n✅ 完成")
    print(f"  analysis.md      → {output_dir / 'analysis.md'}")
    print(f"  refs.json        → {output_dir / 'refs.json'} ({len(enriched)} 条)")
    print(f"  todo_download.txt→ {output_dir / 'todo_download.txt'}")
    print(f"  session log      → {log_path}")
    if parse_failed:
        print(f"  parse_debug.txt  → {output_dir / 'parse_debug.txt'}")


if __name__ == "__main__":
    main()
