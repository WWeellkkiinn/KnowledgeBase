"""ProgressBus —— 进程内 pub-sub，service 层产事件，socket 层消费。

设计目的：把 service 内的进度信号与传输协议（SocketIO / SSE）解耦。
线程安全：listeners 列表写入加锁；publish 时短暂持锁取快照后调用，
避免在持锁状态下进入用户回调。
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Iterable

Listener = Callable[[dict], None]


def _utc_iso_z() -> str:
    """UTC ISO8601 + 'Z' 后缀；与 app/routes/api._iso_utc 保持同一格式。"""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


class ProgressBus:
    """每个 task_id 一个频道；额外有 `*` 通配频道接收所有事件。

    与之前版本相比：内部用普通 dict（非 defaultdict），避免 subscribe 任意 channel
    时永久占位空 list/deque。
    """

    def __init__(self, buffer_size: int = 200, max_channels: int = 1024) -> None:
        self._listeners: dict[str, list[Listener]] = {}
        self._buffer: dict[str, deque[dict]] = {}
        self._buffer_size = buffer_size
        self._max_channels = max_channels
        self._lock = threading.Lock()

    # ─── publish ────────────────────────────────────────────────────

    def publish(self, task_id: str | int, event_type: str, payload: dict | None = None) -> dict:
        channel = str(task_id)
        event = {
            "task_id": channel,
            "type": event_type,
            "payload": payload or {},
            "ts": _utc_iso_z(),
        }
        with self._lock:
            buf = self._buffer.get(channel)
            if buf is None:
                # 简单的 LRU-ish 兜底：超过 max_channels 时丢最旧的
                if len(self._buffer) >= self._max_channels:
                    oldest_key = next(iter(self._buffer))
                    self._buffer.pop(oldest_key, None)
                buf = deque(maxlen=self._buffer_size)
                self._buffer[channel] = buf
            buf.append(event)
            snapshots = [list(self._listeners.get(ch, ())) for ch in (channel, "*")]
        for listeners in snapshots:
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
            self._listeners.setdefault(channel, []).append(listener)

        def _unsub() -> None:
            with self._lock:
                arr = self._listeners.get(channel)
                if not arr:
                    return
                try:
                    arr.remove(listener)
                except ValueError:
                    return
                if not arr:
                    # 清空 list 时同步删 key，避免无界增长
                    self._listeners.pop(channel, None)

        return _unsub

    def replay(self, channel: str) -> Iterable[dict]:
        with self._lock:
            return list(self._buffer.get(channel, ()))

    # ─── 维护 ────────────────────────────────────────────────────────

    def evict(self, channel: str) -> None:
        """显式回收一个 channel 的 buffer 与 listeners（task 完结后调用）。"""
        with self._lock:
            self._buffer.pop(channel, None)
            self._listeners.pop(channel, None)


# 全局单例：默认共享一个 bus 实例
_bus_singleton: ProgressBus | None = None
_singleton_lock = threading.Lock()


def get_bus() -> ProgressBus:
    global _bus_singleton
    bus = _bus_singleton
    if bus is not None:
        return bus
    with _singleton_lock:
        if _bus_singleton is None:
            _bus_singleton = ProgressBus()
        return _bus_singleton
