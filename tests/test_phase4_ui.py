from pathlib import Path

from bs4 import BeautifulSoup


FRONTEND_DIR = Path("frontend")


def read_ui_file(name: str) -> str:
    return (FRONTEND_DIR / name).read_text(encoding="utf-8")


def test_phase4_ui_static_files_exist() -> None:
    assert (FRONTEND_DIR / "index.html").exists()
    assert (FRONTEND_DIR / "styles.css").exists()
    assert (FRONTEND_DIR / "api.js").exists()
    assert (FRONTEND_DIR / "app.js").exists()


def test_phase4_ui_has_required_load_state_components() -> None:
    soup = BeautifulSoup(read_ui_file("index.html"), "html.parser")

    description = soup.select_one('meta[name="description"]')
    header = soup.select_one("header.site-header")
    main = soup.select_one("main")
    footer = soup.select_one("footer.site-footer")
    welcome = soup.select_one('[data-testid="welcome-message"]')
    examples = soup.select('[data-testid="example-questions"] .example-chip')
    chat_input = soup.select_one('[data-testid="chat-input"]')
    chat_history = soup.select_one('[data-testid="chat-history"]')

    assert description is not None
    assert "FAQ website" in description["content"]
    assert header is not None
    assert main is not None
    assert footer is not None
    assert "educational MVP" in footer.get_text(" ", strip=True)
    assert welcome is not None
    assert "five HDFC schemes" in welcome.get_text(" ", strip=True)
    assert len(examples) == 3
    assert chat_input is not None
    assert chat_history is not None


def test_phase4_examples_cover_required_questions() -> None:
    soup = BeautifulSoup(read_ui_file("index.html"), "html.parser")
    questions = {
        button["data-question"]
        for button in soup.select(".example-chip")
    }

    assert "What is the expense ratio of HDFC Large Cap Fund?" in questions
    assert "What is the minimum SIP for HDFC Mid Cap Fund?" in questions
    assert "What is the riskometer for HDFC Gold ETF FoF?" in questions


def test_phase4_frontend_posts_to_ask_endpoint_and_renders_payloads() -> None:
    api_js = read_ui_file("api.js")
    app_js = read_ui_file("app.js")

    assert "/api/ask" in api_js
    assert 'method: "POST"' in api_js
    assert "warmupBackend" in api_js
    assert "/health" in api_js
    assert "warmupBackend" in app_js
    assert "renderResponseCard" in app_js
    assert "renderRefusalCard" in app_js
    assert "Last updated from sources:" in app_js
    assert "target = \"_blank\"" in app_js
    assert "localStorage" not in app_js
    assert "document.cookie" not in app_js
