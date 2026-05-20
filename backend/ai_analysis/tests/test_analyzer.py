"""Tests for AI analyzer service — mocks LLM call."""
import json
from unittest.mock import patch

import pytest

from ai_analysis.services.analyzer import analyze_paper, _sanitize_tags, _sanitize_text


def test_sanitize_tags_basic():
    result = _sanitize_tags(["机器学习", "社会网络", "机器学习"])
    assert result == ["机器学习", "社会网络"]


def test_sanitize_tags_too_long():
    long_tag = "a" * 40
    result = _sanitize_tags([long_tag])
    assert len(result[0]) == 32


def test_sanitize_text_truncate():
    long_text = "x" * 5000
    result = _sanitize_text(long_text)
    assert len(result) == 4000


def _mock_llm_response(messages, **kwargs):
    return json.dumps({
        "title_zh": "测试论文",
        "tags": ["机器学习", "社会网络"],
        "research_question": "这是一个研究问题",
        "methodology": "使用了机器学习方法",
        "key_findings": ["发现1", "发现2"],
    })


@patch("ai_analysis.services.analyzer.chat_completion", side_effect=_mock_llm_response)
def test_analyze_paper_happy(mock_llm):
    result = analyze_paper("Test Paper", "Test abstract")
    assert result["title_zh"] == "测试论文"
    assert "机器学习" in result["tags"]
    assert result["research_question"]
    assert result["methodology"]
    assert len(result["key_findings"]) == 2


@patch("ai_analysis.services.analyzer.chat_completion", return_value="not json at all")
def test_analyze_paper_bad_json(mock_llm):
    result = analyze_paper("Test Paper", "Test abstract")
    assert result == {}
