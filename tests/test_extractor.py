import pytest

from ingestion.extractor import CANONICAL_FIELDS, FactExtractor
from ingestion.parser import ParsedFact, ParsedPage


CORPUS_ENTRY = {
    "scheme_name": "HDFC Large Cap Fund - Direct Growth",
    "scheme_slug": "hdfc-large-cap-fund-direct-growth",
    "category": "Large Cap (Equity)",
    "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "fetched_at": None,
}


def test_extractor_normalizes_canonical_facts_and_attaches_metadata() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title="HDFC Large Cap Fund - Direct Growth",
        facts=[
            ParsedFact(field="nav", label="NAV", value="  ₹ 1,024.18 ", source="dom"),
            ParsedFact(field="expense_ratio", label="Expense Ratio", value=" 0.88 % ", source="dom"),
            ParsedFact(field="exit_load", label="Exit Load", value="Nil", source="dom"),
            ParsedFact(field="min_sip", label="Min SIP", value="INR 100", source="dom"),
            ParsedFact(field="riskometer", label="Riskometer", value="Very High", source="dom"),
            ParsedFact(field="benchmark", label="Benchmark", value="NIFTY 100 TRI", source="dom"),
            ParsedFact(field="fund_manager", label="Fund Manager", value="Jane Doe", source="dom"),
            ParsedFact(field="aum", label="Fund Size", value="Rs. 32,100 Cr", source="dom"),
            ParsedFact(field="lock_in", label="Lock-in Period", value="No lock-in", source="dom"),
        ],
    )

    extracted = FactExtractor().extract(parsed_page, CORPUS_ENTRY, fetched_at="2026-06-28T00:00:00Z")

    assert extracted.ok
    assert extracted.scheme_name == "HDFC Large Cap Fund - Direct Growth"
    assert extracted.scheme_slug == "hdfc-large-cap-fund-direct-growth"
    assert extracted.category == "Large Cap (Equity)"
    assert extracted.source_url == CORPUS_ENTRY["source_url"]
    assert extracted.fetched_at == "2026-06-28T00:00:00Z"
    assert extracted.facts["nav"].value == "Rs 1,024.18"
    assert extracted.facts["expense_ratio"].content == "Expense ratio: 0.88%"
    assert extracted.facts["min_sip"].value == "Rs 100"
    assert extracted.facts["aum"].content == "AUM: Rs 32,100 Cr"
    assert extracted.facts["category"].source == "metadata"
    assert extracted.missing_fields == []


def test_extractor_records_missing_fields_explicitly() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title=None,
        facts=[ParsedFact(field="nav", label="NAV", value="Rs 100.00", source="dom")],
    )

    extracted = FactExtractor().extract(parsed_page, CORPUS_ENTRY)

    assert set(extracted.facts) == {"nav", "category"}
    assert extracted.missing_fields == [
        field_name for field_name in CANONICAL_FIELDS if field_name not in {"nav", "category"}
    ]
    assert "Missing fields:" in extracted.warnings[-1]


def test_extractor_prefers_structured_sources_over_text_fallback() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title=None,
        facts=[
            ParsedFact(field="nav", label="NAV", value="Rs 99.00 and extra surrounding text", source="text"),
            ParsedFact(field="nav", label="NAV", value="Rs 100.00", source="dom"),
            ParsedFact(field="nav", label="nav", value="Rs 101.00", source="json"),
        ],
    )

    extracted = FactExtractor().extract(parsed_page, CORPUS_ENTRY)

    assert extracted.facts["nav"].source == "json"
    assert extracted.facts["nav"].value == "Rs 101.00"


def test_extractor_uses_longer_value_when_sources_are_equal() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title=None,
        facts=[
            ParsedFact(field="exit_load", label="Exit Load", value="1%", source="dom"),
            ParsedFact(field="exit_load", label="Exit Load", value="1% if redeemed within 1 year", source="dom"),
        ],
    )

    extracted = FactExtractor().extract(parsed_page, CORPUS_ENTRY)

    assert extracted.facts["exit_load"].value == "1% if redeemed within 1 year"


def test_extractor_ignores_unknown_and_empty_candidates() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title=None,
        facts=[
            ParsedFact(field="returns", label="Returns", value="12%", source="dom"),
            ParsedFact(field="nav", label="NAV", value="   ", source="dom"),
        ],
    )

    extracted = FactExtractor().extract(parsed_page, CORPUS_ENTRY)

    assert set(extracted.facts) == {"category"}


