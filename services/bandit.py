from __future__ import annotations
import random
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam
from database.models import TagDict


def score_card(db: Session, tags: list[str]) -> float:
    if not tags:
        return 0.0
    rows = db.query(TagDict.tag, TagDict.alpha, TagDict.beta).filter(TagDict.tag.in_(tags)).all()
    stats = {r[0]: (r[1], r[2]) for r in rows}
    samples = []
    for t in tags:
        a, b = stats.get(t, (0.5, 0.5))
        samples.append(random.betavariate(max(a, 1e-6), max(b, 1e-6)))
    return sum(samples) / len(samples)


def apply_action(db: Session, tags: list[str], action: str) -> None:
    if not tags or action not in ('saved', 'skipped', 'passed'):
        return
    field = 'alpha' if action == 'saved' else 'beta'
    stmt = text(f'UPDATE tag_dict SET {field} = {field} + 1 WHERE tag IN :tags').bindparams(
        bindparam('tags', expanding=True)
    )
    db.execute(stmt, {'tags': tags})
