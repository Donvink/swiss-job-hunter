"""Table-driven tests for the shared LLM JSON-repair helper."""
import json

import pytest

from llm.json_repair import parse_llm_json


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param('{"score": 0.8, "notes": "fine"}', {"score": 0.8, "notes": "fine"}, id="plain-json"),
        pytest.param(
            '```json\n{"score": 0.8, "notes": "fine"}\n```',
            {"score": 0.8, "notes": "fine"},
            id="fenced-with-lang",
        ),
        pytest.param(
            '```\n{"score": 0.8, "notes": "fine"}\n```',
            {"score": 0.8, "notes": "fine"},
            id="fenced-no-lang",
        ),
        pytest.param(
            'Here is the result:\n{"score": 0.8, "notes": "fine"}\nHope that helps!',
            {"score": 0.8, "notes": "fine"},
            id="surrounding-prose",
        ),
        pytest.param(
            '{“score”: 0.8, “notes”: “fine”}',
            {"score": 0.8, "notes": "fine"},
            id="smart-double-quotes",
        ),
        pytest.param(
            '{"score": 0.8, "meta": {"provider": "openai"}, "notes": "cut off mid',
            {"score": 0.8, "meta": {"provider": "openai"}},
            id="truncated-after-a-closed-nested-object",
        ),
        pytest.param(
            '{"score": 0.8, "notes": "trailing comma",}',
            {"score": 0.8, "notes": "trailing comma"},
            id="trailing-comma-before-closing-brace",
        ),
        pytest.param(
            '{"score": 0.8, "matched_skills": ["python", "sql",]}',
            {"score": 0.8, "matched_skills": ["python", "sql"]},
            id="trailing-comma-before-closing-bracket",
        ),
        pytest.param(
            '{"score": 0.8, "matched_skills": ["python", "sql"], "explanation": "great fit for the ro',
            {"score": 0.8, "matched_skills": ["python", "sql"], "explanation": "great fit for the ro"},
            id="flat-object-truncated-mid-string-with-no-closing-brace",
        ),
    ],
)
def test_parse_llm_json_valid_inputs(raw, expected):
    assert parse_llm_json(raw) == expected


def test_parse_llm_json_no_object_found_raises():
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("no json here at all")


def test_parse_llm_json_unrepairable_truncation_raises():
    """A malformed token (here: "0." with no trailing digit) isn't something
    bracket/string repair can fix — it should still raise."""
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json('{"score": 0.')
