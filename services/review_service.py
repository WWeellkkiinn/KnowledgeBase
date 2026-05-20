"""ReviewService —— 跨论文综述生成（M3.5）。

策略：map-reduce + 流式 LLM 调用。
- map：每篇 paper 的 analysis_insight.md 抽 "总览/小结" 段
- reduce：拼接 + 第一轮表格 + 第二轮综合（共识/分歧/演化/交叉引用）

API：generate_stream(paper_ids, focus) → 生成器，逐 chunk yield 文本。
路由层接成 SSE 直接喂到前端 EventSource。

LLM 不可用 / 论文缺 insight 时 yield 一条错误 chunk 并结束，不抛异常（前端体验更好）。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import models
from services.llm_client import chat_completion_stream

_log = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


SYSTEM = (
    "你是学术文献方法论分析专家。用户会提供多篇论文的摘要分析，"
    "你需要跨论文进行比较和综合。请用中文回答，语言简洁学术，不要重复用户提供的原文，"
    "而是提炼出洞察。"
)

ROUND1_SUFFIX = (
    "\n\n---\n\n"
    "以上是 {n} 篇论文的「{focus}」维度摘要分析。\n\n"
    "请完成第一步：为每篇论文提取一行速览，格式如下（严格一行一篇）：\n"
    "| 论文ID | 核心方法 | 数据来源 | 因果识别策略 | 模型/估计量 |\n"
)

ROUND2 = (
    "基于你对这 {n} 篇论文的梳理，请输出最终综合分析报告，包含以下章节：\n\n"
    "## 方法论共识\n（这些论文在研究方法上有哪些共同做法？）\n\n"
    "## 主要分歧\n（哪些方法论选择上存在明显差异？各自的理由是什么？）\n\n"
    "## 演化脉络\n（从发表时间看，方法论有哪些演进趋势？）\n\n"
    "## 关键引用交叉\n（哪些方法论文献被多篇论文共同引用？这说明什么？）\n\n"
    "不要重复第一步的表格内容，直接输出上述四个章节。"
)


def _extract_summary(insight_md: str) -> str:
    """从 analysis_insight.md 抽「总览/小结/其他」段，跳过详细内容。"""
    out: list[str] = []
    section: str | None = None
    for line in insight_md.splitlines():
        if line.startswith("# "):
            out.append(line)
            continue
        if line.startswith(("**关注重点**", "**模型**", "**时间**")):
            continue
        if line.startswith("## 总览"):
            section = "总览"; out.append(line); continue
        if line.startswith("## 详细内容"):
            section = "skip"; continue
        if line.startswith("## 小结"):
            section = "小结"; out.append(line); continue
        if line.startswith("## ") and section == "skip":
            section = "other"; out.append(line); continue
        if section in ("总览", "小结", "other"):
            out.append(line)
    return "\n".join(out).strip()


_CHANNEL_RE = re.compile(r"<channel\|>|<\|[^|>]*\|>")


def _stream_llm(messages: list[dict]) -> Iterator[str]:
    """流式调用 Yinli。yield 每个 content chunk。
    异常时 yield 中性错误说明（不含异常详情，避免泄露内网 URL/路径）。"""
    try:
        for chunk in chat_completion_stream(messages, max_tokens=8192):
            if chunk:
                yield _CHANNEL_RE.sub("", chunk)
    except Exception as e:
        _log.warning("[review] LLM stream error: %s", e)
        yield "\n\n[error] LLM 调用失败（详情见服务日志）。\n"


class ReviewService:
    """生成跨论文综述。无状态；session 仅用于查 paper insight_path。"""

    def generate_stream(
        self, db: Session, paper_ids: Iterable[int], focus: str = "研究方法",
    ) -> Iterator[str]:
        """主入口：yield chunks。第一条 chunk 是元数据 JSON（前端用于初始化）。"""
        ids = [int(i) for i in paper_ids]
        if not ids:
            yield "[error] 未选择论文。\n"
            return

        rows = db.execute(
            select(models.Paper).where(models.Paper.id.in_(ids))
        ).scalars().all()
        if not rows:
            yield "[error] 未找到指定论文。\n"
            return

        root = _project_root()
        items: list[tuple[str, str]] = []
        for p in rows:
            if not p.insight_path:
                continue
            ip = (root / p.insight_path).resolve()
            try:
                if not ip.is_file():
                    continue
                # 防止越界访问：必须在 papers/ 子树
                ip.relative_to((root / "papers").resolve())
                text = ip.read_text(encoding="utf-8")
            except (OSError, ValueError) as e:
                _log.warning("[review] read insight failed for #%s: %s", p.id, e)
                continue
            summary = _extract_summary(text)
            if summary:
                items.append((p.stem, summary))

        if not items:
            yield "[error] 所选论文均无可用的 analysis_insight.md。\n"
            return

        # corpus 截断：num_ctx=65536 token ≈ 200KB；保险按字符截到 150KB，
        # 单篇上限 8KB（防止个别 insight 异常长拖垮上下文）。
        _PER_PAPER_CHAR_LIMIT = 8_000
        _TOTAL_CHAR_LIMIT = 150_000
        truncated_pieces: list[str] = []
        total_chars = 0
        for pid, text in items:
            snippet = text[:_PER_PAPER_CHAR_LIMIT]
            piece = f"【{pid}】\n{snippet}"
            if total_chars + len(piece) > _TOTAL_CHAR_LIMIT:
                yield f"\n[info] 上下文超限，仅采用前 {len(truncated_pieces)} 篇。\n"
                break
            truncated_pieces.append(piece)
            total_chars += len(piece)
        if not truncated_pieces:
            yield "[error] 所选论文 insight 全部为空。\n"
            return

        # 第一轮：表格速览
        n_used = len(truncated_pieces)
        corpus = "\n\n---\n\n".join(truncated_pieces)
        msg_round1 = [
            {"role": "system", "content": SYSTEM},
            {"role": "user",
             "content": corpus + ROUND1_SUFFIX.format(n=n_used, focus=focus)},
        ]

        yield f"# 跨论文综述（关注：{focus}，共 {n_used} 篇）\n\n"
        yield "## 第一轮：速览表格\n\n"
        round1_buf: list[str] = []
        for chunk in _stream_llm(msg_round1):
            round1_buf.append(chunk)
            yield chunk
        round1_text = "".join(round1_buf).strip()
        if not round1_text:
            yield "\n[error] 第一轮 LLM 输出为空，终止。\n"
            return

        # 第二轮：综合分析
        yield "\n\n## 第二轮：综合分析\n\n"
        msg_round2 = msg_round1 + [
            {"role": "assistant", "content": round1_text},
            {"role": "user", "content": ROUND2.format(n=n_used)},
        ]
        for chunk in _stream_llm(msg_round2):
            yield chunk

        yield f"\n\n---\n生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}Z\n"
