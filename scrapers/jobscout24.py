"""
Scraper for JobScout24.ch — part of JobCloud group, second-largest Swiss job board.
Search page yields UUID job links; full data (including description) comes from JSON-LD
on each detail page.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import AsyncGenerator, Optional, Tuple
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapedJob

_BASE_URL = "https://www.jobscout24.ch"
_SEARCH_URL = f"{_BASE_URL}/en/jobs/"


class JobScout24Scraper(BaseScraper):
    source_name = "jobscout24.ch"

    async def scrape(
        self, keyword: str, location: str = "Zürich", max_pages: int = 5
    ) -> AsyncGenerator[ScrapedJob, None]:
        seen: set[str] = set()
        yielded = 0
        for page in range(1, max_pages + 1):
            params: dict = {"q": keyword}
            if location:
                params["where"] = location
            if page > 1:
                params["page"] = page
            url = f"{_SEARCH_URL}?{urlencode(params)}"

            try:
                resp = await self._fetch(url)
            except Exception as exc:
                self._page_error(page, exc, yielded)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            job_links = [
                a.get("href", "")
                for a in soup.select('a[href*="/job/"]')
                if "/job/" in a.get("href", "")
            ]

            new_on_page = 0
            for href in job_links:
                parts = [p for p in href.split("/") if p]
                # expect ['en', 'job', '<uuid>']
                if len(parts) < 3 or parts[-1] in seen:
                    continue
                uuid = parts[-1]
                seen.add(uuid)

                detail_url = f"{_BASE_URL}{href}"
                try:
                    job = await self._fetch_detail(detail_url, uuid)
                    if job:
                        new_on_page += 1
                        yielded += 1
                        yield job
                except Exception as exc:
                    print(f"[jobscout24] detail {uuid}: {exc}")

            if new_on_page == 0:
                break
            if not soup.select_one("a[rel='next'], .pagination .next"):
                break

    async def _fetch_detail(self, url: str, uuid: str) -> Optional[ScrapedJob]:
        resp = await self._fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")
        for script in soup.find_all("script"):
            if "json" not in script.get("type", ""):
                continue
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                        continue
                    return self._from_json_ld(item, uuid)
            except (json.JSONDecodeError, AttributeError):
                continue
        return None

    def _from_json_ld(self, item: dict, uuid: str) -> Optional[ScrapedJob]:
        try:
            title = item.get("title", "").strip()
            if not title:
                return None

            company = (item.get("hiringOrganization") or {}).get("name", "Unknown")

            loc_data = item.get("jobLocation") or {}
            if isinstance(loc_data, list):
                loc_data = loc_data[0] if loc_data else {}
            location = (loc_data.get("address") or {}).get("addressLocality", "Switzerland")

            raw_desc = item.get("description", "")
            description = (
                BeautifulSoup(raw_desc, "lxml").get_text(separator="\n", strip=True)
                if raw_desc else ""
            )

            url = item.get("url", "") or f"{_BASE_URL}/en/job/{uuid}/"

            posted_at: Optional[datetime] = None
            if ts := item.get("datePosted"):
                try:
                    posted_at = datetime.fromisoformat(ts)
                except ValueError:
                    pass

            salary_raw: Optional[str] = None
            if sal := item.get("baseSalary"):
                val = sal.get("value", {})
                mn = val.get("minValue", "")
                mx = val.get("maxValue", "")
                currency = sal.get("currency", "CHF")
                if mn and mx:
                    salary_raw = f"{currency} {mn:,} – {mx:,}"

            emp = item.get("employmentType")
            if isinstance(emp, list):
                emp = ", ".join(emp)

            return ScrapedJob(
                title=title,
                company=company,
                location=location,
                description=description,
                url=url,
                source=self.source_name,
                source_job_id=uuid,
                salary_raw=salary_raw,
                employment_type=emp,
                posted_at=posted_at,
            )
        except Exception as exc:
            print(f"[jobscout24] json-ld parse error: {exc}")
            return None

    async def fetch_full_description(self, source_job_id: str) -> Optional[Tuple[str, str]]:
        """Re-fetch detail page by UUID and return (description, canonical_url)."""
        if not source_job_id:
            return None
        url = (
            source_job_id
            if source_job_id.startswith("http")
            else f"{_BASE_URL}/en/job/{source_job_id}/"
        )
        try:
            resp = await self._fetch(url, allow_status={404, 410})
            if resp.status_code in (404, 410):
                return ()  # type: ignore
            soup = BeautifulSoup(resp.text, "lxml")
            for script in soup.find_all("script"):
                if "json" not in script.get("type", ""):
                    continue
                try:
                    data = json.loads(script.string or "")
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                            continue
                        raw = item.get("description", "")
                        if len(raw) > 200:
                            desc = BeautifulSoup(raw, "lxml").get_text(separator="\n", strip=True)
                            return desc, item.get("url", url)
                except (json.JSONDecodeError, AttributeError):
                    continue
            return None
        except Exception as exc:
            print(f"[jobscout24] enrich fetch error: {exc}")
            return None
