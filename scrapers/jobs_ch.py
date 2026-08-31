"""
Scraper for jobs.ch — Switzerland's largest job board.

Reads the server-rendered search page: the private JSON API this used to call
(/api/v1/public/search) was withdrawn and now answers 410 Gone.

Each search page carries the results twice, and neither copy alone is enough:

  * a JSON-LD ItemList of JobPosting nodes — reliable ids, titles, companies
    and exact posting timestamps, but the city is filled in barely a third of
    the time and the description is a generated stub;
  * the visible result cards — the real "Place of work" and "Workload" for
    every hit, keyed by the same vacancy UUID.

So we parse both and join them on the UUID. Full descriptions still come from
the detail pages via `fetch_full_description` (the `enrich` step).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from scrapers.base import BaseScraper, PermanentHTTPError, ScrapedJob

_SEARCH_BASE = "https://www.jobs.ch/en/vacancies/"
_DETAIL_BASE = "https://www.jobs.ch/en/vacancies/detail/"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_PAGE_SIZE = 20

# jobs.ch fills the JSON-LD `description` with a stub built from the title.
# Storing it would give the analyzer nothing to score but its own boilerplate,
# so we blank it and let `enrich` fetch the real text from the detail page.
_STUB_DESCRIPTION_RE = re.compile(r"^We are looking for .{0,300} to join our team\.$")


class JobsChScraper(BaseScraper):
    source_name = "jobs.ch"

    async def scrape(
        self, keyword: str, location: str = "Zürich", max_pages: int = 10
    ) -> AsyncGenerator[ScrapedJob, None]:
        """
        Paginate through jobs.ch search results.

        Search page params:
            term        — keyword
            location    — city name
            page        — 1-based

        Page size is fixed at 20 by the site (page 1 adds a promoted listing on
        top). Results come back in relevance order; the page ignores every sort
        parameter the client-side UI uses, so order newest-first downstream on
        `posted_at` if you need it.
        """
        seen: set[str] = set()
        yielded = 0

        for page in range(1, max_pages + 1):
            params = {"term": keyword, "page": page}
            if location:
                params["location"] = location
            url = f"{_SEARCH_BASE}?{urlencode(params)}"

            try:
                resp = await self._fetch(url)
                postings = self._parse_search_page(resp.text)
            except Exception as exc:
                self._page_error(page, exc, yielded)
                break

            if not postings:
                break

            fresh = 0
            for job in postings:
                if job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                fresh += 1
                yielded += 1
                yield job

            # Past the last page jobs.ch does not 404 or return an empty list —
            # it silently re-serves page 1. An all-seen page therefore means we
            # have reached the end, not that the next page will differ.
            if fresh == 0 or len(postings) < _PAGE_SIZE:
                break

    # ── search page parsing ────────────────────────────────────────────────────

    def _parse_search_page(self, html: str) -> list[ScrapedJob]:
        """
        Parse one search page into jobs.

        Raises ValueError when the page carries no JobPosting ItemList at all —
        that means the markup changed under us, which the caller must report as
        a broken source rather than as an empty result set. An ItemList that is
        present but empty is a genuine "nothing found" and returns [].
        """
        soup = BeautifulSoup(html, "lxml")
        items = self._json_ld_postings(soup)
        if items is None:
            raise ValueError("no JobPosting ItemList in search page")

        cards = self._result_cards(soup)
        jobs = []
        for item in items:
            job = self._parse_posting(item, cards)
            if job:
                jobs.append(job)
        return jobs

    def _json_ld_postings(self, soup: BeautifulSoup) -> Optional[list[dict]]:
        """Return the JobPosting nodes of the page's ItemList, or None if absent."""
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
            except (ValueError, TypeError):
                continue
            for node in data if isinstance(data, list) else [data]:
                if not isinstance(node, dict) or node.get("@type") != "ItemList":
                    continue
                return [
                    entry["item"]
                    for entry in node.get("itemListElement") or []
                    if isinstance(entry, dict)
                    and isinstance(entry.get("item"), dict)
                    and entry["item"].get("@type") == "JobPosting"
                ]
        return None

    def _result_cards(self, soup: BeautifulSoup) -> dict[str, dict[str, str]]:
        """
        Map vacancy UUID → the card's labelled fields ("Place of work",
        "Workload", "Contract type").

        The cards carry only hashed utility classes, so the labels themselves
        are the anchor: each field renders as <span>Label:</span><p>Value</p>.
        """
        cards: dict[str, dict[str, str]] = {}
        for card in soup.select('[data-cy="serp-item"]'):
            link = card.select_one('a[href*="/vacancies/detail/"]')
            if not link:
                continue
            match = _UUID_RE.search(link.get("href", ""))
            if not match:
                continue
            fields = {}
            for value in card.find_all("p"):
                label = value.find_previous_sibling("span")
                if not isinstance(label, Tag):
                    continue
                key = label.get_text(strip=True).rstrip(":").strip()
                if key:
                    fields[key] = value.get_text(" ", strip=True)
            cards[match.group(0).lower()] = fields
        return cards

    def _parse_posting(
        self, item: dict, cards: dict[str, dict[str, str]]
    ) -> Optional[ScrapedJob]:
        try:
            title = (item.get("title") or "").strip()
            job_url = (item.get("url") or "").strip()

            job_id = ((item.get("identifier") or {}).get("value") or "").strip()
            if not job_id:
                match = _UUID_RE.search(job_url)
                job_id = match.group(0) if match else ""
            if not (title and job_id):
                return None

            card = cards.get(job_id.lower(), {})
            company = ((item.get("hiringOrganization") or {}).get("name") or "").strip()

            # The card's "Place of work" is populated for every hit; the JSON-LD
            # address is only filled in for about a third of them.
            location = card.get("Place of work", "").strip()
            if not location:
                address = (item.get("jobLocation") or {}).get("address") or {}
                location = ", ".join(
                    filter(None, [address.get("addressLocality"), address.get("addressRegion")])
                )
            location = location or "Switzerland"
            # Normalize common variants → consistent spelling
            location = location.replace("Zurich", "Zürich").replace(", CH", "").strip()

            # Workload is the percentage range the old API exposed as
            # `employment_grades`; render it the way those records were stored
            # ("80–100%") so old and new rows stay comparable.
            employment_type: Optional[str] = None
            if workload := card.get("Workload", "").strip():
                employment_type = re.sub(r"\s*[–-]\s*", "–", workload)
            elif contract := (item.get("employmentType") or "").strip():
                employment_type = contract

            description = (item.get("description") or "").strip()
            if _STUB_DESCRIPTION_RE.match(description):
                description = ""

            posted_at: Optional[datetime] = None
            if ts := item.get("datePosted"):
                try:
                    posted_at = datetime.fromisoformat(ts)
                except ValueError:
                    pass

            return ScrapedJob(
                title=title,
                company=company,
                location=location,
                description=description,
                url=job_url or f"{_DETAIL_BASE}{job_id}/",
                source=self.source_name,
                source_job_id=job_id,
                salary_raw=None,
                employment_type=employment_type,
                posted_at=posted_at,
                raw_json=json.dumps({"json_ld": item, "card": card}, ensure_ascii=False),
            )
        except Exception as exc:
            print(f"[jobs.ch] parse error: {exc}")
            return None

    # ── detail page ────────────────────────────────────────────────────────────

    async def fetch_full_description(self, job_id: str) -> Optional[tuple[str, str]]:
        """
        Fetch full description and canonical URL from the HTML detail page.
        Returns (description, canonical_url), empty tuple () for 404, or None on error.
        """
        url = f"{_DETAIL_BASE}{job_id}/"
        try:
            resp = await self._fetch(url, allow_status={404, 410})
            if resp.status_code in (404, 410):
                return ()  # type: ignore  # job taken down
            soup = BeautifulSoup(resp.text, "lxml")

            # Get canonical URL (contains full slug)
            canonical = ""
            canon_el = soup.select_one("link[rel='canonical']")
            if canon_el:
                canonical = canon_el.get("href", "")

            # Primary selector confirmed via inspection
            el = soup.select_one('[data-cy="vacancy-description"]')
            if el:
                return el.get_text(separator="\n", strip=True), canonical

            # Fallbacks
            for sel in ["div[class*='description']", "article", "main"]:
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    if len(text) > 200:
                        return text, canonical

            return None
        except PermanentHTTPError as exc:
            print(f"[jobs.ch] detail fetch for {job_id}: {exc}")
            return None
        except Exception as exc:
            print(f"[jobs.ch] detail fetch error for {job_id}: {exc}")
            return None
