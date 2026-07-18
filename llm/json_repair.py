"""
Shared JSON-repair helper for parsing LLM completions expected to be JSON.
"""
from __future__ import annotations

import json
import re


def parse_llm_json(raw: str) -> dict:
    """
    Extract and parse a JSON object from a raw LLM completion.
    Strips markdown fences, normalises smart quotes and literal newlines inside
    string values, then repairs truncated JSON by closing unbalanced brackets/
    braces before retrying. Raises json.JSONDecodeError if still unparseable.
    """
    text = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    text = re.sub(r"\n?```$", "", text)

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise json.JSONDecodeError("no JSON object found in response", text, 0)

    json_str = m.group(0)
    json_str = json_str.replace("“", '"').replace("”", '"')
    json_str = json_str.replace("‘", "'").replace("’", "'")
    json_str = re.sub(
        r'(?<=:)\s*"([^"]*?)\n([^"]*?)"',
        lambda x: ': "' + x.group(1) + " " + x.group(2) + '"',
        json_str,
    )

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        fixed = json_str.rstrip().rstrip(",")
        open_brackets = fixed.count("[") - fixed.count("]")
        open_braces = fixed.count("{") - fixed.count("}")
        fixed += "]" * max(0, open_brackets) + "}" * max(0, open_braces)
        return json.loads(fixed)
