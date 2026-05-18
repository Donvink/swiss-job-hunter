"""
Scraper for Züri.Jobs — Zürich-focused job aggregator.
Parses JSON-LD structured data embedded in HTML.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import AsyncGenerator, Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapedJob

_BASE_URL = "https://www.zueri.jobs"
_SEARCH_URL = f"{_BASE_URL}/jobs"


class ZuriJobsScraper(BaseScraper):
    source_name = "züri.jobs"

    async def scrape(
        self, keyword: str, location: str = "Zürich", max_pages: int = 5
    ) -> AsyncGenerator[ScrapedJob, None]:
        for page in range(1, max_pages + 1):
            params: dict = {"q": keyword, "l": location}
            if page > 1:
                params["page"] = page
            url = f"{_SEARCH_URL}?{urlencode(params)}"

            try:
                resp = await self._fetch(url)
            except Exception as exc:
                print(f"[züri.jobs] page {page} error: {exc}")
                break

            soup = BeautifulSoup(resp.text, "lxml")

            # Try JSON-LD first (most reliable)
            jobs_from_ld = list(self._parse_json_ld(soup))
            if jobs_from_ld:
                for job in jobs_from_ld:
                    yield job
            else:
                # Fallback to HTML parsing
                for job in self._parse_html(soup):
                    yield job

            # Pagination: check if next page exists
            if not soup.select_one("a[rel='next'], .pagination .next"):
                break

    def _parse_json_ld(self, soup: BeautifulSoup) -> AsyncGenerator[ScrapedJob, None]:  # type: ignore[misc, override]
        """Parse JobPosting schema.org structured data."""
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") not in ("JobPosting", "jobPosting"):
                        continue
                    job = self._from_json_ld(item)
                    if job:
                        yield job
            except (json.JSONDecodeError, AttributeError):
                continue

    def _from_json_ld(self, item: dict) -> Optional[ScrapedJob]:
        try:
            title = item.get("title", "").strip()
            company = (item.get("hiringOrganization") or {}).get("name", "Unknown")
            loc_data = item.get("jobLocation") or {}
            if isinstance(loc_data, list):
                loc_data = loc_data[0] if loc_data else {}
            address = (loc_data.get("address") or {})
            location = address.get("addressLocality", "Switzerland")

            description = item.get("description", "")
            url = item.get("url", "") or item.get("sameAs", "")

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

            return ScrapedJob(
                title=title,
                company=company,
                location=location,
                description=description,
                url=url,
                source=self.source_name,
                salary_raw=salary_raw,
                posted_at=posted_at,
            )
        except Exception as exc:
            print(f"[züri.jobs] json-ld parse error: {exc}")
            return None

    def _parse_html(self, soup: BeautifulSoup):  # type: ignore[override]
        for card in soup.select("div.job-listings-item"):
            try:
                link_el = card.select_one("a.job-details-link")
                if not link_el:
                    continue
                title_el = link_el.select_one("h3, h2")
                title = title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)
                if not title:
                    continue

                href = link_el.get("href", "")
                url = href if href.startswith("http") else f"{_BASE_URL}{href}"

                logo = card.select_one("div.job-employer-logo img")
                company = logo.get("alt", "Unknown").strip() if logo else "Unknown"

                loc_el = card.select_one("div.job-tags")
                location = "Zürich"
                if loc_el:
                    for tag in loc_el.get_text(separator="|", strip=True).split("|"):
                        if "zürich" in tag.lower() or "zurich" in tag.lower() or "📍" in tag:
                            location = tag.replace("📍", "").strip()
                            break

                job_id = card.get("data-jobid", "")

                yield ScrapedJob(
                    title=title, company=company, location=location,
                    description="", url=url, source=self.source_name,
                    source_job_id=job_id,
                )
            except Exception:
                continue
