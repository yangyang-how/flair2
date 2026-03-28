"""Shared provider utilities."""

import re


def extract_json(text: str) -> str:
    """Extract JSON from LLM response, stripping markdown fences."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return text
    return text
