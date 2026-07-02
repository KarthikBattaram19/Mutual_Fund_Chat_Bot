from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(".")
DOCS = ROOT / "Docs"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase6_readme_exists_with_required_sections() -> None:
    readme = read_text(ROOT / "README.md")

    assert "# Mutual Fund FAQ Assistant" in readme
    assert "Facts-only. No investment advice." in readme
    assert "## Local Deployment" in readme
    assert "## RAG Architecture Overview" in readme
    assert "## API Reference" in readme
    assert "## Known Limitations" in readme
    assert "POST /api/ask" in readme
    assert "/health" in readme
    assert "ingestion_runbook.md" in readme
    assert "demo_script.md" in readme


def test_phase6_ingestion_runbook_exists() -> None:
    runbook = read_text(DOCS / "ingestion_runbook.md")

    assert "scripts/ingest_corpus.py" in runbook
    assert "--dry-run" in runbook
    assert "Corpus Refresh Procedure" in runbook
    assert "GitHub Actions" in runbook
    assert "ingest_corpus.yml" in runbook


def test_phase6_demo_script_covers_three_factual_and_one_refusal() -> None:
    demo = read_text(DOCS / "demo_script.md")

    assert "What is the expense ratio of HDFC Large Cap Fund?" in demo
    assert "What is the minimum SIP for HDFC Mid Cap Fund?" in demo
    assert "What is the riskometer for HDFC Gold ETF FoF?" in demo
    assert "Should I invest in HDFC Mid Cap Fund?" in demo
    assert '"type": "refusal"' in demo


def test_phase6_env_example_documents_required_variables() -> None:
    env_example = read_text(ROOT / ".env.example")

    for key in (
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "BGE_MODEL_NAME",
        "VECTOR_STORE_PATH",
        "TOP_K",
        "SIMILARITY_THRESHOLD",
        "API_HOST",
        "API_PORT",
        "FRONTEND_ORIGIN",
    ):
        assert key in env_example

    assert env_example.count("#") >= 5


def test_phase6_ui_disclaimer_snippet() -> None:
    soup = BeautifulSoup(read_text(ROOT / "frontend" / "index.html"), "html.parser")
    disclaimer = soup.select_one('[data-testid="disclaimer-snippet"]')
    brand_subtitle = soup.select_one(".brand-subtitle")

    assert disclaimer is not None
    assert "Facts-only. No investment advice." in disclaimer.get_text(strip=True)
    assert brand_subtitle is not None
    assert "Facts-only. No investment advice." in brand_subtitle.get_text(strip=True)


def test_phase6_corpus_index_has_five_schemes_with_urls() -> None:
    import json

    corpus = json.loads(read_text(ROOT / "data" / "corpus_index.json"))

    assert len(corpus) == 5
    for entry in corpus:
        assert entry["source_url"].startswith("https://groww.in/mutual-funds/")
        assert entry.get("fetched_at")
