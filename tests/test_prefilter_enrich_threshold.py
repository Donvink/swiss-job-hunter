"""
`/run/enrich` and the keyword pre-filter must agree on what counts as a
description worth judging (#24).

If enrich only re-fetched jobs under 100 chars while the pre-filter declined to
judge anything under 400, a job holding a 150-char teaser would be neither
re-fetched nor scored — stuck permanently rather than "left for the next enrich
pass". These tests pin the two together.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import analyzer.scorer as scorer
import db.session as db_session
import server
from config.settings import settings
from db.models import Base, Job, JobStatus

TEASER = "Senior Python Engineer wanted in Zürich. Great team, modern stack. " * 2
FULL_JD = (
    "We are looking for a Python engineer to work on our Docker based platform. "
    "You will own services end to end. " * 8
)


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

    async def _keywords(cv_text, direction=None, cv_path=None):
        return scorer._compile_dynamic([{"keyword": "python", "weight": 2.0}])
    monkeypatch.setattr(scorer, "load_cv_keywords", _keywords)

    yield TestClient(server.app)


def _add(description, status=JobStatus.NEW, title="teaser-job"):
    with db_session.get_session() as session:
        job = Job(
            title=title, company="ACME", location="Zürich",
            url=f"https://example.test/{title}", source="jobs.ch",
            description=description, status=status,
            dedup_hash=Job.make_dedup_hash(title, "acme", "zürich"),
        )
        session.add(job)
        session.flush()
        return job.id


def test_teaser_is_sane_test_data():
    """The teaser must sit in the gap the old thresholds left open."""
    assert 100 < len(TEASER) < server.MIN_JD_CHARS


def test_analyze_leaves_unenriched_jobs_alone(client):
    job_id = _add(TEASER)

    r = client.post("/run/analyze",
                    json={"llm": False, "skip_scored": False, "limit": 999})
    assert r.status_code == 200

    with db_session.get_session() as session:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.NEW, "a teaser was treated as a judgement"
        assert job.match_score is None


def test_enrich_selects_exactly_what_analyze_declined(client):
    """
    The same row the pre-filter skipped must be picked up by enrich's query,
    otherwise it is stuck in a gap between the two.
    """
    job_id = _add(TEASER)

    with db_session.get_session() as session:
        selected = (
            session.query(Job.id)
            .filter(Job.source == "jobs.ch")
            .filter(
                (Job.description == None) |  # noqa: E711
                (Job.description == "") |
                (func.length(Job.description) < server.MIN_JD_CHARS)
            )
            .all()
        )
    assert (job_id,) in selected


def test_analyze_still_scores_a_real_description(client):
    job_id = _add(FULL_JD, title="real-job")

    client.post("/run/analyze",
                json={"llm": False, "skip_scored": False, "limit": 999})

    with db_session.get_session() as session:
        job = session.get(Job, job_id)
        assert job.match_score is not None
        assert job.status != JobStatus.NEW
