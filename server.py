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
from pathlib import Path
from typing import AsyncGenerator, Optional

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func

from config.settings import settings

app = FastAPI(title="Swiss Job Hunter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    from db.seed import seed_resume_versions_from_flat_files
    from db.session import init_db
    init_db()
    seed_resume_versions_from_flat_files()


@app.get("/directions")
def get_directions():
    import glob
    from config.settings import settings
    pattern = str(settings.cv_text_path.parent / "cv_*.txt")
    dirs = sorted(
        Path(p).stem[3:]  # strip leading "cv_"
        for p in glob.glob(pattern)
    )
    return dirs


@app.get("/config")
def get_config():
    from config.settings import Settings
    s = Settings()
    return {
        "default_keyword": s.default_keyword,
        "default_location": s.default_location,
        "keyword_presets": s.keyword_presets,
    }


@app.get("/presets")
def get_presets():
    """Return keyword presets configured via KEYWORD_PRESETS in .env."""
    from config.settings import Settings
    return Settings().keyword_presets

# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_jobs_query(status: str = "all", q: str = "", direction: str = "all", min_stars: int = 0):
    from db.session import get_session
    from db.models import Job
    from sqlalchemy import or_

    with get_session() as session:
        query = session.query(Job)
        if status != "all":
            query = query.filter(Job.status == status)
        if direction != "all":
            query = query.filter(Job.direction == direction)
        if q:
            query = query.filter(
                or_(
                    Job.title.ilike(f"%{q}%"),
                    Job.company.ilike(f"%{q}%"),
                    Job.location.ilike(f"%{q}%"),
                )
            )
        if min_stars:
            query = query.filter(Job.user_stars >= min_stars)
        jobs = query.order_by(Job.user_stars.desc().nullslast(), Job.match_score.desc().nullslast(), Job.scraped_at.desc()).all()
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
                "user_stars": j.user_stars,
                "direction": j.direction,
                "posted_at": j.posted_at.isoformat() if j.posted_at else None,
                "scraped_at": j.scraped_at.isoformat() if j.scraped_at else None,
            }
            for j in jobs
        ]


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/jobs")
def list_jobs(status: str = "all", q: str = "", direction: str = "all", min_stars: int = 0):
    from db.session import init_db
    init_db()
    return get_jobs_query(status, q, direction, min_stars)


@app.get("/stats")
def get_stats(threshold: float = 0.1):
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
        above_threshold = session.query(func.count(Job.id)).filter(
            Job.match_score >= threshold
        ).scalar() or 0

    return {
        "total": total,
        "by_status": by_status,
        "by_source": by_source,
        "avg_score": float(avg_score) if avg_score else None,
        "top_score": float(top_score) if top_score else None,
        "above_threshold": above_threshold,
        "threshold": threshold,
    }


@app.delete("/jobs/{job_id}")
def delete_job(job_id: int):
    from db.session import get_session
    from db.models import Job, RawJob, Application, JobEvent
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        session.query(JobEvent).filter(JobEvent.job_id == job_id).delete()
        session.query(Application).filter(Application.job_id == job_id).delete()
        session.query(RawJob).filter(RawJob.canonical_id == job_id).delete()
        session.delete(job)
    return {"ok": True}


@app.patch("/jobs/{job_id}/stars")
def update_stars(job_id: int, body: dict):
    from db.session import get_session
    from db.models import Job
    stars = body.get("stars")
    if stars is not None and stars not in (0, 1, 2, 3, 4, 5):
        raise HTTPException(400, "stars must be 0-5 (0 = clear)")
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        job.user_stars = None if stars == 0 else stars
    return {"ok": True}


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
            yield f"data: ✗ Internal error: {str(e)[:400]}\n\n"
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
    keywords: list[str] = []  # if non-empty, overrides keyword; each is searched in turn
    location: str = "Zürich"
    sources: list[str] = ["jobs.ch"]
    pages: int = 3
    semantic: bool = False
    direction: Optional[str] = None
    linkedin_time_range: str = "r604800"  # r86400=24h | r604800=7d | r2592000=30d
    linkedin_experience_level: str = "3,4"  # 2=Entry,3=Associate,4=Senior,5=Director


