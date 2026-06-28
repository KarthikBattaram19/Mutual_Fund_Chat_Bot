from __future__ import annotations

import re
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes.ask import AskService, set_ask_service
from ingestion.chunker import CorpusChunk
from rag.classifier import QueryClassifier
from rag.formatter import ResponseFormatter
from rag.generator import GroqGenerationError
from rag.refusal import RefusalHandler
from rag.retriever import RetrievalResult, ScoredChunk
from rag.validator import ResponseValidator


@dataclass(frozen=True)
class SchemeCase:
    slug: str
    name: str
    field: str
    value: str
    query: str


SCHEME_CASES = (
    SchemeCase(
        slug="hdfc-large-cap-fund-direct-growth",
        name="HDFC Large Cap Fund - Direct Growth",
        field="expense_ratio",
        value="0.88%",
        query="What is the expense ratio of HDFC Large Cap Fund?",
    ),
    SchemeCase(
        slug="hdfc-mid-cap-fund-direct-growth",
        name="HDFC Mid Cap Fund - Direct Growth",
        field="min_sip",
        value="Rs 100",
        query="What is the minimum SIP for HDFC Mid Cap Fund?",
    ),
    SchemeCase(
        slug="hdfc-small-cap-fund-direct-growth",
        name="HDFC Small Cap Fund - Direct Growth",
        field="nav",
        value="Rs 189.42",
        query="What is the NAV of HDFC Small Cap Fund?",
    ),
    SchemeCase(
        slug="hdfc-gold-etf-fund-of-fund-direct-plan-growth",
        name="HDFC Gold ETF Fund of Fund - Direct Plan Growth",
        field="riskometer",
        value="High",
        query="What is the riskometer for HDFC Gold ETF FoF?",
    ),
    SchemeCase(
        slug="hdfc-silver-etf-fof-direct-growth",
        name="HDFC Silver ETF FoF - Direct Growth",
        field="category",
        value="Commodity (Silver)",
        query="What is the category of HDFC Silver ETF FoF?",
    ),
)


class MatrixRetriever:
    def __init__(self, chunks: list[CorpusChunk]) -> None:
        self.chunks = chunks
        self.calls: list[str] = []

    def retrieve(self, query: str) -> RetrievalResult:
        self.calls.append(query)
        selected = self._select_chunk(query)
        if selected is None:
            return RetrievalResult(chunks=[], scored_chunks=[], low_confidence=True)
        return RetrievalResult(
            chunks=[selected],
            scored_chunks=[
                ScoredChunk(
                    chunk=selected,
                    similarity_score=0.95,
                    final_score=1.25,
                    ranking_tier=3,
                )
            ],
        )

    def _select_chunk(self, query: str) -> CorpusChunk | None:
        normalized = query.lower()
        for chunk in self.chunks:
            if _query_matches_chunk(normalized, chunk):
                return chunk
        return None


class GroundedGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, query: str, chunks: list[CorpusChunk]) -> str:
        self.calls += 1
        chunk = chunks[0]
        label = chunk.field.replace("_", " ")
        _, value = chunk.content.split(": ", 1)
        return f"The {label} is {value}."


class FailingGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, query: str, chunks: list[CorpusChunk]) -> str:
        self.calls += 1
        raise GroqGenerationError("mock Groq timeout")


def build_chunks(fetched_at: str = "2026-06-28T11:45:05Z") -> list[CorpusChunk]:
    return [
        CorpusChunk(
            chunk_id=f"{case.slug}:{case.field}",
            scheme_name=case.name,
            scheme_slug=case.slug,
            category="Test",
            field=case.field,
            content=f"{case.field.replace('_', ' ').title()}: {case.value}",
            source_url=f"https://groww.in/mutual-funds/{case.slug}",
            fetched_at=fetched_at,
        )
        for case in SCHEME_CASES
    ]


def make_service(
    retriever: MatrixRetriever,
    generator: GroundedGenerator | FailingGenerator | None = None,
) -> AskService:
    return AskService(
        classifier=QueryClassifier(),
        retriever=retriever,
        generator=generator or GroundedGenerator(),
        validator=ResponseValidator(),
        formatter=ResponseFormatter(),
        refusal_handler=RefusalHandler(),
    )


@pytest.fixture
def client_with_matrix_service():
    retriever = MatrixRetriever(build_chunks())
    generator = GroundedGenerator()
    set_ask_service(make_service(retriever, generator))
    try:
        yield TestClient(create_app()), retriever, generator
    finally:
        set_ask_service(None)


