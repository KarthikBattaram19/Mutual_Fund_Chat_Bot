from __future__ import annotations

import re
from dataclasses import dataclass


class ResponseValidationError(ValueError):
    """Raised when a generated answer violates compliance constraints."""


ADVISORY_OUTPUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(you should|i recommend|we recommend|best|better option|suitable for you)\b", re.IGNORECASE),
    re.compile(r"\b(buy|sell|invest in|avoid this fund)\b", re.IGNORECASE),
)

RETURN_OUTPUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\breturns?\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s*%\b.*\b(year|yr|return|cagr)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class ResponseValidator:
    """Validate model output before formatting."""

    max_sentences: int = 3

    def validate(self, answer: str, *, context: str, performance_query: bool = False) -> str:
        cleaned = answer.strip()
        if not cleaned:
            raise ResponseValidationError("Generated answer is empty")
        if self._sentence_count(cleaned) > self.max_sentences:
            raise ResponseValidationError("Generated answer exceeds sentence limit")
        if any(pattern.search(cleaned) for pattern in ADVISORY_OUTPUT_PATTERNS):
            raise ResponseValidationError("Generated answer contains advisory language")
        if performance_query or any(pattern.search(cleaned) for pattern in RETURN_OUTPUT_PATTERNS):
            raise ResponseValidationError("Generated answer contains performance or return content")
        if not self._has_context_overlap(cleaned, context):
            raise ResponseValidationError("Generated answer is not grounded in retrieved context")
        return cleaned

    @staticmethod
    def _sentence_count(answer: str) -> int:
        return len([part for part in re.split(r"(?<=[.!?])\s+", answer) if part.strip()])

    @staticmethod
    def _has_context_overlap(answer: str, context: str) -> bool:
        answer_tokens = _meaningful_tokens(answer)
        context_tokens = _meaningful_tokens(context)
        return bool(answer_tokens & context_tokens)


def _meaningful_tokens(value: str) -> set[str]:
    stopwords = {"the", "is", "a", "an", "for", "of", "and", "in", "to", "from", "rs"}
    tokens = re.sub(r"[^a-z0-9.]+", " ", value.lower()).split()
    return {token for token in tokens if token not in stopwords and len(token) > 1}
