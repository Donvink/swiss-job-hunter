"""
Scraper for jobup.ch — leading job board for French-speaking Switzerland.

jobup.ch is JobCloud's sister site to jobs.ch and serves the same search page:
a JSON-LD ItemList plus result cards keyed by vacancy UUID, the same
wrap-back-to-page-1 past the last page, and the same detail-page markup. So
this reuses the jobs.ch scraper and only swaps the URLs.

It used to call the public search API (job-search-api.jobup.ch), which still
answers 200 but now ignores `term` and returns the same unfiltered feed for
every query (#26).
"""
from __future__ import annotations

from scrapers.jobs_ch import JobsChScraper


class JobupChScraper(JobsChScraper):
    source_name = "jobup.ch"
    search_url = "https://www.jobup.ch/en/jobs/"
    detail_url = "https://www.jobup.ch/en/jobs/detail/"
