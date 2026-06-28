from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from ingestion.parser import ParsedFact, ParsedPage


CANONICAL_FIELDS: tuple[str, ...] = (
    "nav",
    "expense_ratio",
    "exit_load",
    "min_sip",
    "riskometer",
    "benchmark",
    "fund_manager",
    "aum",
    "category",
    "lock_in",
)

FIELD_LABELS: dict[str, str] = {
    "nav": "NAV",
    "expense_ratio": "Expense ratio",
    "exit_load": "Exit load",
    "min_sip": "Minimum SIP",
    "riskometer": "Riskometer",
    "benchmark": "Benchmark",
    "fund_manager": "Fund manager",
    "aum": "AUM",
    "category": "Category",
    "lock_in": "Lock-in period",
}

SOURCE_PRIORITY: dict[str, int] = {
    "json": 0,
    "dom": 1,
    "text": 2,
    "metadata": 3,
}

FILTERED_CONTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(blog|editorial|opinion|pros and cons|review|rating|star rating)\b", re.IGNORECASE),
    re.compile(r"\b(return calculator|sip calculator|calculator|chart|graph)\b", re.IGNORECASE),
    re.compile(r"\b(compare|comparison|versus|vs\.?)\b", re.IGNORECASE),
    re.compile(r"\b(should\s+(i|you|one)\s+invest|recommend|recommendation|best fund|better fund)\b", re.IGNORECASE),
    re.compile(r"\b(past performance|historical performance|annualised returns?|cagr|returns?)\b", re.IGNORECASE),
    re.compile(r"\b(login|sign in|subscribe|subscription-only|gated)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class ExtractedFact:
    """Normalized factual value with enough context for field-level chunking."""

    field: str
    label: str
    value: str
    content: str
    source: str
    source_url: str


@dataclass(frozen=True)
class ExtractedSchemeFacts:
    """Canonical facts and ingestion metadata for one scheme page."""

    scheme_name: str
    scheme_slug: str
    category: str
    source_url: str
    fetched_at: str | None
    facts: dict[str, ExtractedFact] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    filtered_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.facts)


