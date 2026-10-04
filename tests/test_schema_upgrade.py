"""
`init_db()` must bring an older database up to date.

`Base.metadata.create_all()` creates missing *tables* but never adds a column to
an existing one, and the project has no migration tool. Without the additive step
in `init_db`, upgrading would leave every query naming a new column failing with
"no such column" on any database created before it.
"""
import importlib
import sqlite3

import db.session as db_session
from config.settings import settings


def _columns(path):
    with sqlite3.connect(path) as con:
        return {row[1] for row in con.execute("PRAGMA table_info(jobs)")}


def _make_pre_flag_db(path):
    """A jobs table as it looked before `archived_by_user` existed."""
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE jobs (
              id INTEGER PRIMARY KEY,
              dedup_hash TEXT, title TEXT, company TEXT, location TEXT,
              description TEXT, url TEXT, source TEXT, status TEXT,
              match_score REAL, viewed_at TIMESTAMP, applied_at TIMESTAMP,
              scraped_at TIMESTAMP, updated_at TIMESTAMP
            );
            INSERT INTO jobs (id, title, company, status)
            VALUES (1, 'existing job', 'ACME', 'considering');
            """
        )


def test_init_db_adds_missing_columns(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    _make_pre_flag_db(db_path)
    assert "archived_by_user" not in _columns(db_path)

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    importlib.reload(db_session)
    db_session.init_db()

    assert "archived_by_user" in _columns(db_path)


def test_init_db_preserves_existing_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    _make_pre_flag_db(db_path)

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    importlib.reload(db_session)
    db_session.init_db()

    with sqlite3.connect(db_path) as con:
        title, flag = con.execute(
            "SELECT title, archived_by_user FROM jobs WHERE id = 1"
        ).fetchone()
    assert title == "existing job"
    assert flag == 0, "existing rows must default to not-user-archived"


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "old.db"
    _make_pre_flag_db(db_path)

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    importlib.reload(db_session)
    db_session.init_db()
    db_session.init_db()          # must not raise "duplicate column name"

    assert "archived_by_user" in _columns(db_path)


def teardown_module():
    # other modules reload this too, but leave it bound to the real settings
    importlib.reload(db_session)
