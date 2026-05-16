"""arxiv_service 单元测试：解析、时间过滤、关键词拼接、错误降级、并发锁。"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from services import arxiv_service


def _make_xml(entries_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:arxiv="http://arxiv.org/schemas/atom">\n'
        f"{entries_xml}\n"
        "</feed>"
    )


def _entry(arxiv_id: str, title: str, published_iso: str, primary: str = "cs.AI") -> str:
    return f"""
  <entry>
    <id>http://arxiv.org/abs/{arxiv_id}</id>
    <title>{title}</title>
    <summary>This is an abstract for {arxiv_id}.</summary>
    <published>{published_iso}</published>
    <updated>{published_iso}</updated>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <arxiv:primary_category term="{primary}"/>
    <category term="{primary}"/>
    <category term="cs.LG"/>
  </entry>
"""


class _FakeResp:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom", request=None, response=None  # type: ignore[arg-type]
            )


@pytest.fixture(autouse=True)
def _reset_rate_clock(monkeypatch):
    """禁用真实 sleep + 重置时钟，确保测试不阻塞、不串扰。"""
    monkeypatch.setattr(arxiv_service.time, "sleep", lambda *_a, **_k: None)
    arxiv_service._LAST_CALL_TS = 0.0
    yield
    arxiv_service._LAST_CALL_TS = 0.0


def _patch_client(monkeypatch, xml_text: str | None, raise_exc: Exception | None = None,
                  capture: dict | None = None):
    """替换 arxiv_service 模块级 _CLIENT.get，使其返回固定响应或抛错。"""

    def _fake_get(url, *a, **kw):
        if capture is not None:
            capture["url"] = url
        if raise_exc is not None:
            raise raise_exc
        return _FakeResp(xml_text or "")

    monkeypatch.setattr(arxiv_service._CLIENT, "get", _fake_get)


def test_fetch_recent_parses_fields(monkeypatch):
    now = datetime.now(timezone.utc)
    iso = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    iso2 = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = _make_xml(
        _entry("2501.12345v1", "Sample Paper Title", iso)
        + _entry("2501.99999v2", "Second Paper", iso2, primary="cs.CL")
    )
    _patch_client(monkeypatch, xml)

    items = arxiv_service.fetch_arxiv_recent(["cs.AI", "cs.CL"], hours=24)
    assert len(items) == 2
    a = items[0]
    assert a["arxiv_id"] == "2501.12345"  # vN 后缀已剥
    assert a["title"] == "Sample Paper Title"
    assert a["abstract"].startswith("This is an abstract")
    assert a["authors"] == ["Alice Smith", "Bob Jones"]
    assert a["primary_category"] == "cs.AI"
    assert "cs.AI" in a["categories"] and "cs.LG" in a["categories"]
    assert a["pdf_url"] == "http://arxiv.org/pdf/2501.12345.pdf"
    assert a["abs_url"] == "http://arxiv.org/abs/2501.12345"
    assert isinstance(a["published_at"], datetime)
    assert a["published_at"].tzinfo is None  # UTC naive
    assert items[1]["primary_category"] == "cs.CL"


def test_fetch_recent_time_filter(monkeypatch):
    now = datetime.now(timezone.utc)
    recent_iso = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_iso = (now - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = _make_xml(
        _entry("2501.00001", "Recent", recent_iso)
        + _entry("2501.00002", "Old", old_iso)
    )
    _patch_client(monkeypatch, xml)

    items = arxiv_service.fetch_arxiv_recent(["cs.AI"], hours=24)
    assert len(items) == 1
    assert items[0]["arxiv_id"] == "2501.00001"


def test_fetch_by_keywords_query_composition(monkeypatch):
    now = datetime.now(timezone.utc)
    iso = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = _make_xml(_entry("2501.11111", "Agent-Based Sim", iso))
    capture: dict = {}
    _patch_client(monkeypatch, xml, capture=capture)

    items = arxiv_service.fetch_arxiv_by_keywords(
        ["agent-based", "simulation"], hours=24, max_results=10
    )
    assert len(items) == 1
    url = capture["url"]
    # 关键词以字面 +AND+ 连接，双引号 URL 编码为 %22；+OR+/+AND+ 不能被 quote
    assert "search_query=all:%22agent-based%22+AND+all:%22simulation%22" in url
    assert "sortBy=submittedDate" in url
    assert "sortOrder=descending" in url
    assert "max_results=10" in url


def test_fetch_recent_category_query(monkeypatch):
    capture: dict = {}
    _patch_client(monkeypatch, _make_xml(""), capture=capture)
    arxiv_service.fetch_arxiv_recent(["cs.AI", "cs.CL"], hours=24, max_per_category=5)
    url = capture["url"]
    assert "search_query=cat:cs.AI+OR+cat:cs.CL" in url
    assert "max_results=5" in url


def test_http_error_returns_empty_and_logs(monkeypatch, caplog):
    _patch_client(monkeypatch, None, raise_exc=httpx.ConnectError("net down"))
    with caplog.at_level(logging.WARNING, logger="services.arxiv_service"):
        items = arxiv_service.fetch_arxiv_recent(["cs.AI"])
    assert items == []
    assert any("arXiv API 调用失败" in r.message for r in caplog.records)


def test_empty_inputs_short_circuit(monkeypatch):
    # 无 categories / keywords 不应发起网络请求
    called = {"n": 0}

    class _Boom:
        def __init__(self, *a, **kw): called["n"] += 1
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **k): called["n"] += 1; return _FakeResp("")

    monkeypatch.setattr(arxiv_service.httpx, "Client", _Boom)
    assert arxiv_service.fetch_arxiv_recent([]) == []
    assert arxiv_service.fetch_arxiv_by_keywords([]) == []
    assert arxiv_service.fetch_arxiv_recent(["  "]) == []
    assert arxiv_service.fetch_arxiv_by_keywords(["  "]) == []
    assert called["n"] == 0


def test_concurrent_fetch_no_deadlock(monkeypatch):
    now = datetime.now(timezone.utc)
    iso = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = _make_xml(_entry("2501.22222", "Concurrent", iso))
    _patch_client(monkeypatch, xml)

    results: list[list] = []
    errors: list[Exception] = []

    def _worker():
        try:
            results.append(arxiv_service.fetch_arxiv_recent(["cs.AI"], hours=24))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), "限速锁导致死锁"
    assert errors == []
    assert len(results) == 2
    assert all(len(r) == 1 for r in results)
