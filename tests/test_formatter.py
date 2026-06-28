from ingestion.chunker import CorpusChunk
from rag.formatter import ResponseFormatter


def test_formatter_attaches_single_source_and_last_updated() -> None:
    chunk = CorpusChunk(
        chunk_id="hdfc-mid-cap-fund-direct-growth:expense_ratio",
        scheme_name="HDFC Mid Cap Fund - Direct Growth",
        scheme_slug="hdfc-mid-cap-fund-direct-growth",
        category="Mid Cap (Equity)",
        field="expense_ratio",
        content="Expense ratio: 0.75%",
        source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        fetched_at="2026-06-28T11:45:05Z",
    )

    response = ResponseFormatter().format_answer("The expense ratio is 0.75%.", [chunk])

    assert response.type == "answer"
    assert response.answer == "The expense ratio is 0.75%."
    assert response.source_url == "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
    assert response.last_updated == "June 2026"


def test_formatter_strips_provenance_sentences_from_answer_body() -> None:
    chunk = CorpusChunk(
        chunk_id="hdfc-gold-etf-fund-of-fund-direct-plan-growth:expense_ratio",
        scheme_name="HDFC Gold ETF Fund of Fund - Direct Plan Growth",
        scheme_slug="hdfc-gold-etf-fund-of-fund-direct-plan-growth",
        category="Commodity (Gold)",
        field="expense_ratio",
        content="Expense ratio: 0.51%",
        source_url="https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth",
        fetched_at="2026-06-28T11:45:07Z",
    )
    noisy_answer = (
        "The expense ratio is 0.51%. "
        "This information was last updated on 2026-06-28T11:45:07Z. "
        "The source of this information is https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth."
    )

    response = ResponseFormatter().format_answer(noisy_answer, [chunk])

    assert response.answer == "The expense ratio is 0.51%."
    assert response.source_url == "https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth"
    assert response.last_updated == "June 2026"


def test_formatter_strips_fetched_from_attribution_from_answer_body() -> None:
    chunk = CorpusChunk(
        chunk_id="hdfc-large-cap-fund-direct-growth:fund_manager",
        scheme_name="HDFC Large Cap Fund - Direct Growth",
        scheme_slug="hdfc-large-cap-fund-direct-growth",
        category="Large Cap (Equity)",
        field="fund_manager",
        content="Fund manager: Ashwani Kumar, Sailesh Raj Bhan",
        source_url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        fetched_at="2026-06-28T11:45:04Z",
    )
    noisy_answer = (
        "This information was fetched from https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth "
        "on 2026-06-28T11:45:04Z. The fund is managed by Ashwani Kumar and Sailesh Raj Bhan."
    )

    response = ResponseFormatter().format_answer(noisy_answer, [chunk])

    assert response.answer == "The fund is managed by Ashwani Kumar and Sailesh Raj Bhan."
    assert response.source_url == "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
    assert response.last_updated == "June 2026"
