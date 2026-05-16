"""recommendation_service 单测：去重、批量评分、单篇兜底、低分过滤。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, models
from database.models_recs import Recommendation, UserProfile
from services import recommendation_service


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture()
def session(tmp_path: Path):
    db_file = tmp_path / "kb_rec.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    import database.models_recs  # noqa: F401
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed_profile(session) -> None:
    row = UserProfile(
        id=1,
        profile_json={
            "themes": [{
                "name": "ABM",
                "keywords_en": ["agent-based modeling"],
                "keywords_zh": ["智能体"],
                "key_authors": [],
                "methods": [],
                "weight": 1.0,
            }],
            "excluded": [],
        },
        generated_at=_utcnow_naive(),
        source_paper_count=10,
        model="test",
    )
    session.add(row)
    session.commit()


def _fake_oa_result(doi: str, title: str) -> dict:
    return {
        "doi": f"https://doi.org/{doi}",
        "title": title,
        "publication_year": 2026,
        "authorships": [{"author": {"display_name": "A. Smith"}}],
        "abstract_inverted_index": {"abstract": [0], "text": [1]},
    }


def _fake_ss_result(doi: str, title: str) -> dict:
    return {
        "externalIds": {"DOI": doi},
        "title": title,
        "abstract": "abstract text from SS",
        "authors": [{"name": "B. Jones"}],
        "year": 2026,
        "url": f"https://doi.org/{doi}",
    }


# ─── 无 profile → 触发 regenerate ──────────────────────────────────


def test_triggers_regenerate_when_no_profile(session, monkeypatch):
    # papers 全部已分析，足够触发 regenerate（>= 5）
    for i in range(6):
        session.add(models.Paper(
            stem=f"p{i}", doi=f"10.1/seed{i}", title=f"seed {i}",
            tags=[], ai_summary={}, ai_analyzed_at=_utcnow_naive(),
            status="analyzed",
        ))
    session.commit()

    fake_profile_resp = json.dumps({
        "themes": [{"name": "ABM", "keywords_en": ["abm"], "keywords_zh": [],
                    "key_authors": [], "methods": [], "weight": 1.0}],
        "excluded": [],
    })
    from services import profile_service
    monkeypatch.setattr(profile_service, "_call_ollama", lambda *a, **k: fake_profile_resp)

    # 不让真的去查 API
    monkeypatch.setattr(recommendation_service, "_search_openalex", lambda *a, **k: [])
    monkeypatch.setattr(recommendation_service, "_search_ss", lambda *a, **k: [])

    result = recommendation_service.run_daily_recommendation(session)
    assert result["candidates_fetched"] == 0
    # profile 应被写入
    assert session.execute(select(UserProfile)).scalar_one() is not None


# ─── 候选去重：已在 papers 表的 DOI 跳过 ────────────────────────


def test_dedup_against_existing_papers(session, monkeypatch):
    _seed_profile(session)
    # papers 表里已有 10.1/exists
    session.add(models.Paper(
        stem="exists", doi="10.1/exists", title="existing",
        status="analyzed", tags=[],
    ))
    session.commit()

    oa_results = [_fake_oa_result("10.1/exists", "Existing"),
                  _fake_oa_result("10.1/new", "New Paper")]
    monkeypatch.setattr(recommendation_service, "_search_openalex",
                        lambda *a, **k: oa_results)
    monkeypatch.setattr(recommendation_service, "_search_ss", lambda *a, **k: [])

    # 评分让两篇都过线（但 exists 应在去重阶段被剔除）
    scoring_resp = json.dumps([
        {"id": 0, "score": 0.9, "matched_theme": "ABM", "reason": "ok"}
    ])
    monkeypatch.setattr(recommendation_service, "_call_ollama",
                        lambda *a, **k: scoring_resp)

    result = recommendation_service.run_daily_recommendation(session, max_candidates=10)
    accepted_recs = session.execute(select(Recommendation)).scalars().all()
    accepted_ids = {r.external_id for r in accepted_recs}
    assert "10.1/exists" not in accepted_ids
    assert "10.1/new" in accepted_ids
    assert result["accepted"] == 1


# ─── 批量评分写入 + 低分过滤 ────────────────────────────────────


def test_batch_scoring_and_min_score_filter(session, monkeypatch):
    _seed_profile(session)

    # 3 篇候选
    oa_results = [
        _fake_oa_result("10.1/a", "Paper A"),
        _fake_oa_result("10.1/b", "Paper B"),
        _fake_oa_result("10.1/c", "Paper C"),
    ]
    monkeypatch.setattr(recommendation_service, "_search_openalex",
                        lambda *a, **k: oa_results)
    monkeypatch.setattr(recommendation_service, "_search_ss", lambda *a, **k: [])

    # 一篇 0.9（写入）、一篇 0.6（写入）、一篇 0.3（跳过）
    scoring_resp = json.dumps([
        {"id": 0, "score": 0.9, "matched_theme": "ABM", "reason": "强相关"},
        {"id": 1, "score": 0.6, "matched_theme": "ABM", "reason": "中等"},
        {"id": 2, "score": 0.3, "matched_theme": "ABM", "reason": "弱"},
    ])
    monkeypatch.setattr(recommendation_service, "_call_ollama",
                        lambda *a, **k: scoring_resp)

    result = recommendation_service.run_daily_recommendation(session, max_candidates=10)
    recs = session.execute(select(Recommendation).order_by(Recommendation.external_id)).scalars().all()
    assert len(recs) == 2
    ext_ids = {r.external_id for r in recs}
    assert ext_ids == {"10.1/a", "10.1/b"}
    assert result["accepted"] == 2
    assert result["skipped"] >= 1


# ─── JSON 解析失败 → 单篇兜底 ─────────────────────────────────────


def test_batch_parse_failure_falls_back_per_paper(session, monkeypatch):
    _seed_profile(session)

    oa_results = [
        _fake_oa_result("10.1/x", "X"),
        _fake_oa_result("10.1/y", "Y"),
    ]
    monkeypatch.setattr(recommendation_service, "_search_openalex",
                        lambda *a, **k: oa_results)
    monkeypatch.setattr(recommendation_service, "_search_ss", lambda *a, **k: [])

    calls = {"n": 0}

    def fake_call(messages, num_predict=2048):
        calls["n"] += 1
        # 第一次（批量）返回烂掉的内容；后续单篇返回合法 JSON 数组
        if calls["n"] == 1:
            return "not a json at all"
        return json.dumps([{"id": 0, "score": 0.8, "matched_theme": "ABM", "reason": "fallback"}])

    monkeypatch.setattr(recommendation_service, "_call_ollama", fake_call)

    result = recommendation_service.run_daily_recommendation(session, max_candidates=10)
    # 至少 1 次批量 + 2 次单篇兜底
    assert calls["n"] >= 3
    recs = session.execute(select(Recommendation)).scalars().all()
    # 两篇兜底都应写入
    assert len(recs) == 2
    assert result["accepted"] == 2
