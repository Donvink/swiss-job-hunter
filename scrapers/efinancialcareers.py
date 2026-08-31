"""
Scraper for eFinancialCareers CH — Angular SPA, requires Playwright.
"""
from __future__ import annotations

import json
import re
from typing import AsyncGenerator, Optional, Tuple
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from config.settings import settings
from scrapers.base import BaseScraper, ScrapedJob

_BASE_URL = "https://www.efinancialcareers.ch"
_SEARCH_URL = f"{_BASE_URL}/jobs"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_EMPLOYMENT_TYPES = re.compile(r"Festanstellung|Teilzeit|Vertrag|Contract|Freelance|Befristet")
_CH_TERMS = re.compile(
    r"schweiz|switzerland|zürich|zurich|geneva|genf|basel|bern|lausanne|zug|"
    r"lugano|luzern|lucerne|winterthur|st\.?\s*gallen|aarau|schaffhausen|thun|"
    r"\bch\b",
    re.IGNORECASE,
)


class EFinancialCareersScraper(BaseScraper):
    source_name = "efinancialcareers.ch"

    async def scrape(
        self, keyword: str, location: str = "Zürich", max_pages: int = 5
    ) -> AsyncGenerator[ScrapedJob, None]:
        slug = keyword.lower().replace(" ", "-")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=settings.playwright_headless)
            context = await browser.new_context(user_agent=_UA)
            page = await context.new_page()
            yielded = 0
            try:
                for page_num in range(1, max_pages + 1):
                    loc_param = f"&location={quote_plus(location)}" if location else ""
                    url = (
                        f"{_SEARCH_URL}/{slug}"
                        f"?q={quote_plus(keyword)}{loc_param}"
                        f"&countryCode=CH&radius=40&radiusUnit=km&pageSize=15"
                        f"&currencyCode=CHF&language=de&enableVectorSearch=true"
                        f"&page={page_num}"
                    )
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    try:
                        await page.wait_for_selector("[class*='job-card']", timeout=10_000)
                    except Exception as exc:
                        # No cards at all on the first page means the layout moved,
                        # not that the search came back empty.
                        self._page_error(page_num, exc, yielded)
                        break

                    cards = await page.query_selector_all("[class*='job-card']")
                    if not cards:
                        break

                    for card in cards:
                        job = await self._parse_card(card)
                        if job:
                            yielded += 1
                            yield job
            finally:
                await browser.close()

    async def _parse_card(self, card) -> Optional[ScrapedJob]:
        try:
            title_el = await card.query_selector("h3")
            if not title_el:
                return None
            title = (await title_el.inner_text()).strip()
            if not title:
                return None

            link_el = await card.query_selector("a[href*='/jobs']")
            href = (await link_el.get_attribute("href") or "") if link_el else ""
            url = href if href.startswith("http") else f"{_BASE_URL}{href}"

            loc_el = await card.query_selector("[class*='location']")
            loc_raw = (await loc_el.inner_text()).strip() if loc_el else ""
            location = _EMPLOYMENT_TYPES.split(loc_raw)[0].strip().rstrip(",").strip()

            # Skip non-Swiss jobs — efinancialcareers.ch is a global platform
            if location and not _CH_TERMS.search(location):
                return None

            # Company name is the line after "Speichern" in the card text
            full_text = (await card.inner_text()).strip()
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]
            company = "Unknown"
            for i, line in enumerate(lines):
                if line == "Speichern" and i + 1 < len(lines):
                    company = lines[i + 1]
                    break

            # Job ID from URL suffix .id12345678
            m = re.search(r"\.id(\d+)$", url)
            job_id = m.group(1) if m else url

            return ScrapedJob(
                title=title,
                company=company,
                location=location or "Switzerland",
                description="",
                url=url,
                source=self.source_name,
                source_job_id=job_id,
            )
        except Exception as exc:
            print(f"[efinancialcareers] parse error: {exc}")
            return None

    async def fetch_full_description(self, job_url: str) -> Optional[Tuple[str, str]]:
        """Fetch full description from an eFinancialCareers detail page.

        Page embeds a script[type=application/json] whose keys are API URLs.
        The branding key contains data.data.description (HTML string).
        """
        if not job_url or not job_url.startswith("http"):
            return None
        try:
            from bs4 import BeautifulSoup
            await self._polite_delay()
            client = await self._get_client()
            resp = await client.get(job_url)
            if resp.status_code in (404, 410):
                return ()  # type: ignore
            soup = BeautifulSoup(resp.text, "lxml")

            canonical = ""
            canon_el = soup.find("link", rel="canonical")
            if canon_el:
                canonical = canon_el.get("href", "")

            for script in soup.find_all("script", type="application/json"):
                try:
                    outer = json.loads(script.string or "")
                    if not isinstance(outer, dict):
                        continue
                    for key, val in outer.items():
                        if "branding" not in key or not isinstance(val, dict):
                            continue
                        body = val.get("body", "")
                        inner = json.loads(body) if isinstance(body, str) else body
                        raw_desc = (inner.get("data") or {}).get("description", "")
                        if raw_desc and len(raw_desc) > 200:
                            desc = BeautifulSoup(raw_desc, "lxml").get_text(
                                separator="\n", strip=True
                            )
                            return desc, canonical or job_url
                except (json.JSONDecodeError, AttributeError, TypeError):
                    continue

            return None
        except Exception as exc:
            print(f"[efinancialcareers] detail fetch error for {job_url}: {exc}")
            return None