def test_phase5_cors_allows_local_website_origin() -> None:
    client = TestClient(create_app())

    for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        response = client.options(
            "/api/ask",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_phase5_full_pipeline_smoke_contract(client_with_matrix_service) -> None:
    client, retriever, generator = client_with_matrix_service

    response = client.post(
        "/api/ask",
        json={"query": "What is the expense ratio of HDFC Large Cap Fund?"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["type"] == "answer"
    assert body["source_url"] == "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
    assert body["last_updated"] == "June 2026"
    assert _sentence_count(body["answer"]) <= 3
    assert retriever.calls == ["What is the expense ratio of HDFC Large Cap Fund?"]
    assert generator.calls == 1


@pytest.mark.parametrize("case", SCHEME_CASES)
def test_phase5_all_five_supported_schemes_return_factual_answers(case: SchemeCase) -> None:
    retriever = MatrixRetriever(build_chunks())
    generator = GroundedGenerator()
    set_ask_service(make_service(retriever, generator))

    try:
        response = TestClient(create_app()).post("/api/ask", json={"query": case.query})
    finally:
        set_ask_service(None)

    body = response.json()
    assert response.status_code == 200
    assert body["type"] == "answer"
    assert case.value in body["answer"]
    assert body["source_url"] == f"https://groww.in/mutual-funds/{case.slug}"
    assert body["last_updated"] == "June 2026"
    assert _sentence_count(body["answer"]) <= 3


def test_phase5_advisory_query_refuses_without_rag(client_with_matrix_service) -> None:
    client, retriever, generator = client_with_matrix_service

    response = client.post("/api/ask", json={"query": "Should I invest in HDFC Mid Cap Fund?"})
    body = response.json()

    assert body["type"] == "refusal"
    assert "cannot offer investment advice" in body["message"]
    assert body["educational_url"].startswith("https://www.amfiindia.com")
    assert retriever.calls == []
    assert generator.calls == 0


def test_phase5_personal_recommendation_refuses_without_rag(client_with_matrix_service) -> None:
    client, retriever, generator = client_with_matrix_service

    response = client.post("/api/ask", json={"query": "Which fund is better for me?"})
    body = response.json()

    assert body["type"] == "refusal"
    assert "cannot offer investment advice" in body["message"]
    assert retriever.calls == []
    assert generator.calls == 0


def test_phase5_returns_comparison_refuses_without_quoting_returns(client_with_matrix_service) -> None:
    client, retriever, generator = client_with_matrix_service

    response = client.post("/api/ask", json={"query": "Compare returns of Large Cap vs Small Cap"})
    body = response.json()

    assert body["type"] == "refusal"
    assert "quote or compare historical returns" in body["message"]
    assert not re.search(r"\d+(?:\.\d+)?\s*%", body["message"])
    assert retriever.calls == []
    assert generator.calls == 0


def test_phase5_single_scheme_performance_query_returns_link_only_without_rag() -> None:
    retriever = MatrixRetriever(build_chunks())
    generator = GroundedGenerator()
    set_ask_service(make_service(retriever, generator))

    try:
        response = TestClient(create_app()).post(
            "/api/ask",
            json={"query": "What are the 1-year returns of HDFC Small Cap Fund?"},
        )
    finally:
        set_ask_service(None)

    body = response.json()
    assert response.status_code == 200
    assert body["type"] == "answer"
    assert body["source_url"] == "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth"
    assert "Please refer to the Groww scheme page" in body["answer"]
    assert not re.search(r"\d+(?:\.\d+)?\s*%", body["answer"])
    assert retriever.calls == []
    assert generator.calls == 0


def test_phase5_pii_query_refuses_without_rag(client_with_matrix_service) -> None:
    client, retriever, generator = client_with_matrix_service

    response = client.post(
        "/api/ask",
        json={"query": "My PAN is ABCDE1234F. What is the expense ratio of HDFC Large Cap Fund?"},
    )
    body = response.json()

    assert body["type"] == "refusal"
    assert "cannot process personal or account information" in body["message"]
    assert retriever.calls == []
    assert generator.calls == 0


def test_phase5_out_of_scope_query_lists_supported_schemes(client_with_matrix_service) -> None:
    client, retriever, generator = client_with_matrix_service

    response = client.post("/api/ask", json={"query": "What is the NAV of HDFC Balanced Advantage Fund?"})
    body = response.json()

    assert body["type"] == "refusal"
    assert "HDFC Large Cap Fund - Direct Growth" in body["message"]
    assert "HDFC Silver ETF FoF - Direct Growth" in body["message"]
    assert retriever.calls == []
    assert generator.calls == 0


def test_phase5_corpus_refresh_date_reaches_answer_footer() -> None:
    retriever = MatrixRetriever(build_chunks(fetched_at="2026-07-15T09:00:00Z"))
    set_ask_service(make_service(retriever))

    try:
        response = TestClient(create_app()).post(
            "/api/ask",
            json={"query": "What is the expense ratio of HDFC Large Cap Fund?"},
        )
    finally:
        set_ask_service(None)

    assert response.json()["last_updated"] == "July 2026"


def test_phase5_groq_failure_returns_safe_error() -> None:
    retriever = MatrixRetriever(build_chunks())
    generator = FailingGenerator()
    set_ask_service(make_service(retriever, generator))

    try:
        response = TestClient(create_app()).post(
            "/api/ask",
            json={"query": "What is the expense ratio of HDFC Large Cap Fund?"},
        )
    finally:
        set_ask_service(None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Generation service is temporarily busy. Please try again later."
    assert generator.calls == 1


def test_phase5_empty_or_whitespace_query_returns_validation_error() -> None:
    response = TestClient(create_app()).post("/api/ask", json={"query": "   "})

    assert response.status_code == 422
    assert response.json()["detail"] == "query cannot be empty"


def test_phase5_no_retrieval_match_returns_safe_not_found() -> None:
    retriever = MatrixRetriever(build_chunks())
    generator = GroundedGenerator()
    set_ask_service(make_service(retriever, generator))

    try:
        response = TestClient(create_app()).post(
            "/api/ask",
            json={"query": "What is the trustee address?"},
        )
    finally:
        set_ask_service(None)

    body = response.json()
    assert body["type"] == "refusal"
    assert "configured Groww corpus" in body["message"]
    assert generator.calls == 0


def _query_matches_chunk(normalized_query: str, chunk: CorpusChunk) -> bool:
    slug_tokens = set(chunk.scheme_slug.replace("-", " ").split())
    field_tokens = set(chunk.field.replace("_", " ").split())
    query_tokens = set(re.sub(r"[^a-z0-9]+", " ", normalized_query).split())
    scheme_match = bool((slug_tokens - {"hdfc", "fund", "direct", "growth", "plan", "of", "etf", "fof"}) & query_tokens)
    field_match = bool(field_tokens & query_tokens)
    return scheme_match and field_match


def _sentence_count(value: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])\s+", value) if part.strip()])
