# syntax=docker/dockerfile:1

# ── Swiss Job Hunter — backend API ───────────────────────────────────────────
# FastAPI + scrapers (incl. Playwright/Chromium) + sentence-transformers.
FROM python:3.11-slim

# Avoid interactive prompts and keep Python output unbuffered for clean logs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Persist the HuggingFace cache (MiniLM embedding model) on a named volume
    # so it is not re-downloaded on every container recreation.
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# System build/runtime essentials. lxml needs libxml2/libxslt headers at build
# time; the rest are pulled in by `playwright install --with-deps` below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install the matching Chromium for the resolved Playwright version plus all of
# its system libraries (robust against Playwright version drift).
RUN playwright install --with-deps chromium

# Copy the application source (respecting .dockerignore).
COPY . .

EXPOSE 8765

# Run the API without --reload (production). The package + llm/prompts/*.txt
# package-data resolve relative to this WORKDIR, so no install step is needed.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8765"]
