from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from time import time
from typing import Callable


class GroqQuotaExceeded(RuntimeError):
    """Raised before Groq is called when local quota budget is exhausted."""


@dataclass(frozen=True)
class GroqQuotaLimits:
    requests_per_minute: int = 30
    requests_per_day: int = 1000
    tokens_per_minute: int = 12000
    tokens_per_day: int = 100000


@dataclass
class GroqQuotaGuard:
    """In-memory request/token budget guard for the configured Groq model."""

    limits: GroqQuotaLimits = field(default_factory=GroqQuotaLimits)
    now_fn: Callable[[], float] = time
    _events: deque[tuple[float, int]] = field(default_factory=deque)

    def check_and_record(self, *, estimated_tokens: int) -> None:
        now = float(self.now_fn())
        self._prune(now)

        minute_events = [(timestamp, tokens) for timestamp, tokens in self._events if now - timestamp < 60]
        day_events = list(self._events)
        if len(minute_events) >= self.limits.requests_per_minute:
            raise GroqQuotaExceeded("Groq request-per-minute budget exhausted")
        if len(day_events) >= self.limits.requests_per_day:
            raise GroqQuotaExceeded("Groq request-per-day budget exhausted")
        if sum(tokens for _, tokens in minute_events) + estimated_tokens > self.limits.tokens_per_minute:
            raise GroqQuotaExceeded("Groq token-per-minute budget exhausted")
        if sum(tokens for _, tokens in day_events) + estimated_tokens > self.limits.tokens_per_day:
            raise GroqQuotaExceeded("Groq token-per-day budget exhausted")

        self._events.append((now, estimated_tokens))

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= 86400:
            self._events.popleft()


def estimate_tokens(*parts: str) -> int:
    text = "\n".join(parts)
    return max(1, (len(text) + 3) // 4)
