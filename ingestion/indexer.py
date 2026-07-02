from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from config import get_settings
from ingestion.chunker import CorpusChunk


@dataclass(frozen=True)
class EmbeddedChunk:
    """Chunk text, metadata, and its BGE embedding vector."""

    chunk: CorpusChunk
    embedding: list[float]

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self.chunk), "embedding": self.embedding}


class EmbedderError(ValueError):
    """Raised when embedding inputs or model outputs are invalid."""


@dataclass(frozen=True)
class VectorIndexWriteResult:
    """Summary of a vector-store upsert operation."""

    collection_name: str
    vector_store_path: Path
    upserted_count: int
    chunk_ids: list[str]


class VectorIndexError(ValueError):
    """Raised when embedded chunks cannot be written to the vector store."""


_shared_embedder: BGEEmbedder | None = None
_shared_query_embedder: FastQueryEmbedder | None = None


def get_shared_embedder() -> BGEEmbedder:
    """Return a process-wide embedder for offline ingestion and batch work."""

    global _shared_embedder
    if _shared_embedder is None:
        _shared_embedder = BGEEmbedder()
    return _shared_embedder


def get_shared_query_embedder() -> FastQueryEmbedder:
    """Return a process-wide lightweight embedder for live query retrieval."""

    global _shared_query_embedder
    if _shared_query_embedder is None:
        _shared_query_embedder = FastQueryEmbedder()
    return _shared_query_embedder


class FastQueryEmbedder:
    """Embed user queries with ONNX-backed fastembed for low cold-start latency."""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        model: Any | None = None,
    ) -> None:
        self.model_name = model_name or get_settings().bge_model_name
        self._model = model

    @property
    def model(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        text_list = [text for text in texts]
        if not text_list:
            return []
        if any(not text.strip() for text in text_list):
            raise EmbedderError("Cannot embed empty text")

        embeddings = list(self.model.embed(text_list))
        normalized_embeddings: list[list[float]] = []
        for embedding in embeddings:
            if hasattr(embedding, "tolist"):
                embedding = embedding.tolist()
            if not isinstance(embedding, list) or not embedding:
                raise EmbedderError("Model returned an invalid embedding vector")
            normalized_embeddings.append([float(value) for value in embedding])

        if len(normalized_embeddings) != len(text_list):
            raise EmbedderError("Embedding count does not match input text count")
        return normalized_embeddings


class BGEEmbedder:
    """Embed corpus chunks with BAAI BGE via sentence-transformers."""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        model: Any | None = None,
        cache_folder: str | Path | None = None,
        batch_size: int = 32,
        normalize_embeddings: bool = True,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        self.model_name = model_name or get_settings().bge_model_name
        self.cache_folder = Path(cache_folder) if cache_folder is not None else None
        self.batch_size = batch_size
        self.normalize_embeddings = normalize_embeddings
        self._model = model

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        text_list = [text for text in texts]
        if not text_list:
            return []
        if any(not text.strip() for text in text_list):
            raise EmbedderError("Cannot embed empty text")

        raw_embeddings = self.model.encode(
            text_list,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        embeddings = self._to_list(raw_embeddings)
        if len(embeddings) != len(text_list):
            raise EmbedderError("Embedding count does not match input text count")
        return embeddings

    def embed_chunks(self, chunks: Iterable[CorpusChunk]) -> list[EmbeddedChunk]:
        chunk_list = list(chunks)
        embeddings = self.embed_texts(chunk.content for chunk in chunk_list)
        return [
            EmbeddedChunk(chunk=chunk, embedding=embedding)
            for chunk, embedding in zip(chunk_list, embeddings, strict=True)
        ]

    def _load_model(self) -> Any:
        from sentence_transformers import SentenceTransformer

        kwargs: dict[str, Any] = {}
        if self.cache_folder is not None:
            kwargs["cache_folder"] = str(self.cache_folder)

        return SentenceTransformer(self.model_name, **kwargs)

    def _to_list(self, embeddings: Any) -> list[list[float]]:
        if hasattr(embeddings, "tolist"):
            embeddings = embeddings.tolist()

        if not isinstance(embeddings, list):
            raise EmbedderError("Model returned embeddings in an unsupported format")

        normalized_embeddings: list[list[float]] = []
        for embedding in embeddings:
            if hasattr(embedding, "tolist"):
                embedding = embedding.tolist()
            if not isinstance(embedding, list) or not embedding:
                raise EmbedderError("Model returned an invalid embedding vector")
            normalized_embeddings.append([float(value) for value in embedding])

        return normalized_embeddings


class ChromaVectorIndexWriter:
    """Persist embedded chunks, vectors, and metadata into a local ChromaDB store."""

    def __init__(
        self,
        *,
        vector_store_path: str | Path | None = None,
        collection_name: str = "mutual_fund_facts",
        client: Any | None = None,
    ) -> None:
        if not collection_name.strip():
            raise ValueError("collection_name cannot be empty")

        self.vector_store_path = Path(vector_store_path) if vector_store_path is not None else get_settings().vector_store_path
        self.collection_name = collection_name
        self._client = client
        self._collection: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._load_client()
        return self._client

    @property
    def collection(self) -> Any:
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def upsert(self, embedded_chunks: Iterable[EmbeddedChunk]) -> VectorIndexWriteResult:
        embedded_list = list(embedded_chunks)
        if not embedded_list:
            return VectorIndexWriteResult(
                collection_name=self.collection_name,
                vector_store_path=self.vector_store_path,
                upserted_count=0,
                chunk_ids=[],
            )

        self._validate_embeddings(embedded_list)

        ids = [embedded.chunk_id for embedded in embedded_list]
        documents = [embedded.chunk.content for embedded in embedded_list]
        embeddings = [embedded.embedding for embedded in embedded_list]
        metadatas = [self._metadata_for_chunk(embedded.chunk) for embedded in embedded_list]

        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        return VectorIndexWriteResult(
            collection_name=self.collection_name,
            vector_store_path=self.vector_store_path,
            upserted_count=len(embedded_list),
            chunk_ids=ids,
        )

    def _load_client(self) -> Any:
        import chromadb

        self.vector_store_path.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(self.vector_store_path))

    @staticmethod
    def _metadata_for_chunk(chunk: CorpusChunk) -> dict[str, str]:
        return {
            "chunk_id": chunk.chunk_id,
            "scheme_name": chunk.scheme_name,
            "scheme_slug": chunk.scheme_slug,
            "category": chunk.category,
            "field": chunk.field,
            "source_url": chunk.source_url,
            "fetched_at": chunk.fetched_at or "",
        }

    @staticmethod
    def _validate_embeddings(embedded_chunks: list[EmbeddedChunk]) -> None:
        for embedded in embedded_chunks:
            if not embedded.embedding:
                raise VectorIndexError(f"Chunk {embedded.chunk_id} has an empty embedding")
            if any(not isinstance(value, int | float) for value in embedded.embedding):
                raise VectorIndexError(f"Chunk {embedded.chunk_id} has a non-numeric embedding")
