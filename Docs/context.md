# Project Context: Mutual Fund FAQ Assistant (Facts-Only Q&A)

## 1. Project Summary

This project builds a **Retrieval-Augmented Generation (RAG)-based FAQ assistant** that answers factual questions about mutual fund schemes. The assistant uses **Groww** as its product reference context and focuses on **five HDFC Mutual Fund schemes**, retrieving information from Groww scheme pages and supplementary official sources including HDFC AMC, AMFI (Association of Mutual Funds in India), and SEBI (Securities and Exchange Board of India).

The system is designed to be strictly **facts-only** — it will never provide investment advice, opinions, or performance comparisons. It is a transparency-first tool that ensures every response is short, verifiable, and source-backed.

---

## 2. Problem Being Solved

Retail investors and customer support teams frequently encounter repetitive, objective questions about mutual fund schemes:

- What is the expense ratio of this fund?
- What is the exit load?
- What is the minimum SIP amount?
- How do I download my capital gains statement?

Currently, finding reliable answers requires navigating dense official documents (SIDs, KIMs, factsheets) or relying on third-party aggregators that may be outdated or editorially biased.

This assistant solves that by:
- Centralizing official document retrieval
- Returning concise, citation-backed answers in natural language
- Refusing subjective or advisory queries to maintain compliance

---

## 3. Target Users

| User Type | Use Case |
|---|---|
| Retail Investors | Quickly verify fund details without reading full documents |
| Customer Support Teams | Answer repetitive mutual fund queries accurately and consistently |
| Content Teams | Reference factual data for articles or guides without advisory language |

---

## 4. Technology Approach: RAG Architecture

The assistant uses a **Retrieval-Augmented Generation (RAG)** pipeline:

```
User Query
    │
    ▼
Query Understanding & Classification
    │
    ├─ Advisory/Non-factual? ──► Polite Refusal + Educational Link
    │
    ▼
Vector Search over Curated Corpus
    │
    ▼
Relevant Document Chunks Retrieved
    │
    ▼
LLM generates factual answer (≤ 3 sentences)
    │
    ▼
Response + Single Citation Link + "Last updated from sources: <date>"
```

### RAG Components

| Component | Description |
|---|---|
| **Document Corpus** | 5 Groww scheme pages covering HDFC Large Cap, Mid Cap, Small Cap, Gold ETF FoF, and Silver ETF FoF |
| **Embedding Model** | Converts document chunks and user queries to vector representations |
| **Vector Store** | Stores and retrieves relevant document chunks by semantic similarity |
| **LLM** | Generates a factual, concise answer grounded in retrieved context |
| **Citation Layer** | Attaches the source URL and last-updated date to every response |
| **Query Classifier** | Detects and refuses advisory or non-factual queries before retrieval |

---

## 5. Corpus Definition

### AMC Selection
**HDFC Mutual Fund** is the selected AMC for this project, providing a well-established and diverse range of publicly documented schemes.

### Scheme Selection (5 Schemes)
The following five HDFC schemes are used, sourced via their Groww scheme pages as the corpus entry points:

| # | Scheme Name | Category | Groww URL |
|---|---|---|---|
| 1 | HDFC Large Cap Fund – Direct Growth | Large Cap (Equity) | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 2 | HDFC Mid Cap Fund – Direct Growth | Mid Cap (Equity) | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| 3 | HDFC Small Cap Fund – Direct Growth | Small Cap (Equity) | https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth |
| 4 | HDFC Gold ETF Fund of Fund – Direct Plan Growth | Commodity (Gold) | https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth |
| 5 | HDFC Silver ETF FoF – Direct Growth | Commodity (Silver) | https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth |

> **Note on Groww as Corpus Source**: Groww scheme pages are used as the sole corpus URLs for this project. They aggregate publicly available factual data (NAV, expense ratio, exit load, riskometer, benchmark, etc.) in a structured format. No Groww proprietary, editorial, or advisory content is used.

### Document / Data Points Collected Per Scheme

