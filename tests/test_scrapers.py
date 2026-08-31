"""Tests for scrapers — uses mocked HTTP responses."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

_UUID_A = "550e8400-e29b-41d4-a716-446655440000"
_UUID_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


def _jobs_ch_page(*ids: str) -> str:
    """
    Build a jobs.ch search page the way the real one is shaped: one JSON-LD
    ItemList plus one result card per hit, joined on the vacancy UUID.

    The JSON-LD deliberately leaves out the city for the first hit and carries
    the site's generated stub description — both are real behaviours the parser
    has to cover.
    """
    postings = []
    cards = []
    for n, uuid in enumerate(ids):
        title = f"Senior ML Engineer {n}"
        address = {"@type": "PostalAddress", "addressCountry": "CH"}
        if n:  # only some hits carry a locality in the JSON-LD
            address["addressLocality"] = "Bern"
        postings.append({
            "@type": "ListItem",
            "position": n + 1,
            "item": {
                "@type": "JobPosting",
                "title": title,
                "description": f"We are looking for a {title} to join our team.",
                "identifier": {"@type": "PropertyValue", "name": "jobs.ch", "value": uuid},
                "datePosted": "2026-01-15T08:00:00+01:00",
                "employmentType": "Permanent position",
                "hiringOrganization": {"@type": "Organization", "name": "Acme AG"},
                "jobLocation": {"@type": "Place", "address": address},
                "url": f"https://www.jobs.ch/en/vacancies/detail/{uuid}/",
            },
        })
        cards.append(
            f'<div data-cy="serp-item">'
            f'<a data-cy="job-link" href="/en/vacancies/detail/{uuid}/">{title}</a>'
            f"<div><span><svg></svg></span><span>Place of work:</span><p>Zurich</p></div>"
            f"<div><span><svg></svg></span><span>Workload:</span><p>80 – 100%</p></div>"
            f"<div><span><svg></svg></span><span>Contract type:</span>"
            f"<p>Permanent position</p></div>"
            f"</div>"
        )
    ld = json.dumps([
        {"@type": "WebSite", "name": "jobs.ch"},
        {"@type": "ItemList", "numberOfItems": len(ids), "itemListElement": postings},
    ])
    return (
        f'<html><head><script type="application/ld+json">{ld}</script></head>'
        f"<body>{''.join(cards)}</body></html>"
    )


@pytest.mark.asyncio
async def test_jobs_ch_scraper_parse():
    from scrapers.jobs_ch import JobsChScraper

    jobs = JobsChScraper()._parse_search_page(_jobs_ch_page(_UUID_A))
    assert len(jobs) == 1
    job = jobs[0]

    assert job.title == "Senior ML Engineer 0"
    assert job.company == "Acme AG"
    assert job.source_job_id == _UUID_A
    assert job.url == f"https://www.jobs.ch/en/vacancies/detail/{_UUID_A}/"
    # The card supplies the city the JSON-LD omitted, and "Zurich" is normalized.
    assert job.location == "Zürich"
    # Workload is stored the way the old API's employment_grades were rendered.
    assert job.employment_type == "80–100%"
    assert job.posted_at is not None and job.posted_at.year == 2026
    # The generated stub is dropped so `enrich` fetches the real text instead.
    assert job.description == ""


@pytest.mark.asyncio
async def test_jobs_ch_falls_back_to_json_ld_locality_without_a_card():
    from scrapers.jobs_ch import JobsChScraper

    html = _jobs_ch_page(_UUID_A, _UUID_B)
    # Strip the second hit's card, keeping its JSON-LD entry.
    second_card = (
        f'<div data-cy="serp-item"><a data-cy="job-link" '
        f'href="/en/vacancies/detail/{_UUID_B}/">Senior ML Engineer 1</a>'
    )
    html = html.replace(second_card, "<div>", 1)

    jobs = JobsChScraper()._parse_search_page(html)
    assert [j.location for j in jobs] == ["Zürich", "Bern"]


@pytest.mark.asyncio
async def test_jobs_ch_missing_itemlist_is_an_error_not_an_empty_result():
    """A page without the ItemList means the markup moved — never "0 jobs"."""
    from scrapers.jobs_ch import JobsChScraper

    with pytest.raises(ValueError):
        JobsChScraper()._parse_search_page("<html><body>redesigned</body></html>")


@pytest.mark.asyncio
async def test_jobs_ch_stops_when_the_site_wraps_back_to_page_one():
    """
    Past the last page jobs.ch silently re-serves page 1 with HTTP 200, so the
    scraper must stop on repeated ids instead of looping to max_pages.
    """
    from scrapers.jobs_ch import _PAGE_SIZE, JobsChScraper

    scraper = JobsChScraper()
    # A *full* page, so the short-page check cannot end the run early — only
    # noticing that every id repeats can.
    ids = [f"550e8400-e29b-41d4-a716-4466554400{n:02d}" for n in range(_PAGE_SIZE)]
    page = _jobs_ch_page(*ids)
    calls = []

    async def fake_fetch(url, **kwargs):
        calls.append(url)
        return MagicMock(text=page, status_code=200)

    scraper._fetch = fake_fetch  # type: ignore[assignment]
    jobs = [j async for j in scraper.scrape("ml", "Zürich", max_pages=10)]

    assert [j.source_job_id for j in jobs] == ids  # each vacancy exactly once
    assert len(calls) == 2  # page 2 came back as page 1, so we stopped there


@pytest.mark.asyncio
async def test_jobs_ch_detail_404_reports_an_expired_vacancy():
    from scrapers.jobs_ch import JobsChScraper

    scraper = JobsChScraper()

    async def fake_fetch(url, **kwargs):
        assert kwargs.get("allow_status") == {404, 410}
        return MagicMock(status_code=410, text="")

    scraper._fetch = fake_fetch  # type: ignore[assignment]
    assert await scraper.fetch_full_description(_UUID_A) == ()


@pytest.mark.asyncio
async def test_jobup_ch_scraper_parse():
    from scrapers.jobup_ch import JobupChScraper

    doc = {
        "id": "99",
        "title": "Data Scientist",
        "company": {"name": "Swiss Bank"},
        "place": {"name": "Genève"},
        "teaser": "Exciting data science role",
        "slug": "data-scientist-swiss-bank",
        "publication_date": "2025-02-01T09:00:00Z",
    }

    scraper = JobupChScraper()
    job = scraper._parse(doc)

    assert job is not None
    assert job.title == "Data Scientist"
    assert job.company == "Swiss Bank"
    assert job.source == "jobup.ch"


# ── source-level failure reporting ────────────────────────────────────────────


def _scraper():
    from scrapers.base import BaseScraper, ScrapedJob

    class _Dummy(BaseScraper):
        source_name = "dummy.ch"

        async def scrape(self, keyword, location, max_pages):  # pragma: no cover
            yield ScrapedJob("t", "c", "l", "d", "u", self.source_name)

    return _Dummy()


def test_page_error_raises_when_the_source_produced_nothing():
    """Zero jobs plus an error is a broken source, not an empty search."""
    from scrapers.base import ScraperError

    with pytest.raises(ScraperError, match="dummy.ch"):
        _scraper()._page_error(page=1, exc=RuntimeError("410 Gone"), yielded=0)


def test_page_error_only_logs_once_some_jobs_are_through(capsys):
    """A later page failing is a truncated run — keep what we have."""
    _scraper()._page_error(page=4, exc=RuntimeError("timeout"), yielded=60)
    assert "after 60 jobs" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_fetch_does_not_retry_a_permanent_status():
    """410 will never recover; retrying it just burns polite-delay seconds."""
    from scrapers.base import PermanentHTTPError

    scraper = _scraper()
    calls = []

    async def fake_get(url, **kwargs):
        calls.append(url)
        return MagicMock(status_code=410)

    scraper._get_client = AsyncMock(return_value=MagicMock(get=fake_get))
    scraper._polite_delay = AsyncMock()

    with pytest.raises(PermanentHTTPError) as excinfo:
        await scraper._fetch("https://example.ch/gone")
    assert excinfo.value.status_code == 410
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_fetch_hands_back_statuses_the_caller_asked_for():
    """allow_status lets a detail fetch tell 'vacancy gone' from 'fetch broke'."""
    scraper = _scraper()

    async def fake_get(url, **kwargs):
        return MagicMock(status_code=404)

    scraper._get_client = AsyncMock(return_value=MagicMock(get=fake_get))
    scraper._polite_delay = AsyncMock()

    resp = await scraper._fetch("https://example.ch/x", allow_status={404, 410})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fetch_still_retries_a_transient_status():
    import httpx

    scraper = _scraper()
    calls = []

    async def fake_get(url, **kwargs):
        calls.append(url)
        resp = MagicMock(status_code=503)
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=resp
        )
        return resp

    scraper._get_client = AsyncMock(return_value=MagicMock(get=fake_get))
    scraper._polite_delay = AsyncMock()

    with pytest.raises(httpx.HTTPStatusError):
        await scraper._fetch("https://example.ch/flaky")
    assert len(calls) == 3
