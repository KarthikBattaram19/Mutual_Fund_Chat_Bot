import pytest

from ingestion.chunker import CorpusChunk
from ingestion.indexer import BGEEmbedder, ChromaVectorIndexWriter, EmbeddedChunk, EmbedderError, FastQueryEmbedder, VectorIndexError


class FakeEmbeddings:
    def __init__(self, values) -> None:
        self.values = values

    def tolist(self):
        return self.values


class FakeModel:
    def __init__(self, embeddings=None) -> None:
        self.embeddings = embeddings
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append({"texts": texts, **kwargs})
        if self.embeddings is not None:
            return self.embeddings
        return [[float(index), float(len(text))] for index, text in enumerate(texts)]


class FakeFastEmbedModel:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeCollection:
    def __init__(self) -> None:
        self.upserts = []

    def upsert(self, **kwargs) -> None:
        self.upserts.append(kwargs)


class FakeClient:
    def __init__(self) -> None:
        self.collection = FakeCollection()
        self.collection_requests = []

    def get_or_create_collection(self, **kwargs):
        self.collection_requests.append(kwargs)
        return self.collection


def chunk(chunk_id: str, content: str) -> CorpusChunk:
    scheme_slug, field = chunk_id.split(":", 1)
    return CorpusChunk(
        chunk_id=chunk_id,
        scheme_name="HDFC Large Cap Fund - Direct Growth",
        scheme_slug=scheme_slug,
        category="Large Cap (Equity)",
        field=field,
        content=content,
        source_url=f"https://groww.in/mutual-funds/{scheme_slug}",
        fetched_at="2026-06-28T00:00:00Z",
    )


def test_fast_query_embedder_uses_configured_model_name() -> None:
    embedder = FastQueryEmbedder(model=FakeFastEmbedModel())

    assert embedder.model_name == "BAAI/bge-small-en-v1.5"


def test_embed_texts_uses_configured_model_options() -> None:
    model = FakeModel()
    embedder = BGEEmbedder(
        model_name="BAAI/bge-small-en-v1.5",
        model=model,
        batch_size=2,
        normalize_embeddings=True,
    )

    embeddings = embedder.embed_texts(["NAV: Rs 100.00", "Expense ratio: 0.88%"])

    assert embeddings == [[0.0, 14.0], [1.0, 20.0]]
    assert model.calls == [
        {
            "texts": ["NAV: Rs 100.00", "Expense ratio: 0.88%"],
            "batch_size": 2,
            "normalize_embeddings": True,
            "show_progress_bar": False,
        }
    ]


def test_embed_chunks_embeds_chunk_content_and_preserves_metadata() -> None:
    model = FakeModel(embeddings=FakeEmbeddings([[0.1, 0.2, 0.3]]))
    corpus_chunk = chunk("hdfc-large-cap-fund-direct-growth:expense_ratio", "Expense ratio: 0.88%")

    embedded = BGEEmbedder(model=model).embed_chunks([corpus_chunk])

    assert len(embedded) == 1
    assert embedded[0].chunk_id == "hdfc-large-cap-fund-direct-growth:expense_ratio"
    assert embedded[0].embedding == [0.1, 0.2, 0.3]
    assert embedded[0].to_dict() == {
        "chunk_id": "hdfc-large-cap-fund-direct-growth:expense_ratio",
        "scheme_name": "HDFC Large Cap Fund - Direct Growth",
        "scheme_slug": "hdfc-large-cap-fund-direct-growth",
        "category": "Large Cap (Equity)",
        "field": "expense_ratio",
        "content": "Expense ratio: 0.88%",
        "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        "fetched_at": "2026-06-28T00:00:00Z",
        "embedding": [0.1, 0.2, 0.3],
    }
    assert model.calls[0]["texts"] == ["Expense ratio: 0.88%"]


def test_embedder_returns_empty_list_for_empty_inputs() -> None:
    model = FakeModel()
    embedder = BGEEmbedder(model=model)

    assert embedder.embed_texts([]) == []
    assert embedder.embed_chunks([]) == []
    assert model.calls == []


def test_embedder_rejects_empty_text() -> None:
    with pytest.raises(EmbedderError, match="Cannot embed empty text"):
        BGEEmbedder(model=FakeModel()).embed_texts(["NAV: Rs 100.00", " "])


def test_embedder_rejects_embedding_count_mismatch() -> None:
    model = FakeModel(embeddings=[[0.1, 0.2]])

    with pytest.raises(EmbedderError, match="Embedding count does not match"):
        BGEEmbedder(model=model).embed_texts(["one", "two"])


