"""
LLM provider router — round-robin between Anthropic and DeepSeek.

DeepSeek is OpenAI-compatible, so we use the openai SDK for it.
Anthropic uses its own SDK.

Usage:
    from llm.router import call_llm

    text = await call_llm(
        system="You are a helpful assistant.",
        user="Write a cover letter for...",
        max_tokens=800,
    )
"""
from __future__ import annotations

import asyncio
import itertools
from typing import Optional

LLM_TIMEOUT = 60  # seconds; hung API calls are cancelled and re-raise TimeoutError

from config.settings import settings

# ── Build the provider cycle ───────────────────────────────────────────────────

def _build_cycle() -> itertools.cycle:
    """
    Build a round-robin cycle from whichever providers are configured.
    If LLM_PROVIDER is pinned to a specific provider, always use that one.
    """
    if settings.llm_provider == "anthropic":
        return itertools.cycle(["anthropic"])
    if settings.llm_provider == "deepseek":
        return itertools.cycle(["deepseek"])

    # "auto" — include only providers that have a key set
    available: list[str] = []
    if settings.anthropic_api_key:
        available.append("anthropic")
    if settings.deepseek_api_key:
        available.append("deepseek")

    if not available:
        raise RuntimeError("No LLM provider configured. Set ANTHROPIC_API_KEY or DEEPSEEK_API_KEY.")

    return itertools.cycle(available)


_provider_cycle = _build_cycle()


def _next_provider() -> str:
    return next(_provider_cycle)


# ── Anthropic call ─────────────────────────────────────────────────────────────

async def _call_anthropic(system: str, user: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages = [{"role": "user", "content": user}]
    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text.strip()


# ── DeepSeek call (OpenAI-compatible) ─────────────────────────────────────────

async def _call_deepseek(system: str, user: str, max_tokens: int) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    response = await client.chat.completions.create(
        model=settings.deepseek_model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (response.choices[0].message.content or "").strip()


# ── Public interface ───────────────────────────────────────────────────────────

async def call_llm(
    user: str,
    system: str = "You are a helpful assistant.",
    max_tokens: int = 1000,
    provider: Optional[str] = None,  # override round-robin for this call
) -> tuple[str, str]:
    """
    Call the next LLM provider in rotation.

    Returns:
        (response_text, provider_used)  — so callers can log which provider ran.
    """
    p = provider or _next_provider()

    if p == "anthropic":
        coro = _call_anthropic(system, user, max_tokens)
    elif p == "deepseek":
        coro = _call_deepseek(system, user, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {p}")

    text = await asyncio.wait_for(coro, timeout=LLM_TIMEOUT)
    return text, p
