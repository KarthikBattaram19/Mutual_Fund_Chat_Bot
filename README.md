# Mutual Fund FAQ Assistant (Facts-Only Q&A)

A facts-only mutual fund FAQ MVP for **five HDFC Mutual Fund schemes**. Answers are grounded in a curated Groww corpus via RAG (retrieval-augmented generation). The assistant refuses advisory, personal, performance-return, and out-of-scope queries.

**Disclaimer:** Facts-only. No investment advice.

---

## Selected AMC and Schemes

| Scheme | Category | Groww source URL | Last ingested |
|---|---|---|---|
| HDFC Large Cap Fund – Direct Growth | Large Cap (Equity) | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth | 2026-06-28 |
| HDFC Mid Cap Fund – Direct Growth | Mid Cap (Equity) | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth | 2026-06-28 |
| HDFC Small Cap Fund – Direct Growth | Small Cap (Equity) | https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth | 2026-06-28 |
| HDFC Gold ETF Fund of Fund – Direct Plan Growth | Commodity (Gold) | https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth | 2026-06-28 |
| HDFC Silver ETF FoF – Direct Growth | Commodity (Silver) | https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth | 2026-06-28 |

Corpus metadata lives in [`data/corpus_index.json`](data/corpus_index.json). Timestamps update after each successful ingestion run.

---

## RAG Architecture Overview

```
User question → Query classifier → [refusal | retrieval]
                                        ↓
                              ChromaDB + BGE embeddings
                                        ↓
                              Groq LLM (grounded generation)
                                        ↓
                              Response validator → Formatter → JSON answer
```

1. **Ingestion (offline):** Fetch Groww pages → parse → extract canonical fields → chunk → embed with BGE → index in ChromaDB.
2. **Query (online):** Classify intent; refuse advisory/PII/out-of-scope queries without retrieval.
3. **Retrieval:** Vector search over approved chunks only (five Groww URLs).
4. **Generation:** Groq produces a short answer from retrieved context only.
5. **Formatting:** Strip inline provenance; attach one Groww citation URL and a last-updated date in the API response (shown in the UI footer).

See [`Docs/architecture.md`](Docs/architecture.md) for full design details.

---

## Prerequisites

