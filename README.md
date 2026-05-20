<div align="center">

# 🇨🇭 Swiss Job Hunter

**Automated job search, scoring, and application tracking for Switzerland**

[![CI](https://github.com/Donvink/swiss-job-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/Donvink/swiss-job-hunter/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Features](#features) · [Quick Start](#quick-start) · [UI](#ui) · [Multi-Direction](#multi-direction-search) · [Architecture](#architecture)

![Swiss Job Hunter UI](docs/screenshot.png)

</div>

---

## Why

Job searching in Switzerland is fragmented — the same listing appears on jobs.ch, LinkedIn, JobScout24, and several other platforms simultaneously. You end up manually deduplicating, copy-pasting cover letters, and losing track of what you applied to.

Swiss Job Hunter automates the boring parts:
- Scrapes 8 Swiss job boards and deduplicates across sources
- Scores each job against your CV (fast keyword match + LLM deep analysis)
- Generates tailored cover letters via Claude / DeepSeek
- Tracks every application with a Kanban board and event timeline
- Supports multiple job directions (e.g. ML Engineer + Perception Engineer) with separate CVs

---

## Features

| | Feature |
|---|---|
| ⬇ | **Multi-source scraping** — 8 Swiss job boards, httpx + Playwright |
| 🔁 | **Smart deduplication** — SHA-256 exact match + MiniLM semantic similarity |
| 📄 | **Full JD enrichment** — fetches complete descriptions beyond preview snippets |
| ⭐ | **CV matching** — weighted keyword scoring + LLM deep analysis (Claude / DeepSeek) |
| 🎯 | **Direction tagging** — separate directions (e.g. ML / Perception) with independent CVs |
| 🏢 | **Company lookup** — LLM-generated company summaries, cached per company |
| ✍ | **Cover letter generation** — personalized EN/DE letters via Claude API |
| 🌐 | **Description translation** — translate JDs to English on demand |
| 📋 | **Kanban tracker** — NEW → Viewed → Applied → Interview → Offer |
| 🕐 | **Timeline** — per-job event log (recruiter calls, interviews, offers, rejections) |
| 🗑 | **Bulk purge** — preview and delete low-scoring jobs by threshold |
| ⌨ | **CLI** — full terminal interface for power users |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- [Anthropic API key](https://console.anthropic.com) and/or [DeepSeek API key](https://platform.deepseek.com)

### 1. Clone & install

```bash
git clone https://github.com/Donvink/swiss-job-hunter.git
cd swiss-job-hunter

pip install -r requirements.txt
playwright install chromium

cd ui && npm install && cd ..
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...   # Claude API (cover letters, LLM scoring, company lookup)
DEEPSEEK_API_KEY=sk-...        # DeepSeek — cheaper alternative for scoring
LLM_PROVIDER=auto              # auto = use whichever key is configured
```

### 3. Add your CV

```bash
cp your_cv.txt data/cv.txt
```

### 4. Start

```bash
# Terminal 1 — backend
python server.py

# Terminal 2 — frontend
cd ui && npm run dev
```

Open **http://localhost:5173**

---

## UI

The sidebar guides you through the full pipeline:

```
① SEARCH → ② PIPELINE (Enrich → Score → Company Lookup → Purge) → FILTER → LOG
```

**① SEARCH** — Pick a direction (ALL / ML / PERCEPTION), set keyword + location, select sources, hit RUN SEARCH. New jobs are tagged with the active direction.

**② PIPELINE**
- **ENRICH DESCRIPTIONS** — fetches full JDs for jobs that only have a preview snippet
- **SCORE (KEYWORD)** — fast TF-IDF-style match against your CV, no API cost
- **SCORE (LLM)** — deep analysis via Claude/DeepSeek; auto-archives jobs below the threshold
- **LOOKUP COMPANIES** — generates a short LLM summary for each company, cached
- **PREVIEW / PURGE** — dry-run or delete scored jobs below a score threshold

**FILTER** — filter by status (NEW / SHORTLISTED / APPLIED / …) and free-text search

**LOG** — live SSE output from every pipeline operation

**BOARD** — job list with score bars, status badges, and direction tags; click a job to inspect, translate, generate a cover letter, or apply

**TRACKER** — Kanban board across all application stages

---

## Multi-Direction Search

If you're targeting multiple job types with different CVs:

```bash
# One CV per direction — filename convention: data/cv_{direction}.txt
cp your_ml_cv.txt      data/cv_ml.txt
cp your_perception_cv.txt data/cv_perception.txt
```

In the UI, select **ML** or **PERCEPTION** before searching or scoring. The system:
- Tags scraped jobs with the active direction
- Loads the matching CV automatically when scoring
- Lets you filter the job list by direction

You can add more directions by placing additional `data/cv_{name}.txt` files and using the direction name in the UI. The `data/cv.txt` file is used as a fallback for the default (ALL) mode.

---

## CLI

```bash
# Scrape jobs
sjh search "ML engineer" --location "Zürich" --source jobs.ch

# Enrich with full descriptions
sjh enrich --source jobs.ch

# Score against your CV
sjh analyze                    # keyword scoring (fast)
sjh analyze --llm              # LLM scoring (accurate)

# View top matches
sjh top --limit 20

# Generate cover letter
sjh cover <job_id> --lang en

# Daily summary
sjh digest
```

---

## Supported Job Boards

| Source | Method | Notes |
|---|---|---|
| jobs.ch | JSON API + HTML detail | Primary Swiss board |
| jobscout24.ch | JSON API | Large Swiss generalist board |
| jobup.ch | JSON API + HTML detail | French-speaking Switzerland |
| swissdevjobs.ch | HTML / BS4 | IT & software focused |
| züri.jobs | JSON-LD + HTML | Zürich-focused |
| efinancialcareers.ch | JSON + HTML | Finance & banking |
| linkedin.com | RSS feed | Public feed, no login required |
| michael-page.ch | HTML / BS4 | Executive & specialist roles |
| indeed.ch | Playwright | JS-rendered; requires Chromium |

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   scrapers/ │────▶│  dedup/      │────▶│  db/        │
│  8 sources  │     │  exact +     │     │  SQLite     │
│  httpx +    │     │  semantic    │     │  jobs.db    │
│  playwright │     └──────────────┘     └──────┬──────┘
└─────────────┘                                 │
                                                ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  ui/        │◀───▶│  server.py   │────▶│  analyzer/  │
│  React +    │     │  FastAPI     │     │  scorer.py  │
│  Vite       │     │  SSE stream  │     │  keyword +  │
└─────────────┘     └──────────────┘     │  LLM        │
                                         └──────┬──────┘
                                                │
                                         ┌──────▼──────┐
                                         │  llm/       │
                                         │  router.py  │
                                         │  Claude /   │
                                         │  DeepSeek   │
                                         └─────────────┘
```

### Tech Stack

| Layer | Tech |
|---|---|
| Scraping | `httpx`, `playwright`, `beautifulsoup4` |
| Dedup | SHA-256 + `sentence-transformers` (MiniLM-L6) |
| Storage | SQLite + SQLAlchemy 2.x |
| LLM | Anthropic Claude + DeepSeek (OpenAI-compatible) |
| Backend | FastAPI + SSE streaming |
| Frontend | React 18 + Vite |
| CLI | Typer + Rich |

---

## Adding a New Job Board

1. Create `scrapers/my_board.py` extending `BaseScraper`
2. Implement `source_name` property and `scrape()` async generator
3. Register in `scrapers/__init__.py` → `SCRAPER_REGISTRY`

```python
class MyBoardScraper(BaseScraper):
    source_name = "myboard.ch"

    async def scrape(self, keyword, location, max_pages):
        # yield ScrapedJob instances
        ...
```

---

## WSL / Windows Notes

If running on WSL with a Windows browser, add to `~/.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

Then `wsl --shutdown` and restart.

---

## Responsible Scraping

- Random delays between requests (1.5–4s)
- Retry with exponential backoff
- Respects rate limits — do not set `SCRAPER_DELAY_MIN` below 1.0

---

## License

MIT © [Leo Zhong](https://github.com/Donvink)

---

<div align="center">
<sub>Built in Zürich · Swiss B Permit holder · Open to collaborations</sub>
</div>
