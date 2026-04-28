from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable


_WORD_RE = re.compile(r"[a-z0-9\-_]+")


@dataclass(slots=True, frozen=True)
class CorpusEntry:
    id: str
    type: str
    title: str
    summary: str
    source_path: str
    keywords: tuple[str, ...] = ()
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SearchHit:
    id: str
    type: str
    title: str
    summary: str
    score: float
    source_path: str
    matched_keywords: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "summary": self.summary,
            "score": round(self.score, 4),
            "sourcePath": self.source_path,
            "matchedKeywords": list(self.matched_keywords),
            "metadata": self.metadata,
        }


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def tokenize(text: str) -> list[str]:
    lowered = normalize_text(text)
    word_tokens = _WORD_RE.findall(lowered)
    chinese_chars = [ch for ch in lowered if "\u4e00" <= ch <= "\u9fff"]
    return word_tokens + chinese_chars


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", normalize_text(text))
    return cleaned.strip("-") or "entry"


def keyword_union(*values: Iterable[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for value in values:
        for item in value:
            normalized = str(item).strip()
            if normalized and normalized not in seen:
                seen.append(normalized)
    return tuple(seen)


def split_markdown_sections(text: str, fallback_title: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = fallback_title
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("#"):
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    sections.append((current_title, body))
            current_title = line.lstrip("#").strip() or fallback_title
            current_lines = []
            continue
        current_lines.append(line)
    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_title, body))
    return sections


class LexicalRetriever:
    def __init__(self, entries: Iterable[CorpusEntry]) -> None:
        self.entries = list(entries)

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        ranked: list[SearchHit] = []
        for entry in self.entries:
            score, matched_keywords = self._score_entry(query, entry)
            ranked.append(
                SearchHit(
                    id=entry.id,
                    type=entry.type,
                    title=entry.title,
                    summary=entry.summary,
                    score=score,
                    source_path=entry.source_path,
                    matched_keywords=matched_keywords,
                    metadata=entry.metadata,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.id))
        return ranked[:top_k]

    def _score_entry(self, query: str, entry: CorpusEntry) -> tuple[float, tuple[str, ...]]:
        query_norm = normalize_text(query)
        query_tokens = set(tokenize(query))
        haystack = " ".join(
            [
                entry.title,
                entry.summary,
                " ".join(entry.keywords),
                entry.content,
                entry.id,
            ]
        )
        haystack_tokens = set(tokenize(haystack))

        score = float(len(query_tokens.intersection(haystack_tokens)))
        matched_keywords: list[str] = []

        for keyword in entry.keywords:
            keyword_norm = normalize_text(keyword)
            if keyword_norm and keyword_norm in query_norm:
                score += 3.0
                matched_keywords.append(keyword)
                continue
            keyword_tokens = set(tokenize(keyword))
            if keyword_tokens:
                overlap = len(query_tokens.intersection(keyword_tokens))
                if overlap:
                    score += 0.25 * overlap

        title_norm = normalize_text(entry.title)
        if title_norm and title_norm in query_norm:
            score += 4.0

        entry_tail = normalize_text(entry.id).split(".")[-1]
        if entry_tail and entry_tail in query_norm:
            score += 2.0

        if entry.type == "rule_doc" and any(
            token in query_norm for token in ("why", "difference", "rule", "rules", "interface", "architecture", "bridge")
        ):
            score += 0.2
        if entry.type == "case" and any(token in query_norm for token in ("case", "example", "regression", "tc")):
            score += 0.2

        return round(score, 4), tuple(matched_keywords)


def build_context_block(
    query: str,
    rule_hits: list[SearchHit],
    case_hits: list[SearchHit],
    max_items: int = 6,
) -> str:
    lines = [f"Query: {query}", ""]
    if rule_hits:
        lines.append("Relevant rules:")
        for hit in rule_hits[:max_items]:
            lines.append(f"- [{hit.id}] {hit.title}: {hit.summary}")
        lines.append("")
    if case_hits:
        lines.append("Relevant cases:")
        for hit in case_hits[:max_items]:
            lines.append(f"- [{hit.id}] {hit.title}: {hit.summary}")
    return "\n".join(lines).strip()
