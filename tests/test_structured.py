import pytest

from newsroom.structured import (
    StructuredResponseError,
    index_complete_results,
    parse_json_array,
    require_fields,
)


def test_parse_json_array_accepts_fenced_json() -> None:
    assert parse_json_array('```json\n[{"url": "https://example.com"}]\n```') == [
        {"url": "https://example.com"}
    ]


def test_index_complete_results_rejects_missing_story() -> None:
    with pytest.raises(StructuredResponseError, match="missing"):
        index_complete_results(
            [{"url": "https://one.example"}],
            ["https://one.example", "https://two.example"],
        )


def test_index_complete_results_rejects_duplicate_story() -> None:
    with pytest.raises(StructuredResponseError, match="Duplicate"):
        index_complete_results(
            [
                {"url": "https://one.example"},
                {"url": "https://one.example"},
            ],
            ["https://one.example"],
        )


def test_require_fields_rejects_incomplete_result() -> None:
    with pytest.raises(StructuredResponseError, match="missing fields"):
        require_fields({"url": "https://one.example"}, ("action",), url="https://one.example")
