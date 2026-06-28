import json

from ingestion.chunker import CorpusChunk
from ingestion.fetcher import FetchResult
from ingestion.indexer import EmbeddedChunk, VectorIndexWriteResult
from scripts.ingest_corpus import IngestionPipeline, _validate_ingestion, _write_artifacts, main


HTML = """
<html>
  <body>
    <table>
      <tr><th>NAV</th><td>Rs 100.00</td></tr>
      <tr><th>Expense Ratio</th><td>0.88%</td></tr>
    </table>
  </body>
</html>
"""


class FakeFetcher:
    def __init__(self, results) -> None:
        self.results = results
        self.entries = None
        self.closed = False

    def fetch_all(self, entries):
        self.entries = list(entries)
        return self.results

    def close(self) -> None:
        self.closed = True


class FakeEmbedder:
    def __init__(self) -> None:
        self.chunks = None

    def embed_chunks(self, chunks):
        self.chunks = list(chunks)
        return [
            EmbeddedChunk(chunk=chunk, embedding=[float(index), float(len(chunk.content))])
            for index, chunk in enumerate(self.chunks)
        ]


class FakeIndexWriter:
    collection_name = "test_facts"
    vector_store_path = "data/vector_store"

    def __init__(self) -> None:
        self.embedded_chunks = None

    def upsert(self, embedded_chunks):
        self.embedded_chunks = list(embedded_chunks)
        return VectorIndexWriteResult(
            collection_name=self.collection_name,
            vector_store_path=self.vector_store_path,
            upserted_count=len(self.embedded_chunks),
            chunk_ids=[embedded.chunk_id for embedded in self.embedded_chunks],
        )


def write_corpus(tmp_path, entries):
    corpus_path = tmp_path / "corpus_index.json"
    corpus_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return corpus_path


def corpus_entry(slug: str, fetched_at=None):
    return {
        "scheme_name": slug.replace("-", " ").title(),
        "scheme_slug": slug,
        "category": "Large Cap (Equity)",
        "source_url": f"https://groww.in/mutual-funds/{slug}",
        "fetched_at": fetched_at,
    }


def test_ingestion_pipeline_runs_end_to_end_and_updates_successful_timestamp(tmp_path) -> None:
    entry = corpus_entry("hdfc-large-cap-fund-direct-growth")
    corpus_path = write_corpus(tmp_path, [entry])
    fetcher = FakeFetcher(
        [
            FetchResult(
                url=entry["source_url"],
                html=HTML,
                status_code=200,
                fetched_at="2026-06-28T00:00:00Z",
            )
        ]
    )
    embedder = FakeEmbedder()
    index_writer = FakeIndexWriter()

    result = IngestionPipeline(fetcher=fetcher, embedder=embedder, index_writer=index_writer).run(
        corpus_index_path=corpus_path,
        expected_scheme_count=1,
    )

    updated_corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    assert result.ok
    assert result.fetched_count == 1
    assert result.parsed_count == 1
    assert result.extracted_count == 1
    assert result.chunk_count == 3
    assert result.embedded_count == 3
    assert result.indexed_count == 3
    assert result.updated_corpus_count == 1
    assert result.validation.ok
    assert result.validation.indexed_scheme_count == 1
    assert result.validation.partial_scheme_slugs == ["hdfc-large-cap-fund-direct-growth"]
    assert result.validation.field_coverage[0].status == "partial"
    assert result.validation.field_coverage[0].indexed_fields == ["nav", "expense_ratio", "category"]
    assert updated_corpus[0]["fetched_at"] == "2026-06-28T00:00:00Z"
    assert [chunk.field for chunk in embedder.chunks] == ["nav", "expense_ratio", "category"]
    assert [chunk.field for chunk in result.chunks] == ["nav", "expense_ratio", "category"]
    assert [embedded.chunk_id for embedded in index_writer.embedded_chunks] == [
        "hdfc-large-cap-fund-direct-growth:nav",
        "hdfc-large-cap-fund-direct-growth:expense_ratio",
        "hdfc-large-cap-fund-direct-growth:category",
    ]


def test_ingestion_pipeline_rerun_refreshes_timestamp_with_stable_chunk_ids(tmp_path) -> None:
    entry = corpus_entry("hdfc-large-cap-fund-direct-growth")
    corpus_path = write_corpus(tmp_path, [entry])

    first_writer = FakeIndexWriter()
    first_result = IngestionPipeline(
        fetcher=FakeFetcher([FetchResult(entry["source_url"], HTML, 200, "2026-06-28T00:00:00Z")]),
        embedder=FakeEmbedder(),
        index_writer=first_writer,
    ).run(corpus_index_path=corpus_path, expected_scheme_count=1)
    first_ids = [embedded.chunk_id for embedded in first_writer.embedded_chunks]

    second_writer = FakeIndexWriter()
    second_result = IngestionPipeline(
        fetcher=FakeFetcher([FetchResult(entry["source_url"], HTML, 200, "2026-06-29T00:00:00Z")]),
        embedder=FakeEmbedder(),
        index_writer=second_writer,
    ).run(corpus_index_path=corpus_path, expected_scheme_count=1)
    second_ids = [embedded.chunk_id for embedded in second_writer.embedded_chunks]
    updated_corpus = json.loads(corpus_path.read_text(encoding="utf-8"))

    assert first_result.ok
    assert second_result.ok
    assert first_ids == second_ids
    assert updated_corpus[0]["fetched_at"] == "2026-06-29T00:00:00Z"


