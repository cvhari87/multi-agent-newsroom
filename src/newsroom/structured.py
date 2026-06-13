"""Validation helpers for structured model responses."""

import json
from collections.abc import Iterable


class StructuredResponseError(ValueError):
    """Raised when a model response does not satisfy its required contract."""


def parse_json_array(raw: str) -> list[dict]:
    """Parse a JSON array and reject malformed or non-object entries."""
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) < 3:
            raise StructuredResponseError("Unclosed markdown fence in model response")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]

    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise StructuredResponseError(f"Invalid JSON response: {exc}") from exc

    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise StructuredResponseError("Expected a JSON array of objects")
    return parsed


def index_complete_results(
    results: list[dict],
    expected_urls: Iterable[str],
) -> dict[str, dict]:
    """Index results by URL and require exactly one result for every expected URL."""
    expected = list(expected_urls)
    expected_set = set(expected)
    indexed: dict[str, dict] = {}

    for result in results:
        url = result.get("url")
        if not isinstance(url, str) or not url:
            raise StructuredResponseError("Every result must include a non-empty URL")
        if url in indexed:
            raise StructuredResponseError(f"Duplicate result for URL: {url}")
        indexed[url] = result

    missing = expected_set - indexed.keys()
    unexpected = indexed.keys() - expected_set
    if missing or unexpected or len(indexed) != len(expected):
        raise StructuredResponseError(
            f"Result URL mismatch; missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    return indexed


def require_fields(result: dict, fields: Iterable[str], *, url: str) -> None:
    """Require fields that must not be silently replaced with defaults."""
    missing = [field for field in fields if field not in result]
    if missing:
        raise StructuredResponseError(f"Result for {url} is missing fields: {missing}")
