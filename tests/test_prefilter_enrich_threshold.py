"""
`/run/enrich` and the keyword pre-filter must agree on what counts as a
description worth judging (#24).

If enrich only re-fetched jobs under 100 chars while the pre-filter declined to
judge anything under 400, a job holding a 150-char teaser would be neither
re-fetched nor scored — stuck permanently rather than "left for the next enrich
pass". These tests pin the two together.
"""

import db.session as db_session
import server
from db.models import Job, JobStatus

TEASER = "Senior Python Engineer wanted in Zürich. Great team, modern stack. " * 2
FULL_JD = (
    "We are looking for a Python engineer to work on our Docker based platform. "
    "You will own services end to end. " * 8
)


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


def test_enrich_retries_exactly_what_analyze_declined(client, monkeypatch):
    """
    Drive /run/enrich itself: it filters twice (the SQL query, then
    `to_enrich`), and either one left at the old bar strands the teaser.
    """
    import scrapers.jobs_ch

    job_id = _add(TEASER)
    fetched = []

    async def fake_fetch(self, source_job_id):
        fetched.append(source_job_id)
        return FULL_JD, ""

    monkeypatch.setattr(scrapers.jobs_ch.JobsChScraper, "fetch_full_description", fake_fetch)
    r = client.post("/run/enrich", json={"source": "jobs.ch", "limit": 99})
    assert r.status_code == 200

    assert len(fetched) == 1
    with db_session.get_session() as session:
        assert session.get(Job, job_id).description == FULL_JD


def test_analyze_still_scores_a_real_description(client):
    job_id = _add(FULL_JD, title="real-job")

    client.post("/run/analyze",
                json={"llm": False, "skip_scored": False, "limit": 999})

    with db_session.get_session() as session:
        job = session.get(Job, job_id)
        assert job.match_score is not None
        assert job.status != JobStatus.NEW