@app.post("/run/search")
async def run_search(req: SearchRequest):
    async def gen():
        from scrapers import SCRAPER_REGISTRY
        from dedup.exact import get_or_create_job, is_exact_duplicate
        from db import init_db
        from db.models import RawJob
        from db.session import get_session
        init_db()

        kw_list = req.keywords if req.keywords else [req.keyword]
        if not req.sources:
            yield "✗ No sources selected"
            return
        total_new = 0
        linkedin_in_sources = "linkedin.com" in req.sources

        async def scrape_source(kw: str, source_name: str, queue: asyncio.Queue) -> int:
            scraper_cls = SCRAPER_REGISTRY.get(source_name)
            if not scraper_cls:
                await queue.put(f"✗ Unknown source: {source_name}")
                return 0
            await queue.put(f"→ {source_name}")
            new_count = 0
            found_count = 0
            try:
                kwargs = {}
                if source_name == "linkedin.com":
                    kwargs["time_range"] = req.linkedin_time_range
                    kwargs["experience_level"] = req.linkedin_experience_level
                async with scraper_cls(**kwargs) as scraper:
                    async for scraped in scraper.scrape(kw, req.location, req.pages):
                        found_count += 1
                        if found_count % 10 == 0:
                            await queue.put(f"  ↳ {source_name}: {found_count} fetched so far...")
                        try:
                            if is_exact_duplicate(scraped.title, scraped.company, scraped.location):
                                continue
                            job, created = get_or_create_job(scraped, direction=req.direction or None)
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
                                await queue.put(f"  + [{source_name}] {scraped.title[:50]} @ {scraped.company}")
                        except Exception as e:
                            await queue.put(f"  ✗ skipped one job: {str(e)[:80]}")
                            continue
            except Exception as e:
                partial = f", saved {new_count} before failure" if new_count else ""
                await queue.put(f"✗ {source_name} failed{partial}: {str(e)[:120]}")
                return new_count
            if found_count == 0:
                await queue.put(f"✓ {source_name}: +0 new jobs (scraper returned 0 results)")
            elif new_count == 0:
                await queue.put(f"✓ {source_name}: +0 new jobs ({found_count} found, all duplicates)")
            else:
                await queue.put(f"✓ {source_name}: +{new_count} new jobs")
            return new_count

        for kw_idx, kw in enumerate(kw_list):
            if kw_idx > 0 and linkedin_in_sources:
                yield f"⏳ LinkedIn cooldown 5s..."
                await asyncio.sleep(5)
            yield f"─── keyword: {kw} · {req.location or 'Switzerland (all)'}"

            queue: asyncio.Queue = asyncio.Queue()
            n_sources = len(req.sources)
            done_count = [0]

            async def _wrap(src: str) -> int:
                try:
                    return await scrape_source(kw, src, queue)
                finally:
                    done_count[0] += 1
                    if done_count[0] == n_sources:
                        await queue.put(None)

            tasks = [asyncio.create_task(_wrap(src)) for src in req.sources]
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                yield msg
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total_new += sum(r for r in results if isinstance(r, int))

        yield f"✓ Done — {total_new} total new jobs"
    return await sse(gen())


class EnrichRequest(BaseModel):
    limit: int = 50
    source: str = "jobs.ch"
    rescore_llm: bool = False
    direction: Optional[str] = None
    concurrency: int = 3


