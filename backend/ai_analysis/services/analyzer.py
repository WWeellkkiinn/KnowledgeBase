"""F1+F2 AI paper analyzer.

Ported from services/ai_service.py — same prompts, same JSON parsing, same sanitization.
Vocab file is in ai_analysis/services/tags_vocab.json (relative to this file).
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from .llm import chat_completion

_log = logging.getLogger(__name__)

_VOCAB_PATH = Path(__file__).parent / "tags_vocab.json"
_CHANNEL_RE = re.compile(r"(<channel\|>|<\|[^|>]*\|>)")

_MAX_TAG_LEN = 32
_MAX_TAGS_PER_PAPER = 6
_MAX_FIELD_LEN = 4000
_MAX_VOCAB_SIZE = 1000

_VOCAB_LOCK = threading.Lock()

_SYSTEM = (
    "你是一名学术论文分析助手。给定论文标题和摘要，"
    "仅输出一个合法 JSON 对象（不带 markdown 包裹，不带任何解释）。"
    "所有内容（标签、研究问题、方法、关键发现、标题翻译）必须用简体中文。"
    "标签使用 2-4 字的中文短语（如：专利分析、机器学习、社会网络）。"
)


def _load_vocab() -> list[str]:
    try:
        data = json.loads(_VOCAB_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [t for t in data if isinstance(t, str) and t]
    except Exception:
        pass
    return []


def _save_vocab(vocab: list[str]) -> None:
    if len(vocab) > _MAX_VOCAB_SIZE:
        vocab = vocab[-_MAX_VOCAB_SIZE:]
    tmp = _VOCAB_PATH.with_name(f"tags_vocab_{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(sorted(set(vocab)), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_VOCAB_PATH)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _sanitize_tags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for t in raw:
        if not isinstance(t, str):
            continue
        t = re.sub(r"[\x00-\x1f\x7f]", "", t).strip()
        if not t:
            continue
        if len(t) > _MAX_TAG_LEN:
            t = t[:_MAX_TAG_LEN]
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= _MAX_TAGS_PER_PAPER:
            break
    return out


def _sanitize_text(raw: Any) -> str:
    if raw is None:
        return ""
    s = str(raw)
    return s[:_MAX_FIELD_LEN]


def _sanitize_findings(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = []
    for f in raw[:10]:
        if f is None:
            continue
        s = str(f)
        if len(s) > _MAX_FIELD_LEN:
            s = s[:_MAX_FIELD_LEN]
        if s.strip():
            out.append(s)
    return out


def analyze_paper(
    title: str,
    abstract: str,
    *,
    _vocab: list[str] | None = None,
) -> dict:
    """F1+F2: tags + research_question + methodology + key_findings + title_zh.

    Returns {} on failure.
    """
    owns_vocab = _vocab is None
    vocab = _load_vocab() if owns_vocab else list(_vocab)
    vocab_str = json.dumps(vocab, ensure_ascii=False)

    prompt = (
        f"已有中文标签词表（优先复用，词表无合适项再新增）:\n{vocab_str}\n\n"
        f"论文标题: {title}\n"
        f"摘要: {abstract}\n\n"
        "请输出包含以下字段的 JSON：\n"
        '{"title_zh": "论文标题的简体中文翻译",'
        '"tags": ["中文标签1","中文标签2","中文标签3"],'
        '"research_question": "1-2 句中文描述本文研究的核心问题",'
        '"methodology": "中文简述研究方法/数据/模型",'
        '"key_findings": ["中文关键发现 1","中文关键发现 2"]}'
    )

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _CHANNEL_RE.sub("", chat_completion(messages)).strip()
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            _log.warning("analyze_paper: no JSON found in response: %.200s", raw)
            return {}
        try:
            result = json.loads(json_match.group())
        except json.JSONDecodeError as exc:
            _log.warning("analyze_paper: JSON parse error: %s", exc)
            return {}
        if not isinstance(result, dict):
            return {}
    except Exception:
        _log.exception("analyze_paper failed for title=%.100s", title)
        return {}

    clean: dict = {
        "tags": _sanitize_tags(result.get("tags")),
        "title_zh": _sanitize_text(result.get("title_zh")),
        "research_question": _sanitize_text(result.get("research_question")),
        "methodology": _sanitize_text(result.get("methodology")),
        "key_findings": _sanitize_findings(result.get("key_findings")),
    }

    if not (clean["tags"] or clean["title_zh"] or clean["research_question"]
            or clean["methodology"] or clean["key_findings"]):
        return {}

    if owns_vocab and clean["tags"]:
        with _VOCAB_LOCK:
            latest = _load_vocab()
            latest_set = set(latest)
            for t in clean["tags"]:
                if t not in latest_set:
                    latest.append(t)
                    latest_set.add(t)
            _save_vocab(latest)

    return clean
