from fastapi.testclient import TestClient

from api.main import create_app
from api.routes.ask import AskService, set_ask_service
from ingestion.chunker import CorpusChunk
from rag.classifier import QueryClassifier
from rag.formatter import ResponseFormatter
from rag.refusal import RefusalHandler
from rag.retriever import RetrievalResult, ScoredChunk
from rag.validator import ResponseValidator


class FakeRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def retrieve(self, query: str) -> RetrievalResult:
        self.calls.append(query)
        return self.result


class FakeGenerator:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls = 0

    def generate(self, *, query: str, chunks: list[CorpusChunk]) -> str:
        self.calls += 1
        return self.answer


def chunk() -> CorpusChunk:
    return CorpusChunk(
        chunk_id="hdfc-mid-cap-fund-direct-growth:expense_ratio",
        scheme_name="HDFC Mid Cap Fund - Direct Growth",
        scheme_slug="hdfc-mid-cap-fund-direct-growth",
        category="Mid Cap (Equity)",
        field="expense_ratio",
        content="Expense ratio: 0.75%",
        source_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        fetched_at="2026-06-28T11:45:05Z",
    )


def make_service(retriever: FakeRetriever, generator: FakeGenerator) -> AskService:
    return AskService(
        classifier=QueryClassifier(),
        retriever=retriever,
        generator=generator,
        validator=ResponseValidator(),
        formatter=ResponseFormatter(),
        refusal_handler=RefusalHandler(),
    )


def test_ask_route_returns_factual_answer_payload() -> None:
    retrieved_chunk = chunk()
    retriever = FakeRetriever(
        RetrievalResult(
            chunks=[retrieved_chunk],
            scored_chunks=[
                ScoredChunk(
                    chunk=retrieved_chunk,
                    similarity_score=0.9,
                    final_score=1.2,
                    ranking_tier=3,
                )
            ],
        )
    )
    generator = FakeGenerator("The expense ratio is 0.75%.")
    set_ask_service(make_service(retriever, generator))

    try:
        response = TestClient(create_app()).post(
            "/api/ask",
            json={"query": "What is the expense ratio of HDFC Mid Cap Fund?"},
        )
    finally:
        set_ask_service(None)

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "answer"
    assert body["answer"] == "The expense ratio is 0.75%."
    assert body["source_url"] == "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
    assert body["last_updated"] == "June 28, 2026"
    assert retriever.calls == ["What is the expense ratio of HDFC Mid Cap Fund?"]
    assert generator.calls == 1


def test_ask_route_refuses_which_fund_is_best_without_retrieval_or_generation() -> None:
    retriever = FakeRetriever(RetrievalResult(chunks=[], scored_chunks=[], low_confidence=True))
    generator = FakeGenerator("unused")
    set_ask_service(make_service(retriever, generator))

    try:
        response = TestClient(create_app()).post(
            "/api/ask",
            json={"query": "Can you tell me which mid cap fund is best?"},
        )
    finally:
        set_ask_service(None)

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "refusal"
    assert "cannot offer investment advice" in body["message"]
    assert retriever.calls == []
    assert generator.calls == 0


def test_ask_route_refuses_advisory_without_retrieval_or_generation() -> None:
    retriever = FakeRetriever(RetrievalResult(chunks=[], scored_chunks=[], low_confidence=True))
    generator = FakeGenerator("unused")
    set_ask_service(make_service(retriever, generator))

    try:
        response = TestClient(create_app()).post(
            "/api/ask",
            json={"query": "Should I invest in HDFC Mid Cap Fund?"},
        )
    finally:
        set_ask_service(None)

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "refusal"
    assert "cannot offer investment advice" in body["message"]
    assert retriever.calls == []
    assert generator.calls == 0


def test_ask_route_returns_safe_not_found_without_generation() -> None:
    retriever = FakeRetriever(RetrievalResult(chunks=[], scored_chunks=[], low_confidence=True))
    generator = FakeGenerator("unused")
    set_ask_service(make_service(retriever, generator))

    try:
        response = TestClient(create_app()).post(
            "/api/ask",
            json={"query": "What is the trustee address?"},
        )
    finally:
        set_ask_service(None)

    assert response.status_code == 200
    assert response.json()["type"] == "refusal"
    assert "configured Groww corpus" in response.json()["message"]
    assert generator.calls == 0
