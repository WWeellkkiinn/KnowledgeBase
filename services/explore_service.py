from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import models
from services.bandit import batch_stats, score_card_with_stats, expected_score_with_stats
from services.reference_fetcher import _openalex_mailto, _reconstruct_abstract

_log = logging.getLogger(__name__)

_NORM_TITLE_RE = re.compile(r"[^\w一-鿿]+", flags=re.UNICODE)
_fill_lock = threading.Lock()
_filling_subs: set[int] = set()   # 防止同一 sub_id 并发填充
_scoring_lock = threading.Lock()
_scoring_subs: set[int] = set()   # 防止同一 sub_id 并发 LLM 评分


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _norm_title(s: str) -> str:
    return _NORM_TITLE_RE.sub(" ", (s or "").lower()).strip()


def _openalex_work_to_meta(work: dict) -> dict:
    doi = (work.get("doi") or "").strip()
    primary = work.get("primary_location") or {}
    venue = primary.get("source") or {}
    url = (
        (primary.get("landing_page_url") or "").strip()
        or (f"https://doi.org/{doi}" if doi and not doi.startswith("http") else doi)
        or (work.get("id") or "").strip()
    )
    authors = [
        a["author"]["display_name"]
        for a in (work.get("authorships") or [])
        if a.get("author") and a["author"].get("display_name")
    ]
    return {
        "external_id": (work.get("id") or doi or "").strip(),
        "source": "openalex",
        "title": (work.get("title") or "").strip(),
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "authors_json": authors,
        "year": work.get("publication_year"),
        "publication_date": work.get("publication_date"),
        "cited_by_count": work.get("cited_by_count"),
        "doi": doi or None,
        "url": url or None,
        "venue_name": (venue.get("display_name") or "").strip() or None,
        "source_query": work.get("_source_query") or None,
    }


def fill_explore_pool(db, sub, target=200) -> dict:
    current = db.execute(
        select(func.count(models.ExplorePool.id)).where(
            models.ExplorePool.subscription_id == sub.id,
            models.ExplorePool.action.is_(None),
        )
    ).scalar_one()
    displayable = db.execute(
        select(func.count(models.ExplorePool.id)).where(
            models.ExplorePool.subscription_id == sub.id,
            models.ExplorePool.action.is_(None),
            models.ExplorePool.scored_at.isnot(None),
        )
    ).scalar_one()
    needed = max(0, int(target) - int(displayable or 0))
    if needed <= 0:
        return {"added": 0, "existing": current}

    queries = list(sub.generated_queries or [])
    if not queries:
        return {"added": 0, "existing": current}

    existing_ids: set[str] = set()
    existing_titles: set[str] = set()
    rows = db.execute(
        select(models.ExplorePool.raw_metadata_json).where(
            models.ExplorePool.subscription_id == sub.id,
        )
    ).all()
    for (meta,) in rows:
        meta = meta or {}
        eid = (meta.get("external_id") or meta.get("doi") or "").strip()
        if eid:
            existing_ids.add(eid)
        title = _norm_title(meta.get("title") or "")
        if title:
            existing_titles.add(title)

    existing_dois = {
        doi.strip().lower()
        for (doi,) in db.execute(select(models.Paper.doi).where(models.Paper.doi.isnot(None))).all()
        if doi
    }

    per_query = min(200, max(10, math.ceil(target * 1.5 / len(queries))))
    since_iso = (_utcnow() - timedelta(days=1825)).date().isoformat()
    mailto = _openalex_mailto()

    def _fetch_page(c, q, page=1):
        params = {
            "filter": f"title_and_abstract.search:{q},from_publication_date:{since_iso},type:article,primary_location.source.type:journal",
            "per_page": per_query,
            "page": page,
            "select": "id,doi,title,abstract_inverted_index,authorships,publication_year,publication_date,cited_by_count,primary_location",
            "sort": "publication_date:desc",
        }
        if mailto:
            params["mailto"] = mailto
        try:
            r = c.get("https://api.openalex.org/works", params=params)
            r.raise_for_status()
            results = r.json().get("results", [])
            for work in results:
                work["_source_query"] = q
            return results
        except Exception:
            return []

    works = []
    page1_counts = {}
    with httpx.Client(timeout=20.0) as c:
        with ThreadPoolExecutor(max_workers=min(len(queries), 4)) as ex:
            futures = {q: ex.submit(_fetch_page, c, q, 1) for q in queries}
            for q, fut in futures.items():
                batch = fut.result()
                page1_counts[q] = len(batch)
                works.extend(batch)

    if len(works) < needed:
        full_queries = [q for q in queries if page1_counts.get(q, 0) >= per_query]
        if full_queries:
            with httpx.Client(timeout=20.0) as c:
                with ThreadPoolExecutor(max_workers=min(len(full_queries), 4)) as ex:
                    for batch in ex.map(lambda q: _fetch_page(c, q, 2), full_queries):
                        works.extend(batch)

    added = 0
    for work in works:
        if added >= needed:
            break
        if not work.get("abstract_inverted_index"):
            continue
        meta = _openalex_work_to_meta(work)
        eid = (meta.get("external_id") or meta.get("doi") or "").strip()
        doi = (meta.get("doi") or "").strip().lower()
        title = _norm_title(meta.get("title") or "")
        if not eid or eid in existing_ids or (doi and doi in existing_dois) or (title and title in existing_titles):
            continue
        db.add(models.ExplorePool(subscription_id=sub.id, raw_metadata_json=meta, external_id=meta.get("external_id") or meta.get("id") or eid or None))
        existing_ids.add(eid)
        if title:
            existing_titles.add(title)
        added += 1
    db.commit()
    return {"added": added, "existing": current}


