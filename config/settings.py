"""
Central configuration — loaded from .env / environment variables.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Anthropic ──────────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    anthropic_model: str = "claude-sonnet-4-20250514"

    # ── DeepSeek ───────────────────────────────────────────────────────────────
    deepseek_api_key: str = Field(default="", description="DeepSeek API key")
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    # ── OpenRouter ─────────────────────────────────────────────────────────────
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── LLM routing ────────────────────────────────────────────────────────────
    # "auto"        → round-robin between all configured providers
    # "anthropic"   → always use Anthropic
    # "deepseek"    → always use DeepSeek
    # "openrouter"  → always use OpenRouter
    llm_provider: Literal["auto", "anthropic", "deepseek", "openrouter"] = "auto"

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/jobs.db"

    # ── Search defaults ────────────────────────────────────────────────────────
    default_keyword: str = "Agent"
    default_location: str = "Zürich"
    default_language: Literal["en", "de", "fr"] = "en"
    search_radius_km: int = 30

    # ── Keyword presets ────────────────────────────────────────────────────────
    # JSON object mapping preset name → list of keywords.
    # Example in .env:
    #   KEYWORD_PRESETS={"agent": ["AI engineer", "LLM engineer"], "devops": ["DevOps engineer", "SRE"]}
    keyword_presets: dict[str, list[str]] = Field(
        default={
            "perception": [
                "computer vision engineer", "ADAS engineer", "sensor fusion engineer",
                "autonomous driving engineer", "robotics engineer", "perception engineer",
                "SLAM engineer", "robot perception engineer", "motion planning engineer",
                "autonomous systems engineer", "robotics software engineer",
            ],
            "agent": [
                "machine learning engineer", "AI engineer", "deep learning engineer",
                "LLM Application Engineer", "agentic AI", "GenAI engineer",
                "MLOps engineer", "AI software engineer", "applied scientist",
            ],
        },
        description="Keyword presets as JSON: {preset_name: [keyword, ...]}",
    )

    @field_validator("keyword_presets", mode="before")
    @classmethod
    def parse_keyword_presets(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"KEYWORD_PRESETS is not valid JSON: {e}") from e
        return v

    # ── Dedup ──────────────────────────────────────────────────────────────────
    semantic_similarity_threshold: float = 0.92
    embedding_model: str = "all-MiniLM-L6-v2"

    # ── Scraper ────────────────────────────────────────────────────────────────
    scraper_delay_min: float = 1.5
    scraper_delay_max: float = 4.0
    scraper_max_pages: int = 10
    playwright_headless: bool = True

    # ── LinkedIn ───────────────────────────────────────────────────────────────
    # Paste the value of the `li_at` cookie from your browser (F12 → Application
    # → Cookies → linkedin.com). Enables authenticated search (1000+ results).
    # Leave empty to use the public guest search (~40 results max).
    linkedin_cookie: str = ""
    # Optional HTTP/HTTPS/SOCKS5 proxy, e.g. "http://user:pass@host:port"
    # or "socks5://host:port". Switch this when your IP gets blocked.
    linkedin_proxy: str = ""

    # ── Email ──────────────────────────────────────────────────────────────────
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    apply_from_email: str = ""
    apply_from_name: str = ""

    # ── CV ─────────────────────────────────────────────────────────────────────
    cv_pdf_path: Path = Path("./data/cv.pdf")
    cv_text_path: Path = Path("./data/cv.txt")

    # ── Scheduler ──────────────────────────────────────────────────────────────
    schedule_enabled: bool = False
    schedule_cron: str = "0 8 * * 1-5"

    @model_validator(mode="after")
    def check_at_least_one_llm_key(self) -> "Settings":
        if not self.anthropic_api_key and not self.deepseek_api_key and not self.openrouter_api_key:
            raise ValueError(
                "At least one LLM API key is required: "
                "set ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, or OPENROUTER_API_KEY in .env"
            )
        return self


# Singleton — import this everywhere
settings = Settings()  # type: ignore[call-arg]
