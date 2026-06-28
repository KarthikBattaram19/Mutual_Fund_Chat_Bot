from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from bs4 import BeautifulSoup, Tag


FACT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "nav": ("nav", "net asset value"),
    "expense_ratio": ("expense ratio", "ter"),
    "exit_load": ("exit load",),
    "min_sip": ("min sip", "minimum sip", "sip minimum", "min. sip"),
    "riskometer": ("riskometer", "risk", "risk level"),
    "benchmark": ("benchmark", "benchmark index"),
    "fund_manager": ("fund manager", "fund managers", "manager"),
    "aum": ("aum", "assets under management", "fund size"),
    "category": ("category", "fund category", "scheme category"),
    "lock_in": ("lock in", "lock-in", "lockin", "lock-in period", "lock in period"),
}

EXCLUDED_TEXT_MARKERS = (
    "calculator",
    "compare",
    "comparison",
    "growth of",
    "investment objective",
    "pros and cons",
    "rating",
    "review",
    "returns",
    "should you invest",
)


@dataclass(frozen=True)
class ParsedFact:
    """One factual field candidate extracted from DOM or embedded JSON."""

    field: str
    label: str
    value: str
    source: str


@dataclass(frozen=True)
class ParsedPage:
    """Structured parser output consumed by the later extractor step."""

    source_url: str
    title: str | None
    facts: list[ParsedFact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.facts)


class ParserError(ValueError):
    """Raised when the parser is asked to parse empty HTML in strict mode."""


