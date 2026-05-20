"""Progress event bus over Redis pub/sub, surfaced to the browser via SSE.

publish(task_id, event)
    Celery tasks call this to emit a JSON event. The event is fan-out-published
    on Redis channel ``progress:<task_id>``.

stream(task_id) -> Iterator[bytes]
    Subscribes to the same channel and yields SSE-formatted bytes
    (``data: {json}\\n\\n``). Used by the streaming Django view.

Why Redis pub/sub instead of a per-process queue: Celery workers and the
Django gunicorn process are separate containers; the publish has to cross a
process boundary. Redis is already in the stack.

Tenant scoping: callers (Celery tasks) are responsible for only publishing
events whose task_id belongs to the right tenant. The stream view double-
checks the task_id belongs to ``request.tenant`` before subscribing.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Iterable

import redis
from django.conf import settings

_log = logging.getLogger(__name__)

_CHANNEL_PREFIX = "progress:"
_HEARTBEAT_SECONDS = 15.0
_KEEPALIVE_TICK = 1.0


def _client() -> redis.Redis:
    return redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)


def publish(task_id: str, event: dict) -> None:
    """Push one progress event to the channel."""
    payload = json.dumps(event, ensure_ascii=False)
    try:
        _client().publish(f"{_CHANNEL_PREFIX}{task_id}", payload)
    except Exception as exc:  # never crash the producing task on broker glitches
        _log.warning("[progress] publish failed task=%s: %s", task_id, exc)


def stream(task_id: str) -> Iterable[bytes]:
    """Yield SSE frames for one task. Sends a comment heartbeat every 15s
    so intermediaries don't close idle connections.
    """
    client = _client()
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    channel = f"{_CHANNEL_PREFIX}{task_id}"
    pubsub.subscribe(channel)
    try:
        # Tell the browser the stream is open.
        yield b"event: open\ndata: {}\n\n"
        last_heartbeat = time.monotonic()
        while True:
            msg = pubsub.get_message(timeout=_KEEPALIVE_TICK)
            now = time.monotonic()
            if msg and msg.get("type") == "message":
                data = msg["data"]
                if isinstance(data, (bytes, bytearray)):
                    yield b"data: " + bytes(data) + b"\n\n"
                else:
                    yield f"data: {data}\n\n".encode("utf-8")
                last_heartbeat = now
            elif now - last_heartbeat >= _HEARTBEAT_SECONDS:
                yield b": heartbeat\n\n"
                last_heartbeat = now
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception:
            pass
