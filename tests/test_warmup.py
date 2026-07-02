from unittest.mock import MagicMock

import pytest

from ingestion.indexer import EmbedderError, FastQueryEmbedder, get_shared_query_embedder
from rag.warmup import WarmupState, get_warmup_state, warmup_rag_stack


class FakeFastEmbedModel:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def test_fast_query_embedder_embeds_texts_with_fake_model() -> None:
    embedder = FastQueryEmbedder(model=FakeFastEmbedModel())

    embeddings = embedder.embed_texts(["What is the NAV?"])

    assert embeddings == [[0.1, 0.2, 0.3]]


def test_fast_query_embedder_rejects_empty_text() -> None:
    embedder = FastQueryEmbedder(model=FakeFastEmbedModel())

    with pytest.raises(EmbedderError, match="Cannot embed empty text"):
        embedder.embed_texts([" "])


def test_shared_query_embedder_returns_singleton() -> None:
    import ingestion.indexer as indexer_module

    indexer_module._shared_query_embedder = FastQueryEmbedder(model=FakeFastEmbedModel())
    try:
        first = get_shared_query_embedder()
        second = get_shared_query_embedder()
        assert first is second
    finally:
        indexer_module._shared_query_embedder = None


def test_warmup_rag_stack_loads_embedder_and_ask_service(monkeypatch) -> None:
    import rag.warmup as warmup_module

    warmup_module._warmup_state = None

    fake_embedder = MagicMock()
    fake_embedder.model_name = "BAAI/bge-small-en-v1.5"
    fake_retriever = MagicMock()
    fake_retriever.ready = True
    fake_retriever.vector_store_path = "data/vector_store"
    fake_retriever.collection = object()

    monkeypatch.setattr("ingestion.indexer.get_shared_query_embedder", lambda: fake_embedder)
    monkeypatch.setattr("rag.retriever.ChromaRetriever", lambda **_: fake_retriever)
    monkeypatch.setattr("api.routes.ask.AskService", lambda **_: object())
    monkeypatch.setattr("api.routes.ask.set_ask_service", lambda _: None)
    monkeypatch.setattr("api.routes.ask.get_ask_service", lambda: object())

    state = warmup_rag_stack(force=True)

    assert state.completed is True
    assert state.error is None
    assert state.duration_seconds is not None
    assert state.details["query_embedder"] == "BAAI/bge-small-en-v1.5"
    assert state.details["ask_service_ready"] is True
    fake_embedder.embed_texts.assert_called_once_with(["warmup"])


def test_get_warmup_state_returns_shared_object() -> None:
    import rag.warmup as warmup_module

    warmup_module._warmup_state = WarmupState(completed=True)
    try:
        assert get_warmup_state().completed is True
    finally:
        warmup_module._warmup_state = None
