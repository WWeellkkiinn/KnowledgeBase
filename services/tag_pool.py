from __future__ import annotations

import json
import random

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.models import ExplorePool, TagDict, TagProposal

POOL_TOP_N = 70
SLOT_MID = 15
SLOT_RECENT = 8
SLOT_BEHAVIOR = 7


def build_candidate_pool(db: Session) -> list[str]:
    rows = db.execute(text("""
        SELECT je.value AS tag, COUNT(*) AS cnt
          FROM explore_pool ep, json_each(ep.tags_json) je
         WHERE ep.scored_at IS NOT NULL AND ep.tags_json IS NOT NULL
         GROUP BY je.value
         ORDER BY cnt DESC
    """)).fetchall()
    ranked = [r[0] for r in rows]

    top = ranked[:POOL_TOP_N]
    top_set = set(top)

    mid_candidates = ranked[POOL_TOP_N:200]
    mid = random.sample(mid_candidates, min(SLOT_MID, len(mid_candidates)))

    recent_rows = db.query(TagDict.tag).filter(TagDict.source == "promoted") \
        .order_by(TagDict.created_at.desc()).limit(SLOT_RECENT * 3).all()
    recent = [r[0] for r in recent_rows if r[0] not in top_set][:SLOT_RECENT]

    saved_rows = db.execute(text("""
        SELECT DISTINCT je.value AS tag
          FROM explore_pool ep, json_each(ep.tags_json) je
         WHERE ep.action = 'saved' AND ep.tags_json IS NOT NULL
         ORDER BY ep.acted_at DESC
         LIMIT 50
    """)).fetchall()
    behavior = [r[0] for r in saved_rows if r[0] not in top_set][:SLOT_BEHAVIOR]

    seen, result = set(), []
    for t in top + mid + recent + behavior:
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result


def record_proposed_tags(db: Session, explore_pool_id: int, proposed: list[str]) -> None:
    if not proposed:
        return
    existing = {r[0] for r in db.query(TagDict.tag).filter(TagDict.tag.in_(proposed)).all()}
    for t in proposed:
        if t and t not in existing:
            db.add(TagProposal(tag=t, explore_pool_id=explore_pool_id))


def promote_proposed_tags(db: Session, explore_pool_id: int) -> list[str]:
    """当论文被 saved 时，把它对应 tag_proposals 升入 tag_dict，返回晋升的 tag 列表。"""
    proposals = db.query(TagProposal).filter(TagProposal.explore_pool_id == explore_pool_id).all()
    if not proposals:
        return []
    promoted = []
    existing = {r[0] for r in db.query(TagDict.tag).all()}
    for p in proposals:
        if p.tag not in existing:
            db.add(TagDict(tag=p.tag, source="promoted"))
            existing.add(p.tag)
            promoted.append(p.tag)
        db.delete(p)
    return promoted
