"""
Central configuration — loaded from .env / environment variables.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
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

    # ── Ollama ─────────────────────────────────────────────────────────────────
    ollama_base_url: str = ""
    ollama_model: str = "qwen3.6:latest"
    ollama_think: bool = False

    # ── LLM routing ────────────────────────────────────────────────────────────
    # "auto"        → round-robin between all configured providers
    # "anthropic"   → always use Anthropic
    # "deepseek"    → always use DeepSeek
    # "openrouter"  → always use OpenRouter
    # "ollama"      → always use Ollama (local, no API key required)
    llm_provider: Literal["auto", "anthropic", "deepseek", "openrouter", "ollama"] = "auto"

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/jobs.db"

    # ── Search defaults ────────────────────────────────────────────────────────
    default_keyword: str = "Agent"
    default_location: str = "Zürich"
    default_language: Literal["en", "de", "fr"] = "en"
    search_radius_km: int = 30

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
    def check_at_least_one_llm(self) -> "Settings":
        has_cloud = self.anthropic_api_key or self.deepseek_api_key or self.openrouter_api_key
        has_local = bool(self.ollama_base_url)
        if not has_cloud and not has_local:
            raise ValueError(
                "At least one LLM provider is required: set ANTHROPIC_API_KEY, "
                "DEEPSEEK_API_KEY, OPENROUTER_API_KEY, or OLLAMA_BASE_URL in .env"
            )
        return self


# Singleton — import this everywhere
settings = Settings()  # type: ignore[call-arg]