def test_extractor_filters_editorial_reviews_ratings_and_advisory_candidates() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title=None,
        facts=[
            ParsedFact(field="riskometer", label="Riskometer", value="5 star rating from users", source="dom"),
            ParsedFact(field="benchmark", label="Benchmark", value="Review says this is a better fund", source="dom"),
            ParsedFact(field="fund_manager", label="Fund Manager", value="Should you invest recommendation", source="text"),
            ParsedFact(field="riskometer", label="Riskometer", value="Very High", source="dom"),
        ],
    )

    extracted = FactExtractor().extract(parsed_page, CORPUS_ENTRY)

    assert extracted.facts["riskometer"].value == "Very High"
    assert "benchmark" not in extracted.facts
    assert "fund_manager" not in extracted.facts
    assert extracted.filtered_count == 3
    assert "Filtered content candidates: 3" in extracted.warnings


def test_extractor_filters_performance_calculator_and_comparison_candidates() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title=None,
        facts=[
            ParsedFact(field="nav", label="NAV", value="Growth chart shows NAV trend", source="dom"),
            ParsedFact(field="aum", label="AUM", value="Compare this fund versus another fund", source="dom"),
            ParsedFact(field="min_sip", label="SIP Calculator", value="Rs 500", source="dom"),
            ParsedFact(field="expense_ratio", label="Expense Ratio", value="0.55%", source="dom"),
        ],
    )

    extracted = FactExtractor().extract(parsed_page, CORPUS_ENTRY)

    assert set(extracted.facts) == {"expense_ratio", "category"}
    assert extracted.filtered_count == 3


def test_extractor_keeps_allowed_factual_values_with_performance_related_field_names() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title=None,
        facts=[
            ParsedFact(field="exit_load", label="Exit Load", value="1% if redeemed within 1 year", source="dom"),
            ParsedFact(field="lock_in", label="Lock-in Period", value="No lock-in", source="dom"),
        ],
    )

    extracted = FactExtractor().extract(parsed_page, CORPUS_ENTRY)

    assert extracted.facts["exit_load"].value == "1% if redeemed within 1 year"
    assert extracted.facts["lock_in"].value == "No lock-in"
    assert extracted.filtered_count == 0


def test_extractor_normalizes_numeric_json_values_into_self_contained_content() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title=None,
        facts=[
            ParsedFact(field="nav", label="nav", value="1217.44", source="json"),
            ParsedFact(field="expense_ratio", label="expenseRatio", value="1.04", source="json"),
            ParsedFact(field="min_sip", label="minSip", value="100", source="json"),
            ParsedFact(field="aum", label="aum", value="76296.98145004", source="json"),
            ParsedFact(field="exit_load", label="exitLoad", value="Exit load of 1% if redeemed within 1 year", source="json"),
            ParsedFact(field="riskometer", label="riskometer", value="Moderately High Riskometer", source="json"),
        ],
    )

    extracted = FactExtractor().extract(parsed_page, CORPUS_ENTRY)

    assert extracted.facts["nav"].content == "NAV: Rs 1,217.44"
    assert extracted.facts["expense_ratio"].content == "Expense ratio: 1.04%"
    assert extracted.facts["min_sip"].content == "Minimum SIP: Rs 100"
    assert extracted.facts["aum"].content == "AUM: Rs 76,296.98145004 Cr"
    assert extracted.facts["exit_load"].content == "Exit load: 1% if redeemed within 1 year"
    assert extracted.facts["riskometer"].content == "Riskometer: Moderately High"


def test_extract_many_matches_pages_to_corpus_entries_and_fetch_dates() -> None:
    parsed_page = ParsedPage(
        source_url=CORPUS_ENTRY["source_url"],
        title=None,
        facts=[ParsedFact(field="nav", label="NAV", value="Rs 100.00", source="dom")],
    )

    extracted = FactExtractor().extract_many(
        [parsed_page],
        [CORPUS_ENTRY],
        fetched_at_by_url={CORPUS_ENTRY["source_url"]: "2026-06-28T00:00:00Z"},
    )

    assert len(extracted) == 1
    assert extracted[0].fetched_at == "2026-06-28T00:00:00Z"


def test_extract_many_raises_for_unknown_page_url() -> None:
    parsed_page = ParsedPage(source_url="https://groww.in/mutual-funds/unknown", title=None)

    with pytest.raises(KeyError, match="No corpus entry found"):
        FactExtractor().extract_many([parsed_page], [CORPUS_ENTRY])
