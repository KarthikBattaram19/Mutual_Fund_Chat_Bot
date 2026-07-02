from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import get_settings
from ingestion.chunker import CorpusChunk
from rag.quota import GroqQuotaGuard, estimate_tokens


class GroqGenerationError(RuntimeError):
    """Raised when Groq generation is unavailable or fails."""


_groq_client: Any | None = None


SYSTEM_PROMPT = """You are a facts-only mutual fund FAQ assistant.
Use only the provided retrieved context.
Do not provide investment advice, recommendations, opinions, or return figures.
Do not include source URLs, update dates, or attribution footers in your answer; the UI displays those separately.
Answer in no more than 3 sentences."""


@dataclass
class GroqGenerator:
    """Generate short grounded answers from retrieved chunks."""

    client: Any | None = None
    quota_guard: GroqQuotaGuard = field(default_factory=GroqQuotaGuard)
    model_name: str | None = None
    max_output_tokens: int = 160

    def generate(self, *, query: str, chunks: list[CorpusChunk]) -> str:
        if not chunks:
            raise GroqGenerationError("Cannot generate without retrieved context")

        settings = get_settings()
        model_name = self.model_name or settings.groq_model
        context = _context_from_chunks(chunks)
        user_prompt = f"Retrieved context:\n{context}\n\nUser question: {query}"
        self.quota_guard.check_and_record(
            estimated_tokens=estimate_tokens(SYSTEM_PROMPT, user_prompt) + self.max_output_tokens
        )

        client = self.client or self._load_client(settings.groq_api_key)
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=self.max_output_tokens,
            )
        except Exception as exc:
            raise GroqGenerationError("Groq generation failed") from exc

        content = response.choices[0].message.content
        if not content:
            raise GroqGenerationError("Groq returned an empty answer")
        return str(content).strip()

    @staticmethod
    def _load_client(api_key: str) -> Any:
        global _groq_client
        if not api_key:
            raise GroqGenerationError("GROQ_API_KEY is not configured")
        if _groq_client is None:
            from groq import Groq

            _groq_client = Groq(api_key=api_key)
        return _groq_client


def _context_from_chunks(chunks: list[CorpusChunk]) -> str:
    return "\n".join(
        f"- {chunk.scheme_name} [{chunk.field}]: {chunk.content}"
        for chunk in chunks
    )
