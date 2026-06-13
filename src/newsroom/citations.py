"""Deterministic citation checks for generated briefings."""

import re

from newsroom.models import WrittenStory

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")


def citation_issues(story: WrittenStory) -> list[str]:
    """Return citation problems that do not require model judgement."""
    cited_urls = set(MARKDOWN_LINK.findall(story["full_briefing"]))
    allowed_urls = {source["url"] for source in story["supporting_sources"]}
    issues: list[str] = []

    if not cited_urls:
        issues.append("Briefing contains no inline source citations.")

    unsupported = sorted(cited_urls - allowed_urls)
    if unsupported:
        issues.append(f"Briefing cites unverified URLs: {unsupported}")

    declared_urls = {
        source.get("url", "")
        for source in story["sources_json"]
        if isinstance(source, dict)
    }
    undeclared = sorted(cited_urls - declared_urls)
    if undeclared:
        issues.append(f"Inline citations missing from sources_json: {undeclared}")

    return issues
