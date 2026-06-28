from ingestion.chunker import CorpusChunk
from rag.retriever import SchemeFieldReranker, cosine_similarity


SCHEMES = {
    "hdfc-large-cap-fund-direct-growth": "HDFC Large Cap Fund - Direct Growth",
    "hdfc-mid-cap-fund-direct-growth": "HDFC Mid Cap Fund - Direct Growth",
    "hdfc-small-cap-fund-direct-growth": "HDFC Small Cap Fund - Direct Growth",
    "hdfc-gold-etf-fund-of-fund-direct-plan-growth": "HDFC Gold ETF Fund of Fund - Direct Plan Growth",
    "hdfc-silver-etf-fof-direct-growth": "HDFC Silver ETF FoF - Direct Growth",
}

FIELD_QUERY_WORDING = {
    "nav": "NAV",
    "expense_ratio": "expense ratio",
    "exit_load": "exit load",
    "min_sip": "minimum SIP",
    "riskometer": "riskometer",
    "benchmark": "benchmark",
    "fund_manager": "fund manager",
    "aum": "AUM",
    "category": "category",
}


def chunk(scheme_slug: str, field: str, content: str, scheme_name: str | None = None) -> CorpusChunk:
    readable_name = scheme_name or scheme_slug.replace("-", " ").title()
    return CorpusChunk(
        chunk_id=f"{scheme_slug}:{field}",
        scheme_name=readable_name,
        scheme_slug=scheme_slug,
        category="Test",
        field=field,
        content=content,
        source_url=f"https://groww.in/mutual-funds/{scheme_slug}",
        fetched_at="2026-06-28T00:00:00Z",
    )


def test_reranker_promotes_mid_cap_expense_ratio_from_near_tie() -> None:
    reranker = SchemeFieldReranker()
    mid_cap = chunk(
        "hdfc-mid-cap-fund-direct-growth",
        "expense_ratio",
        "Expense ratio: 0.75%",
        "HDFC Mid Cap Fund - Direct Growth",
    )
    gold = chunk(
        "hdfc-gold-etf-fund-of-fund-direct-plan-growth",
        "expense_ratio",
        "Expense ratio: 0.13922206%",
        "HDFC Gold ETF Fund of Fund - Direct Plan Growth",
    )

    reranked = reranker.rerank(
        "What is the Expense ration of HDFC mid cap direct fund?",
        [
            (gold, 0.763011),
            (mid_cap, 0.758479),
        ],
    )

    assert reranked[0].chunk.chunk_id == "hdfc-mid-cap-fund-direct-growth:expense_ratio"
    assert reranked[0].final_score > reranked[1].final_score
    assert reranked[0].boosts == ("scheme:hdfc-mid-cap-fund-direct-growth", "field:expense_ratio")


def test_reranker_promotes_large_cap_nav_with_typo() -> None:
    reranker = SchemeFieldReranker()
    gold_nav = chunk(
        "hdfc-gold-etf-fund-of-fund-direct-plan-growth",
        "nav",
        "NAV: Rs 43.279",
        "HDFC Gold ETF Fund of Fund - Direct Plan Growth",
    )
    large_nav = chunk(
        "hdfc-large-cap-fund-direct-growth",
        "nav",
        "NAV: Rs 1,217.44",
        "HDFC Large Cap Fund - Direct Growth",
    )

    reranked = reranker.rerank(
        "What is NAV of HDFC larage cap",
        [
            (gold_nav, 0.712004),
            (large_nav, 0.672679),
        ],
    )

    assert reranked[0].chunk.chunk_id == "hdfc-large-cap-fund-direct-growth:nav"
    assert reranked[0].boosts == ("scheme:hdfc-large-cap-fund-direct-growth", "field:nav")


def test_reranker_prioritizes_detected_scheme_for_broad_detail_query() -> None:
    reranker = SchemeFieldReranker()
    mid_cap = chunk(
        "hdfc-mid-cap-fund-direct-growth",
        "fund_manager",
        "Fund manager: Harshad Patwardhan",
        "HDFC Mid Cap Fund - Direct Growth",
    )
    silver = chunk(
        "hdfc-silver-etf-fof-direct-growth",
        "category",
        "Category: HDFC Silver ETF FoF Direct-Growth",
        "HDFC Silver ETF FoF - Direct Growth",
    )

    reranked = reranker.rerank(
        "show details of HDFC Mid Cap Fund - Direct Growth",
        [
            (silver, 0.832730),
            (mid_cap, 0.668883),
        ],
    )

    assert reranked[0].chunk.scheme_slug == "hdfc-mid-cap-fund-direct-growth"
    assert reranked[0].ranking_tier == 2


def test_reranker_promotes_detected_scheme_and_field_across_supported_corpus() -> None:
    reranker = SchemeFieldReranker()
    all_chunks = [
        chunk(scheme_slug, field, f"{field}: value", scheme_name)
        for scheme_slug, scheme_name in SCHEMES.items()
        for field in FIELD_QUERY_WORDING
    ]

    for scheme_slug, scheme_name in SCHEMES.items():
        for field, query_wording in FIELD_QUERY_WORDING.items():
            intended = next(item for item in all_chunks if item.scheme_slug == scheme_slug and item.field == field)
            same_field_other_scheme = next(item for item in all_chunks if item.scheme_slug != scheme_slug and item.field == field)
            same_scheme_other_field = next(item for item in all_chunks if item.scheme_slug == scheme_slug and item.field != field)
            unrelated = next(item for item in all_chunks if item.scheme_slug != scheme_slug and item.field != field)

            reranked = reranker.rerank(
                f"What is the {query_wording} of {scheme_name}?",
                [
                    (same_field_other_scheme, 0.99),
                    (same_scheme_other_field, 0.98),
                    (unrelated, 1.00),
                    (intended, 0.10),
                ],
            )

            assert reranked[0].chunk.chunk_id == intended.chunk_id
            assert reranked[0].ranking_tier == 3


def test_cosine_similarity_rejects_dimension_mismatch() -> None:
    try:
        cosine_similarity([1.0, 0.0], [1.0])
    except ValueError as exc:
        assert str(exc) == "Embedding dimensions do not match"
    else:
        raise AssertionError("Expected dimension mismatch to raise ValueError")
