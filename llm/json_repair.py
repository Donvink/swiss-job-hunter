"""
Shared JSON-repair helper for parsing LLM completions expected to be JSON.
"""
from __future__ import annotations

import json
import re


def _close_unterminated(json_str: str) -> str:
    """
    Best-effort close of JSON truncated mid-stream: close a dangling open
    string literal, drop a trailing comma left hanging by the cut, then close
    any unclosed brackets/braces innermost-first (tracked via a scan stack,
    since a flat count of '{'/'}' can't tell nesting order apart).
    """
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in json_str:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack and ((ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")):
                stack.pop()

    repaired = json_str + '"' if in_string else json_str
    repaired = re.sub(r",\s*$", "", repaired.rstrip())
    for opener in reversed(stack):
        repaired += "}" if opener == "{" else "]"
    return repaired


def parse_llm_json(raw: str) -> dict:
    """
    Extract and parse a JSON object from a raw LLM completion.
    Strips markdown fences, normalises smart quotes and literal newlines inside
    string values, then repairs truncated JSON (dangling trailing commas,
    unclosed strings/brackets/braces from a response cut off mid-stream)
    before retrying. Raises json.JSONDecodeError if still unparseable.
    """
    text = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    text = re.sub(r"\n?```$", "", text)

    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("no JSON object found in response", text, 0)

    # Prefer the span up through the last '}' in the text (drops trailing
    # prose after a properly-closed object); if the text never closes at all
    # (cut off mid-stream with no '}' anywhere), fall back to everything from
    # the first '{' onward so the repair step below has something to work with.
    m = re.search(r"\{.*\}", text[start:], re.DOTALL)
    json_str = text[start:][: m.end()] if m else text[start:]

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
        pass

    # Trailing/dangling commas before a closer (",}" / ",]") anywhere in the
    # string, not just at the very end.
    fixed = re.sub(r",(\s*[}\]])", r"\1", json_str)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    return json.loads(_close_unterminated(fixed))
