"""Socket.IO 进度推送 namespace（M1.6）。

订阅模型：
- 每个 task_id 在 bus 上**只挂一个 listener**（refcount 由 _subs 维护）
- 客户端 join 房间；房间销毁靠 socketio 自身管理（per-sid）
- 最后一个客户端 unsubscribe 时清理 bus listener + buffer

task_id 校验：仅接受 [A-Za-z0-9._-]{1,128}，防止恶意 channel 注入 + 占内存。
"""
from __future__ import annotations

import hmac
import os
import re
import threading
from typing import Callable

from flask_socketio import disconnect, emit, join_room, leave_room
from flask import request

from app import socketio
from services.progress_bus import get_bus

NAMESPACE = "/progress"
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# subs[task_id] = (unsub_handle, ref_count)
_subs: dict[str, tuple[Callable[[], None], int]] = {}
_subs_lock = threading.Lock()

# 已鉴权 sid 集合：connect 校验通过后写入，disconnect 时移除。
# 后续 subscribe/unsubscribe 事件 handler 必须先校验 sid 是否在集合内，
# 防止攻击者绕过 connect 直接发事件。线程安全用 _authed_lock 保护。
_authed_sids: set[str] = set()
_authed_lock = threading.Lock()


def _is_authed(sid: str | None) -> bool:
    if not sid:
        return False
    with _authed_lock:
        return sid in _authed_sids


def _mark_authed(sid: str) -> None:
    with _authed_lock:
        _authed_sids.add(sid)


def _drop_authed(sid: str) -> None:
    with _authed_lock:
        _authed_sids.discard(sid)


def _valid_task_id(value: str | None) -> str | None:
    if not value:
        return None
    s = str(value)
    return s if _TASK_ID_RE.match(s) else None


def _ensure_listener(task_id: str) -> None:
    """首次订阅时注册 bus listener，已有则 refcount + 1。"""
    bus = get_bus()
    with _subs_lock:
        cur = _subs.get(task_id)
        if cur is not None:
            unsub, n = cur
            _subs[task_id] = (unsub, n + 1)
            return

        def _forward(event: dict, _tid: str = task_id) -> None:
            socketio.emit("event", event, namespace=NAMESPACE, to=_tid)

        unsub = bus.subscribe(task_id, _forward)
        _subs[task_id] = (unsub, 1)


def _release_listener(task_id: str) -> None:
    """refcount - 1；归零时清掉 bus listener + buffer。"""
    bus = get_bus()
    with _subs_lock:
        cur = _subs.get(task_id)
        if cur is None:
            return
        unsub, n = cur
        if n <= 1:
            _subs.pop(task_id, None)
            unsub()
            bus.evict(task_id)
        else:
            _subs[task_id] = (unsub, n - 1)


@socketio.on("connect", namespace=NAMESPACE)
def _on_connect(auth=None):
    """连接时校验 Bearer token；未配置 KB_API_TOKEN 时放行（与 HTTP 鉴权对齐）。

    auth 必须是 dict，否则按未授权处理（防 list/str 触发 AttributeError）。
    校验通过后把 sid 写入 _authed_sids，后续事件 handler 据此判断。
    """
    expected = os.environ.get("KB_API_TOKEN")
    if expected:
        token = ""
        if isinstance(auth, dict):
            token = str(auth.get("token") or "")
        if not token or not hmac.compare_digest(token, expected):
            disconnect()
            return False
    _mark_authed(request.sid)
    emit("connected", {"ok": True})


def _require_authed_sid() -> bool:
    """事件 handler 前置校验：sid 未鉴权直接 disconnect 并返回 False。"""
    if not _is_authed(request.sid):
        disconnect()
        return False
    return True


@socketio.on("subscribe", namespace=NAMESPACE)
def _on_subscribe(data):
    if not _require_authed_sid():
        return
    task_id = _valid_task_id((data or {}).get("task_id"))
    if not task_id:
        emit("error", {"reason": "invalid task_id"})
        return
    join_room(task_id)
    # 回放缓冲
    for ev in get_bus().replay(task_id):
        emit("event", ev)
    _ensure_listener(task_id)


@socketio.on("unsubscribe", namespace=NAMESPACE)
def _on_unsubscribe(data):
    if not _require_authed_sid():
        return
    task_id = _valid_task_id((data or {}).get("task_id"))
    if not task_id:
        return
    leave_room(task_id)
    _release_listener(task_id)


@socketio.on("disconnect", namespace=NAMESPACE)
def _on_disconnect():
    # flask-socketio 会自动 leave 该 sid 的所有 room，但 bus listener 是
    # session-level 的，需要根据 sid 在哪些 room 释放。当前简化处理：
    # 单用户 dev 环境下，依赖客户端显式发 unsubscribe；如果 dirty disconnect
    # 没发 unsubscribe，listener 会等到下一次同 task_id 的 subscribe 重算 refcount。
    # 长期对策：维护 sid → task_ids 映射，断线时按映射释放。M2+ 再补。
    _drop_authed(request.sid)
