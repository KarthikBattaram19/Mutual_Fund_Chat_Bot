from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.chunker import CorpusChunk
from ingestion.indexer import BGEEmbedder, ChromaVectorIndexWriter

DEFAULT_CHUNKS_PATH = Path("data/sample_chunks.json")


def load_chunks(path: Path) -> list[CorpusChunk]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        CorpusChunk(
            chunk_id=str(item["chunk_id"]),
            scheme_name=str(item["scheme_name"]),
            scheme_slug=str(item["scheme_slug"]),
            category=str(item["category"]),
            field=str(item["field"]),
            content=str(item["content"]),
            source_url=str(item["source_url"]),
            fetched_at=item.get("fetched_at"),
        )
        for item in raw
    ]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Embed sample_chunks.json and write the local Chroma vector store.",
    )
    parser.add_argument(
        "--chunks",
        default=str(DEFAULT_CHUNKS_PATH),
        help="Path to chunk JSON (default: data/sample_chunks.json).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    chunks_path = Path(args.chunks)
    if not chunks_path.exists():
        print(f"Chunk file not found: {chunks_path}", file=sys.stderr)
        return 1

    chunks = load_chunks(chunks_path)
    if not chunks:
        print("No chunks found to index.", file=sys.stderr)
        return 1

    embedder = BGEEmbedder()
    embedded = embedder.embed_chunks(chunks)
    result = ChromaVectorIndexWriter().upsert(embedded)
    print(
        f"Indexed {result.upserted_count} chunks into "
        f"{result.vector_store_path} (collection: {result.collection_name})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
