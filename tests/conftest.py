"""
Shared fixtures.

`db.session` builds its engine at import time, so setting DATABASE_URL from a
test only works if that test module happens to be imported first. Rather than
depend on collection order — getting it wrong points the tests at the
developer's real database — `client` binds `db.session` to its own throwaway
SQLite file for each test.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import analyzer.scorer as scorer
import db.session as db_session
from config.settings import settings
from db.models import Base


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(
        db_session, "SessionLocal",
        sessionmaker(bind=engine, autoflush=False, autocommit=False),
    )

    cv = tmp_path / "cv.txt"
    cv.write_text("Senior Python engineer. Docker, Kubernetes, FastAPI.\n", encoding="utf-8")
    monkeypatch.setattr(settings, "cv_text_path", cv)
    # A DEFAULT_DIRECTION in the developer's .env would otherwise swap in their
    # real data/cv_<direction>.txt.
    monkeypatch.setattr(settings, "default_direction", "")

    # keyword scoring must not reach the network
    async def _keywords(cv_text, direction=None, cv_path=None):
        return scorer._compile_dynamic([
            {"keyword": "python", "weight": 2.0},
            {"keyword": "docker", "weight": 1.5},
        ])
    monkeypatch.setattr(scorer, "load_cv_keywords", _keywords)

    import server
    yield TestClient(server.app)
