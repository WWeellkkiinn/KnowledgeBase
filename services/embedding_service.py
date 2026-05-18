from __future__ import annotations

import math
import os
import struct
from typing import Optional

import httpx

_EMBED_MODEL = os.getenv("KB_EMBED_MODEL", "nomic-embed-text")
_OLLAMA_URL = os.getenv("KB_OLLAMA_URL", "http://localhost:11434").rstrip("/")


def embed_text(text: str) -> Optional[bytes]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        r = httpx.post(
            f"{_OLLAMA_URL}/api/embeddings",
            json={"model": _EMBED_MODEL, "prompt": text},
            timeout=60.0,
        )
        r.raise_for_status()
        embedding = r.json().get("embedding") or []
        if not embedding:
            return None
        return struct.pack(f"{len(embedding)}f", *[float(x) for x in embedding])
    except Exception:
        return None


def bytes_to_vec(b: bytes) -> list[float]:
    if not b:
        return []
    return list(struct.unpack(f"{len(b) // 4}f", b))


def cosine_similarity(a: bytes, b: bytes) -> float:
    va = bytes_to_vec(a)
    vb = bytes_to_vec(b)
    if not va or not vb or len(va) != len(vb):
        return 0.0
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def score_candidate(candidate_emb: bytes, labeled: list[tuple[bytes, float]]) -> float:
    usable = [(emb, weight) for emb, weight in labeled if emb]
    if not candidate_emb or not usable:
        return 0.0
    total_weight = sum(abs(weight) for _, weight in usable)
    if not total_weight:
        return 0.0
    return sum(cosine_similarity(candidate_emb, emb) * weight for emb, weight in usable) / total_weight


def embed_texts_batch(texts):
    indexed = [(i, (t or '').strip()) for i, t in enumerate(texts)]
    non_empty = [(i, t) for i, t in indexed if t]
    result = [None] * len(texts)
    if not non_empty:
        return result
    try:
        r = httpx.post(
            f"{_OLLAMA_URL}/api/embed",
            json={"model": _EMBED_MODEL, "input": [t for _, t in non_empty]},
            timeout=120.0,
        )
        r.raise_for_status()
        embeddings = r.json().get("embeddings") or []
        for (orig_idx, _), emb in zip(non_empty, embeddings):
            if emb:
                result[orig_idx] = struct.pack(f"{len(emb)}f", *[float(x) for x in emb])
    except Exception:
        pass
    return result


def score_candidates_matrix(candidate_embs, labeled):
    import numpy as np
    n = len(candidate_embs)
    if not labeled or not n:
        return [0.0] * n
    weights = np.array([w for _, w in labeled], dtype=np.float32)
    lmat = np.array([bytes_to_vec(e) for e, _ in labeled], dtype=np.float32)
    total_w = float(np.sum(np.abs(weights)))
    if total_w == 0:
        return [0.0] * n
    valid = [(i, e) for i, e in enumerate(candidate_embs) if e]
    if not valid:
        return [0.0] * n
    cmat = np.array([bytes_to_vec(e) for _, e in valid], dtype=np.float32)
    def _norm(m):
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        return np.where(norms > 0, m / norms, 0.0)
    sim = _norm(cmat) @ _norm(lmat).T
    raw = (sim @ weights) / total_w
    scores = [0.0] * n
    for (orig_idx, _), s in zip(valid, raw.tolist()):
        scores[orig_idx] = float(s)
    return scores
