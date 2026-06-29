import json
import os
import subprocess
from pathlib import Path

from bs4 import BeautifulSoup

from api.main import VERCEL_ORIGIN_PATTERN, _configured_frontend_origins


def test_frontend_vercel_config_is_static_only() -> None:
    vercel = json.loads(Path("frontend/vercel.json").read_text(encoding="utf-8"))
    package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))

    assert vercel["framework"] is None
    assert "vercel-build" in package["scripts"]
    assert "API_BASE_URL" in package["scripts"]["build"]
    assert not Path("vercel.json").exists()


def test_vercelignore_only_targets_repo_root_paths() -> None:
    ignored = Path(".vercelignore").read_text(encoding="utf-8")

    assert "/api/" in ignored
    assert "/scripts/" in ignored
    assert "api/" not in ignored.replace("/api/", "")
    assert "/requirements.txt" in ignored


def test_frontend_package_build_writes_config_js() -> None:
    config_path = Path("frontend/config.js")
    before = config_path.read_text(encoding="utf-8")
    try:
        env = {**os.environ, "API_BASE_URL": "https://api.example.railway.app"}
        subprocess.run(["npm", "run", "build"], check=True, env=env, cwd="frontend", shell=True)
        generated = config_path.read_text(encoding="utf-8")
        assert "https://api.example.railway.app" in generated
        assert "window.__API_BASE_URL__" in generated
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
