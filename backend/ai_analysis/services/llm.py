"""OpenAI-compatible LLM client.

Ported from services/llm_client.py — identical algorithm, no dependency changes.
"""
from __future__ import annotations

import os
from typing import Iterator

import httpx

_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=10.0)


def _chat_config() -> tuple[str, str, str]:
    try:
        return (
            os.environ["CHAT_API_BASE"].rstrip("/"),
            os.environ["CHAT_API_KEY"],
            os.environ["CHAT_MODEL"],
        )
    except KeyError as e:
        raise RuntimeError(f"Missing chat LLM env var: {e.args[0]}") from None


def chat_completion(
    messages: list[dict],
    max_tokens: int = 8192,
    temperature: float = 0.1,
) -> str:
    base, key, model = _chat_config()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post(
            f"{base}/chat/completions",
            headers=headers,
            json={
                "model": model,
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
    """SSE streaming; yields content delta strings."""
    import json as _json

    base, key, model = _chat_config()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=_TIMEOUT) as c:
        with c.stream(
            "POST",
            f"{base}/chat/completions",
            headers=headers,
            json={
                "model": model,
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
