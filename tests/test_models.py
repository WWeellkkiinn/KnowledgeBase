"""M1.1 验收测试：alembic 迁移 + ORM 行为 + FK/约束/回滚。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database import Base, enable_sqlite_foreign_keys, session_scope
from database import models  # noqa: F401 —— 注册 mapper

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def session_factory(tmp_path: Path):
    """通过 Base.metadata.create_all 起一个干净 engine（带 FK PRAGMA）。"""
    db_file = tmp_path / "kb_test.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield Session
    engine.dispose()


@pytest.fixture()
def alembic_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """通过 alembic upgrade head 建库，验证 migration 与 model 一致。"""
    db_file = tmp_path / "kb_alembic.db"
    monkeypatch.setenv("KB_DB_PATH", str(db_file))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    yield engine
    engine.dispose()


# ─── Alembic ─────────────────────────────────────────────────────────────

def test_alembic_upgrade_creates_all_tables(alembic_db):
    insp = inspect(alembic_db)
    tables = set(insp.get_table_names())
    expected = {
        "papers", "journals", "edges", "tasks",
        "subscriptions", "subscription_results", "citations", "sessions",
        "alembic_version",
    }
    assert expected.issubset(tables), f"missing: {expected - tables}"


def test_alembic_max_attempts_server_default(alembic_db):
    """绕过 ORM，纯 SQL 插入，验证 DB 层 server_default 生效。"""
    with alembic_db.begin() as conn:
        from sqlalchemy import text as sql
        conn.execute(sql("INSERT INTO tasks (type) VALUES ('analyze')"))
        row = conn.execute(sql(
            "SELECT status, attempt, max_attempts FROM tasks"
        )).one()
    assert row.status == "queued"
    assert row.attempt == 0
    assert row.max_attempts == 3


# ─── ORM CRUD ────────────────────────────────────────────────────────────

def test_create_paper_and_edge(session_factory):
    Session = session_factory
    with Session() as s:
        p1 = models.Paper(stem="root_2024", title="Root", source="root", status="analyzed")
        p2 = models.Paper(stem="ref_2020", title="Ref", source="ref")
        s.add_all([p1, p2])
        s.flush()
        s.add(models.Edge(
            from_paper_id=p1.id, to_paper_id=p2.id,
            direction="backward", ref_index=1,
        ))
        s.commit()
    with Session() as s:
        assert s.query(models.Edge).count() == 1


def test_stem_unique(session_factory):
    Session = session_factory
    with Session() as s:
        s.add(models.Paper(stem="dup", source="root")); s.commit()
    with pytest.raises(IntegrityError):
        with Session() as s:
            s.add(models.Paper(stem="dup", source="ref")); s.commit()


# ─── Edge 唯一约束 ────────────────────────────────────────────────────────

def test_edge_backward_duplicate_blocked(session_factory):
    """同一 from + direction=backward + ref_index 重复必须报错。"""
    Session = session_factory
    with Session() as s:
        p1 = models.Paper(stem="a", source="root")
        p2 = models.Paper(stem="b", source="ref")
        p3 = models.Paper(stem="c", source="ref")
        s.add_all([p1, p2, p3]); s.flush()
        s.add(models.Edge(from_paper_id=p1.id, to_paper_id=p2.id,
                          direction="backward", ref_index=1))
        s.commit()
        with pytest.raises(IntegrityError):
            s.add(models.Edge(from_paper_id=p1.id, to_paper_id=p3.id,
                              direction="backward", ref_index=1))
            s.commit()


def test_edge_forward_null_index_allowed(session_factory):
    """forward 边允许 ref_index=NULL，多条共存。"""
    Session = session_factory
    with Session() as s:
        p1 = models.Paper(stem="a", source="root")
        p2 = models.Paper(stem="b", source="forward")
        p3 = models.Paper(stem="c", source="forward")
        s.add_all([p1, p2, p3]); s.flush()
        s.add_all([
            models.Edge(from_paper_id=p1.id, to_paper_id=p2.id, direction="forward"),
            models.Edge(from_paper_id=p1.id, to_paper_id=p3.id, direction="forward"),
        ])
        s.commit()
        assert s.query(models.Edge).count() == 2


# ─── FK cascade ───────────────────────────────────────────────────────────

def test_paper_delete_cascades_edges(session_factory):
    Session = session_factory
    with Session() as s:
        p1 = models.Paper(stem="root", source="root")
        p2 = models.Paper(stem="leaf", source="ref")
        s.add_all([p1, p2]); s.flush()
        s.add(models.Edge(from_paper_id=p1.id, to_paper_id=p2.id,
                          direction="backward", ref_index=1))
        s.commit()
        s.delete(p1)
        s.commit()
    with Session() as s:
        assert s.query(models.Edge).count() == 0


def test_journal_delete_sets_paper_journal_null(session_factory):
    Session = session_factory
    with Session() as s:
        j = models.Journal(issn="1234-5678", name="J", is_predatory=False)
        s.add(j); s.flush()
        p = models.Paper(stem="paper-a", source="root", journal_id=j.id)
        s.add(p); s.commit()
        s.delete(j); s.commit()
    with Session() as s:
        reloaded = s.query(models.Paper).filter_by(stem="paper-a").one()
        assert reloaded.journal_id is None


# ─── session_scope ───────────────────────────────────────────────────────

def test_session_scope_rolls_back_on_error(tmp_path, monkeypatch):
    """session_scope 异常路径必须 rollback。"""
    db_file = tmp_path / "kb_scope.db"
    monkeypatch.setenv("KB_DB_PATH", str(db_file))
    # 重新构建 engine 指向新路径
    from sqlalchemy import create_engine as _create
    import database as _db
    engine = _create(f"sqlite:///{db_file.as_posix()}", future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    SL = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(_db, "SessionLocal", SL)

    with pytest.raises(RuntimeError):
        with _db.session_scope() as s:
            s.add(models.Paper(stem="will_rollback", source="root"))
            raise RuntimeError("boom")

    with SL() as s:
        assert s.query(models.Paper).filter_by(stem="will_rollback").count() == 0
    engine.dispose()


# ─── MutableDict on JSON ──────────────────────────────────────────────────

def test_payload_json_mutation_tracked(session_factory):
    """payload_json 用 MutableDict 包装，in-place 修改应被追踪。"""
    Session = session_factory
    with Session() as s:
        t = models.Task(type="analyze", payload_json={"k": 1})
        s.add(t); s.commit()
        tid = t.id
    with Session() as s:
        t = s.get(models.Task, tid)
        t.payload_json["k"] = 2
        t.payload_json["new"] = "v"
        s.commit()
    with Session() as s:
        t = s.get(models.Task, tid)
        assert t.payload_json == {"k": 2, "new": "v"}


def test_subscription_target_json(session_factory):
    Session = session_factory
    with Session() as s:
        s.add(models.Subscription(
            type="paper_citations",
            target_json={"doi": "10.1234/abc"},
            cron_expr="0 0 * * 1",
        ))
        s.commit()
    with Session() as s:
        loaded = s.query(models.Subscription).one()
        assert loaded.target_json == {"doi": "10.1234/abc"}
        assert loaded.active is True
