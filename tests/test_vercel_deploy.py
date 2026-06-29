import json
import os
import subprocess
from pathlib import Path

from bs4 import BeautifulSoup

from api.main import VERCEL_ORIGIN_PATTERN, _configured_frontend_origins


def test_frontend_vercel_config_exists() -> None:
    vercel = json.loads(Path("frontend/vercel.json").read_text(encoding="utf-8"))
    package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))

    assert vercel["buildCommand"] == "npm run build"
    assert package["scripts"]["build"] == "node ../scripts/generate_frontend_config.js"


def test_generate_frontend_config_writes_api_base_url() -> None:
    config_path = Path("frontend/config.js")
    before = config_path.read_text(encoding="utf-8")
    try:
        env = {**os.environ, "API_BASE_URL": "https://api.example.railway.app"}
        subprocess.run(["node", "scripts/generate_frontend_config.js"], check=True, env=env)
        generated = config_path.read_text(encoding="utf-8")
        assert 'window.__API_BASE_URL__ = "https://api.example.railway.app"' in generated
    finally:
        config_path.write_text(before, encoding="utf-8")


def test_frontend_loads_runtime_config_before_app() -> None:
    soup = BeautifulSoup(Path("frontend/index.html").read_text(encoding="utf-8"), "html.parser")
    scripts = [tag.get("src") for tag in soup.find_all("script") if tag.get("src")]

    assert "./config.js" in scripts
    assert scripts.index("./config.js") < scripts.index("./app.js")


def test_api_cors_allows_configured_and_vercel_origins() -> None:
    origins = _configured_frontend_origins(
        "https://mutual-fund-chat-bot.vercel.app,https://custom.example.com"
    )

    assert "https://mutual-fund-chat-bot.vercel.app" in origins
    assert "https://custom.example.com" in origins
    assert "http://localhost:3000" in origins
    assert VERCEL_ORIGIN_PATTERN == r"https://.*\.vercel\.app"
