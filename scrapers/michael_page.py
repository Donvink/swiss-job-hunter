"""
Scraper for Michael Page CH — premium headhunter, Senior/Lead roles.
Drupal-based site with server-rendered job listings (no API needed).
Client names are hidden in listings (standard headhunter practice).
"""
from __future__ import annotations

from typing import AsyncGenerator, Optional, Tuple
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapedJob

_BASE_URL = "https://www.michaelpage.ch"
_SEARCH_URL = f"{_BASE_URL}/jobs"


class MichaelPageScraper(BaseScraper):
    source_name = "michael-page.ch"

    async def scrape(
        self, keyword: str, location: str = "Zürich", max_pages: int = 5
    ) -> AsyncGenerator[ScrapedJob, None]:
        yielded = 0
        for page in range(max_pages):
            params: dict = {"keywords": keyword}
            if location:
                params["location"] = location
            if page > 0:
                params["page"] = page
            url = f"{_SEARCH_URL}?{urlencode(params)}"

            try:
                resp = await self._fetch(url)
            except Exception as exc:
                self._page_error(page, exc, yielded)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select(".view-content .views-row")
            if not items:
                break

            for item in items:
                job = self._parse_item(item)
                if job:
                    yielded += 1
                    yield job

            if len(items) < 10:
                break

    def _parse_item(self, item) -> Optional[ScrapedJob]:
        try:
            title_el = item.select_one("h3 a, h2 a")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            if not title:
                return None

            href = title_el.get("href", "")
            url = href if href.startswith("http") else f"{_BASE_URL}{href}"

            # Location — strip FontAwesome icon element first
            location = "Switzerland"
            loc_el = item.select_one(".job-location")
            if loc_el:
                for icon in loc_el.select("i"):
                    icon.decompose()
                location = loc_el.get_text(strip=True) or "Switzerland"

            # Contract type
            employment_type: Optional[str] = None
            type_el = item.select_one(".job-contract-type")
            if type_el:
                for icon in type_el.select("i"):
                    icon.decompose()
                employment_type = type_el.get_text(strip=True) or None

            return ScrapedJob(
                title=title,
                company="Michael Page",
                location=location,
                description="",
                url=url,
                source=self.source_name,
                source_job_id=url,
                employment_type=employment_type,
            )
        except Exception as exc:
            print(f"[michael-page] parse error: {exc}")
            return None

    async def fetch_full_description(self, job_url: str) -> Optional[Tuple[str, str]]:
        """Fetch job description from the Michael Page detail page."""
        if not job_url or not job_url.startswith("http"):
            return None
        try:
            resp = await self._fetch(job_url, allow_status={404, 410})
            if resp.status_code in (404, 410):
                return ()  # type: ignore
            soup = BeautifulSoup(resp.text, "lxml")

            canonical = ""
            canon_el = soup.find("link", rel="canonical")
            if canon_el:
                canonical = canon_el.get("href", "")

            for sel in ["[class*=job-content]", "[class*=description]", "article", "main"]:
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    if len(text) > 200:
                        return text, canonical or job_url

            return None
        except Exception as exc:
            print(f"[michael-page] detail fetch error: {exc}")
            return None
