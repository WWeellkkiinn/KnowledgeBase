"""KnowledgeBase 数据库模块。

提供 SQLAlchemy engine / SessionLocal / Base，以及 session_scope 上下文。
DB 路径默认在项目根 `kb.db`，可通过环境变量 `KB_DB_PATH` 覆盖（便于测试）。

SQLite 默认不执行外键约束；本模块在每次 connect 上注册 `PRAGMA foreign_keys=ON`，
保证模型层声明的 ondelete=CASCADE/SET NULL 真正生效。
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "kb.db"


def _db_url() -> str:
    raw = os.environ.get("KB_DB_PATH")
    path = Path(raw).expanduser().resolve() if raw else DEFAULT_DB_PATH
    return f"sqlite:///{path.as_posix()}"


class Base(DeclarativeBase):
    pass


engine = create_engine(_db_url(), future=True, echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


def enable_sqlite_foreign_keys(target: Engine) -> None:
    """对 SQLite engine 注册 PRAGMA foreign_keys=ON。对其他方言无效。"""
    if target.dialect.name != "sqlite":
        return

    @event.listens_for(target, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


enable_sqlite_foreign_keys(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "session_scope",
    "DEFAULT_DB_PATH",
    "enable_sqlite_foreign_keys",
]
