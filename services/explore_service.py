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

from database import models
from services.card_renderer import _env
from services.embedding_service import embed_text, score_candidate
from services.reference_fetcher import _openalex_mailto, _reconstruct_abstract

_log = logging.getLogger(__name__)

_NORM_TITLE_RE = re.compile(r"[^\w一-鿿]+", flags=re.UNICODE)
_fill_lock = threading.Lock()
_filling_subs: set[int] = set()   # 防止同一 sub_id 并发填充
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
    needed = max(0, int(target) - int(current or 0))
    if needed <= 0:
        return {"added": 0, "existing": current}

    queries = list(sub.generated_queries or [])
    legacy_query = (sub.target_json or {}).get("query") if hasattr(sub, "target_json") else None
    if not queries and legacy_query:
        queries = [legacy_query]
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
        db.add(models.ExplorePool(subscription_id=sub.id, raw_metadata_json=meta))
        existing_ids.add(eid)
        if title:
            existing_titles.add(title)
        added += 1
    db.commit()
    return {"added": added, "existing": current}


def score_and_embed_pending(db, sub_id, max_items: int = 120) -> dict:
    stmt = (
        select(models.ExplorePool, models.Subscription.description)
        .join(models.Subscription, models.ExplorePool.subscription_id == models.Subscription.id)
        .where(models.ExplorePool.subscription_id == sub_id)
        .where(models.ExplorePool.action.is_(None))
        .where((models.ExplorePool.scored_at.is_(None)) | (models.ExplorePool.embedding.is_(None)))
        .order_by(models.ExplorePool.found_at.desc())
        .limit(max_items)
    )
    rows = list(db.execute(stmt).all())
    if not rows:
        return {"embedded": 0, "llm_queued": 0, "errors": 0}

    items = [item for item, _ in rows]
    # Truncate description to prevent prompt injection via user-controlled input
    description = (rows[0][1] or "")[:500]
    embedded = 0

    # Step 1: embed first so cards can appear quickly
    no_emb = [item for item in items if item.embedding is None]
    if no_emb:
        from services.embedding_service import embed_texts_batch
        texts = [
            f"{(item.raw_metadata_json or {}).get('title') or ''}\n\n{(item.raw_metadata_json or {}).get('abstract') or ''}"[:8000]
            for item in no_emb
        ]
        embs = embed_texts_batch(texts)
        for item, emb in zip(no_emb, embs):
            if emb is not None:
                item.embedding = emb
                embedded += 1
    db.commit()

    # Step 2: compute pre_scores immediately so GET /cards can return results
    _compute_pre_scores(db, sub_id)

    # Step 3: LLM scoring in background (slow — don't block the caller)
    # _scoring_subs guards against concurrent LLM threads for the same subscription
    needs_scoring = [item.id for item in items if item.scored_at is None]
    llm_queued = 0
    if needs_scoring and sub_id not in _scoring_subs:
        _scoring_subs.add(sub_id)
        llm_queued = len(needs_scoring)
        from database import SessionLocal as _SL
        def _bg_llm(sid, desc, ids):
            from services.subscription_service import _score_batch

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
                        _score_batch(s, desc, batch)
                    except Exception as exc:
                        _log.warning("_bg_llm _score_batch failed sub=%d: %s", sid, exc)
                        for it in batch:
                            it.score_attempts = (it.score_attempts or 0) + 1
                            if it.score_attempts >= 3:
                                it.scored_at = _utcnow()
                                it.llm_reason = "LLM 失败 3 次已放弃"
                    s.commit()
                except Exception as exc:
                    _log.error("_bg_llm batch failed sub=%d: %s", sid, exc)
                finally:
                    s.close()

            try:
                batches = [ids[i:i + 5] for i in range(0, len(ids), 5)]
                with ThreadPoolExecutor(max_workers=5) as ex:
                    list(ex.map(_run_batch, batches))
            except Exception as exc:
                _log.error("_bg_llm failed sub=%d: %s", sid, exc)
            finally:
                _scoring_subs.discard(sid)

        threading.Thread(target=_bg_llm, args=(sub_id, description, needs_scoring), daemon=True).start()

    return {"embedded": embedded, "llm_queued": llm_queued, "errors": 0}


