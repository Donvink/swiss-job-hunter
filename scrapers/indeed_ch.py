"""
Scraper for Indeed Switzerland — uses the public RSS feed.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode

from scrapers.base import BaseScraper, ScrapedJob

_RSS_URL = "https://ch.indeed.com/rss"


class IndeedChScraper(BaseScraper):
    source_name = "indeed.ch"

    async def scrape(
        self, keyword: str, location: str = "Zürich", max_pages: int = 5
    ) -> AsyncGenerator[ScrapedJob, None]:
        for page_num in range(max_pages):
            params = {
                "q": keyword,
                "l": location,
                "fromage": 30,
                "sort": "date",
                "start": page_num * 10,
            }
            url = f"{_RSS_URL}?{urlencode(params)}"
            try:
                resp = await self._fetch(url)
            except Exception as exc:
                raise RuntimeError(f"indeed.ch RSS fetch failed (page {page_num + 1}): {exc}")

            ct = resp.headers.get("content-type", "")
            if resp.status_code != 200 or "Security Check" in resp.text:
                raise RuntimeError(
                    f"indeed.ch blocked by Cloudflare (HTTP {resp.status_code})"
                )
            if "xml" not in ct and not resp.text.strip().startswith("<"):
                raise RuntimeError(
                    f"indeed.ch RSS returned unexpected content-type={ct!r}; "
                    f"preview: {resp.text[:120]!r}"
                )

            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError as exc:
                raise RuntimeError(f"indeed.ch XML parse failed: {exc}; preview: {resp.text[:120]!r}")

            items = root.findall(".//item")
            if not items:
                raise RuntimeError(
                    f"indeed.ch RSS: valid XML but 0 <item> elements; "
                    f"root tag={root.tag!r}; preview={resp.text[:200]!r}"
                )

            parsed = 0
            for item in items:
                job = self._parse_item(item)
                if job:
                    parsed += 1
                    yield job
            if parsed == 0:
                first = items[0]
                raise RuntimeError(
                    f"indeed.ch RSS: {len(items)} items found but all failed to parse; "
                    f"first item tags={[c.tag for c in first]!r}; "
                    f"title={first.findtext('title')!r}"
                )

    def _parse_item(self, item: ET.Element) -> Optional[ScrapedJob]:
        try:
            title = (item.findtext("title") or "").strip()
            if not title:
                return None

            link = (item.findtext("link") or "").strip()

            job_key = ""
            jk_el = item.find("{com.indeed}jobkey")
            if jk_el is not None and jk_el.text:
                job_key = jk_el.text.strip()
            if not job_key and "jk=" in link:
                job_key = link.split("jk=")[-1].split("&")[0]

            company = (item.findtext("source") or "").strip() or "Unknown"
            co_el = item.find("{com.indeed}company")
            if co_el is not None and co_el.text:
                company = co_el.text.strip()

            city_el = item.find("{com.indeed}city")
            state_el = item.find("{com.indeed}state")
            city = city_el.text.strip() if city_el is not None and city_el.text else ""
            state = state_el.text.strip() if state_el is not None and state_el.text else ""
            location = ", ".join(filter(None, [city, state])) or "Switzerland"

            description = ""
            desc_el = item.find("description")
            if desc_el is not None and desc_el.text:
                description = re.sub(r"<[^>]+>", "", desc_el.text).strip()

            salary_el = item.find("{com.indeed}salary")
            salary_raw = salary_el.text.strip() if salary_el is not None and salary_el.text else None

            return ScrapedJob(
                title=title,
                company=company,
                location=location,
                description=description,
                url=link,
                source=self.source_name,
                source_job_id=job_key or link,
                salary_raw=salary_raw,
            )
        except Exception as exc:
            print(f"[indeed.ch] parse error: {exc}")
            return None
