"""
Cover letter generation — routes through llm.router (Anthropic / DeepSeek).
Supports English and German output.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from config.settings import settings
from db.models import Job
from llm.router import call_llm

_PROMPT_DIR = Path(__file__).parent / "prompts"
Language = Literal["en", "de"]


def _load_prompt(language: Language) -> str:
    p = _PROMPT_DIR / f"cover_letter_{language}.txt"
    return p.read_text(encoding="utf-8")


def _build_salutation(company: str, language: Language) -> str:
    if language == "de":
        return f"Sehr geehrte Damen und Herren bei {company},"
    return f"Dear Hiring Team at {company},"


async def generate_cover_letter(
    job: Job,
    cv_text: str,
    language: Language = "en",
    max_tokens: int = 800,
) -> str:
    """
    Generate a personalized cover letter for `job` using the candidate's CV.
    Automatically rotates between Anthropic and DeepSeek per LLM_PROVIDER setting.

    Returns the full letter (salutation + body + sign-off).
    """
    template = _load_prompt(language)
    user_prompt = template.format(
        cv_text=cv_text[:4000],
        job_title=job.title,
        company=job.company,
        location=job.location,
        jd_text=job.description[:3000],
    )

    body, provider = await call_llm(
        user=user_prompt,
        system="You are an expert career coach specializing in Swiss tech job applications.",
        max_tokens=max_tokens,
    )
    print(f"[cover letter] generated via {provider}")

    salutation = _build_salutation(job.company, language)
    from config.settings import settings
    name = settings.apply_from_name or "Your Name"
    sign_off = (
        f"\n\nMit freundlichen Grüßen,\n{name}"
        if language == "de"
        else f"\n\nBest regards,\n{name}"
    )
    return f"{salutation}\n\n{body}{sign_off}"


def save_cover_letter(
    job: Job, letter: str, output_dir: Path = Path("./data/letters")
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_company = job.company.replace(" ", "_").replace("/", "-")[:30]
    filename = f"cover_letter_{job.id}_{safe_company}.txt"
    path = output_dir / filename
    path.write_text(letter, encoding="utf-8")
    return path