def enrich_pending(db, sub_id, max_items: int = 120) -> dict:
    stmt = (
        select(models.ExplorePool, models.Subscription.description)
        .join(models.Subscription, models.ExplorePool.subscription_id == models.Subscription.id)
        .where(models.ExplorePool.subscription_id == sub_id)
        .where(models.ExplorePool.action.is_(None))
        .where(models.ExplorePool.scored_at.is_(None))
        .order_by(models.ExplorePool.found_at.desc())
        .limit(max_items)
    )
    rows = list(db.execute(stmt).all())
    if not rows:
        return {"llm_queued": 0, "errors": 0}

    items = [item for item, _ in rows]
    description = (rows[0][1] or "")[:500]

    # _scoring_subs guards against concurrent LLM threads for the same subscription
    needs_scoring = [item.id for item in items if item.scored_at is None]
    llm_queued = 0
    with _scoring_lock:
        should_score = bool(needs_scoring) and sub_id not in _scoring_subs
        if should_score:
            _scoring_subs.add(sub_id)
    if should_score:
        llm_queued = len(needs_scoring)
        from database import SessionLocal as _SL
        def _bg_llm(sid, desc, ids):
            from services.tag_pool import build_candidate_pool

            pool = None

            def _run_batch(batch_ids):
                s = _SL()
                try:
                    batch = list(s.execute(
                        select(models.ExplorePool).where(
                            models.ExplorePool.id.in_(batch_ids),
                            models.ExplorePool.scored_at.is_(None),
                        )
                    ).scalars().all())
                    if not batch:
                        return
                    try:
                        _score_batch(s, desc, batch, pool=pool)
                        s.commit()
                    except Exception as exc:
                        _log.warning("_bg_llm _score_batch failed sub=%d: %s", sid, exc)
                        for it in batch:
                            it.score_attempts = (it.score_attempts or 0) + 1
                            if it.score_attempts >= 3:
                                it.scored_at = _utcnow()
                                it.llm_reason = "LLM 失败 3 次已放弃"
                        try:
                            s.commit()
                        except Exception:
                            s.rollback()
                            s2 = _SL()
                            try:
                                ids = [it.id for it in batch]
                                from sqlalchemy import update as _upd
                                s2.execute(
                                    _upd(models.ExplorePool)
                                    .where(models.ExplorePool.id.in_(ids))
                                    .values(scored_at=_utcnow(), llm_reason="LLM 评分异常")
                                )
                                s2.commit()
                            finally:
                                s2.close()
                except Exception as exc:
                    _log.error("_bg_llm batch failed sub=%d: %s", sid, exc)
                finally:
                    s.close()

            try:
                s_pool = _SL()
                try:
                    pool = build_candidate_pool(s_pool, sub_id=sid)
                finally:
                    s_pool.close()
                batches = [ids[i:i + 5] for i in range(0, len(ids), 5)]
                with ThreadPoolExecutor(max_workers=5) as ex:
                    list(ex.map(_run_batch, batches))
            except Exception as exc:
                _log.error("_bg_llm failed sub=%d: %s", sid, exc)
            finally:
                with _scoring_lock:
                    _scoring_subs.discard(sid)

        threading.Thread(target=_bg_llm, args=(sub_id, description, needs_scoring), daemon=True).start()

    return {"llm_queued": llm_queued, "errors": 0}