class GrowwHTMLParser:
    """Parse Groww HTML/JSON and keep only structured factual field candidates."""

    def parse(self, html: str, *, source_url: str = "", strict: bool = False) -> ParsedPage:
        if not html or not html.strip():
            if strict:
                raise ParserError("HTML content is empty")
            return ParsedPage(source_url=source_url, title=None, warnings=["HTML content is empty"])

        soup = BeautifulSoup(html, "html.parser")
        title = self._page_title(soup)

        facts: list[ParsedFact] = []
        facts.extend(self._parse_json_scripts(soup))
        self._drop_noise(soup)
        facts.extend(self._parse_dom_pairs(soup))
        found_fields = {fact.field for fact in facts}
        facts.extend(fact for fact in self._parse_text_fallback(soup) if fact.field not in found_fields)

        deduped_facts = self._dedupe_facts(facts)
        warnings = [] if deduped_facts else ["No structured factual fields found"]

        return ParsedPage(
            source_url=source_url,
            title=title,
            facts=deduped_facts,
            warnings=warnings,
        )

    def parse_many(self, pages: Iterable[tuple[str, str]]) -> list[ParsedPage]:
        return [self.parse(html, source_url=source_url) for source_url, html in pages]

    def _parse_dom_pairs(self, soup: BeautifulSoup) -> list[ParsedFact]:
        facts: list[ParsedFact] = []

        for row in soup.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"], recursive=False)]
            if len(cells) >= 2:
                facts.extend(self._fact_from_pair(cells[0], " ".join(cells[1:]), "dom"))

        for details in soup.select("dl"):
            labels = details.find_all("dt", recursive=False)
            values = details.find_all("dd", recursive=False)
            for label, value in zip(labels, values, strict=False):
                facts.extend(self._fact_from_pair(label.get_text(" ", strip=True), value.get_text(" ", strip=True), "dom"))

        facts.extend(self._parse_card_like_pairs(soup))
        return facts

    def _parse_card_like_pairs(self, soup: BeautifulSoup) -> list[ParsedFact]:
        facts: list[ParsedFact] = []
        seen_tags: set[int] = set()

        for tag in soup.find_all(string=True):
            label = self._clean_text(str(tag))
            if not label or self._is_excluded(label):
                continue

            field_name = self._field_for_label(label)
            if field_name is None:
                continue

            parent = tag.parent
            if parent is None or id(parent) in seen_tags:
                continue
            seen_tags.add(id(parent))

            value = self._nearby_value(parent, label)
            facts.extend(self._fact_from_pair(label, value, "dom"))

        return facts

    def _nearby_value(self, label_tag: Tag, label: str) -> str:
        parent_text = label_tag.get_text(" ", strip=True)
        if parent_text and parent_text != label:
            value = parent_text.replace(label, "", 1).strip(" :-")
            if value:
                return value

        for sibling in label_tag.find_next_siblings():
            if isinstance(sibling, Tag):
                value = sibling.get_text(" ", strip=True)
                if value:
                    return value

        parent = label_tag.parent
        if parent is not None:
            for sibling in parent.find_next_siblings():
                if isinstance(sibling, Tag):
                    value = sibling.get_text(" ", strip=True)
                    if value and not self._is_excluded(value):
                        return value

        return ""

    def _parse_json_scripts(self, soup: BeautifulSoup) -> list[ParsedFact]:
        facts: list[ParsedFact] = []
        for payload in self._json_payloads(soup):
            self._walk_json(payload, facts=facts)
        return facts

    def _json_payloads(self, soup: BeautifulSoup) -> list[Any]:
        payloads: list[Any] = []
        for script in soup.find_all("script"):
            raw = script.string or script.get_text("", strip=True)
            raw = raw.strip()
            if not raw:
                continue

            parsed = self._parse_json_blob(raw)
            if parsed is not None:
                payloads.append(parsed)

        return payloads

    def _parse_json_blob(self, raw: str) -> Any | None:
        candidates = [raw]
        if raw.startswith("self.__next_f.push(") and raw.endswith(")"):
            candidates.append(raw.removeprefix("self.__next_f.push(").removesuffix(")"))

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return None

    def _walk_json(self, value: Any, *, facts: list[ParsedFact], key_path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for raw_key, raw_value in value.items():
                key = str(raw_key)
                field_name = self._field_for_label(key)
                if field_name is not None and self._is_scalar(raw_value):
                    facts.extend(self._fact_from_pair(key, str(raw_value), "json"))

                self._walk_json(raw_value, facts=facts, key_path=(*key_path, key))
            return

        if isinstance(value, list):
            if self._looks_like_label_value_list(value):
                label, raw_value = value[0], value[1]
                facts.extend(self._fact_from_pair(str(label), str(raw_value), "json"))
                return

            for item in value:
                self._walk_json(item, facts=facts, key_path=key_path)

    def _parse_text_fallback(self, soup: BeautifulSoup) -> list[ParsedFact]:
        text = self._clean_text(soup.get_text(" ", strip=True))
        facts: list[ParsedFact] = []

        for field_name, aliases in FACT_FIELD_ALIASES.items():
            for alias in aliases:
                pattern = rf"\b{re.escape(alias)}\b\s*:?\s*([A-Za-z0-9][^|;\n]{{0,80}})"
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if match:
                    value = self._clean_text(match.group(1)).strip(" :-")
                    if value and not self._is_excluded(value):
                        facts.append(ParsedFact(field=field_name, label=alias, value=value, source="text"))
                        break

        return facts

    def _fact_from_pair(self, label: str, value: str, source: str) -> list[ParsedFact]:
        label = self._clean_text(label)
        value = self._clean_text(value)
        if not label or not value or self._is_excluded(label):
            return []

        field_name = self._field_for_label(label)
        if field_name is None:
            return []

        return [ParsedFact(field=field_name, label=label, value=value, source=source)]

    def _field_for_label(self, label: str) -> str | None:
        normalized_label = self._normalize_label(label)
        for field_name, aliases in FACT_FIELD_ALIASES.items():
            for alias in aliases:
                normalized_alias = self._normalize_label(alias)
                if normalized_label == normalized_alias:
                    return field_name
                if len(normalized_alias) > 3 and normalized_alias in normalized_label:
                    return field_name
        return None

    def _dedupe_facts(self, facts: list[ParsedFact]) -> list[ParsedFact]:
        deduped: list[ParsedFact] = []
        seen: set[tuple[str, str]] = set()
        for fact in facts:
            key = (fact.field, self._clean_text(fact.value).casefold())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(fact)
        return deduped

    @staticmethod
    def _drop_noise(soup: BeautifulSoup) -> None:
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "button"]):
            tag.decompose()

    @staticmethod
    def _page_title(soup: BeautifulSoup) -> str | None:
        if soup.title is not None:
            title = soup.title.get_text(" ", strip=True)
            if title:
                return title

        heading = soup.find(["h1", "h2"])
        if heading is not None:
            return heading.get_text(" ", strip=True) or None

        return None

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _normalize_label(label: str) -> str:
        label = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", label)
        normalized = label.casefold()
        normalized = re.sub(r"[_\-]+", " ", normalized)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _is_scalar(value: Any) -> bool:
        return isinstance(value, str | int | float | bool) and value not in ("", None)

    def _looks_like_label_value_list(self, value: list[Any]) -> bool:
        return len(value) >= 2 and isinstance(value[0], str) and self._field_for_label(value[0]) is not None

    def _is_excluded(self, value: str) -> bool:
        normalized = self._normalize_label(value)
        return any(marker in normalized for marker in EXCLUDED_TEXT_MARKERS)
