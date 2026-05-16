"""profile_service 单测：冷启动、正常路径、缓存命中。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, models
from database.models_recs import UserProfile
from services import profile_service


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture()
def session(tmp_path: Path):
    db_file = tmp_path / "kb_profile.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    # 同 models_recs 共享 Base.metadata，create_all 一次即可
    import database.models_recs  # noqa: F401 注册 mapper
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _make_paper(i: int, *, analyzed: bool = True) -> models.Paper:
    p = models.Paper(
        stem=f"paper-{i}",
        doi=f"10.1234/test{i}",
        title=f"Paper {i}: agent-based modeling and emergence",
        abstract="abstract text",
        tags=["agent-based", "复杂系统"],
        ai_summary={
            "research_question": "How do agents interact?",
            "methodology": "agent-based simulation",
            "key_findings": [],
            "title_zh": f"论文 {i}",
        },
        status="analyzed",
    )
    if analyzed:
        p.ai_analyzed_at = _utcnow_naive() - timedelta(days=i)
    return p


# ─── 冷启动 ─────────────────────────────────────────────────────────


def test_cold_start_returns_empty(session, monkeypatch):
    # 仅插 3 篇已分析论文（< COLD_START_MIN=5）
    for i in range(3):
        session.add(_make_paper(i))
    session.commit()

    called = {"n": 0}

    def fake_call(*args, **kwargs):
        called["n"] += 1
        return "{}"

    monkeypatch.setattr(profile_service, "_call_ollama", fake_call)

    result = profile_service.regenerate_profile(session, force=True)
    assert result == {"themes": [], "excluded": []}
    assert called["n"] == 0  # 冷启动不调 LLM
    # 不写表
    assert session.execute(select(UserProfile)).scalar_one_or_none() is None


# ─── 正常路径 ───────────────────────────────────────────────────────


def test_regenerate_writes_profile(session, monkeypatch):
    for i in range(6):
        session.add(_make_paper(i))
    session.commit()

    fake_response = json.dumps({
        "themes": [
            {
                "name": "智能体建模",
                "keywords_en": ["agent-based modeling", "complex systems"],
                "keywords_zh": ["智能体建模", "复杂系统"],
                "key_authors": ["Epstein"],
                "methods": ["仿真"],
                "weight": 1.0,
            }
        ],
        "excluded": ["医学影像"],
    })
    monkeypatch.setattr(profile_service, "_call_ollama", lambda *a, **k: fake_response)

    result = profile_service.regenerate_profile(session, force=True)
    assert len(result["themes"]) == 1
    assert result["themes"][0]["name"] == "智能体建模"
    assert "agent-based modeling" in result["themes"][0]["keywords_en"]
    assert result["excluded"] == ["医学影像"]

    row = session.execute(select(UserProfile)).scalar_one()
    assert row.id == 1
    assert row.source_paper_count == 6
    assert row.profile_json["themes"][0]["name"] == "智能体建模"


# ─── 缓存命中 ───────────────────────────────────────────────────────


def test_cache_hit_skips_llm(session, monkeypatch):
    for i in range(6):
        session.add(_make_paper(i))
    # 先种一份新鲜画像
    row = UserProfile(
        id=1,
        profile_json={"themes": [{"name": "已缓存", "keywords_en": [], "keywords_zh": [],
                                   "key_authors": [], "methods": [], "weight": 1.0}],
                       "excluded": []},
        generated_at=_utcnow_naive() - timedelta(days=1),
        source_paper_count=6,
        model="test-model",
    )
    session.add(row)
    session.commit()

    called = {"n": 0}

    def fake_call(*args, **kwargs):
        called["n"] += 1
        return "{}"

    monkeypatch.setattr(profile_service, "_call_ollama", fake_call)

    result = profile_service.regenerate_profile(session, force=False)
    assert called["n"] == 0
    assert result["themes"][0]["name"] == "已缓存"


def test_force_overrides_cache(session, monkeypatch):
    for i in range(6):
        session.add(_make_paper(i))
    row = UserProfile(
        id=1,
        profile_json={"themes": [], "excluded": []},
        generated_at=_utcnow_naive(),
        source_paper_count=6,
        model="old",
    )
    session.add(row)
    session.commit()

    fake_response = json.dumps({
        "themes": [{"name": "更新", "keywords_en": ["x"], "keywords_zh": ["x"],
                    "key_authors": [], "methods": [], "weight": 1.0}],
        "excluded": [],
    })
    monkeypatch.setattr(profile_service, "_call_ollama", lambda *a, **k: fake_response)

    result = profile_service.regenerate_profile(session, force=True)
    assert result["themes"][0]["name"] == "更新"


def test_llm_failure_keeps_old_profile(session, monkeypatch):
    for i in range(6):
        session.add(_make_paper(i))
    old = {"themes": [{"name": "旧", "keywords_en": [], "keywords_zh": [],
                       "key_authors": [], "methods": [], "weight": 1.0}],
           "excluded": []}
    row = UserProfile(
        id=1,
        profile_json=old,
        generated_at=_utcnow_naive() - timedelta(days=30),  # 已过期
        source_paper_count=6,
        model="old",
    )
    session.add(row)
    session.commit()

    def boom(*a, **k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(profile_service, "_call_ollama", boom)

    result = profile_service.regenerate_profile(session, force=True)
    assert result["themes"][0]["name"] == "旧"  # 旧画像保留
