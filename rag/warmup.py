from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter
from typing import Any

_warmup_lock = Lock()
_warmup_state: WarmupState | None = None


@dataclass
class WarmupState:
    """Tracks whether the RAG stack was preloaded at startup."""

    completed: bool = False
    duration_seconds: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def get_warmup_state() -> WarmupState:
    global _warmup_state
    if _warmup_state is None:
        _warmup_state = WarmupState()
    return _warmup_state


def warmup_rag_stack(*, force: bool = False) -> WarmupState:
    """Eagerly load query embedder, vector store, and ask service."""

    state = get_warmup_state()
    if state.completed and not force:
        return state

    with _warmup_lock:
        if state.completed and not force:
            return state

        started = perf_counter()
        details: dict[str, Any] = {}
        try:
            from api.routes.ask import AskService, get_ask_service, set_ask_service
            from ingestion.indexer import get_shared_query_embedder
            from rag.retriever import ChromaRetriever

            embedder = get_shared_query_embedder()
            embedder.embed_texts(["warmup"])
            details["query_embedder"] = embedder.model_name

            retriever = ChromaRetriever(embedder=embedder)
            details["vector_store_ready"] = retriever.ready
            details["vector_store_path"] = str(retriever.vector_store_path)
            if retriever.ready:
                retriever.collection

            set_ask_service(AskService(retriever=retriever))
            get_ask_service()
            details["ask_service_ready"] = True

            state.completed = True
            state.error = None
            state.details = details
            state.duration_seconds = round(perf_counter() - started, 3)
        except Exception as exc:
            state.completed = False
            state.error = str(exc)
            state.details = details
            state.duration_seconds = round(perf_counter() - started, 3)
            raise

        return state
