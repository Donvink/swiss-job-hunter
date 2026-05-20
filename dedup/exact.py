"""
Exact deduplication — hash(title + company + location).
Fast, runs on every insert.
"""
from __future__ import annotations

import re
from typing import Optional

from db.models import Job
from db.session import get_session
from scrapers.base import ScrapedJob


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_exact_duplicate(title: str, company: str, location: str) -> bool:
    """Check if a job with this hash already exists in the DB."""
    h = Job.make_dedup_hash(
        _normalize(title), _normalize(company), _normalize(location)
    )
    with get_session() as session:
        return session.query(Job).filter(Job.dedup_hash == h).count() > 0


def get_or_create_job(scraped: ScrapedJob, direction: Optional[str] = None) -> tuple[Job, bool]:
    """
    Return (job, created).
    The returned Job is expunged from the session so it can be safely
    used after the session closes — no DetachedInstanceError.
    """
    h = Job.make_dedup_hash(
        _normalize(scraped.title),
        _normalize(scraped.company),
        _normalize(scraped.location),
    )

    with get_session() as session:
        existing = session.query(Job).filter(Job.dedup_hash == h).first()
        if existing:
            session.expunge(existing)   # detach cleanly before session closes
            return existing, False

        job = Job(
            dedup_hash=h,
            title=scraped.title,
            company=scraped.company,
            location=scraped.location,
            description=scraped.description,
            url=scraped.url,
            source=scraped.source,
            source_job_id=scraped.source_job_id,
            salary_raw=scraped.salary_raw,
            employment_type=scraped.employment_type,
            remote_ok=scraped.remote_ok,
            language_required=scraped.language_required,
            posted_at=scraped.posted_at,
            direction=direction,
        )
        session.add(job)
        session.flush()         # get DB-assigned id
        session.refresh(job)    # ensure all columns are loaded into memory
        session.expunge(job)    # detach cleanly before session closes
        return job, True
