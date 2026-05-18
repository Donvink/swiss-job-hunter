"""
UI backend server — FastAPI + SSE streaming.
Run: python server.py
Then open: http://localhost:5173 (after `npm run dev` in ui/)
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
from datetime import datetime
from typing import AsyncGenerator, Optional

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func

app = FastAPI(title="Swiss Job Hunter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_jobs_query(status: str = "all", q: str = ""):
    from db.session import get_session
    from db.models import Job
    from sqlalchemy import or_

    with get_session() as session:
        query = session.query(Job)
        if status != "all":
            query = query.filter(Job.status == status)
        if q:
            query = query.filter(
                or_(
                    Job.title.ilike(f"%{q}%"),
                    Job.company.ilike(f"%{q}%"),
                    Job.location.ilike(f"%{q}%"),
                )
            )
        jobs = query.order_by(Job.match_score.desc().nullslast(), Job.scraped_at.desc()).all()
        return [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "description": j.description,
                "url": j.url,
                "source": j.source,
                "source_job_id": j.source_job_id,
                "salary_raw": j.salary_raw,
                "employment_type": j.employment_type,
                "status": j.status,
                "match_score": j.match_score,
                "match_explanation": j.match_explanation,
                "posted_at": j.posted_at.isoformat() if j.posted_at else None,
                "scraped_at": j.scraped_at.isoformat() if j.scraped_at else None,
            }
            for j in jobs
        ]


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/jobs")
def list_jobs(status: str = "all", q: str = ""):
    from db.session import init_db
    init_db()
    return get_jobs_query(status, q)


@app.get("/stats")
def get_stats():
    from db.session import get_session, init_db
    from db.models import Job
    init_db()
    with get_session() as session:
        total = session.query(func.count(Job.id)).scalar() or 0
        by_status = dict(
            session.query(Job.status, func.count(Job.id)).group_by(Job.status).all()
        )
        by_source = dict(
            session.query(Job.source, func.count(Job.id)).group_by(Job.source).all()
        )
        avg_score = session.query(func.avg(Job.match_score)).filter(
            Job.match_score.isnot(None)
        ).scalar()
        top_score = session.query(func.max(Job.match_score)).scalar()

    return {
        "total": total,
        "by_status": by_status,
        "by_source": by_source,
        "avg_score": float(avg_score) if avg_score else None,
        "top_score": float(top_score) if top_score else None,
    }


@app.patch("/jobs/{job_id}/status")
def update_status(job_id: int, body: dict):
    from db.session import get_session
    from db.models import Job, JobStatus
    new_status = body.get("status")
    try:
        s = JobStatus(new_status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {new_status}")
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.status = s
    return {"ok": True}


# ── SSE streaming commands ─────────────────────────────────────────────────────

async def sse(gen: AsyncGenerator[str, None]) -> StreamingResponse:
    async def wrapper():
        try:
            async for line in gen:
                safe = line.replace("\n", " ")
                yield f"data: {safe}\n\n"
        except Exception as e:
            yield f"data: ✗ Internal error: {str(e)[:200]}\n\n"
        finally:
            yield "data: [DONE]\n\n"
    return StreamingResponse(
        wrapper(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


class SearchRequest(BaseModel):
    keyword: str = "ML engineer"
    location: str = "Zürich"
    sources: list[str] = ["jobs.ch"]
    pages: int = 3
    semantic: bool = False


@app.post("/run/search")
async def run_search(req: SearchRequest):
    async def gen():
        from scrapers import SCRAPER_REGISTRY
        from dedup.exact import get_or_create_job, is_exact_duplicate
        from db import init_db
        from db.models import RawJob
        from db.session import get_session
        init_db()

        yield f"Searching: {req.keyword} in {req.location}"
        total_new = 0

        for source_name in req.sources:
            scraper_cls = SCRAPER_REGISTRY.get(source_name)
            if not scraper_cls:
                yield f"✗ Unknown source: {source_name}"
                continue

            yield f"→ {source_name}"
            new_count = 0

            found_count = 0
            try:
                async with scraper_cls() as scraper:
                    async for scraped in scraper.scrape(req.keyword, req.location, req.pages):
                        found_count += 1
                        try:
                            if is_exact_duplicate(scraped.title, scraped.company, scraped.location):
                                continue
                            job, created = get_or_create_job(scraped)
                            if created:
                                try:
                                    with get_session() as session:
                                        raw = RawJob(
                                            canonical_id=job.id,
                                            source=scraped.source,
                                            source_job_id=scraped.source_job_id,
                                            url=scraped.url,
                                            raw_html=scraped.raw_html,
                                            raw_json=scraped.raw_json,
                                        )
                                        session.add(raw)
                                except Exception:
                                    pass
                                new_count += 1
                                yield f"  + [{source_name}] {scraped.title[:50]} @ {scraped.company}"
                        except Exception as e:
                            yield f"  ✗ skipped one job: {str(e)[:80]}"
                            continue
            except Exception as e:
                yield f"✗ {source_name} failed: {str(e)[:120]}"
                continue

            if found_count == 0:
                yield f"✓ {source_name}: +0 new jobs (scraper returned 0 results)"
            elif new_count == 0:
                yield f"✓ {source_name}: +0 new jobs ({found_count} found, all duplicates)"
            else:
                yield f"✓ {source_name}: +{new_count} new jobs"
            total_new += new_count

        yield f"✓ Done — {total_new} total new jobs"
    return await sse(gen())


class EnrichRequest(BaseModel):
    limit: int = 50
    source: str = "jobs.ch"


@app.post("/run/enrich")
async def run_enrich(req: EnrichRequest):
    async def gen():
        from db.models import Job
        from db.session import get_session
        with get_session() as session:
            jobs = (
                session.query(Job)
                .filter(Job.source == req.source)
                .order_by(Job.scraped_at.desc())
                .limit(req.limit)
                .all()
            )
            import re as _re
            job_data = []
            for j in jobs:
                dlen = len(j.description or "")
                # Use source_job_id directly, or extract UUID from URL as fallback
                sjid = j.source_job_id
                if not sjid and j.url:
                    m = _re.search(r'/detail/([a-f0-9-]{36})', j.url)
                    if m:
                        sjid = m.group(1)
                if sjid:
                    job_data.append((j.id, sjid, dlen))

        to_enrich = [(jid, sjid) for jid, sjid, dlen in job_data if dlen < 1500]
        yield f"Enriching {len(to_enrich)} jobs from {req.source}..."

        # Generic enrich — works for any scraper that implements fetch_full_description
        scraper_map = {
            "jobs.ch": "scrapers.jobs_ch.JobsChScraper",
            "swissdevjobs.ch": "scrapers.swissdevjobs.SwissDevJobsScraper",
        }

        scraper_path = scraper_map.get(req.source)
        if not scraper_path:
            yield f"– Enrich not yet implemented for {req.source}"
            return

        module_path, cls_name = scraper_path.rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        scraper_cls = getattr(module, cls_name)

        updated = 0
        try:
            async with scraper_cls() as scraper:
                for job_id, source_job_id in to_enrich:
                    try:
                        result = await scraper.fetch_full_description(source_job_id)
                        if result and len(result) == 2 and len(result[0]) > 100:
                            desc, canonical_url = result
                            with get_session() as session:
                                job = session.get(Job, job_id)
                                if job:
                                    job.description = desc
                                    if canonical_url:
                                        job.url = canonical_url
                            updated += 1
                            yield f"✓ job #{job_id} — {len(desc)} chars"
                        elif result == ():
                            with get_session() as session:
                                job = session.get(Job, job_id)
                                if job:
                                    from db.models import JobStatus
                                    job.status = JobStatus.ARCHIVED
                            yield f"– job #{job_id} — expired, auto-archived"
                        else:
                            yield f"– job #{job_id} — no detail available"
                    except Exception as e:
                        yield f"✗ job #{job_id} error: {str(e)[:80]}"
        except Exception as e:
            yield f"✗ Enrich failed: {str(e)[:120]}"
        yield f"✓ Enriched {updated}/{len(to_enrich)} jobs"
    return await sse(gen())


class AnalyzeRequest(BaseModel):
    limit: int = 100
    llm: bool = False
    min_score: float = 0.3


@app.post("/run/analyze")
async def run_analyze(req: AnalyzeRequest):
    async def gen():
        from analyzer.scorer import fast_score, llm_score, load_cv_text
        from db.models import Job, JobStatus
        from db.session import get_session

        try:
            cv_text = load_cv_text()
        except FileNotFoundError as e:
            yield f"✗ {e}"
            return

        with get_session() as session:
            jobs = (
                session.query(Job)
                .filter(Job.status.in_([JobStatus.NEW, JobStatus.ANALYZED, JobStatus.SHORTLISTED, JobStatus.VIEWED]))
                .limit(req.limit)
                .all()
            )
            job_data = [(j.id, j.title, j.description) for j in jobs]

        # LLM scoring is more conservative — use lower threshold
        threshold = req.min_score if not req.llm else min(req.min_score, 0.2)
        yield f"Analyzing {len(job_data)} jobs (mode: {'LLM' if req.llm else 'keyword'})..."
        shortlisted = 0

        for job_id, title, description in job_data:
            try:
                if req.llm:
                    result = await llm_score(cv_text, title, description or "")
                else:
                    result = fast_score(cv_text, description or "")

                with get_session() as session:
                    job = session.get(Job, job_id)
                    if job:
                        job.match_score = result.score
                        job.match_explanation = result.explanation
                        job.status = (
                            JobStatus.SHORTLISTED
                            if result.score >= threshold
                            else JobStatus.ANALYZED
                        )
                        if result.score >= threshold:
                            shortlisted += 1

                score_pct = f"{result.score:.0%}"
                icon = "⭐" if result.score >= req.min_score else "·"
                yield f"{icon} #{job_id} {score_pct} — {title[:45]}"

            except Exception as e:
                yield f"✗ #{job_id} error: {e}"

        yield f"✓ Done — {shortlisted}/{len(job_data)} shortlisted"
    return await sse(gen())


class CoverRequest(BaseModel):
    job_id: int
    language: str = "en"


@app.post("/run/cover")
async def run_cover(req: CoverRequest):
    from analyzer.scorer import load_cv_text
    from llm.cover_letter import generate_cover_letter
    from db.models import Job
    from db.session import get_session

    with get_session() as session:
        job = session.get(Job, req.job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        # Detach
        session.expunge(job)

    cv_text = load_cv_text()
    letter = await generate_cover_letter(job, cv_text, language=req.language)
    return {"letter": letter}


class ApplyEmailRequest(BaseModel):
    job_id: int
    cover_letter: str
    dry_run: bool = True
    recipient_email: Optional[str] = None


@app.post("/run/apply/email")
async def run_apply_email(req: ApplyEmailRequest):
    from applicator.email_apply import send_application
    from db.models import Job
    from db.session import get_session

    with get_session() as session:
        job = session.get(Job, req.job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        session.expunge(job)

    recipient = req.recipient_email or ""
    subject = f"Application: {job.title} — Leo Zhong"

    if req.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "recipient": recipient or "(no email — add manually)",
            "subject": subject,
        }

    if not recipient:
        raise HTTPException(400, "recipient_email required for real send")

    ok = await send_application(
        job=job,
        cover_letter=req.cover_letter,
        recipient_email=recipient,
        dry_run=False,
    )
    return {"ok": ok}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8765, reload=True)


# ── Progress tracking endpoints ────────────────────────────────────────────────

@app.post("/jobs/{job_id}/view")
def mark_viewed(job_id: int):
    """Auto-called when user opens a job. Sets status=viewed and logs the event."""
    from db.session import get_session
    from db.models import Job, JobStatus, JobEvent, ApplicationEvent
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        # Only upgrade status, never downgrade (don't overwrite applied/interview etc.)
        upgradeable = {JobStatus.NEW, JobStatus.ANALYZED, JobStatus.SHORTLISTED}
        if job.status in upgradeable:
            job.status = JobStatus.VIEWED
            job.viewed_at = datetime.utcnow()
            session.add(JobEvent(
                job_id=job_id,
                event_type=ApplicationEvent.VIEWED,
                note="Opened in UI",
            ))
    return {"ok": True}


@app.post("/jobs/{job_id}/apply")
def mark_applied(job_id: int, body: dict):
    """
    Mark a job as applied. Records method, contact, note on the Application record
    and adds an APPLIED event to the timeline.
    """
    from db.session import get_session
    from db.models import Job, JobStatus, Application, ApplicationStatus, JobEvent, ApplicationEvent
    method = body.get("method", "manual")          # email | form | manual | linkedin
    recipient = body.get("recipient_email", "")
    contact = body.get("contact_name", "")
    cover = body.get("cover_letter", "")
    note = body.get("note", "")

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.status = JobStatus.APPLIED
        job.applied_at = datetime.utcnow()

        # Upsert application record
        app_rec = session.query(Application).filter(Application.job_id == job_id).first()
        if not app_rec:
            app_rec = Application(job_id=job_id)
            session.add(app_rec)
        app_rec.apply_method = method
        app_rec.recipient_email = recipient
        app_rec.contact_name = contact
        app_rec.cover_letter = cover or app_rec.cover_letter
        app_rec.status = ApplicationStatus.SENT
        app_rec.applied_at = datetime.utcnow()
        app_rec.notes = note

        session.add(JobEvent(
            job_id=job_id,
            event_type=ApplicationEvent.APPLIED,
            note=f"via {method}" + (f" → {recipient}" if recipient else ""),
        ))
    return {"ok": True}


@app.post("/jobs/{job_id}/events")
def add_event(job_id: int, body: dict, response: Response):
    """Add any timeline event (interview, offer, rejection, note...)."""
    from db.session import get_session
    from db.models import Job, JobStatus, JobEvent, ApplicationEvent
    event_type = body.get("event_type")
    note = body.get("note", "")
    occurred_at_str = body.get("occurred_at")  # optional ISO string

    try:
        ev = ApplicationEvent(event_type)
    except ValueError:
        raise HTTPException(400, f"Invalid event_type: {event_type}")

    occurred_at = datetime.utcnow()
    if occurred_at_str:
        try:
            occurred_at = datetime.fromisoformat(occurred_at_str)
        except ValueError:
            pass

    # Auto-update job status for key events
    STATUS_MAP = {
        ApplicationEvent.INTERVIEW_1:     JobStatus.INTERVIEWING,
        ApplicationEvent.INTERVIEW_2:     JobStatus.INTERVIEWING,
        ApplicationEvent.TECHNICAL:       JobStatus.INTERVIEWING,
        ApplicationEvent.OFFER_RECEIVED:  JobStatus.OFFER,
        ApplicationEvent.OFFER_ACCEPTED:  JobStatus.OFFER,
        ApplicationEvent.REJECTED:        JobStatus.REJECTED,
    }

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if ev in STATUS_MAP:
            job.status = STATUS_MAP[ev]
        session.add(JobEvent(
            job_id=job_id,
            event_type=ev,
            note=note,
            occurred_at=occurred_at,
        ))
    response.headers["Access-Control-Allow-Origin"] = "*"
    return {"ok": True}


@app.get("/jobs/{job_id}/events")
def get_events(job_id: int):
    """Return the full timeline for a job."""
    from db.session import get_session
    from db.models import JobEvent
    with get_session() as session:
        events = session.query(JobEvent).filter(
            JobEvent.job_id == job_id
        ).order_by(JobEvent.occurred_at).all()
        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "occurred_at": e.occurred_at.isoformat(),
                "note": e.note,
            }
            for e in events
        ]


@app.get("/tracker")
def get_tracker():
    """
    Return all jobs that have been interacted with (viewed or beyond),
    sorted by last activity, for the tracker board.
    """
    from db.session import get_session
    from db.models import Job, JobStatus, Application
    active_statuses = [
        JobStatus.VIEWED, JobStatus.APPLIED,
        JobStatus.INTERVIEWING, JobStatus.OFFER,
        JobStatus.REJECTED,
    ]
    with get_session() as session:
        jobs = (
            session.query(Job)
            .filter(Job.status.in_(active_statuses))
            .order_by(Job.updated_at.desc())
            .all()
        )
        result = []
        for j in jobs:
            app = session.query(Application).filter(Application.job_id == j.id).first()
            result.append({
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "url": j.url,
                "source": j.source,
                "status": j.status,
                "match_score": j.match_score,
                "viewed_at": j.viewed_at.isoformat() if j.viewed_at else None,
                "applied_at": j.applied_at.isoformat() if j.applied_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
                "apply_method": app.apply_method if app else None,
                "recipient_email": app.recipient_email if app else None,
                "contact_name": app.contact_name if app else None,
                "notes": app.notes if app else None,
            })
    return result