def test_ingestion_pipeline_flags_failed_fetch_without_updating_that_entry(tmp_path) -> None:
    good_entry = corpus_entry("hdfc-large-cap-fund-direct-growth")
    bad_entry = corpus_entry("hdfc-mid-cap-fund-direct-growth")
    corpus_path = write_corpus(tmp_path, [good_entry, bad_entry])
    fetcher = FakeFetcher(
        [
            FetchResult(good_entry["source_url"], HTML, 200, "2026-06-28T00:00:00Z"),
            FetchResult(bad_entry["source_url"], None, 503, "2026-06-28T00:01:00Z", error="HTTP 503"),
        ]
    )

    result = IngestionPipeline(fetcher=fetcher, embedder=FakeEmbedder(), index_writer=FakeIndexWriter()).run(
        corpus_index_path=corpus_path,
        expected_scheme_count=2,
    )

    updated_corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    assert result.ok is False
    assert result.fetched_count == 1
    assert len(result.failures) == 1
    assert result.failures[0].stage == "fetch"
    assert result.validation.ok is False
    assert result.validation.unreachable_urls == [bad_entry["source_url"]]
    assert result.validation.field_coverage[1].status == "unreachable"
    assert updated_corpus[0]["fetched_at"] == "2026-06-28T00:00:00Z"
    assert updated_corpus[1]["fetched_at"] is None


def test_ingestion_pipeline_dry_run_skips_embedding_indexing_and_timestamp_write(tmp_path) -> None:
    entry = corpus_entry("hdfc-large-cap-fund-direct-growth")
    corpus_path = write_corpus(tmp_path, [entry])
    fetcher = FakeFetcher([FetchResult(entry["source_url"], HTML, 200, "2026-06-28T00:00:00Z")])
    embedder = FakeEmbedder()
    index_writer = FakeIndexWriter()

    result = IngestionPipeline(fetcher=fetcher, embedder=embedder, index_writer=index_writer).run(
        corpus_index_path=corpus_path,
        dry_run=True,
        expected_scheme_count=1,
    )

    updated_corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    assert result.dry_run
    assert result.chunk_count == 3
    assert result.embedded_count == 0
    assert result.indexed_count == 0
    assert result.updated_corpus_count == 0
    assert result.validation.ok
    assert result.validation.indexed_scheme_count == 1
    assert updated_corpus[0]["fetched_at"] is None
    assert embedder.chunks is None
    assert index_writer.embedded_chunks is None


def test_main_returns_success_for_dry_run_even_when_no_chunks(tmp_path, monkeypatch) -> None:
    corpus_path = write_corpus(tmp_path, [corpus_entry("hdfc-large-cap-fund-direct-growth")])

    class EmptyPipeline:
        def run(self, *, corpus_index_path, dry_run, expected_scheme_count):
            assert corpus_index_path == str(corpus_path)
            assert dry_run is True
            assert expected_scheme_count == 5
            return type(
                "Result",
                (),
                {
                    "dry_run": True,
                    "fetched_count": 0,
                    "parsed_count": 0,
                    "extracted_count": 0,
                    "chunk_count": 0,
                    "embedded_count": 0,
                    "indexed_count": 0,
                    "updated_corpus_count": 0,
                    "validation": None,
                    "failures": [],
                    "ok": False,
                },
            )()

    monkeypatch.setattr("scripts.ingest_corpus.IngestionPipeline", EmptyPipeline)

    assert main(["--corpus-index", str(corpus_path), "--dry-run", "--no-artifacts"]) == 0


def test_ingestion_validation_asserts_five_schemes_by_default(tmp_path) -> None:
    entry = corpus_entry("hdfc-large-cap-fund-direct-growth")
    corpus_path = write_corpus(tmp_path, [entry])
    fetcher = FakeFetcher([FetchResult(entry["source_url"], HTML, 200, "2026-06-28T00:00:00Z")])

    result = IngestionPipeline(fetcher=fetcher, embedder=FakeEmbedder(), index_writer=FakeIndexWriter()).run(
        corpus_index_path=corpus_path
    )

    assert result.ok is False
    assert result.validation.ok is False
    assert result.validation.configured_scheme_count == 1
    assert result.validation.indexed_scheme_count == 1
    assert result.validation.errors == [
        "Expected 5 configured schemes, found 1",
        "Expected 5 indexed schemes, found 1",
    ]


