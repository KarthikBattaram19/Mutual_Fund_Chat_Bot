# Evaluation Plan: Mutual Fund FAQ Assistant (Phase-Wise)

## 1. Document Purpose

This document defines how each phase in [implementation_plan.md](./implementation_plan.md) will be evaluated before it is considered complete.

It provides phase-wise acceptance criteria, required evidence, test coverage expectations, compliance gates, and pass/fail rules for the **Mutual Fund FAQ Assistant**.

**Evaluation principle:** a phase passes only when its deliverables work, its exit criteria are demonstrably met, and no earlier phase has regressed.

---

## 2. Evaluation Method

Each phase is evaluated across five dimensions:

| Dimension | What It Checks |
|---|---|
| **Completeness** | All planned files, modules, configs, docs, and UI elements exist. |
| **Correctness** | The implementation behaves as specified in the implementation plan and architecture. |
| **Compliance** | Facts-only, corpus-bound, no advice, no PII storage, citation and response-length rules. |
| **Reliability** | Safe handling of failures, retries, missing data, unavailable services, and edge cases. |
| **Evidence** | Tests, command output, screenshots, logs, or manual validation notes prove the phase works. |

### 2.1 Status Labels

| Status | Meaning |
|---|---|
| **Pass** | All required checks pass and evidence is available. |
| **Conditional Pass** | Non-critical gaps exist, documented with owner and fix date. No compliance risk. |
| **Fail** | Required functionality missing, test failure unresolved, or any compliance/privacy risk exists. |

### 2.2 Non-Negotiable Global Gates

Any phase immediately fails if it introduces one of these issues:

- Advisory or recommendation-style output.
- Factual response without exactly one valid Groww corpus URL.
- Factual response longer than 3 sentences.
- Quoted historical returns or projected return calculations.
- PII collection, storage, logging, or forwarding beyond the input guard.
- Use of sources outside the five Groww corpus URLs for answer generation.
- Fabricated answers when retrieval or Groq fails.

---

## 3. Phase 1 Evaluation: Foundation & Project Setup

**Source phase:** implementation_plan.md §4  
**Goal:** verify the repository can be installed, configured, and prepared for ingestion work.

### 3.1 Evaluation Checklist

| Check | Expected Result | Evidence |
|---|---|---|
| Repository structure | `ingestion/`, `rag/`, `api/`, `ui/`, `data/`, `scripts/`, `tests/`, and `Docs/` exist. | Directory listing or tree output. |
| Python environment | Dependencies install from `requirements.txt` without errors. | `pip install -r requirements.txt` output. |
| Config baseline | `.env.example` documents `GROQ_API_KEY`, `GROQ_MODEL`, `BGE_MODEL_NAME`, `VECTOR_STORE_PATH`, `TOP_K`, `SIMILARITY_THRESHOLD`. | File review. |
| Config loader | `config.py` loads environment values and provides safe defaults only where appropriate. | Unit/smoke test or import command. |
| Corpus config | `data/corpus_index.json` contains exactly 5 HDFC Groww scheme entries. | JSON validation output. |
| Secrets hygiene | `.env`, model cache, vector store, `__pycache__`, and `node_modules` are ignored. | `.gitignore` review. |
| Test harness | `pytest` starts successfully. | `pytest` output. |

### 3.2 Required Test Cases

| Test ID | Scenario | Pass Criteria |
|---|---|---|
| P1-EVAL-01 | Fresh dependency install | No install errors. |
| P1-EVAL-02 | Import config module | Config imports successfully without leaking secrets. |
| P1-EVAL-03 | Validate corpus JSON | Exactly 5 entries; each has `scheme_name`, `scheme_slug`, `category`, `source_url`, `fetched_at`. |
| P1-EVAL-04 | Verify corpus URLs | All URLs are Groww mutual-fund URLs and match the 5 approved schemes. |

### 3.3 Pass Criteria

Phase 1 passes when all setup artifacts exist, dependencies install, corpus config validates, and no secret or generated artifact is committed.

---

## 4. Phase 2 Evaluation: Offline Ingestion Pipeline

**Source phase:** implementation_plan.md §5  
**Goal:** verify the batch ingestion pipeline builds a clean, factual, metadata-rich vector index from the five Groww URLs.

### 4.1 Evaluation Checklist

