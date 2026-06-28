# Ingestion Runbook

How to run, verify, and schedule corpus ingestion for the Mutual Fund FAQ Assistant.

**Disclaimer:** Facts-only. No investment advice.

---

## Overview

Ingestion is an **offline batch job**. It:

1. Fetches the five configured Groww scheme pages
2. Parses HTML and extracts canonical fund fields
3. Chunks facts into searchable units
4. Embeds chunks with the local BGE model
5. Writes vectors to ChromaDB at `VECTOR_STORE_PATH`
6. Updates `fetched_at` timestamps in `data/corpus_index.json`
7. Writes artifacts to `data/sample_chunks.json` and `logs/ingestion_run.log`

The online API reads from the vector store; it does **not** fetch Groww pages at query time.

---

## Prerequisites

- Python virtual environment with `requirements.txt` installed
- Network access to Groww
- Playwright Chromium (for JS-rendered pages): `playwright install chromium`
- Sufficient disk for BGE model cache (~500 MB on first run)

---

## Standard Ingestion Run

From the project root:

```powershell
python scripts/ingest_corpus.py
```

### Expected output

A successful run prints summary lines similar to:

```
Ingestion mode: WRITE
Fetched pages: 5
Parsed pages: 5
...
Chunks indexed: <count>
Corpus timestamps updated: 5
Validation: 5/5 schemes indexed; ...
```

### Artifacts produced

| File | Purpose |
|---|---|
| `data/vector_store/` | ChromaDB index (gitignored; rebuild on fresh clone) |
| `data/corpus_index.json` | Updated `fetched_at` per scheme |
| `data/sample_chunks.json` | Snapshot of generated chunks for inspection |
| `logs/ingestion_run.log` | Run summary and per-scheme field coverage |

---

## CLI Options

```powershell
python scripts/ingest_corpus.py --help
```

| Flag | Description |
|---|---|
| `--corpus-index PATH` | Corpus config file (default: `data/corpus_index.json`) |
| `--dry-run` | Fetch/parse/extract/chunk only; no embed, index, or timestamp updates |
| `--expected-scheme-count N` | Validation threshold (default: `5`) |
| `--sample-chunks-output PATH` | Where to write chunk JSON (default: `data/sample_chunks.json`) |
| `--log-output PATH` | Where to write run log (default: `logs/ingestion_run.log`) |
| `--no-artifacts` | Skip writing sample chunks and log file |

### Dry run (validate fetch/parse without indexing)

```powershell
python scripts/ingest_corpus.py --dry-run
```

Use this to check Groww connectivity and parsing before a full re-index.

---

## Post-Ingestion Verification

1. **Check the log**

   ```powershell
   type logs\ingestion_run.log
   ```

   Confirm `5/5 schemes indexed` and review any `partial` or `missing` fields.

2. **Check corpus timestamps**

   Open `data/corpus_index.json` and verify `fetched_at` values updated to the run time.

3. **Verify backend readiness**

   Start the API and call health:

   ```powershell
   python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
   curl http://127.0.0.1:8000/health
   ```

   Expect `"vector_store_ready": true`.

4. **Smoke-test a factual query**

   ```powershell
   curl -X POST http://127.0.0.1:8000/api/ask ^
     -H "Content-Type: application/json" ^
     -d "{\"query\": \"What is the expense ratio of HDFC Large Cap Fund?\"}"
   ```

   On Linux/macOS, use `\` line continuation instead of `^`.

---

## Corpus Refresh Procedure

Run this when Groww pages may have changed or `fetched_at` is stale.

1. Stop or accept brief inconsistency (old index serves until the new run completes).
2. Run `python scripts/ingest_corpus.py`.
3. Review `logs/ingestion_run.log` for errors or partial schemes.
4. Restart the backend if it was running (optional; Chroma reads from disk).
5. Confirm UI “Last updated from sources” reflects the new month in answer footers.

Re-running ingestion is **idempotent**: chunk IDs are stable and the index is upserted.

---

## Scheduling (Optional)

### Windows Task Scheduler

- **Trigger:** Weekly (e.g. Sunday 02:00)
- **Action:** `python scripts/ingest_corpus.py`
- **Start in:** Project root directory
- **Environment:** Activate venv in the action or use full path to venv Python

### Linux/macOS cron

```cron
0 2 * * 0 cd /path/to/project && /path/to/.venv/bin/python scripts/ingest_corpus.py >> logs/cron_ingest.log 2>&1
```

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Fetch failures for one or more URLs | Network block or Groww layout change | Check log; retry with backoff; inspect parser warnings |
| `vector_store_ready: false` after ingest | Ingestion failed or wrong `VECTOR_STORE_PATH` | Re-run ingestion; verify `.env` |
| BGE download slow or fails | First-run model download | Ensure disk space and Hugging Face access |
| Partial field coverage | Missing fields on Groww page | Expected for some schemes (e.g. `lock_in`); see log |
| Playwright errors | Browser not installed | Run `playwright install chromium` |

---

## What Ingestion Does Not Do

- Does not call Groq (generation is online-only)
- Does not modify UI or API code
- Does not ingest URLs outside the five configured schemes
- Does not store user queries or PII
