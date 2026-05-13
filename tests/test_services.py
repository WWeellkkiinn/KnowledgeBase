"""M1.3 验收：services/ 委托接口稳定、parse_refs 无 secrets 也能工作。"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest


def test_services_importable():
    from services import (
        AnalysisService,
        DownloadService,
        ExpandService,
        Pdf2MdService,
        SearchService,
    )
    for cls in (AnalysisService, DownloadService, ExpandService, Pdf2MdService, SearchService):
        sig = inspect.signature(cls)
        assert "db_session" in sig.parameters
        assert sig.parameters["db_session"].default is None


def test_parse_refs_does_not_require_scripts_config(monkeypatch):
    """关键回归：parse_refs 不应触发 scripts.run_analysis_ui 的导入链
    （那条链路要求 scripts/config.py，在无 secrets 的 CI/测试环境会失败）。"""
    # 假装 scripts/config.py 不可导入：在 sys.modules 注入哨兵失败模块
    fake_config_failure = type("M", (), {})()
    monkeypatch.setitem(sys.modules, "config", None)  # ImportError on `import config`

    from services import AnalysisService
    refs = AnalysisService.parse_refs(
        "### [1] Foo et al. (2020) — Some title · DOI: 10.1/abc\n"
        "**作用**：xxx\n\n"
        "### [2] Bar (2021) — Another\n"
    )
    assert [r["index"] for r in refs] == [1, 2]
    assert refs[0]["doi"] == "10.1/abc"
    assert refs[0]["first_author"] == "foo"
    assert refs[1]["doi"] == ""


def test_parse_refs_matches_scripts_version():
    """analysis_service.parse_refs 必须与 scripts.run_analysis_ui._parse_refs
    字段输出对齐（同一字符串解析应得到等价结果）。"""
    # 直接以源代码字符串比较正则定义，避免触发 scripts.run_analysis_ui 顶层 import
    services_src = (Path(__file__).resolve().parent.parent / "services" / "analysis_service.py").read_text(encoding="utf-8")
    scripts_src = (Path(__file__).resolve().parent.parent / "scripts" / "run_analysis_ui.py").read_text(encoding="utf-8")
    needle = r"r'^###\s*\[?(\d+)\]?\.?\s*(.+?)\s+\((\d{4})\)\s*[—–-]\s*'"
    assert needle in services_src
    assert needle in scripts_src


# ─── 委托断言 ─────────────────────────────────────────────────────────


def test_search_service_delegates_to_scripts(monkeypatch):
    """SearchService.search 必须以原参数转发至 scripts.search_refs.search。"""
    captured = {}

    fake_module = type(sys)("search_refs")
    def fake_search(title, year="", doi=""):
        captured["args"] = (title, year, doi)
        return {"title": title, "pdf_url": "https://x/y.pdf", "source": "fake"}
    fake_module.search = fake_search
    monkeypatch.setitem(sys.modules, "search_refs", fake_module)

    from services import SearchService
    out = SearchService().search("Test Title", year="2020", doi="10.1/x")
    assert captured["args"] == ("Test Title", "2020", "10.1/x")
    assert out["source"] == "fake"


def test_download_service_delegates(monkeypatch, tmp_path):
    captured = {}
    fake_module = type(sys)("download_pdf")
    def fake_download(url, output_path):
        captured["args"] = (url, output_path)
        return True, "ok"
    fake_module.download = fake_download
    monkeypatch.setitem(sys.modules, "download_pdf", fake_module)

    from services import DownloadService
    target = (Path(__file__).resolve().parent.parent / "papers" / "_tmp_test.pdf")
    ok, msg = DownloadService().download("https://x/y.pdf", str(target))
    assert ok is True and msg == "ok"
    assert captured["args"][0] == "https://x/y.pdf"


def test_download_service_rejects_bad_scheme():
    from services import DownloadService
    with pytest.raises(ValueError, match="scheme"):
        DownloadService().download("file:///etc/passwd", "papers/a.pdf")


def test_download_service_rejects_path_traversal(tmp_path):
    from services import DownloadService
    outside = str(tmp_path / "evil.pdf")
    with pytest.raises(ValueError, match="papers"):
        DownloadService().download("https://x/y.pdf", outside)


def test_expand_service_delegates(monkeypatch):
    captured = {}
    fake_module = type(sys)("expand")
    def fake_expand(*, root_pdf, focus, max_depth, max_breadth):
        captured["kwargs"] = {"root_pdf": root_pdf, "focus": focus,
                              "max_depth": max_depth, "max_breadth": max_breadth}
    fake_module.expand = fake_expand
    monkeypatch.setitem(sys.modules, "expand", fake_module)

    from services import ExpandService
    ExpandService().run(root_pdf=Path("a.pdf"), focus="methodology",
                        max_depth=2, max_breadth=5)
    assert captured["kwargs"]["focus"] == "methodology"
    assert captured["kwargs"]["max_depth"] == 2
    assert captured["kwargs"]["max_breadth"] == 5


def test_pdf2md_parses_last_json_with_trailing_noise(tmp_path, monkeypatch):
    """Pdf2MdService 从 stdout 后往前找首条可解析 JSON，能跳过尾部噪声。"""
    import subprocess as _sub
    fake_completed = type("R", (), {})()
    fake_completed.returncode = 0
    fake_completed.stdout = (
        'warning: foo\n'
        '{"md_path": "out.md", "sections": []}\n'
        'WARN trailing noise after JSON\n'
        '\n'
    )
    fake_completed.stderr = ""
    monkeypatch.setattr(_sub, "run", lambda *a, **kw: fake_completed)

    from services import Pdf2MdService
    result = Pdf2MdService().convert(Path("a.pdf"))
    assert result == {"md_path": "out.md", "sections": []}


def test_pdf2md_returns_error_on_nonzero(monkeypatch):
    import subprocess as _sub
    fake = type("R", (), {})()
    fake.returncode = 1
    fake.stdout = ""
    fake.stderr = "boom"
    monkeypatch.setattr(_sub, "run", lambda *a, **kw: fake)

    from services import Pdf2MdService
    assert Pdf2MdService().convert(Path("a.pdf")) == {"error": "boom"}


def test_pdf2md_returns_error_when_no_json(monkeypatch):
    import subprocess as _sub
    fake = type("R", (), {})()
    fake.returncode = 0
    fake.stdout = "just some logs, no JSON anywhere\n"
    fake.stderr = ""
    monkeypatch.setattr(_sub, "run", lambda *a, **kw: fake)

    from services import Pdf2MdService
    result = Pdf2MdService().convert(Path("a.pdf"))
    assert "error" in result and "no JSON" in result["error"]


def test_search_service_signature():
    from services import SearchService
    sig = inspect.signature(SearchService.search)
    assert {"title", "year", "doi"}.issubset(sig.parameters)


def test_analysis_service_signature():
    from services import AnalysisService
    sig = inspect.signature(AnalysisService.analyze)
    assert {"md_path", "focus"}.issubset(sig.parameters)
