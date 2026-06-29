import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables or .env."""

    groq_api_key: str
    groq_model: str
    bge_model_name: str
    vector_store_path: Path
    top_k: int
    similarity_threshold: float
    api_host: str
    api_port: int
    frontend_origin: str
    serve_ui: bool


def _read_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _get_value(values: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key) or values.get(key) or default


def _bounded_int(raw_value: str, *, minimum: int, maximum: int, name: str) -> int:
    value = int(raw_value)
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_float(raw_value: str, *, minimum: float, maximum: float, name: str) -> float:
    value = float(raw_value)
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _get_bool(values: dict[str, str], key: str, default: str) -> bool:
    raw = os.environ.get(key) or values.get(key) or default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    dotenv_values = _read_dotenv()

    return Settings(
        groq_api_key=_get_value(dotenv_values, "GROQ_API_KEY", ""),
        groq_model=_get_value(dotenv_values, "GROQ_MODEL", "llama-3.3-70b-versatile"),
        bge_model_name=_get_value(dotenv_values, "BGE_MODEL_NAME", "BAAI/bge-small-en-v1.5"),
        vector_store_path=Path(_get_value(dotenv_values, "VECTOR_STORE_PATH", "data/vector_store")),
        top_k=_bounded_int(_get_value(dotenv_values, "TOP_K", "5"), minimum=1, maximum=10, name="TOP_K"),
        similarity_threshold=_bounded_float(
            _get_value(dotenv_values, "SIMILARITY_THRESHOLD", "0.35"),
            minimum=0.0,
            maximum=1.0,
            name="SIMILARITY_THRESHOLD",
        ),
        api_host=_get_value(dotenv_values, "API_HOST", "127.0.0.1"),
        api_port=_bounded_int(
            os.environ.get("PORT") or _get_value(dotenv_values, "API_PORT", "8000"),
            minimum=1,
            maximum=65535,
            name="API_PORT",
        ),
        frontend_origin=_get_value(dotenv_values, "FRONTEND_ORIGIN", "http://localhost:3000"),
        serve_ui=_get_bool(dotenv_values, "SERVE_UI", "false"),
    )
