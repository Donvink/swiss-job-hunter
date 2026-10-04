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
async def test_jobup_ch_searches_its_own_page_and_reads_its_cards():
    """
    jobup.ch reuses the jobs.ch parser. Its search API ignored the query (#26),
    and its cards link to /jobs/detail/ rather than /vacancies/detail/.
    """
    from scrapers.jobup_ch import JobupChScraper

    page = (
        _jobs_ch_page(_UUID_A)
        .replace("/en/vacancies/detail/", "/en/jobs/detail/")
        .replace("https://www.jobs.ch", "https://www.jobup.ch")
    )
    calls = []

    async def fake_fetch(url, **kwargs):
        calls.append(url)
        return MagicMock(text=page, status_code=200)

    scraper = JobupChScraper()
    scraper._fetch = fake_fetch  # type: ignore[assignment]
    jobs = [j async for j in scraper.scrape("intune", "Zürich", max_pages=1)]

    assert calls[0].startswith("https://www.jobup.ch/en/jobs/?term=intune&")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "jobup.ch"
    assert job.url == f"https://www.jobup.ch/en/jobs/detail/{_UUID_A}/"
    assert job.location == "Zürich"  # from the card, which the JSON-LD lacks


def _jobscout24_page(count: int, *uuids: str) -> str:
    items = "".join(
        f'<li class="job-list-item" data-job-detail-url="/en/job/{u}/">'
        f'<a href="/en/job/{u}/">Job</a></li>'
        for u in uuids
    )
    return f"<html><body><h1>{count} Intune jobs  in Zürich found</h1><ul>{items}</ul></body></html>"


@pytest.mark.asyncio
async def test_jobscout24_sends_the_params_the_site_reads():
    """
    `q` / `where` were ignored and returned the whole feed (#26). The site
    filters on `ft` and on `psz`, a postcode from its city autocomplete.
    """
    from urllib.parse import parse_qs, urlsplit

    from scrapers.base import ScrapedJob
    from scrapers.jobscout24 import JobScout24Scraper

    scraper = JobScout24Scraper()
    searches = []

    async def fake_fetch(url, **kwargs):
        if "/jobsearch/Cities/" in url:
            cities = [{"Text": "Egg b. Zürich", "Value": "8132"}, {"Text": "Zurich", "Value": "8000"}]
            return MagicMock(status_code=200, json=lambda: cities)
        searches.append(parse_qs(urlsplit(url).query))
        if len(searches) > 1:
            assert kwargs.get("allow_status") == {404}
            return MagicMock(status_code=404, text="")  # past the last page
        return MagicMock(status_code=200, text=_jobscout24_page(2, _UUID_A, _UUID_B))

    async def fake_detail(url, uuid):
        return ScrapedJob("Endpoint Engineer", "Acme", "Zürich", "d", url, "jobscout24.ch", uuid)

    scraper._fetch = fake_fetch  # type: ignore[assignment]
    scraper._fetch_detail = fake_detail  # type: ignore[assignment]
    jobs = [j async for j in scraper.scrape("intune", "Zürich", max_pages=5)]

    assert [j.source_job_id for j in jobs] == [_UUID_A, _UUID_B]
    # The exact "Zurich" wins over the first autocomplete hit.
    assert searches[0] == {"ft": ["intune"], "psz": ["8000"]}
    assert searches[1]["p"] == ["2"]
    assert len(searches) == 2  # the 404 ended the run


def test_jobscout24_tells_an_empty_search_from_moved_markup():
    from scrapers.jobscout24 import JobScout24Scraper

    scraper = JobScout24Scraper()
    assert scraper._parse_search_page(_jobscout24_page(0)) == []
    with pytest.raises(ValueError):
        scraper._parse_search_page(_jobscout24_page(115))


@pytest.mark.asyncio
async def test_michael_page_sends_search_and_stops_on_404():
    """`keywords` was ignored and returned the unfiltered /jobs feed (#26)."""
    from urllib.parse import parse_qs, urlsplit

    from scrapers.michael_page import MichaelPageScraper

    rows = "".join(
        f'<div class="views-row"><h3><a href="/job-detail/engineer-{n}/ref/jn-{n}">Engineer {n}</a></h3></div>'
        for n in range(10)  # a full page, so only the 404 can end the run
    )
    page = f'<html><body><div class="view-content">{rows}</div></body></html>'
    searches = []

    async def fake_fetch(url, **kwargs):
        assert kwargs.get("allow_status") == {404}
        searches.append(parse_qs(urlsplit(url).query))
        if len(searches) > 1:
            return MagicMock(status_code=404, text="")
        return MagicMock(status_code=200, text=page)

    scraper = MichaelPageScraper()
    scraper._fetch = fake_fetch  # type: ignore[assignment]
    jobs = [j async for j in scraper.scrape("system engineer", "Zürich", max_pages=5)]

    assert len(jobs) == 10
    assert searches[0] == {"search": ["system engineer"], "location": ["Zürich"]}
    assert searches[1]["page"] == ["1"]
    assert len(searches) == 2


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
