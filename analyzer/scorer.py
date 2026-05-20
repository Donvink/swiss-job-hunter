"""
CV ↔ Job Description match scorer.

Two modes:
  1. Fast (keyword overlap) — no API call, runs on all new jobs.
  2. LLM (semantic)        — routes through llm.router, runs on shortlisted jobs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config.settings import settings

# ── Skill keywords grouped by category ────────────────────────────────────────
# Each tuple: (pattern, weight)
# Weight > 1 = core skill (from Leo's CV), counted more heavily

_WEIGHTED_SKILLS: list[tuple[str, float]] = [
    # ── Core perception / AD (Leo's primary expertise) ────────────────────────
    (r"perception",                 2.0),
    (r"autonomous driving",         2.0),
    (r"self.?driving",              2.0),
    (r"adas",                       2.0),
    (r"bev",                        2.0),
    (r"bird.?s.?eye.?view",         2.0),
    (r"sparse4d",                   2.0),
    (r"sensor fusion",              2.0),
    (r"radar.?camera",              2.0),
    (r"camera.?radar",              2.0),
    (r"mmwave",                     2.0),
    (r"lidar",                      1.5),
    (r"3d detection",               2.0),
    (r"object detection",           1.5),
    (r"multi.?object tracking",     2.0),
    (r"\bmot\b",                    1.5),
    (r"trajectory prediction",      2.0),
    (r"wayformer",                  2.0),
    (r"vectornet",                  2.0),
    (r"detr",                       1.5),
    (r"deformable",                 1.5),
    (r"yolo",                       1.5),
    (r"c\-ncap",                    1.5),
    (r"fisheye",                    1.5),
    (r"surround.?view",             1.5),

    # ── Model optimization ─────────────────────────────────────────────────────
    (r"quantization",               2.0),
    (r"\bptq\b",                    2.0),
    (r"\bqat\b",                    2.0),
    (r"mixed.?precision",           2.0),
    (r"int8",                       1.5),
    (r"int16",                      1.5),
    (r"edge deployment",            1.5),
    (r"real.?time inference",       1.5),
    (r"latency",                    1.0),
    (r"model optimization",         1.5),
    (r"pruning",                    1.0),

    # ── Deep learning / ML ─────────────────────────────────────────────────────
    (r"deep learning",              1.5),
    (r"machine learning",           1.0),
    (r"computer vision",            1.5),
    (r"transformer",                1.5),
    (r"attention",                  1.0),
    (r"cross.?attention",           1.5),
    (r"multimodal",                 1.5),
    (r"multi.?modal",               1.5),
    (r"generative",                 1.0),
    (r"diffusion",                  1.0),
    (r"llm",                        1.0),
    (r"fine.?tun",                  1.0),
    (r"rlhf",                       1.0),
    (r"\blora\b",                   1.0),

    # ── Frameworks & tools ─────────────────────────────────────────────────────
    (r"pytorch",                    2.0),
    (r"python",                     1.0),
    (r"c\+\+",                      1.5),
    (r"opencv",                     1.5),
    (r"mmdetection",                1.5),
    (r"mmcv",                       1.5),
    (r"cuda",                       1.5),
    (r"tensorrt",                   1.5),
    (r"onnx",                       1.0),
    (r"docker",                     1.0),
    (r"kubernetes",                 1.0),
    (r"ros\b",                      1.0),
    (r"apollo",                     1.0),

    # ── Generic engineering ────────────────────────────────────────────────────
    (r"algorithm engineer",         1.0),
    (r"research engineer",          1.0),
    (r"ml engineer",                1.0),
    (r"ai engineer",                1.0),
    (r"software engineer",          0.8),
    (r"data scientist",             0.5),
]

_COMPILED: list[tuple[re.Pattern, float, str]] = [
    (re.compile(pat, re.IGNORECASE), weight, pat)
    for pat, weight in _WEIGHTED_SKILLS
]


@dataclass
class MatchResult:
    score: float
    matched_skills: list[str]
    missing_skills: list[str]
    explanation: str
    provider: str = "keyword"


def _extract_weighted(text: str) -> dict[str, float]:
    """Return {skill_label: weight} for all patterns found in text."""
    found = {}
    for pat, weight, label in _COMPILED:
        if pat.search(text):
            # Use a clean label
            clean = label.replace("\\b", "").replace("\\.", ".").replace("?", "").strip()
            found[clean] = weight
    return found


def fast_score(cv_text: str, jd_text: str) -> MatchResult:
    """
    Weighted keyword-overlap score.
    Score = sum(weights of matched skills) / sum(weights of all JD skills)
    Capped at 1.0.
    """
    if not jd_text or len(jd_text.strip()) < 50:
        return MatchResult(
            score=0.0, matched_skills=[], missing_skills=[],
            explanation="JD too short — run Enrich first for better scoring.",
        )

    cv_skills  = _extract_weighted(cv_text)
    jd_skills  = _extract_weighted(jd_text)

    if not jd_skills:
        return MatchResult(
            score=0.2, matched_skills=[], missing_skills=[],
            explanation="No recognizable technical keywords found in JD.",
        )

    matched  = {k: w for k, w in jd_skills.items() if k in cv_skills}
    missing  = {k: w for k, w in jd_skills.items() if k not in cv_skills}

    total_jd_weight  = sum(jd_skills.values())
    matched_weight   = sum(matched.values())
    score = min(matched_weight / total_jd_weight, 1.0)

    # Sort by weight descending for display
    matched_list = sorted(matched, key=lambda k: -matched[k])
    missing_list = sorted(missing, key=lambda k: -missing[k])

    explanation = (
        f"Matched {len(matched)}/{len(jd_skills)} keywords "
        f"(weighted score {score:.0%}). "
        + (f"Key matches: {', '.join(matched_list[:5])}. " if matched_list else "")
        + (f"Missing: {', '.join(missing_list[:4])}." if missing_list else "Perfect match!")
    )

    return MatchResult(
        score=round(score, 3),
        matched_skills=matched_list,
        missing_skills=missing_list,
        explanation=explanation,
    )


async def llm_score(cv_text: str, job_title: str, jd_text: str) -> MatchResult:
    """Deep LLM-based scoring via Claude / DeepSeek."""
    from llm.router import call_llm

    system = (
        "You are an expert technical recruiter evaluating a candidate for a job in Switzerland. "
        "The candidate is a Senior ML/Perception Engineer specializing in autonomous driving. "
        "Respond only with valid JSON."
    )
    user = f"""Evaluate this candidate's fit for the job.