def test_ingestion_validation_reports_complete_scheme_when_all_fields_present(tmp_path) -> None:
    html = """
    <html>
      <body>
        <table>
          <tr><th>NAV</th><td>Rs 100.00</td></tr>
          <tr><th>Expense Ratio</th><td>0.88%</td></tr>
          <tr><th>Exit Load</th><td>Nil</td></tr>
          <tr><th>Min SIP</th><td>Rs 100</td></tr>
          <tr><th>Riskometer</th><td>Very High</td></tr>
          <tr><th>Benchmark</th><td>NIFTY 100 TRI</td></tr>
          <tr><th>Fund Manager</th><td>Jane Doe</td></tr>
          <tr><th>AUM</th><td>Rs 32,100 Cr</td></tr>
          <tr><th>Lock-in Period</th><td>No lock-in</td></tr>
        </table>
      </body>
    </html>
    """
    entry = corpus_entry("hdfc-large-cap-fund-direct-growth")
    corpus_path = write_corpus(tmp_path, [entry])
    fetcher = FakeFetcher([FetchResult(entry["source_url"], html, 200, "2026-06-28T00:00:00Z")])

    result = IngestionPipeline(fetcher=fetcher, embedder=FakeEmbedder(), index_writer=FakeIndexWriter()).run(
        corpus_index_path=corpus_path,
        expected_scheme_count=1,
    )

    assert result.validation.ok
    assert result.validation.partial_scheme_slugs == []
    assert result.validation.field_coverage[0].status == "complete"
    assert result.validation.field_coverage[0].missing_fields == []


def test_ingestion_validation_rejects_incomplete_or_unstable_chunk_metadata() -> None:
    entry = corpus_entry("hdfc-large-cap-fund-direct-growth")
    bad_chunk = CorpusChunk(
        chunk_id="unstable-id",
        scheme_name="",
        scheme_slug=entry["scheme_slug"],
        category=entry["category"],
        field="nav",
        content="NAV: Rs 100.00",
        source_url=entry["source_url"],
        fetched_at=None,
    )

    validation = _validate_ingestion(
        corpus_entries=[entry],
        extracted_schemes=[],
        chunks=[bad_chunk],
        failures=[],
        expected_scheme_count=1,
    )

    assert validation.ok is False
    assert validation.errors == ["Chunk metadata errors: 2"]
    assert validation.metadata_errors == [
        "unstable-id: missing scheme_name, fetched_at",
        "unstable-id: expected stable id hdfc-large-cap-fund-direct-growth:nav",
    ]


def test_ingestion_validation_rejects_excluded_content_in_chunks() -> None:
    entry = corpus_entry("hdfc-large-cap-fund-direct-growth")
    chunk = CorpusChunk(
        chunk_id=f"{entry['scheme_slug']}:nav",
        scheme_name=entry["scheme_name"],
        scheme_slug=entry["scheme_slug"],
        category=entry["category"],
        field="nav",
        content="NAV: Review chart says returns are high",
        source_url=entry["source_url"],
        fetched_at="2026-06-28T00:00:00Z",
    )

    validation = _validate_ingestion(
        corpus_entries=[entry],
        extracted_schemes=[],
        chunks=[chunk],
        failures=[],
        expected_scheme_count=1,
    )

    assert validation.ok is False
    assert validation.errors == ["Excluded content found in chunks: 1"]
    assert validation.excluded_content_hits == [f"{entry['scheme_slug']}:nav: \\b(blog|editorial|opinion|pros and cons|review|rating|star rating)\\b"]


def test_ingestion_artifacts_include_sample_chunks_and_field_coverage_log(tmp_path) -> None:
    entry = corpus_entry("hdfc-large-cap-fund-direct-growth")
    corpus_path = write_corpus(tmp_path, [entry])
    fetcher = FakeFetcher([FetchResult(entry["source_url"], HTML, 200, "2026-06-28T00:00:00Z")])
    result = IngestionPipeline(fetcher=fetcher, embedder=FakeEmbedder(), index_writer=FakeIndexWriter()).run(
        corpus_index_path=corpus_path,
        expected_scheme_count=1,
    )
    sample_path = tmp_path / "sample_chunks.json"
    log_path = tmp_path / "ingestion_run.log"

    _write_artifacts(result, sample_chunks_path=sample_path, log_path=log_path)

    sample_chunks = json.loads(sample_path.read_text(encoding="utf-8"))
    log_text = log_path.read_text(encoding="utf-8")
    assert sample_chunks[0] == {
        "chunk_id": "hdfc-large-cap-fund-direct-growth:nav",
        "scheme_name": "Hdfc Large Cap Fund Direct Growth",
        "scheme_slug": "hdfc-large-cap-fund-direct-growth",
        "category": "Large Cap (Equity)",
        "field": "nav",
        "content": "NAV: Rs 100.00",
        "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        "fetched_at": "2026-06-28T00:00:00Z",
    }
    assert "Field coverage:" in log_text
    assert "- hdfc-large-cap-fund-direct-growth [partial]: indexed=nav, expense_ratio, category;" in log_text
