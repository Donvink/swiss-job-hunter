"""
Database session factory and helpers.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings
from db.models import Base


def _get_engine() -> Engine:
    db_url = settings.database_url
    # Ensure data directory exists for SQLite
    if db_url.startswith("sqlite"):
        db_path = db_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
        echo=False,
    )

    # Enable WAL mode for better SQLite concurrency
    if "sqlite" in db_url:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _):  # type: ignore[misc]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# Columns added after a release. `create_all` creates missing *tables* only, and
# the project has no migration tool, so an existing database would otherwise be
# missing these and every query naming them would fail.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "jobs": [("archived_by_user", "BOOLEAN NOT NULL DEFAULT {false}")],
}


def _add_missing_columns() -> None:
    from sqlalchemy import inspect as sa_inspect, text
    inspector = sa_inspect(engine)
    tables = set(inspector.get_table_names())
    false_literal = "0" if engine.dialect.name == "sqlite" else "FALSE"
    for table, columns in _ADDED_COLUMNS.items():
        if table not in tables:
            continue  # create_all just made it, with the column already present
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in columns:
            if name in existing:
                continue
            with engine.begin() as conn:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {name} {ddl.format(false=false_literal)}"
                ))


def init_db() -> None:
    """Create all tables, then add any columns an older database is missing."""
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for database sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