## Candidate CV
{cv_text[:4000]}

## Job: {job_title}
{jd_text[:3000]}

Return ONLY valid JSON (no markdown):
{{
  "score": <float 0.0-1.0>,
  "matched_skills": ["skill1", "skill2"],
  "missing_skills": ["skill3"],
  "explanation": "2-3 sentence assessment focusing on technical fit and role alignment"
}}"""

    raw, provider = await call_llm(user=user, system=system, max_tokens=600)

    # Strip markdown fences
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    raw = re.sub(r"\n?```$", "", raw)

    # Extract JSON object even if there's surrounding text
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return MatchResult(
            score=0.0, matched_skills=[], missing_skills=[],
            explanation=f"LLM returned unparseable response: {raw[:100]}",
            provider=provider,
        )

    # Clean common JSON issues: smart quotes, unescaped newlines in strings
    json_str = m.group(0)
    json_str = json_str.replace('\u201c', '"').replace('\u201d', '"')
    json_str = json_str.replace('\u2018', "'").replace('\u2019', "'")
    # Remove literal newlines inside string values
    json_str = re.sub(r'(?<=:)\s*"([^"]*?)\n([^"]*?)"', 
                      lambda x: ': "' + x.group(1) + ' ' + x.group(2) + '"', 
                      json_str)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Last resort: extract fields with regex
        score_m = re.search(r'"score"\s*:\s*([0-9.]+)', json_str)
        expl_m  = re.search(r'"explanation"\s*:\s*"([^"]{10,})"', json_str)
        return MatchResult(
            score=float(score_m.group(1)) if score_m else 0.0,
            matched_skills=[],
            missing_skills=[],
            explanation=expl_m.group(1) if expl_m else "Parse error",
            provider=provider,
        )
    return MatchResult(
        score=float(data.get("score", 0.0)),
        matched_skills=data.get("matched_skills", []),
        missing_skills=data.get("missing_skills", []),
        explanation=data.get("explanation", ""),
        provider=provider,
    )


def load_cv_text(path: Optional[Path] = None, direction: Optional[str] = None) -> str:
    if direction:
        candidate = Path(f"./data/cv_{direction}.txt")
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    p = path or settings.cv_text_path
    if not p.exists():
        raise FileNotFoundError(
            f"CV text not found at {p}. "
            "Copy your CV as plain text to data/cv.txt"
        )
    return p.read_text(encoding="utf-8")