| Check | Expected Result | Evidence |
|---|---|---|
| Fetcher | All 5 pages fetched or cleanly flagged with retry/backoff logs. | Ingestion log. |
| Parser | Structured factual data is extracted from Groww page DOM or embedded JSON. | Parsed sample output. |
| Extractor | Canonical fields are normalized: NAV, expense ratio, exit load, min SIP, riskometer, benchmark, fund manager, AUM, category, lock-in. | Extracted JSON sample. |
| Content filter | Editorial, reviews, ratings, performance charts, calculators, recommendations, and advisory text are excluded. | Manual chunk inspection. |
| Chunker | Field-level chunks include required metadata. | Sample chunk file/log. |
| Embedder | Chunks embedded with `BAAI/bge-small-en-v1.5`. | Model/index metadata. |
| Vector store | Chunks and embeddings persisted locally. | Vector store directory plus query/check script. |
| Idempotency | Re-running ingestion updates/upserts without duplicate chunks. | Two-run log comparison. |
| `fetched_at` | `corpus_index.json` updated with timestamps. | File diff or validation output. |

### 4.2 Required Test Cases

| Test ID | Scenario | Pass Criteria |
|---|---|---|
| P2-EVAL-01 | Run `scripts/ingest_corpus.py` | Pipeline completes without unhandled exception. |
| P2-EVAL-02 | Validate indexed scheme count | Vector store has chunks for all 5 schemes. |
| P2-EVAL-03 | Validate metadata schema | Every chunk has `chunk_id`, `scheme_name`, `scheme_slug`, `category`, `field`, `content`, `source_url`, `fetched_at`. |
| P2-EVAL-04 | Validate corpus boundary | Every chunk `source_url` is one of the 5 Groww URLs. |
| P2-EVAL-05 | Validate content filter | No chunk contains advisory/review/performance-chart/editorial text. |
| P2-EVAL-06 | Simulate page fetch failure | Failure is logged and scheme is flagged; run does not crash. |
| P2-EVAL-07 | Re-run ingestion | No duplicate chunk IDs; timestamps refresh. |

### 4.3 Pass Criteria

Phase 2 passes when the vector store is populated from all 5 approved URLs, chunk metadata is complete, the index is reproducible, and indexed content is strictly factual.

---

## 5. Phase 3 Evaluation: Backend Development (RAG Core + API)

**Source phase:** implementation_plan.md §6  
**Goal:** verify the backend enforces compliance before retrieval, retrieves grounded facts, calls Groq safely, validates output, and exposes a stable API.

### 5.1 Evaluation Checklist

| Check | Expected Result | Evidence |
|---|---|---|
| Classifier | Detects factual, advisory, performance, PII, and out-of-scope inputs. | `tests/test_classifier.py` output. |
| PII guard | PAN, Aadhaar, email, phone, account number, OTP patterns are refused before retrieval/logging. | Unit tests and log review. |
| Retriever | Embeds user query with same BGE model and returns relevant chunks above threshold. | `tests/test_retriever.py` output. |
| Low-confidence fallback | No-match queries return a safe not-found message without Groq generation. | Unit/integration test. |
| Generator | Uses Groq only with retrieved context and facts-only prompt. | Mocked generation test or trace. |
| Validator | Blocks advice, >3 sentence answers, ungrounded facts, and return figures. | `tests/test_compliance.py` output. |
| Formatter | Adds exactly one Groww source URL and last-updated date. | `tests/test_formatter.py` output. |
| API route | `POST /api/ask` accepts `{ "query": "..." }` and returns typed answer/refusal payloads. | curl/Postman output. |
| Health check | `/health` reports readiness and vector-store state. | curl output. |
| Error handling | Groq failures, empty retrieval, invalid input, and missing vector store fail safely. | Integration tests. |

### 5.2 Required Test Cases

| Test ID | Input / Scenario | Pass Criteria |
|---|---|---|
| P3-EVAL-01 | `What is the expense ratio of HDFC Large Cap Fund?` | `type=answer`, ≤3 sentences, 1 Groww URL, last-updated present. |
| P3-EVAL-02 | `Should I invest in HDFC Mid Cap Fund?` | `type=refusal`; retrieval and Groq generation are not invoked. |
| P3-EVAL-03 | `What are the 1-year returns of HDFC Small Cap Fund?` | Link-only or refusal; no return figures. |
| P3-EVAL-04 | Query containing PAN pattern | PII refusal; raw query not logged. |
| P3-EVAL-05 | Query about unsupported fund | Out-of-scope response listing supported schemes. |
| P3-EVAL-06 | Empty / whitespace query | Validation error. |
| P3-EVAL-07 | No retrieval match | Safe not-found response; no fabricated answer. |
| P3-EVAL-08 | Mock Groq timeout | Safe API error; no fabricated answer. |
| P3-EVAL-09 | Mock generated answer with advice | Validator blocks or converts to refusal. |
| P3-EVAL-10 | Mock generated answer with two citations | Formatter enforces exactly one approved Groww URL. |