_query_emb_cache: dict[str, list] = {}  # "{sub_id}:{md5(queries)}" -> list[Optional[bytes]]


def _queries_key(sub_id: int, queries: list[str]) -> str:
    h = hashlib.md5("\n".join(queries).encode()).hexdigest()
    return f"{sub_id}:{h}"


def invalidate_query_cache(sub_id: int) -> None:
    prefix = f"{sub_id}:"
    keys_to_delete = [k for k in list(_query_emb_cache.keys()) if k.startswith(prefix)]
    for k in keys_to_delete:
        _query_emb_cache.pop(k, None)


def _compute_pre_scores(db, sub_id: int) -> None:
    from services.embedding_service import embed_texts_batch, score_candidates_matrix
    sub = db.get(models.Subscription, sub_id)

    # 查询锚点：权重动态化，防止用户行为完全主导方向
    query_labeled: list[tuple[bytes, float]] = []
    queries = list(sub.generated_queries or []) if sub else []
    if queries:
        key = _queries_key(sub_id, queries)
        if key not in _query_emb_cache:
            _query_emb_cache[key] = embed_texts_batch(queries)
        q_embs = _query_emb_cache[key]
        query_labeled = [(e, 1.0) for e in q_embs if e]

    # 用户行为（带时间衰减）
    user_labeled = _get_labeled_embeddings(db, sub_id)

    # 冷启动：两者都没有时用描述 embedding
    if not query_labeled and not user_labeled:
        if sub and sub.description:
            from services.embedding_service import embed_text
            desc_emb = embed_text(sub.description)
            if desc_emb:
                user_labeled = [(desc_emb, 1.0)]
        if not user_labeled:
            return

    items = list(db.execute(
        select(models.ExplorePool).where(
            models.ExplorePool.subscription_id == sub_id,
            models.ExplorePool.action.is_(None),
            models.ExplorePool.embedding.isnot(None),
        ).order_by(models.ExplorePool.found_at.desc()).limit(2000)
    ).scalars().all())
    if not items:
        return

    cand_embs = [item.embedding for item in items]

    if query_labeled and user_labeled:
        # 动态锚点比例：按 saved 数量 0/30/60+ 三档：1.0/0.4/0.2
        positive_count = db.execute(
            select(func.count(models.ExplorePool.id)).where(
                models.ExplorePool.subscription_id == sub_id,
                models.ExplorePool.action == "saved",
            )
        ).scalar_one()
        if positive_count == 0:
            anchor_w = 1.0
        elif positive_count < 30:
            anchor_w = 1.0 - 0.6 * (positive_count / 30)
        elif positive_count < 60:
            anchor_w = 0.4 - 0.2 * ((positive_count - 30) / 30)
        else:
            anchor_w = 0.2
        user_w = 1.0 - anchor_w
        q_scores = score_candidates_matrix(cand_embs, query_labeled)
        u_scores = score_candidates_matrix(cand_embs, user_labeled)
        scores = [anchor_w * q + user_w * u for q, u in zip(q_scores, u_scores)]
    elif query_labeled:
        scores = score_candidates_matrix(cand_embs, query_labeled)
    else:
        scores = score_candidates_matrix(cand_embs, user_labeled)

    for item, score in zip(items, scores):
        item.pre_score = score
    db.commit()


def _get_labeled_embeddings(db, sub_id) -> list[tuple[bytes, float]]:
    rows = db.execute(
        select(models.ExplorePool.embedding, models.ExplorePool.action, models.ExplorePool.acted_at).where(
            models.ExplorePool.subscription_id == sub_id,
            models.ExplorePool.action.isnot(None),
            models.ExplorePool.embedding.isnot(None),
        )
    ).all()
    weights = {"saved": 1.0, "skipped": -1.0, "passed": 0.0}
    now = _utcnow()
    result = []
    for emb, action, acted_at in rows:
        if action not in weights:
            continue
        base = weights[action]
        if base == 0.0:
            continue
        if acted_at:
            days = max(0.0, (now - acted_at).total_seconds() / 86400)
            # 半衰期 30 天：30天前的行为权重衰减到原来的一半
            decay = 0.5 ** (days / 30)
            base *= decay
        result.append((emb, base))
    return result