@app.post("/run/enrich")
async def run_enrich(req: EnrichRequest):
    async def gen():
        from db.models import Job
        from db.session import get_session
        with get_session() as session:
            jobs = (
                session.query(Job)
                .filter(Job.source == req.source)
                .filter(
                    (Job.description == None) |  # noqa: E711
                    (Job.description == "") |
                    (func.length(Job.description) < 100)
                )
                .order_by(Job.scraped_at.desc())
                .limit(req.limit)
                .all()
            )
            import re as _re
            job_data = []
            for j in jobs:
                dlen = len(j.description or "")
                # Resolve the identifier to pass to fetch_full_description:
                # - UUID source_job_id → pass as-is (jobs.ch style)
                # - URL source_job_id → pass as-is (züri.jobs new records)
                # - purely numeric source_job_id → substitute j.url (züri.jobs old,
                #   efinancialcareers, linkedin store numeric IDs that need the full URL)
                # - slug source_job_id → pass as-is (swissdevjobs)
                # - no source_job_id → extract UUID from URL, else use URL
                sjid = j.source_job_id
                _uuid_re = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                if sjid and sjid.isdigit() and j.url:
                    sjid = j.url
                elif not sjid and j.url:
                    m = _re.search(r'/detail/([a-f0-9-]{36})', j.url)
                    sjid = m.group(1) if m else j.url
                if sjid:
                    job_data.append((j.id, sjid, dlen))

        to_enrich = [(jid, sjid) for jid, sjid, dlen in job_data if dlen < 100]
        yield f"Enriching {len(to_enrich)} jobs from {req.source}..."
        if not to_enrich:
            yield f"✓ Enriched 0/0 jobs"
            return

        # Generic enrich — works for any scraper that implements fetch_full_description
        scraper_map = {
            "jobs.ch": "scrapers.jobs_ch.JobsChScraper",
            "jobscout24.ch": "scrapers.jobscout24.JobScout24Scraper",
            "swissdevjobs.ch": "scrapers.swissdevjobs.SwissDevJobsScraper",
            "züri.jobs": "scrapers.zuri_jobs.ZuriJobsScraper",
            "efinancialcareers.ch": "scrapers.efinancialcareers.EFinancialCareersScraper",
            "jobup.ch": "scrapers.jobup_ch.JobupChScraper",
            "linkedin.com": "scrapers.linkedin_rss.LinkedInRssScraper",
            "michael-page.ch": "scrapers.michael_page.MichaelPageScraper",
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
        enriched_ids = []
        total_enrich = len(to_enrich)
        enrich_done = [0]
        queue: asyncio.Queue = asyncio.Queue()
        sem = asyncio.Semaphore(req.concurrency)

        async def enrich_one(job_id: int, source_job_id: str, scraper) -> None:
            nonlocal updated
            async with sem:
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
                        enriched_ids.append(job_id)
                        await queue.put(f"✓ job #{job_id} — {len(desc)} chars")
                    elif result == ():
                        with get_session() as session:
                            job = session.get(Job, job_id)
                            if job:
                                from db.models import JobStatus
                                job.status = JobStatus.ARCHIVED
                        await queue.put(f"– job #{job_id} — expired, auto-archived")
                    else:
                        await queue.put(f"– job #{job_id} — no detail available")
                except Exception as e:
                    await queue.put(f"✗ job #{job_id} error: {str(e)[:80]}")
                finally:
                    enrich_done[0] += 1
                    if enrich_done[0] == total_enrich:
                        await queue.put(None)

        try:
            async with scraper_cls() as scraper:
                tasks = [
                    asyncio.create_task(enrich_one(jid, sjid, scraper))
                    for jid, sjid in to_enrich
                ]
                while True:
                    msg = await queue.get()
                    if msg is None:
                        break
                    yield msg
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            yield f"✗ Enrich failed: {str(e)[:120]}"
        yield f"✓ Enriched {updated}/{len(to_enrich)} jobs"

        if req.rescore_llm and enriched_ids:
            from analyzer.scorer import llm_score, load_cv_text
            from db.models import JobStatus
            yield f"→ LLM scoring {len(enriched_ids)} newly enriched jobs..."
            try:
                cv_text = load_cv_text(direction=req.direction or None)
            except FileNotFoundError as e:
                yield f"✗ CV not found: {e}"
                return
            scored = 0
            for job_id in enriched_ids:
                try:
                    with get_session() as session:
                        job = session.get(Job, job_id)
                        if not job:
                            continue
                        if job.match_score is not None:
                            continue  # already scored, skip
                        title, desc = job.title, job.description or ""
                    result = await llm_score(cv_text, title, desc)
                    with get_session() as session:
                        job = session.get(Job, job_id)
                        if job:
                            job.match_score = result.score
                            if result.score < 0.1:
                                job.status = JobStatus.ARCHIVED
                            elif result.score >= 0.6:
                                job.status = JobStatus.SHORTLISTED
                    scored += 1
                    yield f"  🧠 job #{job_id} — {round(result.score * 100)}%"
                except Exception as e:
                    yield f"  ✗ job #{job_id} score error: {str(e)[:80]}"
            yield f"✓ LLM scored {scored}/{len(enriched_ids)} jobs"
    return await sse(gen())


class AnalyzeRequest(BaseModel):
    limit: int = 100
    llm: bool = False
    min_score: float = 0.3
    skip_scored: bool = True
    archive_below: float = 0.1  # auto-archive jobs scoring below this (LLM mode only)
    min_keyword_score: float = 0.10  # skip LLM if keyword pre-filter score < this
    direction: Optional[str] = None
    concurrency: int = 10


@app.post("/run/analyze")
async def run_analyze(req: AnalyzeRequest):
    async def gen():
        import asyncio
        from asyncio import Queue
        from analyzer.scorer import fast_score, llm_score, load_cv_text, load_cv_keywords
        from db.models import Job, JobStatus
        from db.session import get_session

        try:
            cv_text = load_cv_text(direction=req.direction or None)
        except FileNotFoundError as e:
            yield f"✗ {e}"
            return

        with get_session() as session:
            statuses = list(JobStatus)  # all statuses when rescoring
            if req.skip_scored:
                statuses = [JobStatus.NEW, JobStatus.ANALYZED, JobStatus.SHORTLISTED, JobStatus.VIEWED, JobStatus.CONSIDERING]
            query = session.query(Job).filter(Job.status.in_(statuses))
            if req.direction:
                query = query.filter(Job.direction == req.direction)
            if req.skip_scored:
                query = query.filter(Job.match_score.is_(None))
            lim = req.limit if req.skip_scored else 9999
            jobs = query.order_by(Job.scraped_at.desc()).limit(lim).all()
            job_data = [(j.id, j.title, j.description) for j in jobs]

        threshold = req.min_score if not req.llm else min(req.min_score, 0.2)
        yield f"Analyzing {len(job_data)} jobs (mode: {'LLM' if req.llm else 'keyword'}, concurrency: {req.concurrency if req.llm else 1})..."
        if not job_data:
            yield "✓ Nothing to score"
            return
        shortlisted = 0

        if req.llm:
            # Load dynamic CV keywords once for pre-filter (cached per CV file)
            yield f"→ Loading CV keywords for pre-filter..."
            cv_keywords = await load_cv_keywords(cv_text, direction=req.direction or None)
            yield f"→ Loaded {len(cv_keywords)} keywords, pre-filter threshold: {req.min_keyword_score:.0%}"

            queue: Queue = Queue()
            sem = asyncio.Semaphore(req.concurrency)
            completed = 0
            skipped = 0
            total = len(job_data)

            async def score_one(job_id: int, title: str, description: str) -> None:
                nonlocal shortlisted, completed, skipped
                async with sem:
                    try:
                        # Keyword pre-filter: skip LLM if clearly irrelevant
                        kw_result = fast_score(cv_text, description or "", compiled=cv_keywords)
                        if kw_result.score < req.min_keyword_score:
                            with get_session() as session:
                                job = session.get(Job, job_id)
                                if job:
                                    job.match_score = kw_result.score
                                    job.match_explanation = f"[keyword pre-filter] {kw_result.explanation}"
                                    job.status = JobStatus.ARCHIVED
                            skipped += 1
                            await queue.put(f"– #{job_id} {kw_result.score:.0%} (skipped) — {title[:45]}")
                        else:
                            result = await llm_score(cv_text, title, description or "")
                            with get_session() as session:
                                job = session.get(Job, job_id)
                                if job:
                                    job.match_score = result.score
                                    job.match_explanation = result.explanation
                                    if result.score >= threshold:
                                        job.status = JobStatus.SHORTLISTED
                                        shortlisted += 1
                                    elif result.score < req.archive_below:
                                        job.status = JobStatus.ARCHIVED
                                    else:
                                        job.status = JobStatus.ANALYZED
                            score_pct = f"{result.score:.0%}"
                            icon = "⭐" if result.score >= req.min_score else ("✗" if result.score < req.archive_below else "·")
                            await queue.put(f"{icon} #{job_id} {score_pct} — {title[:45]}")
                    except Exception as e:
                        await queue.put(f"✗ #{job_id} error: {e}")
                    finally:
                        completed += 1
                        if completed == total:
                            await queue.put(None)  # sentinel

            tasks = [asyncio.create_task(score_one(jid, t, d)) for jid, t, d in job_data]
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                yield msg
            await asyncio.gather(*tasks)
            yield f"→ Pre-filter skipped {skipped}/{total} jobs (saved ~{skipped} LLM calls)"
        else:
            for job_id, title, description in job_data:
                try:
                    result = fast_score(cv_text, description or "")
                    with get_session() as session:
                        job = session.get(Job, job_id)
                        if job:
                            job.match_score = result.score
                            job.match_explanation = result.explanation
                            job.status = JobStatus.SHORTLISTED if result.score >= threshold else JobStatus.ANALYZED
                            if result.score >= threshold:
                                shortlisted += 1
                    score_pct = f"{result.score:.0%}"
                    icon = "⭐" if result.score >= req.min_score else "·"
                    yield f"{icon} #{job_id} {score_pct} — {title[:45]}"
                except Exception as e:
                    yield f"✗ #{job_id} error: {e}"

        yield f"✓ Done — {shortlisted}/{len(job_data)} shortlisted"
    return await sse(gen())


class PurgeRequest(BaseModel):
    max_score: float = 0.1
    dry_run: bool = True


class CheckLinksRequest(BaseModel):
    statuses: list[str] = ["new", "analyzed", "shortlisted", "viewed", "considering"]
    concurrency: int = 10
    auto_archive: bool = True
    timeout: float = 8.0
    min_score: Optional[float] = None


@app.post("/run/check-links")
async def run_check_links(req: CheckLinksRequest):
    async def gen():
        import random as _random
        import httpx as _httpx
        from db.models import Job, JobStatus
        from db.session import get_session

        _safe_statuses = {JobStatus.APPLIED, JobStatus.INTERVIEWING, JobStatus.OFFER, JobStatus.REJECTED}
        _ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        with get_session() as session:
            valid_statuses = []
            for s in req.statuses:
                try:
                    valid_statuses.append(JobStatus(s))
                except ValueError:
                    pass
            q = (
                session.query(Job.id, Job.url, Job.title, Job.company)
                .filter(Job.status.in_(valid_statuses))
                .filter(Job.url.isnot(None))
                .filter(Job.url != "")
            )
            if req.min_score is not None:
                q = q.filter(Job.match_score >= req.min_score)
            job_data = [(j.id, j.url, j.title, j.company) for j in q.order_by(Job.scraped_at.desc()).all()]

        total = len(job_data)
        if not total:
            yield "✓ No jobs to check"
            return
        yield f"Checking {total} URLs (concurrency={req.concurrency}, auto_archive={'on' if req.auto_archive else 'off'})..."

        dead = 0
        unreachable = 0
        done_count = [0]
        queue: asyncio.Queue = asyncio.Queue()
        sem = asyncio.Semaphore(req.concurrency)          # global cap
        domain_sems: dict[str, asyncio.Semaphore] = {}   # per-domain cap (max 2)

        def _get_domain_sem(url: str) -> asyncio.Semaphore:
            from urllib.parse import urlparse
            host = urlparse(url).netloc
            if host not in domain_sems:
                domain_sems[host] = asyncio.Semaphore(2)
            return domain_sems[host]

        async def check_one(job_id: int, url: str, title: str, company: str, client: _httpx.AsyncClient) -> None:
            nonlocal dead, unreachable
            async with sem:
                async with _get_domain_sem(url):
                    await asyncio.sleep(_random.uniform(0.5, 1.5))
                    try:
                        try:
                            resp = await client.head(url)
                            if resp.status_code == 405:
                                resp = await client.get(url)
                        except (_httpx.TimeoutException, _httpx.ConnectError, _httpx.RemoteProtocolError):
                            resp = await client.get(url)
                        if resp.status_code in (404, 410):
                            dead += 1
                            if req.auto_archive:
                                with get_session() as session:
                                    job = session.get(Job, job_id)
                                    if job and job.status not in _safe_statuses:
                                        job.status = JobStatus.ARCHIVED
                            await queue.put(f"✗ #{job_id} {resp.status_code} — {title[:50]} @ {company[:25]}")
                    except (_httpx.TimeoutException, _httpx.ConnectError, _httpx.RemoteProtocolError,
                            _httpx.TooManyRedirects):
                        unreachable += 1
                    except Exception as e:
                        unreachable += 1
                        await queue.put(f"! #{job_id} error: {str(e)[:70]}")
                    finally:
                        done_count[0] += 1
                        n = done_count[0]
                        if n % 100 == 0 or n == total:
                            await queue.put(f"  [{n}/{total}] checked — {dead} dead so far")
                        if n == total:
                            await queue.put(None)

        async with _httpx.AsyncClient(
            timeout=req.timeout,
            follow_redirects=True,
            headers={"User-Agent": _ua},
        ) as client:
            tasks = [
                asyncio.create_task(check_one(jid, url, title, company, client))
                for jid, url, title, company in job_data
            ]
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                yield msg
            await asyncio.gather(*tasks, return_exceptions=True)

        action = "auto-archived" if req.auto_archive else "dead (not archived)"
        alive = total - dead - unreachable
        yield f"✓ Done — {alive} alive · {dead} {action} · {unreachable} unreachable/timeout"
    return await sse(gen())


@app.post("/run/purge-archived")
async def run_purge_archived(req: PurgeRequest):
    async def gen():
        from db.models import Job, JobStatus, RawJob, Application, JobEvent
        from db.session import get_session

        # Include NEW/ANALYZED/ARCHIVED — all statuses the user hasn't manually acted on
        _purgeable = [JobStatus.NEW, JobStatus.ANALYZED, JobStatus.ARCHIVED]

        with get_session() as session:
            jobs = (
                session.query(Job)
                .filter(
                    Job.status.in_(_purgeable),
                    Job.match_score.isnot(None),
                    Job.match_score < req.max_score,
                )
                .order_by(Job.match_score.asc())
                .all()
            )
            job_data = [(j.id, j.title, j.match_score, j.status.value) for j in jobs]

        mode = "DRY RUN" if req.dry_run else "DELETE"
        yield f"[{mode}] {len(job_data)} jobs (new/analyzed/archived) with score < {req.max_score:.0%}"

        deleted = 0
        for job_id, title, score, status in job_data:
            if req.dry_run:
                yield f"· #{job_id} {score:.0%} [{status}] — {title[:50]}"
                continue
            try:
                with get_session() as session:
                    session.query(JobEvent).filter(JobEvent.job_id == job_id).delete()
                    session.query(Application).filter(Application.job_id == job_id).delete()
                    session.query(RawJob).filter(RawJob.canonical_id == job_id).delete()
                    job = session.get(Job, job_id)
                    if job:
                        session.delete(job)
                deleted += 1
                yield f"✗ #{job_id} {score:.0%} [{status}] — {title[:50]}"
            except Exception as e:
                yield f"! #{job_id} error: {e}"

        if req.dry_run:
            yield "— preview only, nothing deleted —"
        else:
            yield f"✓ Deleted {deleted}/{len(job_data)} jobs"
    return await sse(gen())


_COMPANY_PROMPT = """\
You are a research assistant helping a job seeker evaluate companies in Switzerland.
Given a company name, provide a concise 3–5 sentence overview covering:
- Industry and core business
- Company size and Swiss/global presence
- Reputation, work culture, or tech stack (if known)
If the company is obscure or you are not confident about details, say so honestly — do not fabricate facts.
Reply in English. No bullet points, plain prose only."""


def _normalize_company(name: str) -> str:
    return name.strip()


async def _fetch_company_summary(name: str) -> str:
    from llm.router import call_llm
    text, _ = await call_llm(
        system=_COMPANY_PROMPT,
        user=f"Company: {name}",
        max_tokens=300,
    )
    return text


@app.get("/companies/{name}")
async def get_company(name: str):
    from db.session import get_session, init_db
    from db.models import CompanyInfo
    init_db()
    with get_session() as session:
        row = session.query(CompanyInfo).filter(CompanyInfo.name == _normalize_company(name)).first()
        if row:
            return {"name": row.name, "summary": row.summary, "fetched_at": row.fetched_at.isoformat()}
    return {"name": name, "summary": None}


@app.post("/companies/lookup")
async def lookup_company(body: dict):
    from db.session import get_session, init_db
    from db.models import CompanyInfo
    init_db()
    name = _normalize_company(body.get("name", ""))
    if not name:
        raise HTTPException(400, "name required")

    with get_session() as session:
        row = session.query(CompanyInfo).filter(CompanyInfo.name == name).first()
        if row and row.summary:
            return {"name": row.name, "summary": row.summary, "cached": True}

    summary = await _fetch_company_summary(name)

    with get_session() as session:
        row = session.query(CompanyInfo).filter(CompanyInfo.name == name).first()
        if row:
            row.summary = summary
            row.fetched_at = datetime.utcnow()
        else:
            session.add(CompanyInfo(name=name, summary=summary))

    return {"name": name, "summary": summary, "cached": False}


class CompanyLookupRequest(BaseModel):
    min_score: float = 0.0


@app.post("/run/company-lookup")
async def run_company_lookup(req: CompanyLookupRequest = CompanyLookupRequest()):
    async def gen():
        from db.session import get_session, init_db
        from db.models import Job, CompanyInfo
        init_db()

        with get_session() as session:
            q = session.query(Job.company).distinct()
            if req.min_score > 0:
                q = q.filter(Job.match_score >= req.min_score)
            all_companies = {row[0] for row in q.all() if row[0]}
            cached = {
                row[0] for row in session.query(CompanyInfo.name).all()
            }

        todo = sorted(all_companies - cached)
        yield f"Found {len(all_companies)} unique companies, {len(todo)} not yet looked up"

        done = 0
        for name in todo:
            try:
                summary = await _fetch_company_summary(name)
                with get_session() as session:
                    existing = session.query(CompanyInfo).filter(CompanyInfo.name == name).first()
                    if existing:
                        existing.summary = summary
                        existing.fetched_at = datetime.utcnow()
                    else:
                        session.add(CompanyInfo(name=name, summary=summary))
                done += 1
                yield f"✓ {name[:50]}"
            except Exception as e:
                yield f"✗ {name[:50]}: {str(e)[:60]}"

        yield f"✓ Done — {done}/{len(todo)} companies looked up"
    return await sse(gen())


class TranslateRequest(BaseModel):
    job_id: int
    target: str = "en"  # "en" or "zh"


@app.post("/run/translate")
async def run_translate(req: TranslateRequest):
    from db.models import Job
    from db.session import get_session
    from llm.router import call_llm

    with get_session() as session:
        job = session.get(Job, req.job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        description = job.description or ""

    if not description:
        raise HTTPException(400, "No description to translate")

    target_name = "English" if req.target == "en" else "Simplified Chinese (中文)"
    system = (
        f"You are a professional translator. Translate the following job description to {target_name}. "
        "Output only the translated text, preserving the structure and formatting. Do not add any preamble."
    )
    text, _ = await call_llm(user=description, system=system, max_tokens=3000)
    return {"translated": text}


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


class TailorCVRequest(BaseModel):
    job_id: int
    direction: Optional[str] = None


@app.post("/run/tailor-cv")
async def run_tailor_cv(req: TailorCVRequest):
    from analyzer.scorer import load_cv_text
    from llm.cv_tailor import tailor_cv
    from db.models import Job
    from db.session import get_session

    with get_session() as session:
        job = session.get(Job, req.job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        direction = req.direction or job.direction or None
        session.expunge(job)

    cv_text = load_cv_text(direction=direction)
    result = await tailor_cv(job, cv_text)
    return result


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
    subject = f"Application: {job.title} — {settings.apply_from_name or settings.smtp_user}"

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
        JobStatus.VIEWED, JobStatus.CONSIDERING, JobStatus.APPLIED,
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
