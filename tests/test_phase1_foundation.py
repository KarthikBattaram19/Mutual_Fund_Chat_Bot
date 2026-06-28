import json
import re

from config import get_settings


APPROVED_SOURCE_URLS = {
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth",
    "https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth",
}


def test_settings_load_with_defaults() -> None:
    settings = get_settings()

    assert settings.groq_model == "llama-3.3-70b-versatile"
    assert settings.bge_model_name == "BAAI/bge-small-en-v1.5"
    assert settings.vector_store_path.as_posix() == "data/vector_store"
    assert settings.top_k == 5
    assert settings.similarity_threshold == 0.35


def test_corpus_index_contains_exactly_approved_schemes(corpus_index_path) -> None:
    corpus = json.loads(corpus_index_path.read_text(encoding="utf-8"))

    assert len(corpus) == 5
    assert {item["source_url"] for item in corpus} == APPROVED_SOURCE_URLS


def test_corpus_index_entries_have_required_fields(corpus_index_path) -> None:
    corpus = json.loads(corpus_index_path.read_text(encoding="utf-8"))
    required_fields = {"scheme_name", "scheme_slug", "category", "source_url", "fetched_at"}

    for item in corpus:
        assert required_fields <= set(item)
        assert item["scheme_name"]
        assert item["scheme_slug"]
        assert item["category"]
        assert item["source_url"].startswith("https://groww.in/mutual-funds/")
        assert item["fetched_at"] is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", item["fetched_at"])