def test_embedder_rejects_invalid_embedding_vector() -> None:
    model = FakeModel(embeddings=[[]])

    with pytest.raises(EmbedderError, match="invalid embedding vector"):
        BGEEmbedder(model=model).embed_texts(["NAV: Rs 100.00"])


def test_embedder_uses_default_bge_model_name_from_settings() -> None:
    embedder = BGEEmbedder(model=FakeModel())

    assert embedder.model_name == "BAAI/bge-small-en-v1.5"


def test_vector_writer_upserts_embeddings_documents_and_metadata(tmp_path) -> None:
    client = FakeClient()
    writer = ChromaVectorIndexWriter(
        vector_store_path=tmp_path / "vector_store",
        collection_name="test_facts",
        client=client,
    )
    corpus_chunk = chunk("hdfc-large-cap-fund-direct-growth:expense_ratio", "Expense ratio: 0.88%")
    embedded = EmbeddedChunk(chunk=corpus_chunk, embedding=[0.1, 0.2, 0.3])

    result = writer.upsert([embedded])

    assert result.collection_name == "test_facts"
    assert result.vector_store_path == tmp_path / "vector_store"
    assert result.upserted_count == 1
    assert result.chunk_ids == ["hdfc-large-cap-fund-direct-growth:expense_ratio"]
    assert client.collection_requests == [
        {"name": "test_facts", "metadata": {"hnsw:space": "cosine"}},
    ]
    assert client.collection.upserts == [
        {
            "ids": ["hdfc-large-cap-fund-direct-growth:expense_ratio"],
            "documents": ["Expense ratio: 0.88%"],
            "embeddings": [[0.1, 0.2, 0.3]],
            "metadatas": [
                {
                    "chunk_id": "hdfc-large-cap-fund-direct-growth:expense_ratio",
                    "scheme_name": "HDFC Large Cap Fund - Direct Growth",
                    "scheme_slug": "hdfc-large-cap-fund-direct-growth",
                    "category": "Large Cap (Equity)",
                    "field": "expense_ratio",
                    "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
                    "fetched_at": "2026-06-28T00:00:00Z",
                }
            ],
        }
    ]


def test_vector_writer_converts_missing_fetched_at_to_empty_metadata_value(tmp_path) -> None:
    client = FakeClient()
    writer = ChromaVectorIndexWriter(vector_store_path=tmp_path, client=client)
    corpus_chunk = chunk("hdfc-large-cap-fund-direct-growth:nav", "NAV: Rs 100.00")
    corpus_chunk = CorpusChunk(**{**corpus_chunk.to_dict(), "fetched_at": None})

    writer.upsert([EmbeddedChunk(chunk=corpus_chunk, embedding=[1.0, 2.0])])

    assert client.collection.upserts[0]["metadatas"][0]["fetched_at"] == ""


def test_vector_writer_returns_empty_result_without_touching_collection(tmp_path) -> None:
    client = FakeClient()
    writer = ChromaVectorIndexWriter(vector_store_path=tmp_path, client=client)

    result = writer.upsert([])

    assert result.upserted_count == 0
    assert result.chunk_ids == []
    assert client.collection_requests == []
    assert client.collection.upserts == []


def test_vector_writer_rejects_empty_embedding(tmp_path) -> None:
    writer = ChromaVectorIndexWriter(vector_store_path=tmp_path, client=FakeClient())
    corpus_chunk = chunk("hdfc-large-cap-fund-direct-growth:nav", "NAV: Rs 100.00")

    with pytest.raises(VectorIndexError, match="empty embedding"):
        writer.upsert([EmbeddedChunk(chunk=corpus_chunk, embedding=[])])


def test_vector_writer_rejects_non_numeric_embedding(tmp_path) -> None:
    writer = ChromaVectorIndexWriter(vector_store_path=tmp_path, client=FakeClient())
    corpus_chunk = chunk("hdfc-large-cap-fund-direct-growth:nav", "NAV: Rs 100.00")

    with pytest.raises(VectorIndexError, match="non-numeric embedding"):
        writer.upsert([EmbeddedChunk(chunk=corpus_chunk, embedding=[1.0, "bad"])])


def test_vector_writer_uses_default_vector_store_path() -> None:
    writer = ChromaVectorIndexWriter(client=FakeClient())

    assert writer.vector_store_path.as_posix() == "data/vector_store"
