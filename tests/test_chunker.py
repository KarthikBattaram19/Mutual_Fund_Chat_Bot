import pytest

from ingestion.chunker import ChunkerError, FieldChunker
from ingestion.extractor import ExtractedFact, ExtractedSchemeFacts


def fact(field: str, content: str) -> ExtractedFact:
    return ExtractedFact(
        field=field,
        label=content.split(":", 1)[0],
        value=content.split(":", 1)[1].strip(),
        content=content,
        source="dom",
        source_url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    )


def extracted_scheme(**overrides) -> ExtractedSchemeFacts:
    values = {
        "scheme_name": "HDFC Large Cap Fund - Direct Growth",
        "scheme_slug": "hdfc-large-cap-fund-direct-growth",
        "category": "Large Cap (Equity)",
        "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        "fetched_at": "2026-06-28T00:00:00Z",
        "facts": {
            "expense_ratio": fact("expense_ratio", "Expense ratio: 0.88%"),
            "nav": fact("nav", "NAV: Rs 1,024.18"),
            "lock_in": fact("lock_in", "Lock-in period: No lock-in"),
        },
        "missing_fields": ["aum"],
        "filtered_count": 2,
        "warnings": ["Filtered content candidates: 2", "Missing fields: aum"],
    }
    values.update(overrides)
    return ExtractedSchemeFacts(**values)


def test_chunk_scheme_emits_one_chunk_per_present_canonical_field() -> None:
    chunks = FieldChunker().chunk_scheme(extracted_scheme())

    assert [chunk.field for chunk in chunks] == ["nav", "expense_ratio", "lock_in"]
    assert [chunk.chunk_id for chunk in chunks] == [
        "hdfc-large-cap-fund-direct-growth:nav",
        "hdfc-large-cap-fund-direct-growth:expense_ratio",
        "hdfc-large-cap-fund-direct-growth:lock_in",
    ]


def test_chunk_contains_expected_metadata_and_content() -> None:
    chunks = FieldChunker().chunk_scheme(extracted_scheme())
    expense_ratio_chunk = next(chunk for chunk in chunks if chunk.field == "expense_ratio")

    assert expense_ratio_chunk.to_dict() == {
        "chunk_id": "hdfc-large-cap-fund-direct-growth:expense_ratio",
        "scheme_name": "HDFC Large Cap Fund - Direct Growth",
        "scheme_slug": "hdfc-large-cap-fund-direct-growth",
        "category": "Large Cap (Equity)",
        "field": "expense_ratio",
        "content": "Expense ratio: 0.88%",
        "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        "fetched_at": "2026-06-28T00:00:00Z",
    }


def test_chunker_does_not_index_missing_fields_warnings_or_filtered_counts() -> None:
    chunks = FieldChunker().chunk_scheme(extracted_scheme())
    chunk_text = " ".join(chunk.content for chunk in chunks)

    assert "Missing fields" not in chunk_text
    assert "Filtered content candidates" not in chunk_text
    assert "filtered_count" not in chunk_text
    assert "aum" not in {chunk.field for chunk in chunks}


def test_chunk_many_flattens_chunks_for_multiple_schemes() -> None:
    second_scheme = extracted_scheme(
        scheme_name="HDFC Mid Cap Fund - Direct Growth",
        scheme_slug="hdfc-mid-cap-fund-direct-growth",
        source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        facts={"category": fact("category", "Category: Mid Cap (Equity)")},
    )

    chunks = FieldChunker().chunk_many([extracted_scheme(), second_scheme])

    assert len(chunks) == 4
    assert chunks[-1].chunk_id == "hdfc-mid-cap-fund-direct-growth:category"


def test_chunker_returns_no_chunks_when_no_facts_are_present() -> None:
    chunks = FieldChunker().chunk_scheme(extracted_scheme(facts={}))

    assert chunks == []


def test_chunker_rejects_missing_required_scheme_metadata() -> None:
    with pytest.raises(ChunkerError, match="scheme_slug"):
        FieldChunker().chunk_scheme(extracted_scheme(scheme_slug=""))
