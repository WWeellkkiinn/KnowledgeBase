"""Socket.IO 进度推送 namespace（M1.6）。

订阅模型：
- 每个 task_id 在 bus 上**只挂一个 listener**（refcount 由 _subs 维护）
- 客户端 join 房间；房间销毁靠 socketio 自身管理（per-sid）
- 最后一个客户端 unsubscribe 时清理 bus listener + buffer
- sid->task_ids 已映射，disconnect 时按映射释放 listener refcount，避免内存泄漏

并发模型：所有共享状态（_authed_sids / _sid_subs / _subs）统一由 _state_lock 保护。
临界区都极短（dict 操作 + 偶发 bus.subscribe/unsub 回调注册），单锁简化推理、
彻底消除 subscribe 与 disconnect 之间因双锁顺序错配导致的 listener 泄漏窗口。

task_id 校验：仅接受 [A-Za-z0-9._-]{1,128}，防止恶意 channel 注入 + 占内存。
"""
from __future__ import annotations

import hmac
import logging
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
_log = logging.getLogger(__name__)

# 统一状态锁：保护 _subs / _authed_sids / _sid_subs。
# 改前：_authed_lock 与 _subs_lock 分裂，subscribe 路径先后取两把锁、disconnect
# 在中间穿插 pop 时 listener refcount 与 sid_subs 会撕裂 → bus listener 泄漏。
_state_lock = threading.Lock()

# subs[task_id] = (unsub_handle, ref_count)
_subs: dict[str, tuple[Callable[[], None], int]] = {}

# 已鉴权 sid 集合：connect 校验通过后写入，disconnect 时移除。
# 后续 subscribe/unsubscribe 事件 handler 必须先校验 sid 是否在集合内，
# 防止攻击者绕过 connect 直接发事件。
_authed_sids: set[str] = set()

# sid -> 已订阅 task_id 集合：dirty disconnect 时按此释放 refcount + bus listener。
_sid_subs: dict[str, set[str]] = {}


def _is_authed(sid: str | None) -> bool:
    if not sid:
        return False
    with _state_lock:
        return sid in _authed_sids


def _mark_authed(sid: str) -> None:
    with _state_lock:
        _authed_sids.add(sid)


def _drop_authed(sid: str) -> None:
    with _state_lock:
        _authed_sids.discard(sid)


def _valid_task_id(value: str | None) -> str | None:
    if not value:
        return None
    s = str(value)
    return s if _TASK_ID_RE.match(s) else None


def _ensure_listener_locked(task_id: str) -> None:
    """首次订阅时注册 bus listener，已有则 refcount + 1。**调用方必须已持 _state_lock**。"""
    cur = _subs.get(task_id)
    if cur is not None:
        unsub, n = cur
        _subs[task_id] = (unsub, n + 1)
        return

    def _forward(event: dict, _tid: str = task_id) -> None:
        socketio.emit("event", event, namespace=NAMESPACE, to=_tid)

    unsub = get_bus().subscribe(task_id, _forward)
    _subs[task_id] = (unsub, 1)


def _release_listener_locked(task_id: str) -> tuple[Callable[[], None] | None, bool]:
    """refcount - 1；归零返回 (unsub_callable, True) 让调用方在锁外执行清理。
    **调用方必须已持 _state_lock**。
    """
    cur = _subs.get(task_id)
    if cur is None:
        return None, False
    unsub, n = cur
    if n <= 1:
        _subs.pop(task_id, None)
        return unsub, True
    _subs[task_id] = (unsub, n - 1)
    return None, False


def _release_listener(task_id: str) -> None:
    """refcount - 1；归零时清掉 bus listener + buffer。"""
    with _state_lock:
        unsub, should_evict = _release_listener_locked(task_id)
    if should_evict and unsub is not None:
        unsub()
        get_bus().evict(task_id)


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
    # 回放缓冲（在锁外，避免 bus 读锁与 _state_lock 嵌套）
    for ev in get_bus().replay(task_id):
        emit("event", ev)
    sid = request.sid
    # 单锁原子化：重检 sid 仍 authed → 登记 sid_sub → 注册 listener，
    # 整段在 _state_lock 内完成，杜绝 disconnect 穿插导致的 listener 泄漏。
    with _state_lock:
        if sid not in _authed_sids:
            return
        subs = _sid_subs.setdefault(sid, set())
        if task_id in subs:
            return  # 同 sid 重复 subscribe：不重复 +1
        subs.add(task_id)
        _ensure_listener_locked(task_id)


@socketio.on("unsubscribe", namespace=NAMESPACE)
def _on_unsubscribe(data):
    if not _require_authed_sid():
        return
    task_id = _valid_task_id((data or {}).get("task_id"))
    if not task_id:
        return
    leave_room(task_id)
    sid = request.sid
    # 同样单锁原子化：移除 sid_sub 与 listener refcount-1 在一把锁内完成。
    with _state_lock:
        subs = _sid_subs.get(sid)
        if not subs or task_id not in subs:
            return
        subs.discard(task_id)
        if not subs:
            _sid_subs.pop(sid, None)
        unsub, should_evict = _release_listener_locked(task_id)
    if should_evict and unsub is not None:
        try:
            unsub()
            get_bus().evict(task_id)
        except Exception:
            _log.exception("unsubscribe cleanup failed for task_id=%s", task_id)


@socketio.on("disconnect", namespace=NAMESPACE)
def _on_disconnect():
    # dirty disconnect 也要释放该 sid 通过 subscribe 增加过的 refcount，
    # 否则 bus listener 与 _subs 条目会永久残留 → 内存泄漏。
    sid = request.sid
    # 单锁取出 pending 订阅 + 把 sid 移出 authed（先标记不可订阅、再排空）。
    # subscribe 路径在同一把锁内重检 _authed_sids，因此此处之后 subscribe 不会再
    # 为该 sid 新增条目，无竞争窗口。
    pending_evicts: list[tuple[str, Callable[[], None]]] = []
    with _state_lock:
        _authed_sids.discard(sid)
        pending = _sid_subs.pop(sid, set())
        for task_id in pending:
            unsub, should_evict = _release_listener_locked(task_id)
            if should_evict and unsub is not None:
                pending_evicts.append((task_id, unsub))
    # 锁外执行 unsub + bus.evict，单条失败不影响其余 task_id 释放。
    bus = get_bus()
    for task_id, unsub in pending_evicts:
        try:
            unsub()
        except Exception:
            _log.exception("disconnect: unsub failed for task_id=%s", task_id)
        try:
            bus.evict(task_id)
        except Exception:
            _log.exception("disconnect: bus.evict failed for task_id=%s", task_id)