def get_explore_cards(db, sub_id, limit=10, exclude_ids: list[int] | None = None):
    sub = db.get(models.Subscription, sub_id)
    conditions = [
        models.ExplorePool.subscription_id == sub_id,
        models.ExplorePool.action.is_(None),
        models.ExplorePool.scored_at.isnot(None),
    ]
    if exclude_ids:
        conditions.append(models.ExplorePool.id.notin_(exclude_ids))
    items = list(db.execute(
        select(models.ExplorePool).where(*conditions)
    ).scalars().all())
    all_tags = {t for item in items if item.tags_json for t in item.tags_json}
    stats = batch_stats(db, all_tags)
    scored_items = [
        (score_card_with_stats(item.id, item.tags_json or [], stats), item)
        for item in items
        if item.tags_json
    ]
    scored_items.sort(key=lambda row: row[0], reverse=True)
    items = [item for _, item in scored_items[:int(limit)]]

    # Batch-fetch journals for all venue_names in one query (avoids N+1)
    venue_names = {(item.raw_metadata_json or {}).get("venue_name") or "" for item in items}
    venue_names.discard("")
    journal_cache: dict = {}
    if venue_names:
        journal_rows = db.execute(
            select(models.Journal).where(models.Journal.name.in_(list(venue_names)))
        ).scalars().all()
        journal_cache = {j.name: j for j in journal_rows}
    venue_cache_extra: dict = {}
    missing_journal_names = venue_names - set(journal_cache.keys())
    if missing_journal_names:
        cache_rows = db.execute(
            select(models.VenueEasyscholarCache)
            .where(models.VenueEasyscholarCache.name.in_(list(missing_journal_names)))
        ).scalars().all()
        venue_cache_extra = {row.name: row.easyscholar_json for row in cache_rows}

    displayable = db.execute(
        select(func.count(models.ExplorePool.id)).where(
            models.ExplorePool.subscription_id == sub_id,
            models.ExplorePool.action.is_(None),
            models.ExplorePool.scored_at.isnot(None),
        )
    ).scalar_one()
    with _fill_lock:
        should_fill = displayable < 100 and sub_id not in _filling_subs
        if should_fill:
            _filling_subs.add(sub_id)
    if should_fill:
        from database import SessionLocal as _SL
        def _bg_fill(sid):
            s = _SL()
            try:
                sub_ = s.get(models.Subscription, sid)
                if sub_:
                    # #17: last_filled_at < 60s 则跳过，防并发重复 fill
                    if sub_.last_filled_at is not None:
                        elapsed = (_utcnow() - sub_.last_filled_at).total_seconds()
                        if elapsed < 60:
                            return
                    fill_explore_pool(s, sub_)
                    enrich_pending(s, sid)
                    sub_ = s.get(models.Subscription, sid)
                    if sub_:
                        sub_.last_filled_at = _utcnow()
                        s.commit()
            finally:
                s.close()
                with _fill_lock:
                    _filling_subs.discard(sid)
        threading.Thread(target=_bg_fill, args=(sub_id,), daemon=True).start()

    uncached = venue_names - set(venue_cache_extra.keys()) - set(journal_cache.keys())
    if uncached:
        from database import SessionLocal as _SL
        from services.easyscholar_service import get_or_cache_by_name
        def _bg_prefetch(names):
            s = _SL()
            try:
                for name in names:
                    get_or_cache_by_name(s, name)
                    s.commit()
            finally:
                s.close()
        threading.Thread(target=_bg_prefetch, args=(list(uncached),), daemon=True).start()

    result = []
    for item in items:
        card = build_explore_card_data(
            item, sub,
            journal_cache=journal_cache, venue_cache=venue_cache_extra,
        )
        card["bandit_score"] = expected_score_with_stats(item.tags_json or [], stats)
        result.append({"id": item.id, "card": card, "action": item.action})
    return result