| Data Point | Purpose |
|---|---|
| NAV (current) | Per-unit price reference |
| Expense Ratio | Annual fund cost |
| Exit Load | Redemption fee structure |
| Minimum SIP Amount | Investment threshold |
| Riskometer Classification | Risk level (Low to Very High) |
| Benchmark Index | Performance comparison index |
| Fund Manager(s) | Manager name and tenure |
| AUM | Total assets under management |
| Fund Category | Large Cap / Mid Cap / Small Cap / Commodity |
| Lock-in Period | Applicable only if locked (N/A for these schemes) |

---

## 6. Query Types Supported

### Answerable (Factual) Queries

| Query | Source Document |
|---|---|
| Expense ratio of a scheme | Factsheet / KIM |
| Exit load details | KIM / SID |
| Minimum SIP amount | KIM |
| ELSS lock-in period | SID / AMFI page |
| Riskometer classification | Factsheet / KIM |
| Benchmark index | Factsheet / SID |
| How to download account statement | AMC Help / CAMS guide |
| How to download capital gains report | AMC Help / KFintech guide |
| Fund manager name | Factsheet |
| Fund AUM | Factsheet |

### Refused (Advisory / Non-Factual) Queries

| Query | Refusal Reason |
|---|---|
| "Should I invest in this fund?" | Investment advice |
| "Which fund is better for me?" | Comparative recommendation |
| "Will this fund give good returns?" | Speculative / opinion-based |
| "Is this a safe fund?" | Subjective risk assessment |
| "Compare Fund A vs Fund B returns" | Performance comparison / advisory |

---

## 7. Response Format

Every factual response must follow this strict structure:

```
<Concise factual answer in 1–3 sentences>

Source: <single official URL>
Last updated from sources: <date>
```

**Example:**
> The exit load for HDFC Large Cap Fund is 1% if redeemed within 1 year from the date of allotment. No exit load applies after 1 year.
>
> Source: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth
> Last updated from sources: June 2026

Every refusal response must follow this structure:

```
I can only provide factual information about mutual fund schemes and cannot offer investment advice or recommendations.
For guidance on evaluating mutual funds, please refer to: <AMFI or SEBI educational link>
```

---

## 8. User Interface Requirements

The UI is intentionally minimal:

| Element | Specification |
|---|---|
| Welcome Message | Brief intro explaining the assistant's purpose and limitations |
| Example Questions | 3 pre-populated clickable example queries |
| Disclaimer Banner | "Facts-only. No investment advice." — always visible |
| Chat Input | Single text input for user queries |
| Response Area | Displays answer, source link, and last-updated date |

---

## 9. Constraints and Compliance Rules

### Data & Sources
- Corpus: **exactly 5 Groww scheme pages** for HDFC funds (publicly accessible, no login required)
- No additional external URLs, supplementary official sources, or third-party documents are included in the RAG pipeline
- No third-party blogs, news articles, or editorial/opinion content
- No scraping of login-required or subscription pages
- Only factual fields displayed on Groww scheme pages (expense ratio, exit load, riskometer, etc.) are extracted — no editorial or advisory content

### Privacy & Security
The system must **never** collect, store, process, or prompt for:
- PAN or Aadhaar numbers
- Bank account numbers
- OTPs or passwords
- Email addresses or phone numbers

### Content Restrictions
- No investment advice, buy/sell recommendations, or portfolio suggestions
- No performance comparisons or projected return calculations
- For performance-related queries (e.g., "What are the returns?"), respond with a link to the official factsheet only — do not quote historical returns directly

### Response Quality
- Maximum 3 sentences per factual response
- Exactly 1 citation link per response
- Footer with last-updated date on every response

---

## 10. Key Definitions

