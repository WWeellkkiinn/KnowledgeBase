"""ProgressBus —— 进程内 pub-sub，service 层产事件，socket 层消费。

设计目的：把 service 内的进度信号与传输协议（SocketIO / SSE）解耦，
便于多种前端共存（旧 SSE 入口 + Web Socket.IO）。

线程安全：listeners 列表写入加锁；publish 时短暂持锁取快照后调用，
避免在持锁状态下进入用户回调。
"""
from __future__ import annotations

import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Callable, Iterable

Listener = Callable[[dict], None]


class ProgressBus:
    """每个 task_id 一个频道；额外有 `*` 通配频道接收所有事件。"""

    def __init__(self, buffer_size: int = 200) -> None:
        self._listeners: dict[str, list[Listener]] = defaultdict(list)
        self._buffer: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=buffer_size))
        self._lock = threading.Lock()

    # ─── publish ────────────────────────────────────────────────────

    def publish(self, task_id: str | int, event_type: str, payload: dict | None = None) -> dict:
        event = {
            "task_id": str(task_id),
            "type": event_type,
            "payload": payload or {},
            "ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }
        with self._lock:
            self._buffer[str(task_id)].append(event)
            channels = [str(task_id), "*"]
            snapshots = [(ch, list(self._listeners.get(ch, ()))) for ch in channels]
        for _ch, listeners in snapshots:
            for fn in listeners:
                try:
                    fn(event)
                except Exception:
                    # listeners 不可影响生产者
                    pass
        return event

    # ─── subscribe ──────────────────────────────────────────────────

    def subscribe(self, channel: str, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners[channel].append(listener)
        def _unsub():
            with self._lock:
                try:
                    self._listeners[channel].remove(listener)
                except ValueError:
                    pass
        return _unsub

    def replay(self, channel: str) -> Iterable[dict]:
        with self._lock:
            return list(self._buffer.get(channel, ()))


# 全局单例：默认共享一个 bus 实例
_bus_singleton: ProgressBus | None = None
_singleton_lock = threading.Lock()


def get_bus() -> ProgressBus:
    global _bus_singleton
    with _singleton_lock:
        if _bus_singleton is None:
            _bus_singleton = ProgressBus()
    return _bus_singleton
