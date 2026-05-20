"""Bandit scoring — ported from services/bandit.py.

Uses per-tenant TagDict instead of the old global tag_dict table.
All public functions accept an optional `tenant_id` to scope DB queries.
"""
from __future__ import annotations

import hashlib
import random
from typing import Optional


def _stable_seed(key) -> int:
    return int(hashlib.md5(str(key).encode("utf-8")).hexdigest()[:16], 16)


def _fetch_stats(tenant_id: int, tags: list[str]) -> dict[str, tuple[float, float]]:
    from explore.models import TagDict
    rows = TagDict.objects.filter(tenant_id=tenant_id, tag__in=tags).values_list("tag", "alpha", "beta")
    return {r[0]: (r[1], r[2]) for r in rows}


def batch_stats(tenant_id: int, all_tags: set[str]) -> dict[str, tuple[float, float]]:
    if not all_tags:
        return {}
    return _fetch_stats(tenant_id, list(all_tags))


def score_card_with_stats(pool_id: int, tags: list, stats: dict) -> float:
    if not tags:
        return 0.0
    seed_key = (pool_id, tuple(sorted((t, stats.get(t, (0.5, 0.5))) for t in tags)))
    rng = random.Random(_stable_seed(seed_key))
    samples = [rng.betavariate(max(a, 1e-6), max(b, 1e-6)) for t in tags for a, b in [stats.get(t, (0.5, 0.5))]]
    return sum(samples) / len(samples)


def expected_score_with_stats(tags: list, stats: dict) -> Optional[float]:
    if not tags:
        return None
    vals = [a / (a + b) for t in tags for a, b in [stats.get(t, (0.5, 0.5))]]
    return sum(vals) / len(vals)


def apply_action(tenant_id: int, tags: list[str], action: str) -> None:
    """Increment alpha (saved) or beta (skipped/passed) for each tag."""
    if not tags or action not in ("saved", "skipped", "passed"):
        return
    from explore.models import TagDict
    field = "alpha" if action == "saved" else "beta"
    from django.db.models import F
    TagDict.objects.filter(tenant_id=tenant_id, tag__in=tags).update(**{field: F(field) + 1})
