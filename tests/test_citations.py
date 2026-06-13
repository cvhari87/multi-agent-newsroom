from newsroom.citations import citation_issues


def _story(briefing: str, sources_json: list[dict]) -> dict:
    return {
        "full_briefing": briefing,
        "sources_json": sources_json,
        "supporting_sources": [{"name": "Source", "url": "https://source.example"}],
    }


def test_citation_issues_accepts_verified_inline_citation() -> None:
    story = _story(
        "Supported claim [Source](https://source.example).",
        [{"name": "Source", "url": "https://source.example"}],
    )

    assert citation_issues(story) == []


def test_citation_issues_rejects_unverified_url() -> None:
    story = _story(
        "Unsupported claim [Other](https://other.example).",
        [{"name": "Other", "url": "https://other.example"}],
    )

    assert any("unverified URLs" in issue for issue in citation_issues(story))
