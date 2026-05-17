from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

_TPL_DIR = Path(__file__).parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TPL_DIR)),
    autoescape=select_autoescape(['html', 'j2']),
    auto_reload=False,
)
_card_tpl = _env.get_template("subscription_card.html.j2")


def _display_date(meta: dict) -> str:
    pdate = (meta.get("publication_date") or "").strip()
    year = meta.get("year")
    if pdate:
        return pdate
    if year:
        return str(year)
    return ""


def render_subscription_card(result, subscription, card_index: int | None = None) -> str:
    """渲染单个订阅推送卡片 HTML 片段。"""
    meta = result.raw_metadata_json or {}
    authors_list = (meta.get("authors_json") or [])[:3]
    authors = ", ".join(a for a in authors_list if a)

    desc = (subscription.description or "").strip() if subscription else ""
    sub_label = desc[:80] if desc else (subscription.type if subscription else "")

    return _card_tpl.render(
        card_index=card_index,
        result_id=result.id,
        paper_id=result.paper_id,
        title=meta.get("title") or "",
        url=meta.get("url") or "",
        title_zh=result.title_zh or "",
        llm_score=result.llm_score,
        display_date=_display_date(meta),
        authors=authors,
        cited_by_count=meta.get("cited_by_count"),
        tags=list(result.tags_json or [])[:4],
        research_question=result.research_question or "",
        methodology=result.methodology or "",
        key_findings=list(result.key_findings_json or []),
        llm_reason=result.llm_reason or "",
        subscription_label=sub_label,
    )
