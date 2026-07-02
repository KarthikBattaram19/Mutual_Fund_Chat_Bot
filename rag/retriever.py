from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from typing import Iterable

from config import get_settings
from ingestion.chunker import CorpusChunk
from ingestion.indexer import BGEEmbedder, get_shared_query_embedder


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "nav": ("nav", "net asset value"),
    "expense_ratio": ("expense ratio", "expense ration", "expense", "ratio"),
    "exit_load": ("exit load", "exit fee", "redemption charge"),
    "min_sip": ("minimum sip", "min sip", "sip amount", "monthly sip"),
    "riskometer": ("riskometer", "risk level", "risk"),
    "benchmark": ("benchmark", "index"),
    "fund_manager": ("fund manager", "manager", "manages", "managed by"),
    "aum": ("aum", "assets under management", "asset under management"),
    "category": ("category", "type"),
    "lock_in": ("lock in", "lock-in", "lockin"),
}

GENERIC_SCHEME_TOKENS = {
    "hdfc",
    "fund",
    "direct",
    "growth",
    "plan",
    "of",
    "the",
    "fof",
    "etf",
}


@dataclass(frozen=True)
class QueryIntent:
    """Deterministic scheme and field hints parsed from a user query."""

    scheme_slug: str | None = None
    field: str | None = None


@dataclass(frozen=True)
class ScoredChunk:
    """A chunk plus its vector and rerank scores."""

    chunk: CorpusChunk
    similarity_score: float
    final_score: float
    ranking_tier: int
    boosts: tuple[str, ...] = field(default_factory=tuple)


class RetrievalError(RuntimeError):
    """Raised when vector retrieval cannot run safely."""


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[CorpusChunk]
    scored_chunks: list[ScoredChunk]
    low_confidence: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.chunks) and not self.low_confidence


class SchemeFieldReranker:
    """Boost vector-search results whose metadata matches query intent."""

    def __init__(
        self,
        *,
        scheme_boost: float = 0.30,
        field_boost: float = 0.08,
    ) -> None:
        self.scheme_boost = scheme_boost
        self.field_boost = field_boost

    def infer_intent(self, query: str, chunks: Iterable[CorpusChunk]) -> QueryIntent:
        chunk_list = list(chunks)
        return QueryIntent(
            scheme_slug=self._infer_scheme_slug(query, chunk_list),
            field=self._infer_field(query),
        )

    def rerank(
        self,
        query: str,
        scored_chunks: Iterable[tuple[CorpusChunk, float]],
    ) -> list[ScoredChunk]:
        scored_list = list(scored_chunks)
        intent = self.infer_intent(query, (chunk for chunk, _ in scored_list))

        reranked: list[ScoredChunk] = []
        for chunk, similarity_score in scored_list:
            final_score = similarity_score
            boosts: list[str] = []
            scheme_match = intent.scheme_slug is not None and chunk.scheme_slug == intent.scheme_slug
            field_match = intent.field is not None and chunk.field == intent.field
            if scheme_match:
                final_score += self.scheme_boost
                boosts.append(f"scheme:{intent.scheme_slug}")
            if field_match:
                final_score += self.field_boost
                boosts.append(f"field:{intent.field}")
            reranked.append(
                ScoredChunk(
                    chunk=chunk,
                    similarity_score=similarity_score,
                    final_score=final_score,
                    ranking_tier=_ranking_tier(scheme_match=scheme_match, field_match=field_match),
                    boosts=tuple(boosts),
                )
            )

        return sorted(
            reranked,
            key=lambda scored: (scored.ranking_tier, scored.final_score, scored.similarity_score, scored.chunk.chunk_id),
            reverse=True,
        )

    def _infer_scheme_slug(self, query: str, chunks: list[CorpusChunk]) -> str | None:
        query_tokens = set(_normalize_tokens(query))
        if not query_tokens:
            return None

        candidates: dict[str, set[str]] = {}
        for chunk in chunks:
            candidates.setdefault(
                chunk.scheme_slug,
                _distinctive_scheme_tokens(chunk.scheme_name, chunk.scheme_slug),
            )

        scored_candidates: list[tuple[float, int, str]] = []
        for scheme_slug, scheme_tokens in candidates.items():
            if not scheme_tokens:
                continue
            matched = {scheme_token for scheme_token in scheme_tokens if _token_matches_any(scheme_token, query_tokens)}
            coverage = len(matched) / len(scheme_tokens)
            if coverage <= 0:
                continue
            scored_candidates.append((coverage, len(matched), scheme_slug))

        if not scored_candidates:
            return None

        best_coverage, best_matches, best_slug = max(scored_candidates)
        if best_coverage < 1.0 and best_matches < 2:
            return None
        return best_slug

    @staticmethod
    def _infer_field(query: str) -> str | None:
        normalized_query = " ".join(_normalize_tokens(query))
        for field_name, aliases in FIELD_ALIASES.items():
            if any(alias in normalized_query for alias in aliases):
                return field_name
        return None


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions do not match")

    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("Cannot compare zero-length embedding vector")

    return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True)) / (left_norm * right_norm)


