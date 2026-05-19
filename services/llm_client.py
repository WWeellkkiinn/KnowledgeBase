"""Yinli OpenAI-compatible API client。

对外暴露：
    chat_completion(messages, max_tokens, temperature) -> str
    chat_completion_stream(messages, max_tokens) -> Iterator[str]
    embed_texts_batch(texts) -> list[Optional[bytes]]
    embed_text(text) -> Optional[bytes]

配置全部从环境变量读取，缺失则 import 时 KeyError。
失败直接抛 httpx.HTTPStatusError，不吞错。
"""
from __future__ import annotations

import os
import struct
from typing import Iterator, Optional

import httpx

_BASE = os.environ["YINLI_API_BASE"].rstrip("/")
_KEY = os.environ["YINLI_API_KEY"]
_CHAT_MODEL = os.environ["YINLI_CHAT_MODEL"]
_EMBED_MODEL = os.environ["YINLI_EMBED_MODEL"]

_HEADERS = {"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"}

_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(
            timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=10.0),
        )
    return _client


def chat_completion(
    messages: list[dict],
    max_tokens: int = 8192,
    temperature: float = 0.1,
) -> str:
    resp = _get_client().post(
        f"{_BASE}/chat/completions",
        headers=_HEADERS,
        json={
            "model": _CHAT_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        },
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def chat_completion_stream(
    messages: list[dict],
    max_tokens: int = 8192,
) -> Iterator[str]:
    """SSE 流式调用，yield content delta 字符串块。"""
    import json as _json

    with _get_client().stream(
        "POST",
        f"{_BASE}/chat/completions",
        headers=_HEADERS,
        json={
            "model": _CHAT_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.1,
            "stream": True,
        },
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = _json.loads(payload)
            except _json.JSONDecodeError:
                continue
            delta = obj.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content")
            if content:
                yield content


def embed_texts_batch(texts: list[str]) -> list[Optional[bytes]]:
    indexed = [(i, (t or "").strip()) for i, t in enumerate(texts)]
    non_empty = [(i, t) for i, t in indexed if t]
    result: list[Optional[bytes]] = [None] * len(texts)
    if not non_empty:
        return result
    resp = _get_client().post(
        f"{_BASE}/embeddings",
        headers=_HEADERS,
        json={"model": _EMBED_MODEL, "input": [t for _, t in non_empty]},
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or []
    for (orig_idx, _), item in zip(non_empty, data):
        emb = item.get("embedding") or []
        if emb:
            result[orig_idx] = struct.pack(f"{len(emb)}f", *[float(x) for x in emb])
    return result


def embed_text(text: str) -> Optional[bytes]:
    results = embed_texts_batch([text])
    return results[0]
