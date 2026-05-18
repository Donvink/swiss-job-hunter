"""
Scraper for jobup.ch — leading job board for French-speaking Switzerland.
Uses their public REST API.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode

from scrapers.base import BaseScraper, ScrapedJob

_API_BASE = "https://job-search-api.jobup.ch/search"
_PAGE_SIZE = 20
_HEADERS = {
    "Origin": "https://www.jobup.ch",
    "Referer": "https://www.jobup.ch/",
}


class JobupChScraper(BaseScraper):
    source_name = "jobup.ch"

    async def scrape(
        self, keyword: str, location: str = "Genève", max_pages: int = 5
    ) -> AsyncGenerator[ScrapedJob, None]:
        for page in range(1, max_pages + 1):
            params = {
                "term": keyword,
                "location": location,
                "page": page,
                "rows": _PAGE_SIZE,
            }
            url = f"{_API_BASE}?{urlencode(params)}"

            try:
                resp = await self._fetch(url, headers=_HEADERS)
                data = resp.json()
            except Exception as exc:
                print(f"[jobup.ch] page {page} error: {exc}")
                break

            jobs = data.get("documents", [])
            if not jobs:
                break

            for doc in jobs:
                job = self._parse(doc)
                if job:
                    yield job

            if page >= data.get("numPages", 1):
                break

    def _parse(self, doc: dict) -> Optional[ScrapedJob]:
        try:
            title = doc.get("title", "").strip()
            company = (doc.get("company") or {}).get("name", "Unknown").strip()
            place = doc.get("place", "")
            location = (place if isinstance(place, str) else (place or {}).get("name", "Switzerland")).strip() or "Switzerland"

            description = doc.get("teaser", "") or doc.get("description", "")
            slug = doc.get("slug", "") or str(doc.get("id", ""))
            url = f"https://www.jobup.ch/en/jobs/detail/{slug}/"

            posted_at: Optional[datetime] = None
            if ts := doc.get("publication_date"):
                try:
                    posted_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    pass

            return ScrapedJob(
                title=title,
                company=company,
                location=location,
                description=description,
                url=url,
                source=self.source_name,
                source_job_id=str(doc.get("id", "")),
                posted_at=posted_at,
                raw_json=json.dumps(doc, ensure_ascii=False),
            )
        except Exception as exc:
            print(f"[jobup.ch] parse error: {exc}")
            return None
