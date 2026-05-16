"""LLM 把用户自然语言研究兴趣翻译成 OpenAlex 检索式（3-5 条）。

设计：
- 输入 intent：用户填的一段自然语言，如 "ABM 应用于宏观经济动态、金融市场、企业行为"
- 输出 list[str]：OpenAlex `?search=` 友好的关键词短语（英文，2-5 词）
- 失败兜底：返回 [intent[:80]] 单条原样
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from services.ai_service import _call_ollama

_log = logging.getLogger(__name__)

_SYSTEM = (
    "You translate a researcher's interest description into OpenAlex ADVANCED boolean "
    "search queries (NOT simple keyword phrases).\n\n"
    "Each query MUST use:\n"
    "- Double quotes around every multi-word phrase: \"agent-based\"\n"
    "- Boolean operators: AND, OR (uppercase)\n"
    "- Parentheses to group alternatives: (\"a\" OR \"b\")\n\n"
    "Strategy: pick the CORE concept that must always be present (use AND), and "
    "expand each side concept with synonyms / variants (use OR). Each query should "
    "cover ONE sub-aspect of the interest. Generate 3-5 such queries, one per aspect.\n\n"
    "Example for interest \"ABM applied to macroeconomic dynamics, financial markets, firm behavior\":\n"
    "[\n"
    "  \"\\\"agent-based\\\" AND (\\\"macroeconomic\\\" OR \\\"macroeconomics\\\" OR \\\"business cycle\\\")\",\n"
    "  \"\\\"agent-based\\\" AND (\\\"financial market\\\" OR \\\"market microstructure\\\" OR \\\"asset price\\\")\",\n"
    "  \"\\\"agent-based\\\" AND (\\\"firm\\\" OR \\\"firm dynamics\\\" OR \\\"corporate\\\")\",\n"
    "  \"\\\"heterogeneous agent\\\" AND (\\\"economic\\\" OR \\\"economy\\\")\"\n"
    "]\n\n"
    "Output ONLY the JSON array. No prose, no markdown fences."
)

# 解析时取第一个出现的 JSON 数组
# greedy 模式：贪婪匹配，避免提前在 "..." 内部停下；qwen 思维链结尾会输出干净的数组，取最长那个
_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def generate_openalex_queries(intent: str, max_n: int = 5) -> list[str]:
    """生成 OpenAlex 检索式。失败回退到 [intent[:80]]。"""
    if not intent or not intent.strip():
        return []
    intent_clean = intent.strip()[:1000]  # 防超长
    # fallback：把整个 intent 当一个带引号的短语；总比啥都不查强
    fallback = [f'"{intent_clean[:80]}"']
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Research interest:\n{intent_clean}\n\nOutput 3-5 advanced OpenAlex boolean queries as JSON array now."},
    ]
    try:
        # qwen3.6-27b 默认开 thinking，思考占 ~3000 token 后才输出答案；
        # num_predict 限制单次输出 token 数，给到 16k（思考 3-5k + 答案足够）。
        # 不能 >= num_ctx (32k) 否则没空间放 input + history。
        raw = _call_ollama(messages, num_predict=16384)
    except Exception as exc:
        _log.warning("generate_openalex_queries ollama error: %s", exc)
        return fallback

    # 优先抓 </think> 之后的内容（如果有 think 标签）
    think_end = raw.rfind("</think>")
    search_text = raw[think_end + len("</think>"):] if think_end >= 0 else raw
    match = _ARRAY_RE.search(search_text)
    if not match:
        match = _ARRAY_RE.search(raw)
    if not match:
        _log.warning("generate_openalex_queries: no JSON array in %.200s", raw)
        return fallback
    try:
        arr = json.loads(match.group())
    except json.JSONDecodeError:
        _log.warning("generate_openalex_queries: JSON decode failed for %.200s", match.group())
        return fallback
    if not isinstance(arr, list):
        return fallback
    out: list[str] = []
    for item in arr[:max_n]:
        if isinstance(item, str):
            s = item.strip()
            # 上限 500：boolean 复合 query 经常 100-300 字符
            # （`"agent-based" AND ("a" OR "b" OR "c" OR "d")` 已经 80+）
            if 2 <= len(s) <= 500:
                out.append(s)
    return out or fallback