def build_explore_card_data(item, sub, db_session=None, journal_cache: dict | None = None,
                            venue_cache: dict | None = None) -> dict:
    from services.easyscholar_service import extract_badges

    meta = item.raw_metadata_json or {}
    venue_name = meta.get("venue_name") or ""
    rank_badges: list[dict] = []
    if venue_name:
        try:
            if journal_cache is not None:
                journal = journal_cache.get(venue_name)
            elif db_session is not None:
                journal = db_session.execute(
                    select(models.Journal).where(models.Journal.name == venue_name)
                ).scalar_one_or_none()
            else:
                journal = None
            if journal and journal.easyscholar_json:
                rank_badges = extract_badges(journal.easyscholar_json)
            elif venue_cache is not None:
                rank_badges = extract_badges(venue_cache.get(venue_name))
        except Exception:
            pass
    _u = (meta.get("url") or "")
    url = _u if _u.lower().startswith(("http://", "https://")) else ""
    return {
        "card_index": None,
        "pool_id": item.id,
        "title": meta.get("title") or "",
        "url": url,
        "title_zh": item.title_zh or "",
        "display_date": meta.get("publication_date") or str(meta.get("year") or ""),
        "authors": ", ".join((meta.get("authors_json") or [])[:3]),
        "cited_by_count": meta.get("cited_by_count"),
        "venue_name": venue_name,
        "rank_badges": rank_badges,
        "tags": list(item.tags_json or [])[:4],
        "research_question": item.research_question or "",
        "methodology": item.methodology or "",
        "key_findings": list(item.key_findings_json or []),
        "llm_reason": item.llm_reason or "",
        "llm_pending": item.scored_at is None,
        "bandit_score": None,
    }


def record_explore_action(db, pool_id, action) -> dict:
    if action not in {"saved", "skipped", "passed"}:
        raise ValueError("invalid action")
    item = db.get(models.ExplorePool, pool_id)
    if item is None:
        raise ValueError("not found")
    if item.action is not None:
        if item.action == action:
            return {
                "pool_id": item.id,
                "action": action,
                "paper_id": item.paper_id,
                "query_refresh": None,
                "changed": False,
            }
        _log.warning("Overwriting explore action pool_id=%s from %s to %s", item.id, item.action, action)
    paper_id = None
    if action == "saved":
        paper_id = _import_explore_to_paper(db, item)
    item.action = action
    item.acted_at = _utcnow()
    db.commit()

    refreshed = None
    sid = item.subscription_id

    # query_refresh 保留 % 10 触发
    action_count = db.execute(
        select(func.count(models.ExplorePool.id)).where(
            models.ExplorePool.subscription_id == sid,
            models.ExplorePool.action.isnot(None),
        )
    ).scalar_one()
    if action_count and action_count % 10 == 0:
        from services.query_refresh_service import refresh_subscription_queries
        sub = db.get(models.Subscription, sid)
        if sub is not None:
            refreshed = refresh_subscription_queries(db, sub)
    return {"pool_id": item.id, "action": action, "paper_id": paper_id or item.paper_id, "query_refresh": refreshed, "changed": True}


def undo_explore_action(db, pool_id) -> dict:
    item = db.get(models.ExplorePool, pool_id)
    if item is None:
        raise ValueError("not found")
    # Delete Paper only if it was created specifically for this explore item (not a pre-existing paper matched by DOI)
    if item.paper_id:
        expected_suffix = hashlib.md5(f"explore:{item.id}".encode()).hexdigest()[:8]
        paper = db.get(models.Paper, item.paper_id)
        if paper and (paper.stem or "").endswith(expected_suffix):
            db.delete(paper)
    item.action = None
    item.acted_at = None
    item.paper_id = None
    db.commit()
    return {"pool_id": item.id, "action": None}


