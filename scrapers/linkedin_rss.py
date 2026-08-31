"""
Scraper for LinkedIn Jobs — uses LinkedIn's public guest JSON/HTML API.

No Playwright or login required. If LINKEDIN_COOKIE (li_at) is set in .env,
it is sent as an HTTP cookie which may unlock more results, but the scraper
works without it.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import AsyncGenerator, Optional, Tuple
from urllib.parse import quote_plus, urlencode

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapedJob

_GUEST_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_PAGE_SIZE = 25

LAST_24H = "r86400"
LAST_7D  = "r604800"
LAST_30D = "r2592000"


class LinkedInRssScraper(BaseScraper):
    source_name = "linkedin.com"

    def __init__(self, time_range: str = LAST_7D, experience_level: str = "3,4") -> None:
        super().__init__()
        self.time_range = time_range
        self.experience_level = experience_level  # LinkedIn f_E: 2=Entry,3=Associate,4=Senior,5=Director
        # Re-read .env on every instantiation so cookie updates take effect immediately
        from config.settings import Settings
        _fresh = Settings()
        self._li_at = _fresh.linkedin_cookie.strip()

    async def scrape(
        self, keyword: str, location: str = "Switzerland", max_pages: int = 5
    ) -> AsyncGenerator[ScrapedJob, None]:
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.linkedin.com/jobs/search/",
        }
        if self._li_at:
            headers["Cookie"] = f"li_at={self._li_at}"

        yielded = 0
        for page_num in range(max_pages):
            params = {
                "keywords": keyword,
                "location": location or "Switzerland",
                "f_TPR": self.time_range,
                "start": page_num * _PAGE_SIZE,
                "count": _PAGE_SIZE,
            }
            if self.experience_level:
                params["f_E"] = self.experience_level
            url = f"{_GUEST_SEARCH}?{urlencode(params)}"

            try:
                resp = await self._fetch(url, headers=headers)
            except Exception as exc:
                self._page_error(page_num + 1, exc, yielded)
                break

            jobs = self._parse_page(resp.text)
            if not jobs:
                break

            for job in jobs:
                yielded += 1
                yield job

    def _parse_page(self, html: str) -> list[ScrapedJob]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for card in soup.select("li"):
            job = self._parse_card(card)
            if job:
                results.append(job)
        return results

    def _parse_card(self, card) -> Optional[ScrapedJob]:
        try:
            title_el = card.select_one("h3.base-search-card__title")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            if not title:
                return None

            company_el = card.select_one("h4.base-search-card__subtitle")
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            loc_el = card.select_one(".job-search-card__location")
            location = loc_el.get_text(strip=True) if loc_el else "Switzerland"

            link_el = card.select_one("a.base-card__full-link")
            href = link_el.get("href", "") if link_el else ""
            m = re.search(r"/jobs/view/[^/]+-(\d+)", href)
            job_id = m.group(1) if m else ""
            url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id else href

            time_el = card.select_one("time")
            posted_at = None
            if time_el and time_el.get("datetime"):
                try:
                    posted_at = datetime.fromisoformat(time_el["datetime"])
                except (ValueError, TypeError):
                    pass

            return ScrapedJob(
                title=title,
                company=company,
                location=location,
                description="",
                url=url,
                source=self.source_name,
                source_job_id=job_id or href,
                posted_at=posted_at,
            )
        except Exception as exc:
            print(f"[linkedin] card parse error: {exc}")
            return None

    async def fetch_full_description(self, job_url: str) -> Optional[Tuple[str, str]]:
        """Fetch full description via LinkedIn's public guest job posting API."""
        m = re.search(r"(\d{6,})", job_url)
        if not m:
            return None
        job_id = m.group(1)
        api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        canonical = f"https://www.linkedin.com/jobs/view/{job_id}/"
        try:
            resp = await self._fetch(api_url, allow_status={404, 410})
            if resp.status_code in (404, 410):
                return ()  # type: ignore
            soup = BeautifulSoup(resp.text, "lxml")
            el = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 100:
                    return text, canonical
            return None
        except Exception as exc:
            print(f"[linkedin] detail fetch error for {job_id}: {exc}")
            return None
