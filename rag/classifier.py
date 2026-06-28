from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class QueryIntent(StrEnum):
    FACTUAL = "factual"
    ADVISORY = "advisory"
    PERFORMANCE = "performance"
    PII_DETECTED = "pii_detected"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class ClassificationResult:
    intent: QueryIntent
    reason: str
    supported_schemes: tuple[str, ...] = ()
    matched_schemes: tuple[dict[str, Any], ...] = ()


ADVISORY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bshould\s+(i|we|you|one)\s+invest\b", re.IGNORECASE),
    re.compile(r"\b(recommend|recommendation|suggest|advice|advise)\b", re.IGNORECASE),
    re.compile(r"\b(best|better|good|safe(?:st)?)\s+(fund|option|investment)\b", re.IGNORECASE),
    re.compile(r"\bfund\b.*\bis\s+(?:the\s+)?(?:best|better|good|right|safe(?:st)?)\b", re.IGNORECASE),
    re.compile(r"\bwhich\b.*\bfund\b.*\b(?:best|better|good|right|safe(?:st)?)\b", re.IGNORECASE),
    re.compile(r"\bfor\s+me\b", re.IGNORECASE),
)

PERFORMANCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\breturns?\b", re.IGNORECASE),
    re.compile(r"\b(cagr|xirr|alpha|beta|sharpe|performance)\b", re.IGNORECASE),
    re.compile(r"\b(1|3|5|10)[-\s]?(year|yr)\b", re.IGNORECASE),
    re.compile(r"\bcompare\b.*\breturns?\b", re.IGNORECASE),
)

PII_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE),  # PAN
    re.compile(r"\b(?:\d[ -]?){12}\b"),  # Aadhaar-like 12 digits
    re.compile(r"\b[6-9]\d{9}\b"),  # Indian mobile number
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(?:account|acct|a/c)\s*(?:number|no\.?)?\s*\d{9,18}\b", re.IGNORECASE),
    re.compile(r"\botp\s*(?:is|:)?\s*\d{4,8}\b", re.IGNORECASE),
)

GENERIC_SCOPE_TOKENS = {
    "hdfc",
    "fund",
    "mutual",
    "direct",
    "growth",
    "plan",
    "scheme",
    "etf",
    "fof",
    "of",
}


class QueryClassifier:
    """Rule-based compliance classifier that runs before retrieval."""

    def __init__(self, *, corpus_index_path: str | Path = "data/corpus_index.json") -> None:
        self.corpus_index_path = Path(corpus_index_path)
        self._supported_schemes = self._load_supported_schemes()
        self._scope_tokens_by_scheme = {
            scheme["scheme_name"]: _distinctive_tokens(f"{scheme['scheme_name']} {scheme['scheme_slug']}")
            for scheme in self._supported_schemes
        }

    @property
    def supported_scheme_names(self) -> tuple[str, ...]:
        return tuple(str(scheme["scheme_name"]) for scheme in self._supported_schemes)

    def classify(self, query: str) -> ClassificationResult:
        normalized = query.strip()
        matched_schemes = self._matched_supported_schemes(normalized)
        if self._contains_pii(normalized):
            return ClassificationResult(QueryIntent.PII_DETECTED, "PII detected", self.supported_scheme_names)
        if self._matches_any(normalized, ADVISORY_PATTERNS):
            return ClassificationResult(QueryIntent.ADVISORY, "Investment advice or recommendation requested", self.supported_scheme_names)
        if self._matches_any(normalized, PERFORMANCE_PATTERNS):
            return ClassificationResult(
                QueryIntent.PERFORMANCE,
                "Performance or returns query",
                self.supported_scheme_names,
                matched_schemes,
            )
        if self._is_out_of_scope(normalized):
            return ClassificationResult(QueryIntent.OUT_OF_SCOPE, "Scheme is outside the supported corpus", self.supported_scheme_names)
        return ClassificationResult(QueryIntent.FACTUAL, "Factual corpus-bound query", self.supported_scheme_names)

    def _load_supported_schemes(self) -> list[dict[str, Any]]:
        return json.loads(self.corpus_index_path.read_text(encoding="utf-8"))

    @staticmethod
    def _contains_pii(query: str) -> bool:
        return any(pattern.search(query) for pattern in PII_PATTERNS)

    @staticmethod
    def _matches_any(query: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
        return any(pattern.search(query) for pattern in patterns)

    def _is_out_of_scope(self, query: str) -> bool:
        query_tokens = set(_tokens(query))
        if "hdfc" not in query_tokens or "fund" not in query_tokens:
            return False

        for scheme_tokens in self._scope_tokens_by_scheme.values():
            required_matches = min(2, len(scheme_tokens))
            if scheme_tokens and len(scheme_tokens & query_tokens) >= required_matches:
                return False

        distinctive_query_tokens = query_tokens - GENERIC_SCOPE_TOKENS
        return bool(distinctive_query_tokens)

    def _matched_supported_schemes(self, query: str) -> tuple[dict[str, Any], ...]:
        query_tokens = set(_tokens(query))
        matches: list[dict[str, Any]] = []
        for scheme in self._supported_schemes:
            scheme_tokens = self._scope_tokens_by_scheme[str(scheme["scheme_name"])]
            required_matches = min(2, len(scheme_tokens))
            if scheme_tokens and len(scheme_tokens & query_tokens) >= required_matches:
                matches.append(scheme)
        return tuple(matches)


def _tokens(value: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).split()


def _distinctive_tokens(value: str) -> set[str]:
    return {token for token in _tokens(value) if token not in GENERIC_SCOPE_TOKENS}
