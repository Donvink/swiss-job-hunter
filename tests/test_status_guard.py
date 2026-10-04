"""
A rescore must never move a job out of a status the user put it in (#22).

`db.session` builds its engine at import time, so setting DATABASE_URL from a
test only works if this module happens to be imported first. Rather than depend
on collection order — getting it wrong points the tests at the developer's real
database — each test binds `db.session` to its own throwaway SQLite file.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import analyzer.scorer as scorer
import db.session as db_session
from config.settings import settings
from db.models import (
    Base,
    Job,
    JobStatus,
    PIPELINE_OWNED_STATUSES,
    USER_OWNED_STATUSES,
)


# ── the sets themselves ───────────────────────────────────────────────────────

def test_status_sets_do_not_overlap():
    assert not (USER_OWNED_STATUSES & PIPELINE_OWNED_STATUSES)


def test_every_decision_status_is_user_owned():
    for status in (JobStatus.CONSIDERING, JobStatus.APPLIED,
                   JobStatus.INTERVIEWING, JobStatus.OFFER, JobStatus.REJECTED):
        assert status in USER_OWNED_STATUSES


def test_viewed_and_archived_belong_to_neither():
    # VIEWED is not a decision; ARCHIVED should not be resurrected by a rescore
    # or by opening a listing.
    for status in (JobStatus.VIEWED, JobStatus.ARCHIVED):
        assert status not in USER_OWNED_STATUSES
        assert status not in PIPELINE_OWNED_STATUSES


# ── the behaviour the sets exist to protect ───────────────────────────────────

JD = (
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

    # keyword scoring must not reach the network
    async def _keywords(cv_text, direction=None, cv_path=None):
        return scorer._compile_dynamic([
            {"keyword": "python", "weight": 2.0},
            {"keyword": "docker", "weight": 1.5},
        ])
    monkeypatch.setattr(scorer, "load_cv_keywords", _keywords)

    import server
    yield TestClient(server.app)


def _add(status, *, score=None, title=None):
    title = title or f"job-{status.value}"
    with db_session.get_session() as session:
        job = Job(
            title=title,
            company="ACME",
            location="Zürich",
            url=f"https://example.test/{title}",
            source="jobs.ch",
            description=JD,
            status=status,
            match_score=score,
            dedup_hash=Job.make_dedup_hash(title, "acme", "zürich"),
        )
        session.add(job)
        session.flush()
        return job.id


def _rescore(client):
    r = client.post("/run/analyze",
                    json={"llm": False, "skip_scored": False, "limit": 999})
    assert r.status_code == 200
    return r


def test_rescore_does_not_move_user_owned_jobs(client):
    """The regression behind #22: RESCORE ALL emptied the tracker."""
    ids = {status: _add(status, score=0.9) for status in USER_OWNED_STATUSES}

    _rescore(client)

    with db_session.get_session() as session:
        for status, job_id in ids.items():
            assert session.get(Job, job_id).status == status, (
                f"{status.value} was overwritten by a rescore"
            )


def test_rescore_still_refreshes_score_and_explanation(client):
    """Protecting the status must not mean skipping the row entirely."""
    job_id = _add(JobStatus.APPLIED, score=0.01)
    with db_session.get_session() as session:
        before = session.get(Job, job_id).match_explanation

    _rescore(client)

    with db_session.get_session() as session:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.APPLIED
        assert job.match_score != 0.01
        assert job.match_explanation != before


def test_rescore_still_moves_pipeline_owned_jobs(client):
    """The guard must not freeze the statuses the pipeline is meant to manage."""
    job_id = _add(JobStatus.NEW)

    _rescore(client)

    with db_session.get_session() as session:
        assert session.get(Job, job_id).status != JobStatus.NEW
