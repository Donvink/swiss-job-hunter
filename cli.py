"""
Swiss Job Hunter — CLI
Usage: sjh <command> [options]
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="sjh",
    help="🇨🇭 Swiss Job Hunter — search, deduplicate, analyze, apply.",
    rich_markup_mode="rich",
)
console = Console()


# ── search ────────────────────────────────────────────────────────────────────
@app.command()
def search(
    keyword: str = typer.Argument(..., help="Job title / keywords to search"),
    location: str = typer.Option("Zürich", "--location", "-l", help="City or region"),
    sources: Optional[List[str]] = typer.Option(
        None, "--source", "-s", help="Sources to scrape (default: all)"
    ),
    max_pages: int = typer.Option(5, "--pages", "-p", help="Max pages per source"),
    no_semantic: bool = typer.Option(False, "--no-semantic", help="Skip semantic dedup"),
) -> None:
    """Scrape job listings and store them (with dedup)."""
    asyncio.run(_search(keyword, location, sources, max_pages, not no_semantic))


async def _search(
    keyword: str,
    location: str,
    sources: Optional[List[str]],
    max_pages: int,
    semantic: bool,
) -> None:
    from scrapers import ALL_SOURCES, SCRAPER_REGISTRY
    from dedup.exact import get_or_create_job, is_exact_duplicate
    from dedup.semantic import SemanticDeduplicator
    from db import init_db
    from db.models import RawJob
    from db.session import get_session

    init_db()

    active_sources = sources or ALL_SOURCES
    console.print(f"\n[bold]Searching:[/bold] [cyan]{keyword}[/cyan] in [yellow]{location}[/yellow]")
    console.print(f"Sources: {', '.join(active_sources)}\n")

    sem_dedup: Optional[SemanticDeduplicator] = None
    if semantic:
        sem_dedup = SemanticDeduplicator()
        n = sem_dedup.load_from_db()
        console.print(f"[dim]Semantic dedup index: {n} jobs loaded[/dim]")

    total_new = 0
    failed: list[tuple[str, str]] = []

    for source_name in active_sources:
        scraper_cls = SCRAPER_REGISTRY.get(source_name)
        if not scraper_cls:
            console.print(f"[yellow]Unknown source: {source_name}[/yellow]")
            continue

        console.print(f"[bold]→ {source_name}[/bold]", end=" ")
        new_count = 0

        try:
            async with scraper_cls() as scraper:
                async for scraped in scraper.scrape(keyword, location, max_pages):
                    # Stage 1: exact dedup
                    if is_exact_duplicate(scraped.title, scraped.company, scraped.location):
                        continue

                    # Stage 2: semantic dedup
                    if sem_dedup:
                        text = f"{scraped.title} {scraped.company} {scraped.location}"
                        is_dup, sim = sem_dedup.is_duplicate(text)
                        if is_dup:
                            continue
                        sem_dedup.add(text)

                    # Insert
                    job, created = get_or_create_job(scraped)
                    if created:
                        # Also save raw record
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
                        new_count += 1
        except Exception as exc:
            # One broken source must not end the run, and it must not be
            # reported as +0 either — a dead board is not a quiet one.
            failed.append((source_name, str(exc)))
            partial = f" (kept {new_count} scraped before it failed)" if new_count else ""
            console.print(f"[red]failed{partial}[/red]: {exc}")
            total_new += new_count
            continue

        console.print(f"[green]+{new_count} new[/green]")
        total_new += new_count

    console.print(f"\n[bold]Total new jobs:[/bold] [green]{total_new}[/green]")
    if failed:
        console.print(f"[red]Failed sources ({len(failed)}/{len(active_sources)}):[/red]")
        for name, reason in failed:
            console.print(f"  [red]✗[/red] {name} — {reason}")


# ── enrich ───────────────────────────────────────────────────────────────────
@app.command()
def enrich(
    limit: int = typer.Option(50, "--limit", "-n", help="Max jobs to enrich"),
    source: str = typer.Option("jobs.ch", "--source", "-s", help="Source to enrich"),
) -> None:
    """Fetch full descriptions for jobs that only have preview text."""
    asyncio.run(_enrich(limit, source))


async def _enrich(limit: int, source: str) -> None:
    from db.models import Job, JobStatus
    from db.session import get_session

    with get_session() as session:
        # Find jobs with short descriptions (likely just preview)
        jobs = (
            session.query(Job)
            .filter(Job.source == source)
            .filter(Job.description.isnot(None))
            .order_by(Job.scraped_at.desc())
            .limit(limit)
            .all()
        )
        job_data = [(j.id, j.source_job_id, len(j.description or "")) for j in jobs]

    # Only enrich jobs with short descriptions (preview is typically < 300 chars)
    to_enrich = [(jid, sjid) for jid, sjid, dlen in job_data if dlen < 1500 and sjid]
    console.print(f"Enriching [cyan]{len(to_enrich)}[/cyan] jobs from {source}...")

    if source != "jobs.ch":
        console.print(
            f"[yellow]enrich only covers jobs.ch here — use the web UI "
            f"(/run/enrich) for {source}[/yellow]"
        )
        return

    from scrapers.jobs_ch import JobsChScraper

    updated = 0
    archived = 0
    async with JobsChScraper() as scraper:
        for job_id, source_job_id in to_enrich:
            # fetch_full_description returns (description, canonical_url),
            # () when the vacancy is gone, or None when the fetch failed.
            result = await scraper.fetch_full_description(source_job_id)
            if result == ():
                with get_session() as session:
                    job = session.get(Job, job_id)
                    if job:
                        job.status = JobStatus.ARCHIVED
                archived += 1
                console.print(f"  [dim]– job {job_id} — expired, archived[/dim]")
            elif result and len(result[0]) > 100:
                description, canonical = result
                with get_session() as session:
                    job = session.get(Job, job_id)
                    if job:
                        job.description = description
                        if canonical:
                            job.url = canonical
                updated += 1
                console.print(f"  [green]✓[/green] job {job_id} — {len(description)} chars")
            else:
                console.print(f"  [dim]– job {job_id} — no detail available[/dim]")

    summary = f"\n✓ Enriched [green]{updated}[/green] jobs"
    if archived:
        summary += f", archived [yellow]{archived}[/yellow] expired"
    console.print(summary)


# ── analyze ───────────────────────────────────────────────────────────────────
@app.command()
def analyze(
    limit: int = typer.Option(100, "--limit", "-n", help="Max jobs to analyze"),
    llm: bool = typer.Option(False, "--llm", help="Use LLM scoring (slower, more accurate)"),
    min_score: float = typer.Option(0.3, "--min-score", help="Min score to shortlist"),
    rescore: bool = typer.Option(False, "--rescore", help="Re-score all jobs regardless of status"),
    concurrency: int = typer.Option(10, "--concurrency", "-c", help="Parallel LLM workers"),
) -> None:
    """Score jobs against your CV and shortlist top matches."""
    asyncio.run(_analyze(limit, llm, min_score, rescore, concurrency))


async def _analyze(limit: int, use_llm: bool, min_score: float, rescore: bool, concurrency: int) -> None:
    import asyncio as _asyncio
    from analyzer.scorer import fast_score, llm_score, load_cv_text
    from db.models import Job, JobStatus
    from db.session import get_session

    try:
        cv_text = load_cv_text()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    with get_session() as session:
        q = session.query(Job.id, Job.title, Job.description, Job.status).filter(
            Job.description.isnot(None),
            Job.description != "",
        )
        if not rescore:
            q = q.filter(Job.status == JobStatus.NEW).limit(limit)
        rows = q.all()

    # rows: list of (id, title, description, status)
    if rescore:
        rows = [(jid, t, d, st) for jid, t, d, st in rows if len(d or "") >= 200]

    console.print(f"Analyzing [cyan]{len(rows)}[/cyan] jobs"
                  + (" (rescore all)" if rescore else "") + "...")
    shortlisted = 0
    completed = 0
    total = len(rows)

    if use_llm and rescore:
        sem = _asyncio.Semaphore(concurrency)

        async def score_one(jid: int, title: str, description: str, old_status) -> None:
            nonlocal shortlisted, completed
            async with sem:
                result = await llm_score(cv_text, title, description)
            with get_session() as session:
                j = session.get(Job, jid)
                if j:
                    j.match_score = result.score
                    j.match_explanation = result.explanation
                    # Preserve ARCHIVED/VIEWED; only promote NEW/ANALYZED
                    if j.status in (JobStatus.NEW, JobStatus.ANALYZED):
                        j.status = (
                            JobStatus.SHORTLISTED if result.score >= min_score else JobStatus.ANALYZED
                        )
                    if result.score >= min_score:
                        shortlisted += 1
            completed += 1
            if completed % 50 == 0 or completed == total:
                console.print(f"  {completed}/{total} done...")

        await _asyncio.gather(*[score_one(jid, t, d, st) for jid, t, d, st in rows])
    else:
        for jid, title, description, _ in rows:
            if use_llm:
                result = await llm_score(cv_text, title, description)
            else:
                result = fast_score(cv_text, description)

            with get_session() as session:
                j = session.get(Job, jid)
                if j:
                    j.match_score = result.score
                    j.match_explanation = result.explanation
                    j.status = (
                        JobStatus.SHORTLISTED if result.score >= min_score else JobStatus.ANALYZED
                    )
                    if result.score >= min_score:
                        shortlisted += 1

    console.print(f"✓ Done. [yellow]{shortlisted}[/yellow] jobs shortlisted (score ≥ {min_score:.0%})")


# ── top ───────────────────────────────────────────────────────────────────────
@app.command()
def top(
    limit: int = typer.Option(20, "--limit", "-n"),
    min_score: float = typer.Option(0.0, "--min-score"),
) -> None:
    """Show top matching jobs."""
    from analyzer.report import print_top_matches
    print_top_matches(limit=limit, min_score=min_score)


# ── digest ────────────────────────────────────────────────────────────────────
@app.command()
def digest() -> None:
    """Show daily job search summary."""
    from analyzer.report import daily_digest, pipeline_summary
    daily_digest()
    pipeline_summary()


# ── cover ─────────────────────────────────────────────────────────────────────
@app.command()
def cover(
    job_id: int = typer.Argument(..., help="Job ID to generate cover letter for"),
    language: str = typer.Option("en", "--lang", "-l", help="Language: en | de"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate a cover letter for a specific job."""
    asyncio.run(_cover(job_id, language, output))  # type: ignore[arg-type]


