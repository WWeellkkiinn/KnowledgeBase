"""cross_analysis.py — 跨论文综合分析，调用本地 LLM 产出方法论对比报告。

用法：
    python scripts/cross_analysis.py [--focus 研究方法] [--output papers/cross_analysis.md]
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PAPERS_DIR = ROOT / "papers"

sys.path.insert(0, str(Path(__file__).parent))
from run_analysis_ui import OLLAMA_CHAT, MODEL  # noqa: E402

TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=10.0)


def _call_llm(messages: list[dict], num_ctx: int = 65536, num_predict: int = 8192) -> str:
    """流式调用 Ollama，实时打印 token，返回完整文本。"""
    full = ""
    with httpx.stream(
        "POST", OLLAMA_CHAT,
        json={"model": MODEL, "messages": messages, "stream": True,
              "options": {"temperature": 0.1, "num_ctx": num_ctx, "num_predict": num_predict}},
        timeout=TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = obj.get("message", {}).get("content", "")
            if content:
                content = re.sub(r'(<channel\|>|<\|[^>]*\|?>)', '', content)
                print(content, end="", flush=True)
                full += content
            if obj.get("done"):
                break
    print()
    return full


def _extract_summary(insight_md: str) -> str:
    """从 analysis_insight.md 中提取：标题 + 总览 + 小结，跳过详细内容。"""
    lines = insight_md.splitlines()
    result = []
    section = None
    for line in lines:
        if line.startswith("# "):
            result.append(line)
            continue
        if line.startswith("**关注重点**") or line.startswith("**模型**") or line.startswith("**时间**"):
            continue
        if line.startswith("## 总览"):
            section = "总览"
            result.append(line)
            continue
        if line.startswith("## 详细内容"):
            section = "skip"
            continue
        if line.startswith("## 小结"):
            section = "小结"
            result.append(line)
            continue
        if line.startswith("## ") and section == "skip":
            section = "other"
            result.append(line)
            continue
        if section in ("总览", "小结", "other"):
            result.append(line)
    return "\n".join(result).strip()


def collect_insights(focus: str) -> list[tuple[str, str]]:
    """收集所有 analysis_insight.md，返回 [(paper_id, summary_text)]。"""
    items = []
    for insight_path in sorted(PAPERS_DIR.glob("*/analysis_insight.md")):
        paper_id = insight_path.parent.name
        text = insight_path.read_text(encoding="utf-8")
        summary = _extract_summary(text)
        if summary:
            items.append((paper_id, summary))
    return items


SYSTEM = """/no_think
你是学术文献方法论分析专家。用户会提供多篇论文的摘要分析，你需要跨论文进行比较和综合。
请用中文回答，语言简洁学术，不要重复用户提供的原文，而是提炼出洞察。"""

ROUND1_SUFFIX = """

---

以上是 {n} 篇论文的「{focus}」维度摘要分析。

请完成第一步：为每篇论文提取一行速览，格式如下（严格一行一篇）：
| 论文ID | 核心方法 | 数据来源 | 因果识别策略 | 模型/估计量 |
"""

ROUND2 = """基于你对这 {n} 篇论文的梳理，请输出最终综合分析报告，包含以下章节：

## 方法论共识
（这些论文在研究方法上有哪些共同做法？）

## 主要分歧
（哪些方法论选择上存在明显差异？各自的理由是什么？）

## 演化脉络
（从发表时间看，方法论有哪些演进趋势？）

## 关键引用交叉
（哪些方法论文献被多篇论文共同引用？这说明什么？）

不要重复第一步的表格内容，直接输出上述四个章节。"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--focus", default="研究方法")
    parser.add_argument("--output", default=str(PAPERS_DIR / "cross_analysis.md"))
    args = parser.parse_args()

    output_path = Path(args.output)

    print(f"[cross_analysis] 收集论文摘要...", flush=True)
    items = collect_insights(args.focus)
    if not items:
        print("未找到任何 analysis_insight.md，退出。")
        sys.exit(1)
    print(f"[cross_analysis] 共 {len(items)} 篇，开始第一轮 LLM 分析...\n", flush=True)

    # 拼接所有摘要
    corpus = "\n\n---\n\n".join(f"【{pid}】\n{text}" for pid, text in items)
    user1 = corpus + ROUND1_SUFFIX.format(n=len(items), focus=args.focus)

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user1},
    ]
    round1_out = _call_llm(messages)
    if not round1_out:
        print("\n[cross_analysis] 第一轮 LLM 返回为空，退出。")
        sys.exit(1)

    print(f"\n[cross_analysis] 第一轮完成，开始第二轮综合...\n", flush=True)

    messages += [
        {"role": "assistant", "content": round1_out},
        {"role": "user", "content": ROUND2.format(n=len(items))},
    ]
    round2_out = _call_llm(messages)
    if not round2_out:
        print("\n[cross_analysis] 第二轮 LLM 返回为空，退出。")
        sys.exit(1)

    # 写输出文件
    header = (
        f"# 跨论文方法论综合分析\n"
        f"**关注重点**：{args.focus}  \n"
        f"**论文数**：{len(items)} 篇  \n"
        f"**时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n\n"
        f"---\n\n"
        f"## 各论文方法速览\n\n"
        f"{round1_out.strip()}\n\n"
        f"---\n\n"
        f"{round2_out.strip()}\n"
    )
    output_path.write_text(header, encoding="utf-8")
    print(f"\n[cross_analysis] 完成 → {output_path}")


if __name__ == "__main__":
    main()
