import json
from pathlib import Path

from scripts.index_from_samples import load_chunks


def test_railway_config_files_define_start_command() -> None:
    railway_toml = Path("railway.toml").read_text(encoding="utf-8")
    railpack_json = json.loads(Path("railpack.json").read_text(encoding="utf-8"))

    assert "uvicorn api.main:app" in railway_toml
    assert "$PORT" in railway_toml
    assert "index_from_samples.py" in railway_toml
    assert "uvicorn api.main:app" in railpack_json["deploy"]["startCommand"]


def test_index_from_samples_loads_committed_chunks() -> None:
    chunks = load_chunks(Path("data/sample_chunks.json"))

    assert len(chunks) > 0
    assert chunks[0].source_url.startswith("https://groww.in/mutual-funds/")
