from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ingestion.chunker import CorpusChunk

_PROVENANCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\s*This (?:information|data) was (?:fetched|retrieved|sourced) from\s+https?://\S+\s+on\s+[^.!?]+[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s*This (?:information|data) was (?:fetched|retrieved|sourced) from\s+https?://\S+\.?\s*",
        re.IGNORECASE,
    ),
    re.compile(r"\s*This information was last updated on\s+[^.!?]+[.!?]\s*", re.IGNORECASE),
    re.compile(r"\s*The source of this information is\s+https?://\S+\.?\s*", re.IGNORECASE),
    re.compile(r"\s*Source:\s*https?://\S+\.?\s*", re.IGNORECASE),
    re.compile(r"\s*Last updated(?: from sources)?:\s*[^.!?]+[.!?]\s*", re.IGNORECASE),
)


@dataclass(frozen=True)
class AnswerResponse:
    type: str
    answer: str
    source_url: str
    last_updated: str


class ResponseFormatter:
    """Attach the single approved citation and source freshness footer."""

    def format_answer(self, answer: str, chunks: list[CorpusChunk]) -> AnswerResponse:
        if not chunks:
            raise ValueError("Cannot format an answer without retrieved chunks")

        source_chunk = chunks[0]
        return AnswerResponse(
            type="answer",
            answer=_strip_provenance_from_answer(answer),
            source_url=source_chunk.source_url,
            last_updated=_format_date(source_chunk.fetched_at),
        )


def _strip_provenance_from_answer(answer: str) -> str:
    cleaned = answer.strip()
    for pattern in _PROVENANCE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned.strip()


def _format_date(fetched_at: str | None) -> str:
    if not fetched_at:
        return "Unknown"
    try:
        parsed = datetime.strptime(fetched_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return fetched_at
    return parsed.strftime("%B %Y")
