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
