"""
Interview coach — critique an interview answer and produce an optimized rewrite,
drawing on the candidate's full STAR story library.
"""
from __future__ import annotations

import json

from db.models import StarStory
from llm.json_repair import parse_llm_json
from llm.router import call_llm


def _format_stories(stories: list[StarStory]) -> str:
    if not stories:
        return "(no stories in library)"
    blocks = []
    for s in stories:
        blocks.append(
            f"### {s.title}\n"
            f"Situation: {s.situation}\n"
            f"Task: {s.task}\n"
            f"Action: {s.action}\n"
            f"Result: {s.result}"
        )
    return "\n\n".join(blocks)


async def optimize_answer(question: str, my_answer: str, stories: list[StarStory]) -> dict:
    """
    Returns:
    {
      "critique": "what's weak about the current answer",
      "optimized_answer": "rewritten answer",
      "stories_used": ["title1", ...]
    }
    """
    system = (
        "You are an expert interview coach helping a candidate prepare sharper, "
        "more structured answers for technical and behavioral interviews. You give "
        "concrete, actionable feedback — not vague advice. Respond only with valid JSON."
    )

    stories_block = _format_stories(stories)

    user = f"""Critique and improve the candidate's interview answer below, drawing on their STAR story library where relevant.

## Question
{question[:2000]}

## Candidate's answer
{my_answer[:4000]}

## Candidate's STAR story library
{stories_block[:8000]}

Return ONLY valid JSON (no markdown fences):
{{
  "critique": "concise assessment of what's weak or missing in the current answer",
  "optimized_answer": "rewritten answer, using STAR structure and pulling from the library where it strengthens the answer",
  "stories_used": ["title of any library story incorporated into the optimized answer"]
}}

Rules:
- Do NOT invent experience or stories the candidate doesn't have
- Only reference stories_used titles that appear in the library above"""

    raw, provider = await call_llm(user=user, system=system, max_tokens=2000)
    print(f"[interview_coach] generated via {provider}")

    try:
        return parse_llm_json(raw)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": raw[:500]}
