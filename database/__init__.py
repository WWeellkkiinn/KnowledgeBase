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
    # 优先 KB_DB_URL（任意方言）；否则回退 KB_DB_PATH（SQLite 路径）
    url = os.environ.get("KB_DB_URL")
    if url:
        return url
    raw = os.environ.get("KB_DB_PATH")
    path = Path(raw).expanduser().resolve() if raw else DEFAULT_DB_PATH
    return f"sqlite:///{path.as_posix()}"


class Base(DeclarativeBase):
    pass


_DB_URL = _db_url()
# connect_args 仅 SQLite 接受 timeout；PG/MySQL 会报 TypeError
_is_sqlite = _DB_URL.startswith("sqlite")
_engine_kwargs: dict = {"future": True, "echo": False}
if _is_sqlite:
    # 连接级超时：等锁最多 30s，避免公网请求和 APScheduler 并发时立刻报错
    _engine_kwargs["connect_args"] = {"timeout": 30}

engine = create_engine(_DB_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


def enable_sqlite_foreign_keys(target: Engine) -> None:
    """对 SQLite engine 注册 PRAGMA：FK + busy_timeout（每连接）。
    WAL 是数据库级持久设置，用独立 sqlite3 连接一次性完成 —— 不经过 SQLAlchemy
    连接池，避免该连接被归还池后跳过 connect 监听器（导致 FK/busy_timeout 未生效）。
    其他方言无效。
    """
    if target.dialect.name != "sqlite":
        return

    # 一次性设置 WAL（数据库级持久），用独立 sqlite3 连接，不污染 SQLAlchemy 池
    try:
        db_path = target.url.database
        # 仅对落盘 SQLite 文件设置；":memory:" / 空路径跳过
        if db_path and db_path != ":memory:":
            import sqlite3
            _raw = sqlite3.connect(db_path, timeout=30)
            try:
                _raw.execute("PRAGMA journal_mode=WAL")
                _raw.commit()
            finally:
                _raw.close()
    except Exception:
        # WAL 设置失败不致命（如只读 / 内存库），继续按默认 journal 模式工作
        pass

    @event.listens_for(target, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # 任何 SQL 遇锁等待 30s 再报错（毫秒）。连接级，必须每次设
        cursor.execute("PRAGMA busy_timeout=30000")
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