def get_explore_cards(db, sub_id, limit=10, exclude_ids: list[int] | None = None):
    sub = db.get(models.Subscription, sub_id)
    conditions = [
        models.ExplorePool.subscription_id == sub_id,
        models.ExplorePool.action.is_(None),
        models.ExplorePool.scored_at.isnot(None),
        models.ExplorePool.pre_score >= 0,
    ]
    if exclude_ids:
        conditions.append(models.ExplorePool.id.notin_(exclude_ids))
    items = list(db.execute(
        select(models.ExplorePool).where(*conditions).order_by(
            ((models.ExplorePool.pre_score * 0.6) + (func.coalesce(models.ExplorePool.llm_score, 0.0) * 0.4)).desc(),
            models.ExplorePool.found_at.desc(),
        ).limit(int(limit))
    ).scalars().all())

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

    # #5: 补池阈值用「可展示数」（scored_at NOT NULL + pre_score >= 0）
    displayable = db.execute(
        select(func.count(models.ExplorePool.id)).where(
            models.ExplorePool.subscription_id == sub_id,
            models.ExplorePool.action.is_(None),
            models.ExplorePool.scored_at.isnot(None),
            models.ExplorePool.pre_score >= 0,
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
                    score_and_embed_pending(s, sid)
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

    return [
        {
            "id": item.id,
            "card_html": render_explore_card(
                item, sub, embedding_score=item.pre_score,
                journal_cache=journal_cache, venue_cache=venue_cache_extra,
            ),
            "score": round(item.pre_score or 0.0, 4),
            "action": item.action,
        }
        for item in items
    ]


def render_explore_card(item, sub, embedding_score: float | None = None,
                        db_session=None, journal_cache: dict | None = None,
                        venue_cache: dict | None = None) -> str:
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
    tpl = _env.get_template("explore_card.html.j2")
    return tpl.render(
        card_index=None,
        pool_id=item.id,
        title=meta.get("title") or "",
        url=meta.get("url") or "",
        title_zh=item.title_zh or "",
        llm_score=item.llm_score,
        embedding_score=embedding_score,
        display_date=meta.get("publication_date") or str(meta.get("year") or ""),
        authors=", ".join((meta.get("authors_json") or [])[:3]),
        cited_by_count=meta.get("cited_by_count"),
        venue_name=venue_name,
        rank_badges=rank_badges,
        tags=list(item.tags_json or [])[:4],
        research_question=item.research_question or "",
        methodology=item.methodology or "",
        key_findings=list(item.key_findings_json or []),
        llm_reason=item.llm_reason or "",
        llm_pending=item.scored_at is None,
    )


def record_explore_action(db, pool_id, action) -> dict:
    if action not in {"saved", "skipped", "passed"}:
        raise ValueError("invalid action")
    item = db.get(models.ExplorePool, pool_id)
    if item is None:
        raise ValueError("not found")
    paper_id = None
    if action == "saved":
        paper_id = _import_explore_to_paper(db, item)
    item.action = action
    item.acted_at = _utcnow()
    db.commit()

    refreshed = None
    sid = item.subscription_id

    # #2: 每次打分都后台重算 pre_score
    from database import SessionLocal as _SL
    def _bg_rescore(sub_id_):
        s = _SL()
        try:
            _compute_pre_scores(s, sub_id_)
        finally:
            s.close()
    threading.Thread(target=_bg_rescore, args=(sid,), daemon=True).start()

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
    return {"pool_id": item.id, "action": action, "paper_id": paper_id or item.paper_id, "query_refresh": refreshed}


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