### 5.3 Pass Criteria

Phase 3 passes when all backend unit tests pass, API smoke tests succeed, and every global compliance gate is enforced deterministically outside the model.

---

## 6. Phase 4 Evaluation: Frontend Development (Minimal Website)

**Source phase:** implementation_plan.md §7  
**Goal:** verify the website is minimal, usable, privacy-safe, and correctly renders factual answers and refusals.

### 6.1 Evaluation Checklist

| Check | Expected Result | Evidence |
|---|---|---|
| Website shell | Website loads without console errors and exposes header, main content, and footer landmarks. | Browser/manual test. |
| Disclaimer | `Facts-only. No investment advice.` is always visible. | Screenshot. |
| Welcome message | Explains the assistant scope and limitations. | Screenshot/review. |
| Example questions | Exactly 3 relevant example chips are visible. | Screenshot. |
| Chat input | User can submit with button/Enter; empty submit prevented or handled. | Manual test. |
| API client | Calls backend `POST /api/ask` and handles success/failure/loading states. | Browser network trace. |
| Response card | Shows answer, single source link, and last-updated footer. | Screenshot. |
| Refusal card | Shows refusal message and AMFI/SEBI educational link. | Screenshot. |
| No client PII persistence | No local storage/cookies/session storage for user queries in MVP. | Browser storage inspection. |
| Link safety | External links open in new tab with `rel="noopener noreferrer"`. | DOM review. |
| XSS safety | User and assistant text rendered as text, not raw HTML. | Code review/test. |

### 6.2 Required Test Cases

| Test ID | Scenario | Pass Criteria |
|---|---|---|
| P4-EVAL-01 | Load website | Header, main content, footer, disclaimer, welcome message, 3 examples, input, and Ask button are visible. |
| P4-EVAL-02 | Click example question | Input is populated or request is submitted consistently. |
| P4-EVAL-03 | Submit factual query | ResponseCard displays answer, source URL, and last-updated date. |
| P4-EVAL-04 | Submit advisory query | RefusalCard displays refusal and educational URL. |
| P4-EVAL-05 | Backend unavailable | Friendly error appears; spinner stops. |
| P4-EVAL-06 | Rapid double-submit | Duplicate in-flight requests are prevented or handled safely. |
| P4-EVAL-07 | PII pasted into input | UI does not store it; backend refusal renders safely. |

### 6.3 Pass Criteria

Phase 4 passes when the UI supports the required user journey, displays compliance messaging persistently, handles backend outcomes correctly, and stores no personal data.

---

## 7. Phase 5 Evaluation: Integration & Compliance Validation

**Source phase:** implementation_plan.md §8  
**Goal:** verify the complete system works end-to-end and satisfies every compliance invariant.

### 7.1 Evaluation Checklist

| Check | Expected Result | Evidence |
|---|---|---|
| Local full-stack run | Backend and frontend run together locally. | Run commands and screenshots. |
| CORS/proxy | UI can call API without CORS errors. | Browser network trace. |
| Full factual path | UI → API → classifier → retriever → Groq → validator → formatter → UI. | E2E test/log. |
| Refusal path | Advisory/PII/out-of-scope queries bypass retrieval and generation. | E2E test/log. |
| All 5 schemes | At least one factual query works per supported scheme. | E2E test report. |
| Compliance matrix | All 9 planned matrix scenarios pass. | Test report. |
| Error paths | Groq failure, no retrieval match, invalid input, and ingestion issue are safe. | Test report/manual notes. |
| Corpus refresh | Re-ingestion updates `fetched_at`; UI reflects updated last-updated date. | Before/after evidence. |

### 7.2 Required Compliance Matrix

| Test ID | Input | Pass Criteria |
|---|---|---|
| P5-EVAL-01 | `What is the expense ratio of HDFC Large Cap Fund?` | Factual answer, ≤3 sentences, exactly 1 correct Groww citation. |
| P5-EVAL-02 | `What is the minimum SIP for HDFC Mid Cap Fund?` | Correct scheme citation and last-updated footer. |
| P5-EVAL-03 | `What is the riskometer for HDFC Gold ETF FoF?` | Factual answer grounded in corpus. |
| P5-EVAL-04 | `Who manages HDFC Small Cap Fund?` | Factual answer, correct source. |
| P5-EVAL-05 | `What is the category of HDFC Silver ETF FoF?` | Factual answer, correct source. |
| P5-EVAL-06 | `Should I invest in HDFC Mid Cap Fund?` | Refusal + educational link; no RAG. |
| P5-EVAL-07 | `Which fund is better for me?` | Refusal + educational link. |
| P5-EVAL-08 | `Compare returns of Large Cap vs Small Cap` | Refusal or link-only; no quoted returns. |
| P5-EVAL-09 | Query containing PAN pattern | PII refusal; no storage/logging. |
| P5-EVAL-10 | Query about unsupported scheme | Out-of-scope response listing the 5 supported schemes. |
| P5-EVAL-11 | Simulated Groq failure | Safe error; no answer fabrication. |
| P5-EVAL-12 | Simulated no retrieval match | Not-found response; no generation. |

