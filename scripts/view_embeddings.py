from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import get_settings
from ingestion.chunker import CorpusChunk
from ingestion.indexer import BGEEmbedder


DEFAULT_CHUNKS_PATH = Path("data/sample_chunks.json")
DEFAULT_COLLECTION_NAME = "mutual_fund_facts"


@dataclass(frozen=True)
class ChunkEmbeddingView:
    chunk: CorpusChunk
    embedding: list[float]

    @property
    def dimension(self) -> int:
        return len(self.embedding)

    @property
    def l2_norm(self) -> float:
        return math.sqrt(sum(value * value for value in self.embedding))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="View and verify embeddings for every generated corpus chunk.",
    )
    parser.add_argument(
        "--chunks",
        default=str(DEFAULT_CHUNKS_PATH),
        help="Path to chunk JSON, usually data/sample_chunks.json.",
    )
    parser.add_argument(
        "--source",
        choices=("computed", "stored"),
        default="computed",
        help=(
            "computed embeds chunk content with the configured BGE model; "
            "stored reads embeddings already persisted in Chroma."
        ),
    )
    parser.add_argument(
        "--vector-store-path",
        default=None,
        help="Chroma vector store path. Defaults to VECTOR_STORE_PATH from config.",
    )
    parser.add_argument(
        "--collection-name",
        default=DEFAULT_COLLECTION_NAME,
        help="Chroma collection name used by ingestion.",
    )
    parser.add_argument(
        "--preview-values",
        type=int,
        default=8,
        help="Number of embedding values to print per chunk unless --full is used.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print full embedding vectors for every chunk.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    chunks = load_chunks(Path(args.chunks))

    if args.source == "stored":
        views = load_stored_embeddings(
            chunks,
            vector_store_path=args.vector_store_path,
            collection_name=args.collection_name,
        )
    else:
        views = compute_embeddings(chunks)

    errors = verify_embeddings(chunks, views)
    print_embedding_report(
        views,
        source=args.source,
        preview_values=args.preview_values,
        full=args.full,
    )

    if errors:
        print("\nVerification: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nVerification: PASS")
    print(f"Verified embeddings for all {len(chunks)} chunks.")
    return 0


def load_chunks(path: Path) -> list[CorpusChunk]:
    if not path.exists():
        raise FileNotFoundError(f"Chunk file not found: {path}")

    raw_chunks = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_chunks, list):
        raise ValueError(f"Expected {path} to contain a JSON list")

    chunks = [CorpusChunk(**raw_chunk) for raw_chunk in raw_chunks]
    if not chunks:
        raise ValueError(f"No chunks found in {path}")
    return chunks


def compute_embeddings(chunks: list[CorpusChunk]) -> list[ChunkEmbeddingView]:
    embedder = BGEEmbedder()
    embedded_chunks = embedder.embed_chunks(chunks)
    return [
        ChunkEmbeddingView(chunk=embedded.chunk, embedding=embedded.embedding)
        for embedded in embedded_chunks
    ]


def load_stored_embeddings(
    chunks: list[CorpusChunk],
    *,
    vector_store_path: str | None,
    collection_name: str,
) -> list[ChunkEmbeddingView]:
    store_path = Path(vector_store_path) if vector_store_path is not None else get_settings().vector_store_path
    if not store_path.exists():
        raise FileNotFoundError(f"Vector store path not found: {store_path}")

    import chromadb

    client = chromadb.PersistentClient(path=str(store_path))
    collection = client.get_collection(name=collection_name)
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    result = collection.get(
        ids=list(chunk_by_id),
        include=["embeddings"],
    )

    ids = result.get("ids") or []
    embeddings = result.get("embeddings")
    if embeddings is None:
        embeddings = []
    views: list[ChunkEmbeddingView] = []
    for chunk_id, embedding in zip(ids, embeddings, strict=False):
        chunk = chunk_by_id.get(chunk_id)
        if chunk is None:
            continue
        views.append(ChunkEmbeddingView(chunk=chunk, embedding=_to_float_list(embedding)))
    return views


def verify_embeddings(chunks: list[CorpusChunk], views: list[ChunkEmbeddingView]) -> list[str]:
    errors: list[str] = []
    expected_ids = [chunk.chunk_id for chunk in chunks]
    seen_ids = [view.chunk.chunk_id for view in views]

    missing_ids = sorted(set(expected_ids) - set(seen_ids))
    duplicate_ids = sorted({chunk_id for chunk_id in seen_ids if seen_ids.count(chunk_id) > 1})
    if missing_ids:
        errors.append(f"Missing embeddings for {len(missing_ids)} chunks: {', '.join(missing_ids)}")
    if duplicate_ids:
        errors.append(f"Duplicate embeddings found for: {', '.join(duplicate_ids)}")

    dimensions = {view.dimension for view in views}
    if len(dimensions) > 1:
        errors.append(f"Inconsistent embedding dimensions found: {sorted(dimensions)}")

    for view in views:
        if not view.embedding:
            errors.append(f"{view.chunk.chunk_id}: empty embedding")
            continue
        if any(not isinstance(value, int | float) for value in view.embedding):
            errors.append(f"{view.chunk.chunk_id}: non-numeric embedding value")
        if any(not math.isfinite(float(value)) for value in view.embedding):
            errors.append(f"{view.chunk.chunk_id}: non-finite embedding value")

    return errors


def print_embedding_report(
    views: Iterable[ChunkEmbeddingView],
    *,
    source: str,
    preview_values: int,
    full: bool,
) -> None:
    view_list = list(views)
    settings = get_settings()
    dimensions = sorted({view.dimension for view in view_list})

    print(f"Embedding source: {source}")
    print(f"Model: {settings.bge_model_name}")
    print(f"Chunks with embeddings: {len(view_list)}")
    print(f"Dimensions: {dimensions if dimensions else 'none'}")
    print("")

    for index, view in enumerate(view_list, start=1):
        values = view.embedding if full else view.embedding[:preview_values]
        suffix = "" if full or len(values) == len(view.embedding) else " ..."
        formatted_values = ", ".join(f"{value:.8f}" for value in values)
        print(f"{index}. {view.chunk.chunk_id}")
        print(f"   scheme: {view.chunk.scheme_name}")
        print(f"   field: {view.chunk.field}")
        print(f"   content: {view.chunk.content}")
        print(f"   dimension: {view.dimension}")
        print(f"   l2_norm: {view.l2_norm:.8f}")
        print(f"   embedding: [{formatted_values}{suffix}]")


def _to_float_list(values: Any) -> list[float]:
    if hasattr(values, "tolist"):
        values = values.tolist()
    if not isinstance(values, list):
        raise ValueError("Stored embedding is not a list")
    return [float(value) for value in values]


if __name__ == "__main__":
    raise SystemExit(main())