| Term | Definition |
|---|---|
| **AMC** | Asset Management Company — the entity that manages a mutual fund (e.g., HDFC Mutual Fund, SBI, Mirae Asset) |
| **AMFI** | Association of Mutual Funds in India — the industry body that regulates and provides investor education |
| **SEBI** | Securities and Exchange Board of India — the statutory regulator for securities markets |
| **NAV** | Net Asset Value — the per-unit price of a mutual fund scheme |
| **SIP** | Systematic Investment Plan — periodic fixed-amount investment into a mutual fund |
| **ELSS** | Equity Linked Savings Scheme — a tax-saving mutual fund with a 3-year lock-in period |
| **KIM** | Key Information Memorandum — a condensed document with key scheme features |
| **SID** | Scheme Information Document — the full legal document for a mutual fund scheme |
| **Expense Ratio** | Annual fee charged by the fund as a % of AUM |
| **Exit Load** | Fee charged when redeeming units before a specified holding period |
| **Riskometer** | SEBI-mandated visual indicator of a fund's risk level (Low to Very High) |
| **AUM** | Assets Under Management — total market value of assets managed by the fund |
| **Benchmark Index** | The market index used to compare the fund's performance (e.g., Nifty 50, BSE Sensex) |
| **RAG** | Retrieval-Augmented Generation — an AI approach that grounds LLM answers in retrieved documents |
| **FoF** | Fund of Funds — a mutual fund that invests in units of other mutual funds or ETFs (e.g., HDFC Gold ETF FoF) |
| **ETF** | Exchange Traded Fund — a fund traded on a stock exchange, tracking an index or commodity |
| **Gold ETF FoF** | A fund that invests in Gold ETF units, giving indirect exposure to gold prices without holding physical gold |
| **Silver ETF FoF** | A fund that invests in Silver ETF units, giving indirect exposure to silver prices |

---

## 11. Expected Deliverables

| Deliverable | Description |
|---|---|
| `README.md` | Setup instructions, selected AMC/schemes, architecture overview, known limitations |
| Corpus Index | List of 5 Groww scheme page URLs with scheme name, category, and date of retrieval |
| RAG Pipeline | Ingestion, embedding, retrieval, and generation code |
| Query Classifier | Logic to detect and refuse advisory queries |
| Minimal UI | Chat interface with welcome message, example queries, and disclaimer |
| Disclaimer Snippet | "Facts-only. No investment advice." embedded in the UI |

---

## 12. Success Criteria

| Criterion | Measure |
|---|---|
| Factual Accuracy | Retrieved answers match source documents |
| Citation Compliance | 100% of responses include exactly one valid source link |
| Refusal Accuracy | Advisory queries are refused consistently and politely |
| Response Length | All factual answers are ≤ 3 sentences |
| UI Usability | Welcome message, 3 example questions, and disclaimer are always visible |
| Privacy Compliance | No PII is collected, processed, or stored |

---

## 13. Known Limitations

- **Static Corpus**: The assistant answers only from the curated set of documents. Information from newly published factsheets will require a corpus refresh.
- **No Real-Time NAV**: NAV changes daily; the assistant will not provide live NAV data and will point users to the official AMC or AMFI website instead.
- **Single AMC Scope**: The MVP focuses on **HDFC Mutual Fund** and **5 specific schemes** (Large Cap, Mid Cap, Small Cap, Gold ETF FoF, Silver ETF FoF). Cross-AMC comparisons are out of scope.
- **Language**: The assistant supports English only in the initial version.
- **No Account Integration**: The assistant cannot access user portfolios or account-specific data.

---

## 14. Relationship to Groww

Groww serves two roles in this project:

1. **Product Reference Context**: The assistant is designed with Groww's user base in mind — retail investors on a digital mutual fund platform who ask quick, factual questions.

2. **Corpus Source**: The five Groww scheme pages are the **only** URLs used in the RAG pipeline. Groww aggregates and displays factual scheme data (NAV, expense ratio, exit load, riskometer, benchmark, etc.) in a structured, accessible format, making them the sole source for information extraction in this project.

### Corpus URLs (All Five Schemes)

| Scheme | Groww URL |
|---|---|
| HDFC Large Cap Fund – Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| HDFC Mid Cap Fund – Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| HDFC Small Cap Fund – Direct Growth | https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth |
| HDFC Gold ETF Fund of Fund – Direct Plan Growth | https://groww.in/mutual-funds/hdfc-gold-etf-fund-of-fund-direct-plan-growth |
| HDFC Silver ETF FoF – Direct Growth | https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth |

### What is NOT used from Groww
- No Groww editorial content, blog posts, or recommendations
- No Groww APIs or proprietary data feeds
- No user review or rating data from Groww
- No performance charts, return calculators, or comparison tools

All responses cite the corresponding Groww scheme page URL as the source.

---

*This context document is derived from the project Problem Statement and is intended to guide all design, development, and compliance decisions for the Mutual Fund FAQ Assistant.*
