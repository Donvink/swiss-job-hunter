"""
Scraper for SwissDevJobs.ch — niche IT/software jobs in Switzerland.
Uses Playwright (SPA, JS-rendered content).
"""
from __future__ import annotations

from typing import AsyncGenerator, Optional
from urllib.parse import urlencode

from playwright.async_api import async_playwright

from config.settings import settings
from scrapers.base import BaseScraper, ScrapedJob

_BASE_URL = "https://swissdevjobs.ch"

_JOB_KEYWORDS = {
    "senior", "junior", "lead", "head", "principal", "staff",
    "engineer", "developer", "manager", "consultant", "analyst",
    "scientist", "researcher", "architect", "director", "specialist",
    "administrator", "designer", "devops", "cloud", "data", "ai",
    "ml", "software", "platform", "security", "forward", "deployed",
}


def _extract_company_from_slug(slug: str) -> str:
    """Extract company name from URL slug like 'CONVOTIS-Schweiz-AG-Senior-Engineer'"""
    parts = slug.split("-")
    company_parts = []
    for part in parts:
        if not part:
            continue  # skip empty parts from double dashes
        if part.lower() in _JOB_KEYWORDS:
            break
        company_parts.append(part)
    return " ".join(company_parts) if company_parts else "Unknown"


class SwissDevJobsScraper(BaseScraper):
    source_name = "swissdevjobs.ch"

    async def scrape(
        self, keyword: str, location: str = "Zürich", max_pages: int = 5
    ) -> AsyncGenerator[ScrapedJob, None]:
        params: dict = {"position": keyword}
        if location:
            params["city"] = location
        search_url = f"{_BASE_URL}/jobs?{urlencode(params)}"

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=settings.playwright_headless)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            yielded = 0
            try:
                await page.goto(search_url, wait_until="networkidle", timeout=30_000)
                await page.wait_for_timeout(1000)

                cards = await page.query_selector_all("div[data-test='card-body']")
                if not cards:
                    cards = await page.query_selector_all("div[class*='card']")

                for card in cards:
                    job = await self._parse_card(card)
                    if job:
                        yielded += 1
                        yield job

            except Exception as exc:
                self._page_error(1, exc, yielded)
            finally:
                await browser.close()

    async def _parse_card(self, card) -> Optional[ScrapedJob]:
        try:
            link_el = await card.query_selector("a[title][href]")
            if not link_el:
                return None

            href = await link_el.get_attribute("href") or ""

            # Skip company ads — only real job listings start with /jobs/
            if not href.startswith("/jobs/"):
                return None

            slug = href.replace("/jobs/", "")
            url = f"{_BASE_URL}{href}"

            # Title from link title attribute: "Job Title job in City"
            raw_title = await link_el.get_attribute("title") or ""
            title = raw_title.split(" job in ")[0].strip() if " job in " in raw_title else raw_title.strip()

            # Location from title suffix
            location = "Switzerland"
            if " job in " in raw_title:
                location = raw_title.split(" job in ")[-1].strip()

            # Company from URL slug
            company = _extract_company_from_slug(slug)

            # Salary
            salary_raw = None
            for sel in ["span[class*='salary']", "div[class*='salary']"]:
                salary_el = await card.query_selector(sel)
                if salary_el:
                    text = (await salary_el.inner_text()).strip()
                    if text:
                        salary_raw = text
                        break

            description = ""  # filled by Enrich step

            if not title:
                return None

            return ScrapedJob(
                title=title,
                company=company,
                location=location,
                description=description,
                url=url,
                source=self.source_name,
                source_job_id=slug,
                salary_raw=salary_raw,
            )
        except Exception as exc:
            print(f"[swissdevjobs] parse error: {exc}")
            return None

    async def fetch_full_description(self, source_job_id: str) -> Optional[tuple]:
        """Fetch full JD from the job detail page using Playwright (SPA)."""
        url = f"{_BASE_URL}/jobs/{source_job_id}"
        try:
            await self._polite_delay()
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=settings.playwright_headless)
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()
                try:
                    resp = await page.goto(url, wait_until="networkidle", timeout=30_000)
                    if resp and resp.status == 404:
                        return ()
                    await page.wait_for_timeout(1000)
                    for sel in [
                        "[class*='job-description']",
                        "[class*='description']",
                        "[class*='content']",
                        "article",
                        "main",
                    ]:
                        el = await page.query_selector(sel)
                        if el:
                            text = (await el.inner_text()).strip()
                            if len(text) > 200:
                                return text, url
                    return None
                finally:
                    await browser.close()
        except Exception as exc:
            print(f"[swissdevjobs] detail fetch error: {exc}")
            return None