- Python 3.11+ (3.14 tested)
- A [Groq API key](https://console.groq.com/) (`GROQ_API_KEY`)
- Network access for Groww ingestion and Groq inference
- ~500 MB disk for the BGE embedding model (downloaded on first ingestion)

---

## Local Deployment

### 1. Clone and install dependencies

```powershell
cd "Mutual Fund FAQ Assistant (Facts-Only Q&A)"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

On Linux/macOS, use `source .venv/bin/activate` instead of the PowerShell activate command.

### 2. Configure environment

```powershell
copy .env.example .env
```

Edit `.env` and set at minimum:

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq LLM inference |
| `GROQ_MODEL` | No | Default: `llama-3.3-70b-versatile` |
| `BGE_MODEL_NAME` | No | Default: `BAAI/bge-small-en-v1.5` (downloads on first run) |
| `VECTOR_STORE_PATH` | No | Default: `data/vector_store` |
| `TOP_K` | No | Retrieval top-k (default `5`) |
| `SIMILARITY_THRESHOLD` | No | Minimum similarity (default `0.35`) |
| `API_HOST` / `API_PORT` | No | Backend bind address (default `127.0.0.1:8000`) |
| `FRONTEND_ORIGIN` | No | CORS origin for the static UI (default `http://localhost:3000`) |

See [`.env.example`](.env.example) for the full template.

### 3. Ingest the corpus

```powershell
python scripts/ingest_corpus.py
```

This fetches all five Groww pages, builds embeddings, writes the vector store, and updates `data/corpus_index.json` timestamps. See [`Docs/ingestion_runbook.md`](Docs/ingestion_runbook.md) for refresh and scheduling details.

### 4. Start the backend

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

### 5. Start the frontend

In a second terminal:

```powershell
python -m http.server 3000 --directory frontend
```

Open http://localhost:3000 in your browser.

### 6. Verify health

```powershell
curl http://127.0.0.1:8000/health
```

Expected response (when the vector store exists):

```json
{
  "status": "ok",
  "vector_store_path": "data\\vector_store",
  "vector_store_ready": true,
  "groq_model": "llama-3.3-70b-versatile"
}
```

If `vector_store_ready` is `false`, run ingestion first. `/api/ask` returns `503` until the index is ready.

---

## Production Deploy (Vercel + Railway)

Recommended split:

| Component | Platform | Serves |
|---|---|---|
| **Frontend** | [Vercel](https://vercel.com) | Static site from `frontend/` |
| **Backend** | [Railway](https://railway.com) | FastAPI API only |

### Railway (API)

`railway.toml` configures:

- **Build:** `python scripts/index_from_samples.py`
- **Start:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- **Health check:** `/health`

Set on Railway:

| Variable | Required | Example |
|---|---|---|
| `GROQ_API_KEY` | Yes | Your Groq key |
| `FRONTEND_ORIGIN` | Yes | `https://your-app.vercel.app` |
| `SERVE_UI` | No | `false` (default) |

`PORT` is set by Railway. CORS also allows any `https://*.vercel.app` origin for preview deployments.

### Vercel (UI) — Option A

1. Import the GitHub repo in Vercel.
2. Set **Root Directory** to `frontend`.
3. Leave **Framework Preset** as **Other** (this is a static HTML/JS site, not Next.js or React).
4. Add environment variable `API_BASE_URL` = your Railway API URL (required).
5. Deploy — Vercel runs `npm run build` to generate `config.js` and serves the `frontend/` folder.

Do **not** use a root-level `vercel.json`; config lives in `frontend/vercel.json` only.

Local UI config: copy `frontend/config.example.js` to `frontend/config.js` or rely on the committed local default.

---

## Single-Server Deploy (Optional)

For a demo on one machine without Vercel:

| Process | Command | Port |
|---|---|---|
| Backend | `python -m uvicorn api.main:app --host 0.0.0.0 --port 8000` | 8000 |
| Static UI | `python -m http.server 3000 --directory frontend` | 3000 |

Set `FRONTEND_ORIGIN=http://localhost:3000` in `.env`. The UI uses `frontend/config.js` (default `http://127.0.0.1:8000`) to reach the API.

To serve UI from the API process instead, set `SERVE_UI=true`.

---

## API Reference

### `POST /api/ask`

Ask a factual question about the five supported schemes.

**Request**

```http
POST /api/ask HTTP/1.1
Content-Type: application/json

{"query": "What is the expense ratio of HDFC Mid Cap Fund?"}
```

**Answer response** (`200 OK`)

```json
{
  "type": "answer",
  "answer": "The expense ratio is 0.75%.",
  "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
  "last_updated": "June 2026"
}
```

**Refusal response** (`200 OK`)

```json
{
  "type": "refusal",
  "message": "I can only provide factual information about mutual fund schemes and cannot offer investment advice or recommendations.",
  "educational_url": "https://www.amfiindia.com/investor-corner/knowledge-center"
}
```

**Error responses**

| Status | When |
|---|---|
| `422` | Empty or invalid query |
| `429` | Per-client rate limit exceeded |
| `503` | Vector store not ready or Groq unavailable |

### `GET /health`

Returns backend status and vector store readiness. See [Health verification](#6-verify-health) above.

---

## Demo Script

Use [`Docs/demo_script.md`](Docs/demo_script.md) for a stakeholder walkthrough: three factual questions and one advisory refusal.

---

## Running Tests

```powershell
python -m pytest
```

---

## Known Limitations

| Limitation | Detail |
|---|---|
| **Static corpus** | Answers come only from the five configured Groww pages. New factsheets require re-ingestion. |
| **No real-time NAV** | NAV changes daily; the assistant does not provide live NAV. |
| **Single AMC** | HDFC Mutual Fund only; five specific schemes. No cross-AMC comparisons. |
| **English only** | No multilingual support in this MVP. |
| **No account integration** | Cannot access portfolios, holdings, or account-specific data. |
| **No PII storage** | Queries are not persisted; PII in input is refused. |

---

## Deliverables Checklist (context.md §11)

| Deliverable | Location |
|---|---|
| `README.md` | This file |
| Corpus index (5 URLs, metadata, dates) | [`data/corpus_index.json`](data/corpus_index.json) |
| RAG pipeline | `ingestion/`, `rag/` |
| Query classifier | [`rag/classifier.py`](rag/classifier.py) |
| Minimal UI | [`frontend/`](frontend/) |
| Disclaimer snippet | UI footer + this README |

---

## Project Documentation

| Document | Description |
|---|---|
| [`Docs/context.md`](Docs/context.md) | Product context and scope |
| [`Docs/architecture.md`](Docs/architecture.md) | System architecture |
| [`Docs/implementation_plan.md`](Docs/implementation_plan.md) | Phased build plan |
| [`Docs/ingestion_runbook.md`](Docs/ingestion_runbook.md) | Corpus refresh procedure |
| [`Docs/demo_script.md`](Docs/demo_script.md) | Stakeholder demo script |
| [`Docs/eval.md`](Docs/eval.md) | Phase evaluation criteria |

---

## License and Compliance

This is an educational MVP. It does not provide investment advice, recommendations, account services, or live portfolio support. Data is sourced from public Groww scheme pages and is not real-time NAV.
