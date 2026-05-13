"""Socket.IO 进度推送 namespace（M1.6）。

客户端订阅 `progress` namespace 后可发 `subscribe` 事件指定 task_id；
ProgressBus 上每条事件通过 socketio.emit 推到对应房间。
"""
from __future__ import annotations

from flask_socketio import emit, join_room, leave_room

from app import socketio
from services.progress_bus import get_bus

NAMESPACE = "/progress"
_unsub_handles: dict[str, callable] = {}


def _make_listener(task_id: str):
    def _listener(event: dict) -> None:
        socketio.emit("event", event, namespace=NAMESPACE, to=task_id)
    return _listener


@socketio.on("connect", namespace=NAMESPACE)
def _on_connect():
    emit("connected", {"ok": True})


@socketio.on("subscribe", namespace=NAMESPACE)
def _on_subscribe(data):
    task_id = str((data or {}).get("task_id", ""))
    if not task_id:
        emit("error", {"reason": "missing task_id"})
        return
    join_room(task_id)
    # 回放缓冲
    bus = get_bus()
    for ev in bus.replay(task_id):
        emit("event", ev)
    # 订阅未来事件（按 task_id 只注册一次）
    if task_id not in _unsub_handles:
        _unsub_handles[task_id] = bus.subscribe(task_id, _make_listener(task_id))


@socketio.on("unsubscribe", namespace=NAMESPACE)
def _on_unsubscribe(data):
    task_id = str((data or {}).get("task_id", ""))
    leave_room(task_id)
