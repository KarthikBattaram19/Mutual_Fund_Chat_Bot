from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.chunker import CorpusChunk, FieldChunker
from ingestion.extractor import ExtractedSchemeFacts, FactExtractor
from ingestion.fetcher import FetchResult, URLFetcher
from ingestion.indexer import BGEEmbedder, ChromaVectorIndexWriter, VectorIndexWriteResult
from ingestion.parser import GrowwHTMLParser, ParsedPage


DEFAULT_CORPUS_INDEX_PATH = Path("data/corpus_index.json")
DEFAULT_SAMPLE_CHUNKS_PATH = Path("data/sample_chunks.json")
DEFAULT_LOG_PATH = Path("logs/ingestion_run.log")
EXPECTED_SCHEME_COUNT = 5
REQUIRED_CHUNK_METADATA_FIELDS = (
    "chunk_id",
    "scheme_name",
    "scheme_slug",
    "category",
    "field",
    "content",
    "source_url",
    "fetched_at",
)
EXCLUDED_CHUNK_CONTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(blog|editorial|opinion|pros and cons|review|rating|star rating)\b", re.IGNORECASE),
    re.compile(r"\b(return calculator|sip calculator|calculator|chart|graph)\b", re.IGNORECASE),
    re.compile(r"\b(compare|comparison|versus|vs\.?)\b", re.IGNORECASE),
    re.compile(r"\b(should\s+(i|you|one)\s+invest|recommend|recommendation|best fund|better fund)\b", re.IGNORECASE),
    re.compile(r"\b(past performance|historical performance|annualised returns?|cagr|returns?)\b", re.IGNORECASE),
    re.compile(r"\b(login|sign in|subscribe|subscription-only|gated)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class IngestionFailure:
    source_url: str
    stage: str
    error: str


@dataclass(frozen=True)
class SchemeFieldCoverage:
    scheme_name: str
    scheme_slug: str
    source_url: str
    indexed_fields: list[str]
    missing_fields: list[str]
    chunk_count: int
    status: str


@dataclass(frozen=True)
class IngestionValidationResult:
    expected_scheme_count: int
    configured_scheme_count: int
    indexed_scheme_count: int
    field_coverage: list[SchemeFieldCoverage]
    unreachable_urls: list[str] = field(default_factory=list)
    partial_scheme_slugs: list[str] = field(default_factory=list)
    metadata_errors: list[str] = field(default_factory=list)
    excluded_content_hits: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class IngestionRunResult:
    fetched_count: int
    parsed_count: int
    extracted_count: int
    chunk_count: int
    embedded_count: int
    indexed_count: int
    updated_corpus_count: int
    dry_run: bool = False
    validation: IngestionValidationResult | None = None
    failures: list[IngestionFailure] = field(default_factory=list)
    chunks: list[CorpusChunk] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures and self.indexed_count > 0 and (self.validation is None or self.validation.ok)


class IngestionPipeline:
    """Orchestrates fetch -> parse -> extract/filter -> chunk -> embed -> index."""

    def __init__(
        self,
        *,
        fetcher: Any | None = None,
        parser: GrowwHTMLParser | None = None,
        extractor: FactExtractor | None = None,
        chunker: FieldChunker | None = None,
        embedder: BGEEmbedder | None = None,
        index_writer: ChromaVectorIndexWriter | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.parser = parser or GrowwHTMLParser()
        self.extractor = extractor or FactExtractor()
        self.chunker = chunker or FieldChunker()
        self.embedder = embedder or BGEEmbedder()
        self.index_writer = index_writer or ChromaVectorIndexWriter()

    def run(
        self,
        *,
        corpus_index_path: str | Path = DEFAULT_CORPUS_INDEX_PATH,
        dry_run: bool = False,
        expected_scheme_count: int = EXPECTED_SCHEME_COUNT,
    ) -> IngestionRunResult:
        corpus_path = Path(corpus_index_path)
        corpus_entries = _load_corpus_index(corpus_path)
        corpus_by_url = {str(entry["source_url"]): entry for entry in corpus_entries}

        fetcher = self.fetcher or URLFetcher()
        should_close_fetcher = self.fetcher is None
        try:
            fetch_results = fetcher.fetch_all(corpus_entries)
        finally:
            if should_close_fetcher and hasattr(fetcher, "close"):
                fetcher.close()

        failures: list[IngestionFailure] = []
        parsed_pages: list[ParsedPage] = []
        fetched_at_by_url: dict[str, str] = {}

        for fetch_result in fetch_results:
            if not fetch_result.ok or fetch_result.html is None:
                failures.append(
                    IngestionFailure(
                        source_url=fetch_result.url,
                        stage="fetch",
                        error=fetch_result.error or f"HTTP {fetch_result.status_code}",
                    )
                )
                continue

            try:
                parsed_pages.append(self.parser.parse(fetch_result.html, source_url=fetch_result.url))
                fetched_at_by_url[fetch_result.url] = fetch_result.fetched_at
            except Exception as exc:
                failures.append(IngestionFailure(source_url=fetch_result.url, stage="parse", error=str(exc)))

        extracted_schemes: list[ExtractedSchemeFacts] = []
        for parsed_page in parsed_pages:
            corpus_entry = corpus_by_url.get(parsed_page.source_url)
            if corpus_entry is None:
                failures.append(
                    IngestionFailure(
                        source_url=parsed_page.source_url,
                        stage="extract",
                        error="No corpus entry found for parsed page",
                    )
                )
                continue

            try:
                extracted_schemes.append(
                    self.extractor.extract(
                        parsed_page,
                        corpus_entry,
                        fetched_at=fetched_at_by_url.get(parsed_page.source_url),
                    )
                )
            except Exception as exc:
                failures.append(IngestionFailure(source_url=parsed_page.source_url, stage="extract", error=str(exc)))

        chunks: list[CorpusChunk] = []
        for extracted in extracted_schemes:
            try:
                chunks.extend(self.chunker.chunk_scheme(extracted))
            except Exception as exc:
                failures.append(IngestionFailure(source_url=extracted.source_url, stage="chunk", error=str(exc)))

        embedded_chunks = [] if dry_run else self.embedder.embed_chunks(chunks)
        write_result = (
            VectorIndexWriteResult(
                collection_name=getattr(self.index_writer, "collection_name", "dry_run"),
                vector_store_path=Path(getattr(self.index_writer, "vector_store_path", "")),
                upserted_count=0,
                chunk_ids=[],
            )
            if dry_run
            else self.index_writer.upsert(embedded_chunks)
        )

        updated_corpus_count = 0
        if not dry_run:
            indexed_urls = {embedded.chunk.source_url for embedded in embedded_chunks}
            updated_corpus_count = _update_corpus_fetched_at(corpus_path, corpus_entries, fetched_at_by_url, indexed_urls)

        validation = _validate_ingestion(
            corpus_entries=corpus_entries,
            extracted_schemes=extracted_schemes,
            chunks=chunks,
            failures=failures,
            expected_scheme_count=expected_scheme_count,
        )

        return IngestionRunResult(
            fetched_count=sum(1 for result in fetch_results if result.ok),
            parsed_count=len(parsed_pages),
            extracted_count=len(extracted_schemes),
            chunk_count=len(chunks),
            embedded_count=len(embedded_chunks),
            indexed_count=write_result.upserted_count,
            updated_corpus_count=updated_corpus_count,
            dry_run=dry_run,
            validation=validation,
            failures=failures,
            chunks=chunks,
        )


def _load_corpus_index(corpus_index_path: Path) -> list[dict[str, Any]]:
    return json.loads(corpus_index_path.read_text(encoding="utf-8"))


def _update_corpus_fetched_at(
    corpus_index_path: Path,
    corpus_entries: list[dict[str, Any]],
    fetched_at_by_url: Mapping[str, str],
    indexed_urls: Iterable[str],
) -> int:
    indexed_url_set = set(indexed_urls)
    updated_count = 0

    for entry in corpus_entries:
        source_url = str(entry["source_url"])
        if source_url not in indexed_url_set:
            continue
        fetched_at = fetched_at_by_url.get(source_url)
        if fetched_at is None:
            continue
        entry["fetched_at"] = fetched_at
        updated_count += 1

    corpus_index_path.write_text(json.dumps(corpus_entries, indent=2) + "\n", encoding="utf-8")
    return updated_count


def _validate_ingestion(
    *,
    corpus_entries: list[dict[str, Any]],
    extracted_schemes: list[ExtractedSchemeFacts],
    chunks: list[CorpusChunk],
    failures: list[IngestionFailure],
    expected_scheme_count: int,
) -> IngestionValidationResult:
    chunks_by_slug: dict[str, list[CorpusChunk]] = {}
    for chunk in chunks:
        chunks_by_slug.setdefault(chunk.scheme_slug, []).append(chunk)

    extracted_by_slug = {scheme.scheme_slug: scheme for scheme in extracted_schemes}
    unreachable_urls = sorted({failure.source_url for failure in failures if failure.stage == "fetch"})
    field_coverage: list[SchemeFieldCoverage] = []
    partial_scheme_slugs: list[str] = []

    for entry in corpus_entries:
        scheme_slug = str(entry["scheme_slug"])
        source_url = str(entry["source_url"])
        scheme_chunks = chunks_by_slug.get(scheme_slug, [])
        indexed_fields = [chunk.field for chunk in scheme_chunks]
        extracted = extracted_by_slug.get(scheme_slug)
        missing_fields = list(extracted.missing_fields) if extracted is not None else []

        if source_url in unreachable_urls:
            status = "unreachable"
        elif not scheme_chunks:
            status = "not_indexed"
        elif missing_fields:
            status = "partial"
            partial_scheme_slugs.append(scheme_slug)
        else:
            status = "complete"

        field_coverage.append(
            SchemeFieldCoverage(
                scheme_name=str(entry["scheme_name"]),
                scheme_slug=scheme_slug,
                source_url=source_url,
                indexed_fields=indexed_fields,
                missing_fields=missing_fields,
                chunk_count=len(scheme_chunks),
                status=status,
            )
        )

    indexed_scheme_count = sum(1 for coverage in field_coverage if coverage.chunk_count > 0)
    metadata_errors = _validate_chunk_metadata(chunks)
    excluded_content_hits = _find_excluded_chunk_content(chunks)
    errors: list[str] = []
    if len(corpus_entries) != expected_scheme_count:
        errors.append(f"Expected {expected_scheme_count} configured schemes, found {len(corpus_entries)}")
    if indexed_scheme_count != expected_scheme_count:
        errors.append(f"Expected {expected_scheme_count} indexed schemes, found {indexed_scheme_count}")
    if unreachable_urls:
        errors.append(f"Unreachable schemes: {len(unreachable_urls)}")
    if metadata_errors:
        errors.append(f"Chunk metadata errors: {len(metadata_errors)}")
    if excluded_content_hits:
        errors.append(f"Excluded content found in chunks: {len(excluded_content_hits)}")

    return IngestionValidationResult(
        expected_scheme_count=expected_scheme_count,
        configured_scheme_count=len(corpus_entries),
        indexed_scheme_count=indexed_scheme_count,
        field_coverage=field_coverage,
        unreachable_urls=unreachable_urls,
        partial_scheme_slugs=partial_scheme_slugs,
        metadata_errors=metadata_errors,
        excluded_content_hits=excluded_content_hits,
        errors=errors,
    )


def _validate_chunk_metadata(chunks: list[CorpusChunk]) -> list[str]:
    errors: list[str] = []
    seen_chunk_ids: set[str] = set()

    for chunk in chunks:
        values = chunk.to_dict()
        missing = [field_name for field_name in REQUIRED_CHUNK_METADATA_FIELDS if not values.get(field_name)]
        if missing:
            errors.append(f"{chunk.chunk_id or '<missing chunk_id>'}: missing {', '.join(missing)}")

        expected_chunk_id = f"{chunk.scheme_slug}:{chunk.field}"
        if chunk.chunk_id != expected_chunk_id:
            errors.append(f"{chunk.chunk_id}: expected stable id {expected_chunk_id}")

        if chunk.chunk_id in seen_chunk_ids:
            errors.append(f"{chunk.chunk_id}: duplicate chunk id")
        seen_chunk_ids.add(chunk.chunk_id)

    return errors


def _find_excluded_chunk_content(chunks: list[CorpusChunk]) -> list[str]:
    hits: list[str] = []
    for chunk in chunks:
        for pattern in EXCLUDED_CHUNK_CONTENT_PATTERNS:
            if pattern.search(chunk.content):
                hits.append(f"{chunk.chunk_id}: {pattern.pattern}")
                break
    return hits


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest the configured Groww mutual fund corpus.")
    parser.add_argument(
        "--corpus-index",
        default=str(DEFAULT_CORPUS_INDEX_PATH),
        help="Path to data/corpus_index.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run fetch/parse/extract/chunk without embedding, indexing, or updating corpus timestamps.",
    )
    parser.add_argument(
        "--expected-scheme-count",
        type=int,
        default=EXPECTED_SCHEME_COUNT,
        help="Expected number of configured and indexed schemes.",
    )
    parser.add_argument(
        "--sample-chunks-output",
        default=str(DEFAULT_SAMPLE_CHUNKS_PATH),
        help="Path for sample chunk JSON generated from the current ingestion run.",
    )
    parser.add_argument(
        "--log-output",
        default=str(DEFAULT_LOG_PATH),
        help="Path for the ingestion run log with per-scheme field coverage.",
    )
    parser.add_argument(
        "--no-artifacts",
        action="store_true",
        help="Skip writing sample chunk and ingestion log artifacts.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = IngestionPipeline().run(
        corpus_index_path=args.corpus_index,
        dry_run=args.dry_run,
        expected_scheme_count=args.expected_scheme_count,
    )
    _print_summary(result)
    if not args.no_artifacts:
        _write_artifacts(
            result,
            sample_chunks_path=Path(args.sample_chunks_output),
            log_path=Path(args.log_output),
        )
    return 0 if result.ok or args.dry_run else 1


def _print_summary(result: IngestionRunResult) -> None:
    for line in _summary_lines(result):
        print(line)


def _write_artifacts(
    result: IngestionRunResult,
    *,
    sample_chunks_path: Path = DEFAULT_SAMPLE_CHUNKS_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
) -> None:
    _write_sample_chunks(result, sample_chunks_path)
    _write_run_log(result, log_path)


def _write_sample_chunks(result: IngestionRunResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chunks = getattr(result, "chunks", [])
    output_path.write_text(
        json.dumps([chunk.to_dict() for chunk in chunks], indent=2) + "\n",
        encoding="utf-8",
    )


def _write_run_log(result: IngestionRunResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(_summary_lines(result)) + "\n", encoding="utf-8")


def _summary_lines(result: IngestionRunResult) -> list[str]:
    lines: list[str] = []
    mode = "DRY RUN" if result.dry_run else "WRITE"
    lines.append(f"Ingestion mode: {mode}")
    lines.append(f"Fetched pages: {result.fetched_count}")
    lines.append(f"Parsed pages: {result.parsed_count}")
    lines.append(f"Extracted schemes: {result.extracted_count}")
    lines.append(f"Chunks produced: {result.chunk_count}")
    lines.append(f"Embeddings produced: {result.embedded_count}")
    lines.append(f"Chunks indexed: {result.indexed_count}")
    lines.append(f"Corpus timestamps updated: {result.updated_corpus_count}")

    if result.validation is not None:
        validation = result.validation
        lines.append(
            "Validation: "
            f"{validation.indexed_scheme_count}/{validation.expected_scheme_count} schemes indexed; "
            f"{len(validation.partial_scheme_slugs)} partial; "
            f"{len(validation.unreachable_urls)} unreachable"
        )
        lines.append("Field coverage:")
        for coverage in validation.field_coverage:
            indexed = ", ".join(coverage.indexed_fields) or "none"
            missing = ", ".join(coverage.missing_fields) or "none"
            lines.append(f"- {coverage.scheme_slug} [{coverage.status}]: indexed={indexed}; missing={missing}")

        if validation.errors:
            lines.append("Validation errors:")
            for error in validation.errors:
                lines.append(f"- {error}")

        if validation.metadata_errors:
            lines.append("Chunk metadata errors:")
            for error in validation.metadata_errors:
                lines.append(f"- {error}")

        if validation.excluded_content_hits:
            lines.append("Excluded content hits:")
            for hit in validation.excluded_content_hits:
                lines.append(f"- {hit}")

    if result.failures:
        lines.append("Failures:")
        for failure in result.failures:
            lines.append(f"- [{failure.stage}] {failure.source_url}: {failure.error}")

    return lines


if __name__ == "__main__":
    raise SystemExit(main())
