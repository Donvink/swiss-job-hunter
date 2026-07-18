"""Tests for load_cv_text()'s DB-first, flat-file-fallback ordering."""
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, FileFormat, ResumeVersion


@pytest.fixture
def db_session_factory(tmp_path, monkeypatch):
    """Point analyzer.scorer.get_session at an isolated temp SQLite DB and
    pin the default flat-file path so ambient .env overrides don't leak in."""
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    @contextmanager
    def fake_get_session():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("analyzer.scorer.get_session", fake_get_session)
    monkeypatch.setattr("analyzer.scorer.settings.cv_text_path", tmp_path / "data" / "cv.txt")
    return SessionLocal


def _add_active_version(SessionLocal, direction, text):
    session = SessionLocal()
    session.add(
        ResumeVersion(
            direction=direction,
            label="v1",
            original_filename="cv.txt",
            file_path="data/resumes/cv.txt",
            file_format=FileFormat.TXT,
            extracted_text=text,
            is_active=True,
        )
    )
    session.commit()
    session.close()


def test_prefers_active_resume_version_over_flat_file(db_session_factory, monkeypatch, tmp_path):
    from analyzer.scorer import load_cv_text

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cv_backend.txt").write_text("stale flat-file CV", encoding="utf-8")
    _add_active_version(db_session_factory, "backend", "DB-backed CV text")

    assert load_cv_text("backend") == "DB-backed CV text"


def test_falls_back_to_direction_flat_file_when_no_db_row(db_session_factory, monkeypatch, tmp_path):
    from analyzer.scorer import load_cv_text

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cv_backend.txt").write_text("direction flat-file CV", encoding="utf-8")

    assert load_cv_text("backend") == "direction flat-file CV"


def test_falls_back_to_default_flat_file_when_direction_file_missing(db_session_factory, monkeypatch, tmp_path):
    from analyzer.scorer import load_cv_text

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cv.txt").write_text("default flat-file CV", encoding="utf-8")

    assert load_cv_text("backend") == "default flat-file CV"


def test_no_direction_uses_default_flat_file(db_session_factory, monkeypatch, tmp_path):
    from analyzer.scorer import load_cv_text

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cv.txt").write_text("direction-less CV", encoding="utf-8")

    assert load_cv_text(None) == "direction-less CV"


def test_raises_when_nothing_found(db_session_factory, monkeypatch, tmp_path):
    from analyzer.scorer import load_cv_text

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    with pytest.raises(FileNotFoundError):
        load_cv_text("backend")