async def _cover(job_id: int, language: str, output: Optional[str]) -> None:
    from analyzer.scorer import load_cv_text
    from llm.cover_letter import generate_cover_letter, save_cover_letter
    from db.models import Job
    from db.session import get_session

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            console.print(f"[red]Job {job_id} not found[/red]")
            raise typer.Exit(1)

    cv_text = load_cv_text()
    console.print(f"Generating cover letter for: [bold]{job.title}[/bold] @ {job.company}...")

    letter = await generate_cover_letter(job, cv_text, language=language)  # type: ignore[arg-type]

    if output:
        from pathlib import Path
        Path(output).write_text(letter, encoding="utf-8")
        console.print(f"[green]Saved to {output}[/green]")
    else:
        console.print("\n" + "=" * 60)
        console.print(letter)
        console.print("=" * 60)


# ── status ────────────────────────────────────────────────────────────────────
@app.command()
def status(
    job_id: int = typer.Argument(..., help="Job ID"),
    new_status: str = typer.Argument(..., help="New status: applied | rejected | interviewing | offer"),
) -> None:
    """Update the status of a job in the pipeline."""
    from db.models import Job, JobStatus
    from db.session import get_session

    try:
        s = JobStatus(new_status)
    except ValueError:
        valid = [x.value for x in JobStatus]
        console.print(f"[red]Invalid status. Valid: {valid}[/red]")
        raise typer.Exit(1)

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            console.print(f"[red]Job {job_id} not found[/red]")
            raise typer.Exit(1)
        job.status = s
    console.print(f"[green]Job {job_id} → {new_status}[/green]")


if __name__ == "__main__":
    app()
