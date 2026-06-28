# Demo Script

Stakeholder walkthrough for the Mutual Fund FAQ Assistant MVP.

**Disclaimer:** Facts-only. No investment advice.

---

## Before You Start

1. Complete [local deployment](../README.md#local-deployment) (ingestion + backend + frontend running).
2. Open http://localhost:3000
3. Confirm the welcome message lists five HDFC schemes and the footer shows the compliance disclaimer.

**Health check (optional):**

```powershell
curl http://127.0.0.1:8000/health
```

Expect `"vector_store_ready": true`.

---

## Demo Flow (~5 minutes)

### 1. Factual question — expense ratio

**Ask:** `What is the expense ratio of HDFC Large Cap Fund?`

**Expected:**

- Response card with “Answer from corpus” badge
- Short factual answer (≤ 3 sentences)
- One Groww source link in the footer
- “Last updated from sources:” date (from corpus `fetched_at`)

**Talking point:** Answers are grounded in retrieved corpus chunks, not general LLM knowledge.

---

### 2. Factual question — minimum SIP

**Ask:** `What is the minimum SIP for HDFC Mid Cap Fund?`

**Expected:**

- Factual answer with citation to the Mid Cap Groww URL
- No investment recommendation language

**Talking point:** Each answer cites exactly one approved Groww scheme page.

---

### 3. Factual question — riskometer

**Ask:** `What is the riskometer for HDFC Gold ETF FoF?`

**Expected:**

- Factual answer about risk level for the Gold ETF FoF scheme
- Source link to the Gold ETF FoF Groww page

**Talking point:** Commodity FoF schemes are in scope alongside equity large/mid/small cap funds.

---

### 4. Advisory refusal (compliance)

**Ask:** `Should I invest in HDFC Mid Cap Fund?`

**Expected:**

- Refusal card (“Regulatory compliance notice”)
- Message stating the assistant cannot offer investment advice
- Link to AMFI educational resources
- **No** factual answer, **no** Grow citation for a fabricated answer

**Talking point:** Advisory queries are blocked at classification — no retrieval or LLM generation runs.

---

## Optional API Demo

Show the same factual question via curl:

```powershell
curl -X POST http://127.0.0.1:8000/api/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"What is the expense ratio of HDFC Large Cap Fund?\"}"
```

Expected JSON:

```json
{
  "type": "answer",
  "answer": "...",
  "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
  "last_updated": "June 2026"
}
```

Advisory refusal via API:

```powershell
curl -X POST http://127.0.0.1:8000/api/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"Should I invest in HDFC Mid Cap Fund?\"}"
```

Expected JSON:

```json
{
  "type": "refusal",
  "message": "I can only provide factual information about mutual fund schemes and cannot offer investment advice or recommendations.",
  "educational_url": "https://www.amfiindia.com/investor-corner/knowledge-center"
}
```

---

## Closing Points

- **Scope:** Five HDFC schemes only; static Groww corpus
- **Compliance:** No advice, no PII, no live NAV, no account access
- **Refresh:** Re-run `python scripts/ingest_corpus.py` to update corpus data
- **Docs:** Full setup in [README.md](../README.md); ingestion in [ingestion_runbook.md](./ingestion_runbook.md)
