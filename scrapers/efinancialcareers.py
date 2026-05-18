"""
Scraper for eFinancialCareers CH — Angular SPA, requires Playwright.
"""
from __future__ import annotations

import re
from typing import AsyncGenerator, Optional
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
            try:
                for page_num in range(1, max_pages + 1):
                    url = (
                        f"{_SEARCH_URL}/{slug}"
                        f"?q={quote_plus(keyword)}&location={quote_plus(location)}"
                        f"&countryCode=CH&radius=40&radiusUnit=km&pageSize=15"
                        f"&currencyCode=CHF&language=de&enableVectorSearch=true"
                        f"&page={page_num}"
                    )
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    try:
                        await page.wait_for_selector("[class*='job-card']", timeout=10_000)
                    except Exception:
                        break  # no results on this page

                    cards = await page.query_selector_all("[class*='job-card']")
                    if not cards:
                        break

                    for card in cards:
                        job = await self._parse_card(card)
                        if job:
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
