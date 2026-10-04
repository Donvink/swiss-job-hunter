"""
Scraper for JobScout24.ch — part of JobCloud group, second-largest Swiss job board.
Search page yields UUID job links; full data (including description) comes from JSON-LD
on each detail page.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from typing import AsyncGenerator, Optional, Tuple
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapedJob

_BASE_URL = "https://www.jobscout24.ch"
_SEARCH_URL = f"{_BASE_URL}/en/jobs/"
_CITIES_URL = f"{_BASE_URL}/en/jobsearch/Cities/"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def _fold(name: str) -> str:
    """Case- and accent-insensitive form of a place name: "Zürich" → "zurich"."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold().strip()


class JobScout24Scraper(BaseScraper):
    source_name = "jobscout24.ch"

    async def scrape(
        self, keyword: str, location: str = "Zürich", max_pages: int = 5
    ) -> AsyncGenerator[ScrapedJob, None]:
        """
        Search page params (what the site's own search form redirects to):
            ft   — keyword
            psz  — postcode of a city from /jobsearch/Cities/; a city *name*
                   is silently ignored
            p    — 1-based page; past the last page the site answers 404

        `q` / `where` / `page` look plausible but are all ignored — with them
        every search returned the site's whole unfiltered feed (#26).
        """
        params: dict = {"ft": keyword}
        if location:
            postcode = await self._postcode(location)
            if postcode:
                params["psz"] = postcode
            else:
                print(f"[jobscout24] unknown location {location!r} — searching all of Switzerland")

        seen: set[str] = set()
        yielded = 0
        for page in range(1, max_pages + 1):
            if page > 1:
                params["p"] = page
            url = f"{_SEARCH_URL}?{urlencode(params)}"

            try:
                resp = await self._fetch(url, allow_status={404})
                if resp.status_code == 404:
                    break  # past the last page
                uuids = self._parse_search_page(resp.text)
            except Exception as exc:
                self._page_error(page, exc, yielded)
                break

            new_on_page = 0
            for uuid in uuids:
                if uuid in seen:
                    continue
                seen.add(uuid)

                detail_url = f"{_BASE_URL}/en/job/{uuid}/"
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

    async def _postcode(self, location: str) -> Optional[str]:
        """Resolve a city name to the postcode `psz` expects, via the site's autocomplete."""
        try:
            resp = await self._fetch(f"{_CITIES_URL}?{urlencode({'namePart': location})}")
            cities = resp.json()
        except Exception as exc:
            print(f"[jobscout24] city lookup for {location!r} failed: {exc}")
            return None
        if not cities:
            return None
        # "Zürich" lists "Egg b. Zürich" before "Zurich", so prefer an exact
        # name match over the first hit.
        wanted = _fold(location)
        for city in cities:
            if _fold(city.get("Text", "")) == wanted:
                return city.get("Value")
        return cities[0].get("Value")

    def _parse_search_page(self, html: str) -> list[str]:
        """
        Return the vacancy UUIDs on one search page, promoted listings included.

        Raises ValueError when the heading reports hits but no result items
        parse — the markup moved, which must surface as a broken source rather
        than as "0 jobs".
        """
        soup = BeautifulSoup(html, "lxml")
        uuids = []
        for item in soup.select("li.job-list-item[data-job-detail-url]"):
            match = _UUID_RE.search(item["data-job-detail-url"])
            if match and match.group(0) not in uuids:
                uuids.append(match.group(0))
        if not uuids:
            heading = soup.find("h1")
            count = re.match(r"\s*(\d[\d',]*)", heading.get_text()) if heading else None
            if not count or int(re.sub(r"\D", "", count.group(1))) > 0:
                raise ValueError("no job items in search page")
        return uuids

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