class InMemoryRetriever:
    """Retrieve from a small in-memory chunk set, useful for tests and smoke checks."""

    def __init__(
        self,
        *,
        chunks: list[CorpusChunk],
        embeddings: list[list[float]] | None = None,
        embedder: BGEEmbedder | None = None,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        reranker: SchemeFieldReranker | None = None,
    ) -> None:
        settings = get_settings()
        self.chunks = chunks
        self.embedder = embedder or BGEEmbedder()
        self.top_k = top_k or settings.top_k
        self.similarity_threshold = similarity_threshold if similarity_threshold is not None else settings.similarity_threshold
        self.reranker = reranker or SchemeFieldReranker()
        self.embeddings = embeddings

    def retrieve(self, query: str) -> RetrievalResult:
        if not self.chunks:
            return RetrievalResult(chunks=[], scored_chunks=[], low_confidence=True)
        if self.embeddings is None:
            self.embeddings = self.embedder.embed_texts(chunk.content for chunk in self.chunks)

        query_embedding = self.embedder.embed_texts([query])[0]
        scored = [
            (chunk, cosine_similarity(query_embedding, embedding))
            for chunk, embedding in zip(self.chunks, self.embeddings, strict=True)
        ]
        reranked = self.reranker.rerank(query, scored)
        selected = reranked[: self.top_k]
        low_confidence = not selected or max(item.similarity_score for item in selected) < self.similarity_threshold
        return RetrievalResult(
            chunks=[item.chunk for item in selected],
            scored_chunks=selected,
            low_confidence=low_confidence,
        )


class ChromaRetriever:
    """Corpus-bound BGE retriever over the local Chroma vector store."""

    def __init__(
        self,
        *,
        vector_store_path: str | Path | None = None,
        collection_name: str = "mutual_fund_facts",
        corpus_index_path: str | Path = "data/corpus_index.json",
        embedder: BGEEmbedder | None = None,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        reranker: SchemeFieldReranker | None = None,
        client: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.vector_store_path = Path(vector_store_path) if vector_store_path is not None else settings.vector_store_path
        self.collection_name = collection_name
        self.corpus_index_path = Path(corpus_index_path)
        self.embedder = embedder or get_shared_query_embedder()
        self.top_k = top_k or settings.top_k
        self.similarity_threshold = similarity_threshold if similarity_threshold is not None else settings.similarity_threshold
        self.reranker = reranker or SchemeFieldReranker()
        self._client = client
        self._collection: Any | None = None
        self._approved_urls = self._load_approved_urls()

    @property
    def ready(self) -> bool:
        return self.vector_store_path.exists()

    @property
    def collection(self) -> Any:
        if self._collection is None:
            if self._client is None:
                if not self.vector_store_path.exists():
                    raise RetrievalError(f"Vector store not found: {self.vector_store_path}")
                import chromadb

                self._client = chromadb.PersistentClient(path=str(self.vector_store_path))
            self._collection = self._client.get_collection(name=self.collection_name)
        return self._collection

    def retrieve(self, query: str) -> RetrievalResult:
        query_embedding = self.embedder.embed_texts([query])[0]
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=max(self.top_k * 3, self.top_k),
            include=["documents", "metadatas", "distances"],
        )

        documents = _first_result_list(result.get("documents"))
        metadatas = _first_result_list(result.get("metadatas"))
        distances = _first_result_list(result.get("distances"))
        scored: list[tuple[CorpusChunk, float]] = []
        for document, metadata, distance in zip(documents, metadatas, distances, strict=False):
            if str(metadata.get("source_url", "")) not in self._approved_urls:
                continue
            chunk = _chunk_from_chroma(document=document, metadata=metadata)
            scored.append((chunk, max(0.0, 1.0 - float(distance))))

        reranked = self.reranker.rerank(query, scored)
        selected = reranked[: self.top_k]
        low_confidence = not selected or max(item.similarity_score for item in selected) < self.similarity_threshold
        return RetrievalResult(
            chunks=[item.chunk for item in selected],
            scored_chunks=selected,
            low_confidence=low_confidence,
        )

    def _load_approved_urls(self) -> set[str]:
        corpus = json.loads(self.corpus_index_path.read_text(encoding="utf-8"))
        return {str(item["source_url"]) for item in corpus}


def _distinctive_scheme_tokens(scheme_name: str, scheme_slug: str) -> set[str]:
    tokens = set(_normalize_tokens(f"{scheme_name} {scheme_slug}"))
    return {token for token in tokens if token not in GENERIC_SCHEME_TOKENS}


def _normalize_tokens(value: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).split()


def _ranking_tier(*, scheme_match: bool, field_match: bool) -> int:
    if scheme_match and field_match:
        return 3
    if scheme_match:
        return 2
    if field_match:
        return 1
    return 0


def _token_matches_any(expected: str, candidates: set[str]) -> bool:
    if expected in candidates:
        return True
    if len(expected) < 4:
        return False
    return any(SequenceMatcher(a=expected, b=candidate).ratio() >= 0.84 for candidate in candidates)


def _first_result_list(value: Any) -> list[Any]:
    if not value:
        return []
    first = value[0]
    if hasattr(first, "tolist"):
        first = first.tolist()
    return list(first)


def _chunk_from_chroma(*, document: str, metadata: dict[str, Any]) -> CorpusChunk:
    return CorpusChunk(
        chunk_id=str(metadata["chunk_id"]),
        scheme_name=str(metadata["scheme_name"]),
        scheme_slug=str(metadata["scheme_slug"]),
        category=str(metadata["category"]),
        field=str(metadata["field"]),
        content=str(document),
        source_url=str(metadata["source_url"]),
        fetched_at=str(metadata.get("fetched_at") or "") or None,
    )
