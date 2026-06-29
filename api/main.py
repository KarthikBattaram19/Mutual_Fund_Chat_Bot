from __future__ import annotations

from collections import defaultdict, deque
from time import time
from typing import Callable

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings
from rag.retriever import ChromaRetriever

from api.routes.ask import router as ask_router

VERCEL_ORIGIN_PATTERN = r"https://.*\.vercel\.app"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Mutual Fund FAQ Assistant")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_configured_frontend_origins(settings.frontend_origin),
        allow_origin_regex=VERCEL_ORIGIN_PATTERN,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.middleware("http")(PerClientRateLimiter(limit=30, window_seconds=60))
    app.include_router(ask_router)

    @app.get("/health")
    def health() -> dict[str, object]:
        retriever = ChromaRetriever()
        return {
            "status": "ok",
            "vector_store_path": str(retriever.vector_store_path),
            "vector_store_ready": retriever.ready,
            "groq_model": settings.groq_model,
        }

    if settings.serve_ui:
        _mount_ui(app)
    return app


def _mount_ui(app: FastAPI) -> None:
    """Optionally serve the static UI from the API process (local single-server mode)."""

    frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


def _configured_frontend_origins(configured_origin: str) -> list[str]:
    """Allow configured origins plus local static dev servers."""

    origins = [part.strip() for part in configured_origin.split(",") if part.strip()]
    origins.extend(
        [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    return list(dict.fromkeys(origins))


class PerClientRateLimiter:
    """Small in-memory per-client limiter for local MVP use."""

    def __init__(self, *, limit: int, window_seconds: int, now_fn: Callable[[], float] = time) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.now_fn = now_fn
        self.events: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, request: Request, call_next):
        if request.url.path != "/api/ask":
            return await call_next(request)

        client_id = request.client.host if request.client else "unknown"
        now = self.now_fn()
        events = self.events[client_id]
        while events and now - events[0] >= self.window_seconds:
            events.popleft()
        if len(events) >= self.limit:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
        events.append(now)
        return await call_next(request)


app = create_app()
