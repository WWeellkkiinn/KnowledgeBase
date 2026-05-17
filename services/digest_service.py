"""每日邮件日报服务（F3）。"""
from __future__ import annotations

import html as _html
import logging
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from database import models
from services.ai_service import analyze_paper, score_relevance

_log = logging.getLogger(__name__)

_SMTP_HOST = "smtp.163.com"
_SMTP_PORT = 465

# 单次 digest 处理的硬上限，防失控阻塞
_HARD_PAPER_CAP = 500

_LABEL_STYLE = (
    "display:block;color:#0f172a;font-size:14px;font-weight:600;"
    "margin:14px 0 4px;letter-spacing:0.3px"
)


def _ensure_scripts_path() -> None:
    scripts_dir = str(Path(__file__).parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def _get_email_config() -> tuple[str, str, str]:
    """返回 (from_addr, to_addr, auth_code)；缺失时返回空 auth_code 以阻止意外发件。"""
    _ensure_scripts_path()
    try:
        import config as _cfg
        return _cfg.DIGEST_FROM, _cfg.DIGEST_TO, _cfg.DIGEST_AUTH_CODE
    except Exception:
        return "", "", ""


def _e(text) -> str:
    """HTML 转义，防止 XSS。"""
    return _html.escape("" if text is None else str(text))


def _journal_dict(p) -> Optional[dict]:
    if p.journal is None:
        return None
    return {"name": p.journal.name, "quality_tier": p.journal.quality_tier}


def _make_entry(p, *, relevance: float, tags, ai_summary) -> dict:
    return {
        "title": p.title or "",
        "year": p.year,
        "authors": p.authors_json or [],
        "relevance": relevance,
        "tags": tags or [],
        "ai_summary": ai_summary or {},
        "journal": _journal_dict(p),
    }


def _build_html(entries: list[dict], date_str: str) -> str:
    parts: list[str] = []
    for e in entries:
        tags_html = ""
        if e.get("tags"):
            chips = "".join(
                f'<span style="display:inline-block;background:#dbeafe;color:#1d4ed8;'
                f'border-radius:9999px;padding:2px 10px;font-size:13px;margin:2px 4px 0 0">'
                f'{_e(t)}</span>'
                for t in e["tags"]
            )
            tags_html = f'<p style="margin:10px 0 0">{chips}</p>'

        summary_parts: list[str] = []
        s = e.get("ai_summary") or {}
        if s.get("research_question"):
            summary_parts.append(
                f'<div><span style="{_LABEL_STYLE}">研究问题</span>'
                f'<p style="margin:0;line-height:1.6">{_e(s["research_question"])}</p></div>'
            )
        if s.get("methodology"):
            summary_parts.append(
                f'<div><span style="{_LABEL_STYLE}">方法</span>'
                f'<p style="margin:0;line-height:1.6">{_e(s["methodology"])}</p></div>'
            )
        if s.get("key_findings"):
            findings = "".join(
                f'<li style="margin:2px 0">{_e(f)}</li>' for f in s["key_findings"]
            )
            summary_parts.append(
                f'<div><span style="{_LABEL_STYLE}">关键发现</span>'
                f'<ul style="margin:0;padding-left:20px;line-height:1.6">{findings}</ul></div>'
            )
        summary_html = "".join(summary_parts)

        relevance_badge = (
            f'<span style="background:#f0fdf4;color:#16a34a;border-radius:4px;'
            f'padding:2px 8px;font-size:12px;margin-left:8px">相关性 {e["relevance"]:.2f}</span>'
        )

        authors = ", ".join(_e(a) for a in (e.get("authors") or [])[:3])
        year_str = _e(e.get("year"))

        journal = e.get("journal") or {}
        journal_html = ""
        if journal.get("name"):
            tier = journal.get("quality_tier")
            tier_html = (
                f' <span style="background:#fef3c7;color:#92400e;border-radius:4px;'
                f'padding:1px 6px;font-size:11px;margin-left:4px">T{_e(tier)}</span>'
                if tier else ""
            )
            journal_html = (
                f' &nbsp;·&nbsp; <em style="color:#475569;font-style:normal">'
                f'{_e(journal["name"])}</em>{tier_html}'
            )

        meta = f'{year_str}{"  ·  " + authors if authors else ""}{journal_html}'

        title_zh = (e.get("ai_summary") or {}).get("title_zh") or ""
        title_zh_html = (
            f'<p style="margin:0 0 4px;font-size:13px;color:#475569">{_e(title_zh)}</p>'
            if title_zh else ""
        )

        parts.append(
            f'<div style="border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:16px">'
            f'<p style="margin:0 0 2px;font-size:16px;font-weight:600;color:#1e293b">{_e(e["title"])}</p>'
            f'{title_zh_html}'
            f'<p style="margin:0;font-size:12px;color:#64748b">{meta} &nbsp; {relevance_badge}</p>'
            f'{tags_html}{summary_html}'
            f'</div>'
        )

    body = "".join(parts) or '<p style="color:#64748b">今日暂无相关论文。</p>'
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;max-width:720px;margin:0 auto;padding:24px;color:#334155">
<h2 style="color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:8px">
  KnowledgeBase · 今日论文日报 · {_e(date_str)}</h2>
{body}
<p style="font-size:11px;color:#94a3b8;margin-top:24px">
  由 KnowledgeBase 自动生成</p>
</body></html>"""


def _send_html_mail(subject: str, html: str) -> dict:
    """组装并发送一封 HTML 邮件。配置缺失返回 reason；SMTP 失败抛 RuntimeError。"""
    from_addr, to_addr, auth_code = _get_email_config()
    if not auth_code or not from_addr or not to_addr:
        _log.error("digest: email config not loaded")
        return {"sent": False, "reason": "missing_email_config"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, context=ctx) as server:
            server.login(from_addr, auth_code)
            server.send_message(msg)
        return {"sent": True}
    except smtplib.SMTPException as exc:
        # 不让授权码意外随 stack trace 漏到日志
        _log.error("digest send failed (SMTP): %s", type(exc).__name__)
        raise RuntimeError(f"SMTP failure: {type(exc).__name__}") from None


def send_digest(
    db: Session,
    *,
    hours_back: int = 24,
    core_only: bool = False,
    skip_ai: bool = False,
    limit: int | None = None,
    min_relevance: float = 0.6,
) -> dict:
    """查询过去 hours_back 小时新增论文，过滤 ABM 相关，发送 HTML 邮件。
    hours_back=0 表示查询全部论文（手动全量触发用）。
    core_only=True 时只查核心论文（is_core=True）。
    skip_ai=True 时跳过 score_relevance 和 analyze_paper，全部论文直接进邮件（仅验证 SMTP）。
    limit 限定最多取多少篇（None 时使用硬上限 _HARD_PAPER_CAP）。
    min_relevance 是 ABM 相关性阈值；设 0.0 关闭过滤。
    """
    base_filters = [
        models.Paper.abstract.isnot(None),
        models.Paper.abstract != "",
    ]
    if core_only:
        base_filters.append(models.Paper.is_core.is_(True))

    effective_limit = limit if limit is not None else _HARD_PAPER_CAP

    if hours_back > 0:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours_back)
        stmt = select(models.Paper).where(models.Paper.added_at >= since, *base_filters)
    else:
        stmt = select(models.Paper).where(*base_filters)
    # eager load journal 避免 N+1
    stmt = stmt.options(selectinload(models.Paper.journal)).limit(effective_limit)

    papers = db.execute(stmt).scalars().all()

    if not papers:
        _log.info("digest: no papers found (hours_back=%d)", hours_back)
        return {"sent": False, "reason": "no_new_papers"}

    entries: list[dict] = []
    score_failed = 0
    analyze_failed = 0

    for p in papers:
        title = p.title or ""
        abstract = p.abstract or ""
        if not title:
            continue

        if skip_ai:
            ai_summary = p.ai_summary or {
                "research_question": (abstract[:300] + "…") if len(abstract) > 300 else abstract
            }
            entries.append(_make_entry(p, relevance=1.0, tags=p.tags, ai_summary=ai_summary))
            continue

        rel = score_relevance(title, abstract)
        if rel is None:
            score_failed += 1
            continue
        if rel < min_relevance:
            continue

        entry_tags = list(p.tags or [])
        entry_summary = dict(p.ai_summary or {})

        # 触发 F1+F2（未分析过）
        if abstract and not p.ai_analyzed_at:
            result = analyze_paper(title, abstract)
            # 无论成功失败，都标记 ai_analyzed_at 避免反复重试
            p.ai_analyzed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if result:
                new_tags = result.get("tags") or []
                new_summary = {k: v for k, v in result.items() if k != "tags"}
                if new_tags:
                    p.tags = new_tags
                    entry_tags = new_tags
                p.ai_summary = new_summary
                entry_summary = new_summary
            else:
                analyze_failed += 1
            try:
                db.commit()
            except Exception:
                db.rollback()

        # 当本篇彻底无内容（无 tags / 无 summary）时跳过，避免空白卡片
        if not entry_tags and not entry_summary:
            continue

        entries.append(_make_entry(p, relevance=rel, tags=entry_tags, ai_summary=entry_summary))

    if not entries:
        _log.info(
            "digest: no entries (score_failed=%d, analyze_failed=%d, threshold=%.2f)",
            score_failed, analyze_failed, min_relevance,
        )
        return {
            "sent": False,
            "reason": "no_relevant_papers",
            "score_failed": score_failed,
            "analyze_failed": analyze_failed,
        }

    entries.sort(key=lambda x: x["relevance"], reverse=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html = _build_html(entries, date_str)

    result = _send_html_mail(
        f"[KnowledgeBase] 今日论文日报 · {date_str}（共 {len(entries)} 篇）", html,
    )
    if result.get("sent"):
        _log.info("digest sent: %d papers", len(entries))
        result["paper_count"] = len(entries)
    return result


def _build_subscription_html(rows: list[tuple], date_str: str) -> str:
    """rows: [(SubscriptionResult, Subscription)]，按 llm_score desc 已排序"""
    from services.card_renderer import render_subscription_card

    # 按订阅分组，(sub, results) 保留首次出现顺序（dict 在 Python 3.7+ 已保序）
    groups: dict[int, tuple] = {}
    for r, sub in rows:
        sid = sub.id if sub else 0
        if sid not in groups:
            groups[sid] = (sub, [])
        groups[sid][1].append(r)

    parts: list[str] = []
    for sub, results in groups.values():
        label = ((sub.description or "").strip() or (sub.type or "订阅")) if sub else "订阅"
        parts.append(
            f'<h3 style="color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:6px;'
            f'margin:28px 0 12px;font-size:14px;font-weight:600">{_e(label)}</h3>'
        )
        for i, r in enumerate(results):
            parts.append(render_subscription_card(r, sub, card_index=i + 1))

    body = "".join(parts) or '<p style="color:#64748b">无评分结果。</p>'
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,sans-serif;max-width:720px;margin:0 auto;padding:24px;color:#334155">
<h2 style="color:#1e293b;border-bottom:1px solid #e2e8f0;padding-bottom:8px">
  KnowledgeBase · 订阅推送 · {_e(date_str)}</h2>
{body}
<p style="font-size:11px;color:#94a3b8;margin-top:24px">由 KnowledgeBase 自动生成</p>
</body></html>"""


def send_subscription_digest(
    db: Session,
    *,
    subscription_id: Optional[int] = None,
    limit: int = 30,
    min_score: float = 0.65,
) -> dict:
    """把 subscription_results 中已评分的 top-N（按 llm_score desc）打成邮件。
    subscription_id 不为空时只取该订阅的结果。
    """
    stmt = (
        select(models.SubscriptionResult, models.Subscription)
        .join(models.Subscription, models.SubscriptionResult.subscription_id == models.Subscription.id)
        .where(models.SubscriptionResult.scored_at.isnot(None))
        .where(models.SubscriptionResult.llm_score.isnot(None))
        .where(models.SubscriptionResult.llm_score >= min_score)
        .where(models.SubscriptionResult.notified.is_(False))
    )
    if subscription_id is not None:
        stmt = stmt.where(models.SubscriptionResult.subscription_id == subscription_id)
    stmt = stmt.order_by(
        models.SubscriptionResult.llm_score.desc(),
        models.SubscriptionResult.found_at.desc(),
    ).limit(limit)
    rows = list(db.execute(stmt).all())
    if not rows:
        _log.info("subscription_digest: no scored rows")
        return {"sent": False, "reason": "no_scored_results"}

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html = _build_subscription_html(rows, date_str)

    result = _send_html_mail(
        f"[KnowledgeBase] 订阅推送 · {date_str}（共 {len(rows)} 篇）", html,
    )
    if result.get("sent"):
        _log.info("subscription_digest sent: %d papers", len(rows))
        for r, _sub in rows:
            r.notified = True
        db.commit()
        result["paper_count"] = len(rows)
    return result
