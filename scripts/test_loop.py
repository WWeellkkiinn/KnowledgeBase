"""test_loop.py — Stress test tool-use loop capability of local LLM.

T1: Basic tool call format reliability (5 independent calls)
T2: Multi-turn coherence with short context (up to 10-turn simulated loop)
T3: Long context stress test (2k / 6k / 12k / 24k chars, 3 turns each)

Usage:
  python scripts/test_loop.py
  python scripts/test_loop.py --md-path papers/xxx/xxx.md
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

OLLAMA_BASE = "http://<ollama-host>:13811/v1"
MODEL = "gemma4-31b"
TIMEOUT = 180

SYSTEM_PROMPT = """\
你是一个学术文献调研助手。每次回复只输出一个工具调用，格式如下，不要加任何其他文字：

[TOOL: list_sections]
→ 列出论文的所有章节标题

[TOOL: read_section] {"id": <整数>}
→ 读取指定章节内容

[TOOL: search_ref] {"title": "<标题>", "year": "<年份>"}
→ 搜索引用文献元数据

[TOOL: finish] {"analysis": "<中文分析>", "refs": [{"index": <整数>, "relevance": "high"|"medium"|"low", "reason": "<理由>"}]}
→ 输出最终分析结果，结束对话

规则：每次只输出一行工具调用，调用后等待结果，不要自行补充工具结果。\
"""

TOOL_CALL_RE = re.compile(r'\[TOOL:\s*(\w+)\]\s*(\{.*\})?', re.DOTALL)

# ── Mock data for T2/T3 ──────────────────────────────────────────────────────

MOCK_SECTIONS = json.dumps([
    {"id": 0, "title": "Introduction"},
    {"id": 1, "title": "Literature Review"},
    {"id": 2, "title": "Methodology"},
    {"id": 3, "title": "Results"},
    {"id": 4, "title": "Conclusion"},
    {"id": 5, "title": "References"},
], ensure_ascii=False)

MOCK_SECTION_CONTENT = """\
## Methodology

