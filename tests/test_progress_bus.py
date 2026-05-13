"""M1.6 验收：ProgressBus pub/sub + 回放 + 通配频道。"""
from __future__ import annotations

from services.progress_bus import ProgressBus


def test_publish_and_subscribe():
    bus = ProgressBus()
    received: list[dict] = []
    unsub = bus.subscribe("42", received.append)
    bus.publish(42, "phase", {"step": 1})
    bus.publish(42, "done", {"ok": True})
    unsub()
    bus.publish(42, "after_unsub", {})
    assert [e["type"] for e in received] == ["phase", "done"]


def test_wildcard_channel_receives_all():
    bus = ProgressBus()
    seen: list[str] = []
    bus.subscribe("*", lambda e: seen.append(e["task_id"]))
    bus.publish("a", "x")
    bus.publish("b", "y")
    assert set(seen) == {"a", "b"}


def test_replay_returns_buffered_events():
    bus = ProgressBus(buffer_size=10)
    for i in range(3):
        bus.publish("t1", "step", {"i": i})
    events = list(bus.replay("t1"))
    assert [e["payload"]["i"] for e in events] == [0, 1, 2]


def test_buffer_bounded():
    bus = ProgressBus(buffer_size=2)
    for i in range(5):
        bus.publish("t", "x", {"i": i})
    events = list(bus.replay("t"))
    assert len(events) == 2
    assert events[0]["payload"]["i"] == 3
    assert events[1]["payload"]["i"] == 4


def test_listener_exception_isolated():
    bus = ProgressBus()
    seen: list[dict] = []
    bus.subscribe("c", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("c", seen.append)
    bus.publish("c", "y")  # 不能因 listener 异常崩溃
    assert len(seen) == 1