def _score_batch(db: Session, description: str, batch: list, pool: list[str] | None = None) -> None:
    """5 篇/批 LLM 内容生成（title_zh / tags / reason 等）。失败整批抛异常，由调用方决定重试。"""
    import json
    import re as _re
    from services.ai_service import _sanitize_tags, _sanitize_text, _sanitize_findings
    from services.llm_client import chat_completion as _call_llm
    from services.tag_pool import build_candidate_pool, record_proposed_tags
    from datetime import datetime as _dt, timezone as _tz

    payload = []
    for idx, r in enumerate(batch):
        meta = r.raw_metadata_json or {}
        payload.append({
            "idx": idx,
            "title": (meta.get("title") or "")[:200],
            "abstract": (meta.get("abstract") or "")[:600],
        })
    sub_id = batch[0].subscription_id if batch else None
    pool = pool if pool is not None else build_candidate_pool(db, sub_id=sub_id)
    pool_str = "、".join(pool)
    sys_prompt = f"""你是学术论文晨报助手。目标读者是忙碌的研究者，需要在10秒内判断一篇论文是否值得打开。

【候选 tag 池（请优先从中选 3-5 个）】
{pool_str}

对输入论文列表中的每篇，输出一个 JSON 数组项，包含：
- idx: 输入论文的索引（int）
- reason: <=80 字，说明为什么值得或不值得推送（不用学术语气）
- title_zh: 中文翻译标题
- tags: 中文标签数组，4-6 个，优先从【候选 tag 池】选 3-5 个；如池里无合适匹配，可新增 1-2 个 tag（2-4 字、规范），但绝不超过 6 个 tag
- proposed_tags: 你新增的 tag 数组（来自上面 tags 但不在候选池里的子集；如全部从池里选则空数组）
- research_question: ≤40 字，用普通中文说清楚【这篇文章在问什么】，不用学术语气，不写【本文】
- methodology: ≤50 字，说【它怎么做】，遇到专业术语立刻用括号解释
- key_findings: 中文数组，最多 3 条，每条≤35 字，说【能用它做什么/有什么用】，偏应用价值，不写【本文提出/本文研究】

只输出 JSON 数组，无 markdown 围栏、无说明。"""
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": (
            f"用户研究兴趣：\n{description}\n\n"
            f"论文列表：\n{json.dumps(payload, ensure_ascii=False)}"
        )},
    ]
    raw = _call_llm(messages, max_tokens=4096)
    match = _re.search(r"\[[\s\S]*\]", raw)
    if not match:
        raise ValueError("no JSON array")
    arr = json.loads(match.group())
    now = _dt.now(_tz.utc).replace(tzinfo=None)
    by_idx = {int(item["idx"]): item for item in arr if isinstance(item, dict) and "idx" in item}
    all_proposed = set()
    for info in by_idx.values():
        proposed_tags = _sanitize_tags(info.get("proposed_tags", []))
        info["proposed_tags"] = proposed_tags
        all_proposed.update(proposed_tags)
    existing_set = set()
    if all_proposed:
        existing_set = {
            row[0]
            for row in db.query(models.TagDict.tag)
            .filter(models.TagDict.tag.in_(all_proposed))
            .all()
        }
    for idx, r in enumerate(batch):
        info = by_idx.get(idx, {})
        reason = info.get("reason")
        if isinstance(reason, str):
            r.llm_reason = reason[:500]
        r.title_zh = _sanitize_text(info.get("title_zh")) or None
        tags = _sanitize_tags(info.get("tags"))
        r.tags_json = tags if tags else None
        proposed_tags = info.get("proposed_tags", [])
        record_proposed_tags(db, r.id, proposed_tags, existing_set=existing_set)
        r.research_question = _sanitize_text(info.get("research_question")) or None
        r.methodology = _sanitize_text(info.get("methodology")) or None
        findings = _sanitize_findings(info.get("key_findings"))
        r.key_findings_json = findings if findings else None
        r.scored_at = now


def _import_explore_to_paper(db, item) -> Optional[int]:
    meta = item.raw_metadata_json or {}
    title = (meta.get("title") or "").strip()
    doi = (meta.get("doi") or "").strip() or None
    if item.paper_id:
        return item.paper_id
    if doi:
        existing = db.execute(select(models.Paper).where(models.Paper.doi == doi)).scalar_one_or_none()
        if existing:
            item.paper_id = existing.id
            return existing.id

    base = re.sub(r"[^\w]+", "_", title.lower())[:40].strip("_") or "explore"
    suffix = hashlib.md5(f"explore:{item.id}".encode()).hexdigest()[:8]
    stem = f"{base}_{suffix}"
    paper = models.Paper(
        stem=stem,
        title=title or None,
        abstract=meta.get("abstract") or None,
        doi=doi,
        year=meta.get("year"),
        authors_json=meta.get("authors_json") or [],
        tags=item.tags_json or [],
        ai_summary={
            k: v for k, v in {
                "title_zh": item.title_zh,
                "research_question": item.research_question,
                "methodology": item.methodology,
                "key_findings": item.key_findings_json,
            }.items() if v
        } or None,
        ai_analyzed_at=item.scored_at,
        is_core=False,
        status="analyzed",
        source="subscription",
        added_at=_utcnow(),
    )
    db.add(paper)
    db.flush()
    item.paper_id = paper.id
    return paper.id
