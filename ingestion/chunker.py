from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ingestion.extractor import CANONICAL_FIELDS, ExtractedFact, ExtractedSchemeFacts


@dataclass(frozen=True)
class CorpusChunk:
    """Field-level chunk ready for embedding and vector-store metadata."""

    chunk_id: str
    scheme_name: str
    scheme_slug: str
    category: str
    field: str
    content: str
    source_url: str
    fetched_at: str | None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


class ChunkerError(ValueError):
    """Raised when extracted scheme metadata is insufficient for chunking."""


class FieldChunker:
    """Create deterministic one-field chunks from extracted scheme facts."""

    def chunk_scheme(self, extracted: ExtractedSchemeFacts) -> list[CorpusChunk]:
        self._validate_scheme_metadata(extracted)

        chunks: list[CorpusChunk] = []
        for field_name in CANONICAL_FIELDS:
            fact = extracted.facts.get(field_name)
            if fact is None:
                continue
            chunks.append(self._to_chunk(extracted, fact))
        return chunks

    def chunk_many(self, extracted_schemes: Iterable[ExtractedSchemeFacts]) -> list[CorpusChunk]:
        chunks: list[CorpusChunk] = []
        for extracted in extracted_schemes:
            chunks.extend(self.chunk_scheme(extracted))
        return chunks

    def _to_chunk(self, extracted: ExtractedSchemeFacts, fact: ExtractedFact) -> CorpusChunk:
        return CorpusChunk(
            chunk_id=f"{extracted.scheme_slug}:{fact.field}",
            scheme_name=extracted.scheme_name,
            scheme_slug=extracted.scheme_slug,
            category=extracted.category,
            field=fact.field,
            content=fact.content,
            source_url=extracted.source_url,
            fetched_at=extracted.fetched_at,
        )

    @staticmethod
    def _validate_scheme_metadata(extracted: ExtractedSchemeFacts) -> None:
        missing = [
            name
            for name, value in (
                ("scheme_name", extracted.scheme_name),
                ("scheme_slug", extracted.scheme_slug),
                ("category", extracted.category),
                ("source_url", extracted.source_url),
            )
            if not value
        ]
        if missing:
            raise ChunkerError(f"Missing required chunk metadata: {', '.join(missing)}")
