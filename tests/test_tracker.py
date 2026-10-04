"""
The tracker board shows decisions, not browsing.

`/tracker` feeds the Kanban columns, so what it returns defines what the board
can show and what a card can be dragged into.
"""
from datetime import datetime

import db.session as db_session
from db.models import Job, JobStatus

_WHEN = datetime(2026, 1, 1, 12, 0)  # fixed, avoids utcnow() deprecation noise


def _add(status, *, title, viewed=False, applied=False):
    with db_session.get_session() as session:
        job = Job(
            title=title, company="ACME", location="Zürich",
            url=f"https://example.test/{title}", source="jobs.ch",
            description="A real description, long enough to be a job ad. " * 10,
            status=status,
            viewed_at=_WHEN if viewed else None,
            applied_at=_WHEN if applied else None,
            dedup_hash=Job.make_dedup_hash(title, "acme", "zürich"),
        )
        session.add(job)
        session.flush()
        return job.id


def _tracker(client):
    r = client.get("/tracker")
    assert r.status_code == 200
    return {j["id"]: j["status"] for j in r.json()}


def test_viewed_jobs_are_not_on_the_board(client):
    """Opening a listing is not a decision, so it must not create a card."""
    job_id = _add(JobStatus.VIEWED, title="merely-viewed", viewed=True)
    assert job_id not in _tracker(client)


def test_decisions_are_on_the_board(client):
    ids = {
        status: _add(status, title=f"job-{status.value}")
        for status in (JobStatus.CONSIDERING, JobStatus.APPLIED,
                       JobStatus.INTERVIEWING, JobStatus.OFFER, JobStatus.REJECTED)
    }
    board = _tracker(client)
    for status, job_id in ids.items():
        assert board.get(job_id) == status.value


def test_handled_archived_jobs_are_on_the_board(client):
    """A dismissed card must still be visible, so it can be dragged back out."""
    seen = _add(JobStatus.ARCHIVED, title="archived-after-reading", viewed=True)
    sent = _add(JobStatus.ARCHIVED, title="archived-after-applying", applied=True)
    board = _tracker(client)
    assert board.get(seen) == "archived"
    assert board.get(sent) == "archived"


def test_untouched_archived_jobs_stay_off_the_board(client):
    """
    Most archived rows are pipeline rejects that were never opened — 829 against
    5 on a real database. Listing those would bury the column.
    """
    job_id = _add(JobStatus.ARCHIVED, title="auto-archived")
    assert job_id not in _tracker(client)


def test_dropping_a_card_updates_the_job(client):
    """What the drag handler does: PATCH the status, and the board reflects it."""
    job_id = _add(JobStatus.CONSIDERING, title="to-be-applied")

    r = client.patch(f"/jobs/{job_id}/status", json={"status": "applied"})
    assert r.status_code == 200

    assert _tracker(client)[job_id] == "applied"


def test_a_card_can_be_dropped_into_archived(client):
    job_id = _add(JobStatus.CONSIDERING, title="to-be-dismissed", viewed=True)

    r = client.patch(f"/jobs/{job_id}/status", json={"status": "archived"})
    assert r.status_code == 200

    # still listed, because it was handled — the card stays draggable
    assert _tracker(client)[job_id] == "archived"


def test_a_card_without_timestamps_survives_being_archived(client):
    """
    A job can reach CONSIDERING without ever being opened in the UI — set through
    the API, or by an earlier version. Dropping it into ARCHIVED must not make it
    vanish from the board, or it cannot be dragged back out.
    """
    job_id = _add(JobStatus.CONSIDERING, title="no-timestamps")
    assert job_id in _tracker(client)

    r = client.patch(f"/jobs/{job_id}/status", json={"status": "archived"})
    assert r.status_code == 200

    assert _tracker(client)[job_id] == "archived", (
        "a dropped card disappeared and can no longer be dragged back"
    )


def test_pipeline_archived_jobs_are_not_flagged(client):
    """The flag must only be set by a person, or the column fills with rejects."""
    job_id = _add(JobStatus.ARCHIVED, title="auto-archived-no-flag")
    assert job_id not in _tracker(client)

    with db_session.get_session() as session:
        assert session.get(Job, job_id).archived_by_user is False


def test_leaving_archived_clears_the_user_flag(client):
    """Otherwise a later pipeline re-archive would look like a user decision."""
    job_id = _add(JobStatus.CONSIDERING, title="archive-then-restore")
    client.patch(f"/jobs/{job_id}/status", json={"status": "archived"})
    client.patch(f"/jobs/{job_id}/status", json={"status": "considering"})

    with db_session.get_session() as session:
        assert session.get(Job, job_id).archived_by_user is False


def test_dropping_into_applied_sets_applied_at(client):
    job_id = _add(JobStatus.CONSIDERING, title="dragged-to-applied")
    client.patch(f"/jobs/{job_id}/status", json={"status": "applied"})

    with db_session.get_session() as session:
        assert session.get(Job, job_id).applied_at is not None


def test_dropping_into_applied_keeps_an_existing_applied_at(client):
    job_id = _add(JobStatus.CONSIDERING, title="already-applied", applied=True)
    client.patch(f"/jobs/{job_id}/status", json={"status": "applied"})

    with db_session.get_session() as session:
        assert session.get(Job, job_id).applied_at == _WHEN
