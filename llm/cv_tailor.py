"""
CV tailoring — compare a job description against the candidate's CV and produce
specific bullet-point rewrite suggestions.
"""
from __future__ import annotations

import json
import re

from db.models import Job
from llm.json_repair import parse_llm_json
from llm.router import call_llm

# Section headers that signal the start of requirements content
_REQ_START = re.compile(
    r"^[ \t]*("
    r"requirement|qualification|what you('ll| will)? (need|bring)|"
    r"your (profile|background|experience|skills)|"
    r"who you are|what we('re| are) looking for|"
    r"must.have|nice.to.have|preferred|"
    r"responsibilities|what you('ll| will)? do|role overview|about the role|"
    r"ihr profil|anforderung|aufgaben|was (wir suchen|sie mitbringen)|"
    r"votre profil|compétences requises"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

# Section headers that signal boilerplate we want to drop
_NOISE_START = re.compile(
    r"^[ \t]*("
    r"about (us|the company|the team)|who we are|our (company|mission|values|culture)|"
    r"we offer|what we offer|benefits|perks|compensation|salary|"
    r"how to apply|application process|equal opportunity|diversity|"
    r"über uns|wir bieten|unser angebot|"
    r"à propos|nous offrons"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def extract_jd_requirements(jd: str) -> str:
    """
    Extract only the requirements/responsibilities sections from a JD.
    Falls back to the full text if no known headers are found.
    """
    lines = jd.splitlines()
    total = len(lines)
    if total < 10:
        return jd

    # Find all candidate section boundaries
    req_positions = [m.start() for m in _REQ_START.finditer(jd)]
    noise_positions = [m.start() for m in _NOISE_START.finditer(jd)]

    if not req_positions:
        return jd  # no recognisable structure — return full text

    # Build character-offset ranges to keep
    keep_ranges: list[tuple[int, int]] = []
    for start_char in req_positions:
        # End at the next noise section or another noise block, whichever comes first
        end_candidates = [p for p in noise_positions if p > start_char]
        end_char = end_candidates[0] if end_candidates else len(jd)
        keep_ranges.append((start_char, end_char))

    if not keep_ranges:
        return jd

    extracted = "\n\n".join(jd[s:e].strip() for s, e in keep_ranges)
    # Sanity check: if extraction is tiny, the headers probably didn't match well
    if len(extracted) < 200:
        return jd
    return extracted


async def tailor_cv(job: Job, cv_text: str) -> dict:
    """
    Returns:
    {
      "missing_keywords": ["kw1", ...],
      "suggestions": [
        {"section": "...", "original": "...", "rewrite": "...", "reason": "..."},
        ...
      ],
      "ats_cv": "full plain-text ATS-optimised CV"
    }
    """
    system = (
        "You are an expert technical resume coach specialising in ATS optimisation "
        "for Swiss tech and engineering jobs. You give concrete, actionable rewrites — "
        "not vague advice. Respond only with valid JSON."
    )

    jd_core = extract_jd_requirements(job.description or "")

    user = f"""Tailor the candidate's CV for the job below.

## Job: {job.title} at {job.company}
{jd_core[:5000]}

## Candidate CV
{cv_text[:8000]}

Return ONLY valid JSON (no markdown fences):
{{
  "missing_keywords": ["keyword from JD that is absent from CV but candidate likely has"],
  "suggestions": [
    {{
      "section": "which CV section / experience entry (e.g. 'Experience — Motovis 2021-2024')",
      "original": "exact original bullet or phrase from the CV",
      "rewrite": "improved version that naturally incorporates missing JD keywords",
      "reason": "which JD requirement this addresses"
    }}
  ]
}}

Rules:
- suggestions: 3-6 most impactful changes only
- Do NOT invent experience or skills the candidate doesn't have"""

    raw, provider = await call_llm(user=user, system=system, max_tokens=2500)
    print(f"[cv_tailor] generated via {provider}")

    try:
        return parse_llm_json(raw)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": raw[:500]}