class FactExtractor:
    """Normalize parsed candidates into the canonical scheme fact schema."""

    def extract(
        self,
        parsed_page: ParsedPage,
        corpus_entry: Mapping[str, Any],
        *,
        fetched_at: str | None = None,
    ) -> ExtractedSchemeFacts:
        source_url = str(corpus_entry.get("source_url") or parsed_page.source_url)
        category = self._clean_value(str(corpus_entry.get("category", "")))

        candidates = list(parsed_page.facts)
        if category and not any(candidate.field == "category" for candidate in candidates):
            candidates.append(ParsedFact(field="category", label="Category", value=category, source="metadata"))

        filtered_candidates, filtered_count = self._filter_candidates(candidates)
        facts = self._select_facts(filtered_candidates, source_url=source_url)
        missing_fields = [field_name for field_name in CANONICAL_FIELDS if field_name not in facts]
        warnings = list(parsed_page.warnings)
        if filtered_count:
            warnings.append(f"Filtered content candidates: {filtered_count}")
        if missing_fields:
            warnings.append(f"Missing fields: {', '.join(missing_fields)}")

        return ExtractedSchemeFacts(
            scheme_name=self._clean_value(str(corpus_entry.get("scheme_name", ""))),
            scheme_slug=self._clean_value(str(corpus_entry.get("scheme_slug", ""))),
            category=category,
            source_url=source_url,
            fetched_at=fetched_at if fetched_at is not None else corpus_entry.get("fetched_at"),
            facts=facts,
            missing_fields=missing_fields,
            filtered_count=filtered_count,
            warnings=warnings,
        )

    def extract_many(
        self,
        parsed_pages: Iterable[ParsedPage],
        corpus_entries: Iterable[Mapping[str, Any]],
        *,
        fetched_at_by_url: Mapping[str, str] | None = None,
    ) -> list[ExtractedSchemeFacts]:
        corpus_by_url = {str(entry["source_url"]): entry for entry in corpus_entries}
        fetched_at_by_url = fetched_at_by_url or {}

        extracted: list[ExtractedSchemeFacts] = []
        for parsed_page in parsed_pages:
            corpus_entry = corpus_by_url.get(parsed_page.source_url)
            if corpus_entry is None:
                raise KeyError(f"No corpus entry found for {parsed_page.source_url}")
            extracted.append(
                self.extract(
                    parsed_page,
                    corpus_entry,
                    fetched_at=fetched_at_by_url.get(parsed_page.source_url),
                )
            )
        return extracted

    def _filter_candidates(self, candidates: list[ParsedFact]) -> tuple[list[ParsedFact], int]:
        filtered: list[ParsedFact] = []
        dropped_count = 0

        for candidate in candidates:
            if self._is_filtered_content(candidate):
                dropped_count += 1
                continue
            filtered.append(candidate)

        return filtered, dropped_count

    def _is_filtered_content(self, candidate: ParsedFact) -> bool:
        if candidate.source == "metadata":
            return False

        haystack = f"{candidate.label} {candidate.value}"
        return any(pattern.search(haystack) for pattern in FILTERED_CONTENT_PATTERNS)

    def _select_facts(self, candidates: list[ParsedFact], *, source_url: str) -> dict[str, ExtractedFact]:
        best_by_field: dict[str, ParsedFact] = {}

        for candidate in candidates:
            if candidate.field not in CANONICAL_FIELDS:
                continue

            value = self._clean_value(candidate.value)
            if not value:
                continue

            normalized_candidate = ParsedFact(
                field=candidate.field,
                label=candidate.label,
                value=value,
                source=candidate.source,
            )

            current = best_by_field.get(candidate.field)
            if current is None or self._is_better_candidate(normalized_candidate, current):
                best_by_field[candidate.field] = normalized_candidate

        return {
            field_name: self._to_extracted_fact(candidate, source_url=source_url)
            for field_name, candidate in best_by_field.items()
        }

    def _to_extracted_fact(self, candidate: ParsedFact, *, source_url: str) -> ExtractedFact:
        label = FIELD_LABELS[candidate.field]
        value = self._normalize_field_value(candidate.field, candidate.value)
        return ExtractedFact(
            field=candidate.field,
            label=label,
            value=value,
            content=f"{label}: {value}",
            source=candidate.source,
            source_url=source_url,
        )

    def _is_better_candidate(self, candidate: ParsedFact, current: ParsedFact) -> bool:
        candidate_priority = SOURCE_PRIORITY.get(candidate.source, 99)
        current_priority = SOURCE_PRIORITY.get(current.source, 99)
        if candidate_priority != current_priority:
            return candidate_priority < current_priority

        return len(candidate.value) > len(current.value)

    def _normalize_field_value(self, field_name: str, value: str) -> str:
        value = self._clean_value(value)
        value = self._strip_redundant_field_text(field_name, value)

        if field_name in {"nav", "min_sip", "aum"}:
            value = value.replace("₹", "Rs ")
            value = re.sub(r"\bINR\b", "Rs", value, flags=re.IGNORECASE)
            value = re.sub(r"\bRs\.?\s*", "Rs ", value, flags=re.IGNORECASE)
            if self._is_plain_number(value):
                value = f"Rs {self._format_number(value)}"
                if field_name == "aum":
                    value = f"{value} Cr"
            value = self._clean_value(value)

        if field_name == "expense_ratio":
            value = f"{self._format_number(value)}%" if self._is_plain_number(value) else re.sub(r"\s*%\s*", "%", value)

        if field_name == "riskometer":
            value = re.sub(r"\s*riskometer\s*$", "", value, flags=re.IGNORECASE)
            value = self._clean_value(value)

        return value

    def _strip_redundant_field_text(self, field_name: str, value: str) -> str:
        if field_name == "exit_load":
            value = re.sub(r"^exit\s+load\s+(?:of\s+)?", "", value, flags=re.IGNORECASE)
        else:
            label = re.escape(FIELD_LABELS[field_name])
            value = re.sub(rf"^{label}\s*:?\s*", "", value, flags=re.IGNORECASE)
        return self._clean_value(value)

    @staticmethod
    def _is_plain_number(value: str) -> bool:
        try:
            Decimal(value.replace(",", ""))
        except InvalidOperation:
            return False
        return True

    @staticmethod
    def _format_number(value: str) -> str:
        number = Decimal(value.replace(",", "")).normalize()
        formatted = format(number, "f")
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")
        integral, separator, fractional = formatted.partition(".")
        integral = f"{int(integral):,}"
        return f"{integral}{separator}{fractional}"

    @staticmethod
    def _clean_value(value: str) -> str:
        value = value.replace("\xa0", " ")
        value = re.sub(r"\s+", " ", value)
        return value.strip(" :-|")
