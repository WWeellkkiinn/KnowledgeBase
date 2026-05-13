"""M1.3 验收：services/ 公共 API 可导入，委托接口可调用，签名稳定。

不调用真实 LLM / 下载 / MinerU；只验证抽离层接口完整。
"""
from __future__ import annotations

import inspect

import pytest


def test_services_importable():
    from services import (
        AnalysisService,
        DownloadService,
        ExpandService,
        Pdf2MdService,
        SearchService,
    )
    # db_session 必须是可选构造参数
    for cls in (AnalysisService, DownloadService, ExpandService, Pdf2MdService, SearchService):
        sig = inspect.signature(cls)
        assert "db_session" in sig.parameters
        assert sig.parameters["db_session"].default is None


def test_search_service_signature():
    from services import SearchService
    sig = inspect.signature(SearchService.search)
    assert {"title", "year", "doi"}.issubset(sig.parameters)


def test_download_service_signature():
    from services import DownloadService
    sig = inspect.signature(DownloadService.download)
    assert {"url", "output_path"}.issubset(sig.parameters)


def test_analysis_service_signature():
    from services import AnalysisService
    sig = inspect.signature(AnalysisService.analyze)
    assert {"md_path", "focus"}.issubset(sig.parameters)
    # parse_refs 是静态方法
    assert callable(AnalysisService.parse_refs)


def test_analysis_parse_refs_static():
    from services import AnalysisService
    sample = (
        "# title\n\n---\n\n"
        "### [1] Foo et al. (2020) — Sample paper title\n"
        "**在论文中的作用**：...\n"
        "**与「研究方法」的联系**：...\n\n"
        "### [2] Bar et al. (2021) — Another paper\n"
        "**在论文中的作用**：...\n"
        "**与「研究方法」的联系**：...\n"
    )
    refs = AnalysisService.parse_refs(sample)
    assert isinstance(refs, list)
    assert len(refs) >= 1


def test_expand_service_signature():
    from services import ExpandService
    sig = inspect.signature(ExpandService.run)
    assert {"root_pdf", "focus", "max_depth", "max_breadth"}.issubset(sig.parameters)


def test_pdf2md_service_signature():
    from services import Pdf2MdService
    sig = inspect.signature(Pdf2MdService.convert)
    assert "pdf_path" in sig.parameters
