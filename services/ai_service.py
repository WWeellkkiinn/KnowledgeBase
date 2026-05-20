"""AI 论文分析服务（F1 打标签 + F2 精炼，单次 LLM 调用）。"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models
from services.llm_client import chat_completion

_log = logging.getLogger(__name__)

_VOCAB_PATH = Path(__file__).parent / "tags_vocab.json"
_CHANNEL_RE = re.compile(r"(<channel\|>|<\|[^|>]*\|>)")
_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?")

# 字段长度上限（防 AI 返回超长字符串污染 DB）
_MAX_TAG_LEN = 32
_MAX_TAGS_PER_PAPER = 6
_MAX_FIELD_LEN = 4000
_MAX_VOCAB_SIZE = 1000

# 进程内 vocab 锁：避免单篇 / 批量并发覆盖文件
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
    # 截断到上限，避免长期无界增长
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
    """规范化 tags：去重、限长、去控制字符、限数量。"""
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
    """规范化字符串字段：转 str + 截断。"""
    if raw is None:
        return ""
    s = str(raw)
    if len(s) > _MAX_FIELD_LEN:
        s = s[:_MAX_FIELD_LEN]
    return s


def _sanitize_findings(raw: Any) -> list[str]:
    """关键发现列表：每条限长，最多 10 条。"""
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
    """F1+F2: 单次调用返回 tags + research_question + methodology + key_findings + title_zh。

    _vocab: 外部传入词表时跳过文件读写（批量场景），由调用方负责持久化。
    返回 {} 表示分析失败（JSON 解析错误或 Ollama 异常）。
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
            _log.warning("analyze_paper: JSON parse error: %s — raw: %.200s", exc, raw)
            return {}

        if not isinstance(result, dict):
            _log.warning("analyze_paper: response is not an object")
            return {}
    except Exception:
        _log.exception("analyze_paper failed for paper title=%.100s", title)
        return {}

    # 规范化所有字段
    clean: dict = {
        "tags": _sanitize_tags(result.get("tags")),
        "title_zh": _sanitize_text(result.get("title_zh")),
        "research_question": _sanitize_text(result.get("research_question")),
        "methodology": _sanitize_text(result.get("methodology")),
        "key_findings": _sanitize_findings(result.get("key_findings")),
    }

    # 至少要有一个有效字段，否则视为失败
    if not (clean["tags"] or clean["title_zh"] or clean["research_question"]
            or clean["methodology"] or clean["key_findings"]):
        _log.warning("analyze_paper: all fields empty after sanitize")
        return {}

    # 更新词表（仅在独立调用时）；加锁 + 读最新 vocab 后写入，避免并发覆盖
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


def score_relevance(title: str, abstract: str) -> Optional[float]:
    """为 digest 服务返回论文与 ABM 领域的相关性分（0.0–1.0）。
    返回 None 表示评分失败（区别于真实低相关 0.0）。
    """
    messages = [
        {
            "role": "system",
            "content": (
                "Output only a single decimal number between 0.0 and 1.0 indicating "
                "how relevant this paper is to Agent-Based Modeling (ABM), complex adaptive "
                "systems, social simulation, or computational social science. "
                "No explanation, just the number."
            ),
        },
        {
            "role": "user",
            "content": f"Title: {title}\nAbstract: {abstract[:600]}",
        },
    ]
    try:
        raw = chat_completion(messages, max_tokens=64)

        # 容错解析：从带文本的响应中抓第一个小数
        m = _FLOAT_RE.search(raw)
        if not m:
            _log.warning("score_relevance: no float in response: %.100s", raw)
            return None
        try:
            return min(1.0, max(0.0, float(m.group())))
        except ValueError:
            return None
    except Exception:
        _log.exception("score_relevance failed for title=%.100s", title)
        return None


def run_batch_analysis(db: Session) -> dict:
    """对所有有摘要但尚未 AI 分析的论文批量运行 F1+F2。"""
    papers = db.execute(
        select(models.Paper).where(
            models.Paper.abstract.isnot(None),
            models.Paper.abstract != "",
            models.Paper.ai_analyzed_at.is_(None),
        )
    ).scalars().all()

    # 词表锁保护下读 + 写
    with _VOCAB_LOCK:
        vocab = _load_vocab()
        vocab_set = set(vocab)

    processed = 0
    errors = 0
    for p in papers:
        result = analyze_paper(p.title or "", p.abstract or "", _vocab=vocab)
        if not result:
            # 标记已尝试，避免反复重试同一失败论文
            p.ai_analyzed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            try:
                db.commit()
            except Exception:
                db.rollback()
            errors += 1
            continue

        for t in result.get("tags") or []:
            if t and t not in vocab_set:
                vocab_set.add(t)
                vocab.append(t)

        new_tags = result.get("tags") or []
        # 只在拿到新 tags 时覆盖，避免 [] 抹掉原有有效值
        if new_tags:
            p.tags = new_tags
        p.ai_summary = {k: v for k, v in result.items() if k != "tags"}
        p.ai_analyzed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            db.commit()
            processed += 1
        except Exception as exc:
            db.rollback()
            _log.warning("run_batch_analysis commit error paper_id=%s: %s", p.id, exc)
            errors += 1

    if vocab:
        with _VOCAB_LOCK:
            # 合并最新磁盘 vocab（防并发覆盖）后写回
            disk = _load_vocab()
            disk_set = set(disk)
            for t in vocab:
                if t not in disk_set:
                    disk.append(t)
                    disk_set.add(t)
            _save_vocab(disk)

    _log.info("run_batch_analysis done: processed=%d errors=%d", processed, errors)
    return {"processed": processed, "errors": errors}