本研究使用倾向得分匹配（PSM）从 USPTO 专利数据库识别 AI 专利。
机器学习分类器 [1] 对1990-2020年专利进行分类，以 IT 专利 [2] 为对照组。
粗化精确匹配（CEM）[3] 确保样本均衡，控制申请人、类别和年份。
回归采用加权最小二乘法（WLS）[4]，因变量为专利引文覆盖度。
"""

MOCK_REF_META = json.dumps({
    "title": "Machine learning classification of patents",
    "authors": "Smith, J., Lee, K.",
    "year": "2020",
    "doi": "10.1234/example",
    "pdf_url": "https://example.com/paper.pdf",
}, ensure_ascii=False)


# ── Helpers ──────────────────────────────────────────────────────────────────

def call_llm(messages: list[dict], label: str = "") -> str:
    client = httpx.Client(timeout=TIMEOUT)
    resp = client.post(
        f"{OLLAMA_BASE}/chat/completions",
        headers={"Authorization": "Bearer ollama"},
        json={"model": MODEL, "messages": messages, "stream": False, "temperature": 0.1},
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    # Clean Gemma special tokens
    content = re.sub(r'(<channel\|>|<\|[^>]*\|?>|\bthought\b)', '', content).strip()
    if label:
        preview = content[:120].replace('\n', ' ')
        print(f"    [{label}] {preview!r}")
    return content


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


def simulate_tool(name: str, args: dict) -> str:
    if name == "list_sections":
        return f"[TOOL_RESULT: list_sections]\n{MOCK_SECTIONS}"
    if name == "read_section":
        return f"[TOOL_RESULT: read_section]\n{MOCK_SECTION_CONTENT}"
    if name == "search_ref":
        return f"[TOOL_RESULT: search_ref]\n{MOCK_REF_META}"
    return f"[TOOL_RESULT: {name}]\nunknown tool"


def check_degradation(text: str) -> list[str]:
    issues = []
    if bool(re.search(r'(.{15,})\1{3,}', text)):
        issues.append("重复输出")
    if '\ufffd' in text:
        issues.append("乱码字符")
    if len(re.findall(r'<\|[^>]*\|>', text)) > 3:
        issues.append("特殊token残留")
    if len(text) > 4000:
        issues.append(f"输出过长({len(text)}字)")
    return issues


# ── T1 ───────────────────────────────────────────────────────────────────────

def test_t1() -> dict:
    print("\n=== T1: 基础工具调用格式（5次独立调用）===")
    successes = 0
    for i in range(5):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "请开始分析论文，首先列出所有章节。"},
        ]
        try:
            t0 = time.time()
            text = call_llm(messages, f"T1-{i+1}")
            elapsed = time.time() - t0
            result = parse_tool_call(text)
            if result and result[0] == "list_sections":
                successes += 1
                print(f"  T1-{i+1}: ✓ list_sections ({elapsed:.1f}s)")
            else:
                got = result[0] if result else "未解析到工具调用"
                print(f"  T1-{i+1}: ✗ got={got!r} ({elapsed:.1f}s)")
        except Exception as e:
            print(f"  T1-{i+1}: ✗ 异常: {e}")
    passed = successes >= 4
    print(f"  结果: {successes}/5 {'✓ 通过' if passed else '✗ 未通过'}")
    return {"success": successes, "total": 5, "pass": passed}


# ── T2 ───────────────────────────────────────────────────────────────────────

def test_t2() -> dict:
    print("\n=== T2: 多轮对话连贯性（最多10轮）===")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "请分析这篇论文的研究方法，关注重点：研究方法和样本构建策略。"},
    ]

    completed = False
    finish_ok = False

    for turn in range(1, 11):
        try:
            t0 = time.time()
            text = call_llm(messages, f"T2-轮{turn}")
            elapsed = time.time() - t0
            result = parse_tool_call(text)
            issues = check_degradation(text)

            if result is None:
                print(f"  轮{turn}: ✗ 未检测到工具调用 ({elapsed:.1f}s) issues={issues}")
                break

            name, args = result
            print(f"  轮{turn}: [{name}] ({elapsed:.1f}s)", end="")
            if issues:
                print(f" ⚠ {issues}", end="")
            print()

            if name == "finish":
                completed = True
                analysis = args.get("analysis", "")
                refs = args.get("refs", [])
                if isinstance(refs, list) and analysis:
                    finish_ok = True
                    print(f"    analysis={len(analysis)}字, refs={len(refs)}条 ✓")
                else:
                    print(f"    ✗ finish 结构不完整 analysis={bool(analysis)} refs_type={type(refs).__name__}")
                break

            tool_result = simulate_tool(name, args)
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": tool_result})

        except Exception as e:
            print(f"  轮{turn}: ✗ 异常: {e}")
            break

    passed = completed and finish_ok
    print(f"  结果: completed={completed}, finish_json={finish_ok} {'✓ 通过' if passed else '✗ 未通过'}")
    return {"completed": completed, "finish_ok": finish_ok, "pass": passed}


# ── T3 ───────────────────────────────────────────────────────────────────────

def test_t3(md_path: Path | None) -> dict:
    print("\n=== T3: 长上下文压力测试（2k/6k/12k/24k，各3轮）===")

    if md_path and md_path.exists():
        base_text = md_path.read_text(encoding="utf-8")
        print(f"  使用论文文件: {md_path.name} ({len(base_text)}字符)")
    else:
        base_text = ("这是模拟的论文正文，包含方法论描述和引用标记 [1][2][3]。"
                     "研究使用倾向得分匹配方法，采用专利数据库。") * 500
        print("  使用合成文本（未找到论文MD文件）")

    results = {}
    for length in [2000, 6000, 12000, 24000]:
        chunk = base_text[:length]
        label = f"{length // 1000}k"
        print(f"\n  --- {label}字符 ---")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是论文内容节选（{label}字符）：\n\n{chunk}\n\n请开始分析，首先列出所有章节。"},
        ]

        turn_results = []
        for turn in range(1, 4):
            try:
                t0 = time.time()
                text = call_llm(messages, f"T3-{label}-轮{turn}")
                elapsed = time.time() - t0

                result = parse_tool_call(text)
                issues = check_degradation(text)
                ok = result is not None and not issues

                status = "✓" if ok else "✗"
                issue_str = f" ⚠ {issues}" if issues else ""
                fmt_str = f"[{result[0]}]" if result else "无工具调用"
                print(f"    轮{turn}: {status} {fmt_str} ({elapsed:.1f}s){issue_str}")
                turn_results.append(ok)

                if result and result[0] != "finish":
                    name, args = result
                    tool_result = simulate_tool(name, args)
                    messages.append({"role": "assistant", "content": text})
                    messages.append({"role": "user", "content": tool_result})

            except Exception as e:
                print(f"    轮{turn}: ✗ 异常: {e}")
                turn_results.append(False)

        stable = sum(turn_results) >= 2
        results[label] = {"turn_results": turn_results, "stable": stable}
        print(f"    {label} → {'✓ 稳定' if stable else '✗ 不稳定'} ({sum(turn_results)}/3 轮正常)")

    stable_labels = [k for k, v in results.items() if v["stable"]]
    return {"results": results, "stable_lengths": stable_labels}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--md-path", default=None, help="已转换的论文 MD 文件路径（T3 用）")
    parser.add_argument("--skip", nargs="*", choices=["t1", "t2", "t3"], default=[],
                        help="跳过指定测试")
    args = parser.parse_args()

    md_path = Path(args.md_path) if args.md_path else None

    # Auto-detect if not provided
    if md_path is None:
        candidates = list(Path("papers").glob("**/*.md")) if Path("papers").exists() else []
        if candidates:
            md_path = candidates[0]
            print(f"自动检测到论文文件: {md_path}")

    print(f"模型: {MODEL}")
    print(f"Ollama: {OLLAMA_BASE}")
    print("=" * 50)

    r1 = test_t1() if "t1" not in args.skip else {"pass": None, "skip": True}
    r2 = test_t2() if "t2" not in args.skip else {"pass": None, "skip": True}
    r3 = test_t3(md_path) if "t3" not in args.skip else {"stable_lengths": None, "skip": True}

    print("\n" + "=" * 50)
    print("测试报告")
    print("=" * 50)

    def fmt(r, key="pass"):
        v = r.get(key)
        if r.get("skip"):
            return "跳过"
        return "✓ 通过" if v else "✗ 未通过"

    t1_detail = f"{r1.get('success', '?')}/5" if not r1.get("skip") else ""
    t2_detail = f"completed={r1.get('completed', '?')}" if not r2.get("skip") else ""
    t3_stable = ", ".join(r3.get("stable_lengths") or []) or "无" if not r3.get("skip") else "跳过"

    print(f"T1 格式成功率: {t1_detail}  {fmt(r1)}")
    print(f"T2 多轮连贯性: {fmt(r2)}")
    print(f"T3 稳定上下文长度: {t3_stable}")

    # Conclusion
    t1_ok = r1.get("pass") is not False
    t2_ok = r2.get("pass") is not False
    t3_lengths = r3.get("stable_lengths") or []

    if t1_ok and t2_ok and ("12k" in t3_lengths or "24k" in t3_lengths):
        conclusion = "✓ 可用 — 推荐实施 agentic loop 方案"
    elif t1_ok and t2_ok:
        max_stable = t3_lengths[-1] if t3_lengths else "2k以下"
        conclusion = f"⚠ 有限可用 — 上下文建议不超过 {max_stable}，可实施但需限制章节长度"
    elif t1_ok:
        conclusion = "⚠ 格式可用但多轮不稳定 — 建议回退到单次调用方案（固定管道）"
    else:
        conclusion = "✗ 不可用 — 模型无法可靠输出工具调用格式，建议回退到固定管道方案"

    print(f"\n结论: {conclusion}")


if __name__ == "__main__":
    main()
