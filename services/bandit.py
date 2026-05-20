from __future__ import annotations
import hashlib
import random
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam
from database.models import TagDict


def _stable_seed(key) -> int:
    return int(hashlib.md5(str(key).encode('utf-8')).hexdigest()[:16], 16)


def _fetch_stats(db, tags):
    rows = db.query(TagDict.tag, TagDict.alpha, TagDict.beta).filter(TagDict.tag.in_(tags)).all()
    return {r[0]: (r[1], r[2]) for r in rows}


def score_card(db: Session, pool_id: int, tags: list[str]) -> float:
    if not tags:
        return 0.0
    stats = _fetch_stats(db, tags)
    seed_key = (pool_id, tuple(sorted((t, stats.get(t, (0.5, 0.5))) for t in tags)))
    rng = random.Random(_stable_seed(seed_key))
    samples = []
    for t in tags:
        a, b = stats.get(t, (0.5, 0.5))
        samples.append(rng.betavariate(max(a, 1e-6), max(b, 1e-6)))
    return sum(samples) / len(samples)


def expected_score(db: Session, tags: list[str]) -> float | None:
    """mean of α/(α+β) over tags. Stable across calls (no sampling)."""
    if not tags:
        return None
    stats = _fetch_stats(db, tags)
    vals = []
    for t in tags:
        a, b = stats.get(t, (0.5, 0.5))
        vals.append(a / (a + b))
    return sum(vals) / len(vals)


def batch_stats(db, all_tags):
    if not all_tags:
        return {}
    return _fetch_stats(db, list(set(all_tags)))


def score_card_with_stats(pool_id: int, tags: list, stats: dict) -> float:
    if not tags:
        return 0.0
    seed_key = (pool_id, tuple(sorted((t, stats.get(t, (0.5, 0.5))) for t in tags)))
    rng = random.Random(_stable_seed(seed_key))
    samples = [rng.betavariate(max(a, 1e-6), max(b, 1e-6)) for t in tags for a, b in [stats.get(t, (0.5, 0.5))]]
    return sum(samples) / len(samples)


def expected_score_with_stats(tags: list, stats: dict):
    if not tags:
        return None
    vals = [a / (a + b) for t in tags for a, b in [stats.get(t, (0.5, 0.5))]]
    return sum(vals) / len(vals)


def apply_action(db: Session, tags: list[str], action: str) -> None:
    if not tags or action not in ('saved', 'skipped', 'passed'):
        return
    field = 'alpha' if action == 'saved' else 'beta'
    stmt = text(f'UPDATE tag_dict SET {field} = {field} + 1 WHERE tag IN :tags').bindparams(
        bindparam('tags', expanding=True)
    )
    db.execute(stmt, {'tags': tags})