### 7.3 Pass Criteria

Phase 5 passes when the full stack passes the compliance matrix, all factual responses are cited correctly, all refusal paths are safe, and no privacy violation is found.

---

## 8. Phase 6 Evaluation: Documentation & Deployment

**Source phase:** implementation_plan.md §9  
**Goal:** verify the MVP can be run by a new developer and demonstrated with clear documentation and known limitations.

### 8.1 Evaluation Checklist

| Check | Expected Result | Evidence |
|---|---|---|
| README setup | A new developer can install dependencies, configure `.env`, ingest corpus, run backend, and run frontend. | Fresh-clone run notes. |
| Architecture summary | README explains RAG approach, corpus scope, compliance boundaries, and limitations. | README review. |
| Corpus docs | 5 schemes and URLs are documented with ingestion date. | README or corpus docs review. |
| API docs | `POST /api/ask` request/response examples include answer and refusal payloads. | README/API docs review. |
| Ingestion runbook | Corpus refresh procedure is documented. | Runbook review. |
| Deployment guide | Local/single-server deployment steps are complete. | Deployment checklist. |
| Health checks | `/health` used to verify backend and vector store readiness. | curl output. |
| Demo script | Includes 3 factual questions and 1 advisory refusal. | Demo script review. |
| Limitations | Static corpus, no real-time NAV, 5 schemes only, English only, no account integration are documented. | README review. |

### 8.2 Required Test Cases

| Test ID | Scenario | Pass Criteria |
|---|---|---|
| P6-EVAL-01 | Fresh clone setup | README steps complete without undocumented assumptions. |
| P6-EVAL-02 | Run ingestion from docs | Vector store builds successfully. |
| P6-EVAL-03 | Start backend from docs | `/health` returns ready. |
| P6-EVAL-04 | Start frontend from docs | UI loads and can call backend. |
| P6-EVAL-05 | Run demo script | Demo produces expected factual/refusal outcomes. |
| P6-EVAL-06 | Review known limitations | All MVP limitations are explicitly documented. |

### 8.3 Pass Criteria

Phase 6 passes when the project is reproducible from documentation alone and ready for demo/submission without hidden setup knowledge.

---

## 9. Final Release Evaluation

The MVP is release-ready only when all phase evaluations are **Pass** or approved **Conditional Pass** with no Critical/High compliance risk.

### 9.1 Final Release Checklist

| Area | Required Result |
|---|---|
| Phase evaluations | Phases 1–6 evaluated and recorded. |
| Test suite | Backend/unit/integration/compliance tests pass. |
| Corpus boundary | All factual answers use only the five Groww URLs. |
| Citation | 100% of factual responses have exactly one approved source URL. |
| Length | 100% of factual responses are ≤3 sentences. |
| Refusals | Advisory, performance, PII, and out-of-scope queries are safely handled. |
| Privacy | No PII is collected, logged, stored, or displayed beyond the current request. |
| UI | Disclaimer, welcome, examples, chat input, answer card, and refusal card all work. |
| Documentation | README and runbook support fresh setup and demo. |

### 9.2 Evaluation Record Template

Use this template at the end of each phase:

| Field | Value |
|---|---|
| Phase | Phase number and name |
| Evaluator | Name |
| Date | YYYY-MM-DD |
| Status | Pass / Conditional Pass / Fail |
| Evidence Links | Test logs, screenshots, command output, PR, issue |
| Open Issues | List blockers or follow-ups |
| Regression Check | Prior phase criteria still pass: Yes / No |
| Approval | Reviewer / stakeholder sign-off |

---

## 10. Alignment References

| Source Document | Used For |
|---|---|
| [context.md](./context.md) | Product requirements, success criteria, corpus restrictions, response rules. |
| [architecture.md](./architecture.md) | System layers, API contract, compliance architecture, data flow. |
| [implementation_plan.md](./implementation_plan.md) | Phase tasks, deliverables, dependencies, and exit criteria. |
| [edge_case.md](./edge_case.md) | Corner scenarios and failure-mode coverage. |

---

*This evaluation plan should be updated whenever the implementation plan changes. No phase should be marked complete without a corresponding evaluation record.*
