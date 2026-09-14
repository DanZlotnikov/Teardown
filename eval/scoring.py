"""Objective scoring primitives used before any model judge."""
from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(text: str) -> dict | None:
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def required_phrase_recall(text: str, phrases: list[str]) -> float:
    if not phrases:
        return 1.0
    normalized = text.casefold()
    return sum(phrase.casefold() in normalized for phrase in phrases) / len(phrases)


def retrieval_recall(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    if not relevant_ids:
        return 1.0
    found = set(retrieved_ids[:k])
    return len(found.intersection(relevant_ids)) / len(set(relevant_ids))


def normalized_token_jaccard(left: str, right: str) -> float:
    tokenize = lambda value: set(re.findall(r"[a-z0-9]+", value.casefold()))
    a, b = tokenize(left), tokenize(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)
