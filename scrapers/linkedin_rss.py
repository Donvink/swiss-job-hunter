"""
Scraper for LinkedIn Jobs — uses Playwright (public job listings, no login required).
"""
from __future__ import annotations

import re
from typing import AsyncGenerator, Optional
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from config.settings import settings
from scrapers.base import BaseScraper, ScrapedJob

_SEARCH_URL = "https://www.linkedin.com/jobs/search"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LAST_24H = "r86400"
LAST_7D  = "r604800"
LAST_30D = "r2592000"


class LinkedInRssScraper(BaseScraper):
    source_name = "linkedin.com"

    def __init__(self, time_range: str = LAST_7D) -> None:
        super().__init__()
        self.time_range = time_range

    async def scrape(
        self, keyword: str, location: str = "Zürich", max_pages: int = 3
    ) -> AsyncGenerator[ScrapedJob, None]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=settings.playwright_headless)
            context = await browser.new_context(
                user_agent=_UA,
                locale="en-US",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            try:
                for page_num in range(max_pages):
                    url = (
                        f"{_SEARCH_URL}"
                        f"?keywords={quote_plus(keyword)}"
                        f"&location={quote_plus(location)}"
                        f"&f_TPR={self.time_range}"
                        f"&start={page_num * 25}"
                    )
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    try:
                        await page.wait_for_selector("div.job-search-card", timeout=10_000)
                    except Exception:
                        break  # no results on this page

                    cards = await page.query_selector_all("div.job-search-card")
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

            company_el = await card.query_selector("h4")
            company = (await company_el.inner_text()).strip() if company_el else "Unknown"

            loc_el = await card.query_selector(".job-search-card__location")
            location = (await loc_el.inner_text()).strip() if loc_el else "Switzerland"

            link_el = await card.query_selector("a[href*='/jobs/view/']")
            href = (await link_el.get_attribute("href") or "") if link_el else ""
            # Extract canonical job ID
            m = re.search(r"/jobs/view/[^/]+-(\d+)", href)
            job_id = m.group(1) if m else href
            url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id.isdigit() else href

            return ScrapedJob(
                title=title,
                company=company,
                location=location,
                description="",
                url=url,
                source=self.source_name,
                source_job_id=job_id,
            )
        except Exception as exc:
            print(f"[linkedin] parse error: {exc}")
            return None
