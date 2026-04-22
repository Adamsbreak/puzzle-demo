from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class RuleChunk:
    source: str
    heading: str
    content: str
    tokens: set[str]


class LocalRuleRetriever:
    def __init__(self, docs_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.docs_dir = docs_dir or (root / "v1" / "docs")
        self._chunks = self._load_chunks()

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, str]]:
        if not self._chunks:
            return []

        query_tokens = self._tokenize(query)
        scored: list[tuple[float, RuleChunk]] = []
        for chunk in self._chunks:
            overlap = len(query_tokens.intersection(chunk.tokens))
            if overlap == 0:
                continue
            score = float(overlap)
            if "solver" in chunk.source.lower():
                score += 0.25
            if "rule" in chunk.source.lower():
                score += 0.15
            scored.append((score, chunk))

        if not scored:
            fallback = self._chunks[:top_k]
            return [self._format_hit(chunk, 0.0) for chunk in fallback]

        scored.sort(key=lambda item: item[0], reverse=True)
        return [self._format_hit(chunk, score) for score, chunk in scored[:top_k]]

    def format_context(self, hits: Iterable[dict[str, str]]) -> str:
        lines: list[str] = []
        for hit in hits:
            lines.append(
                f"[{hit.get('source', 'rule-doc')} :: {hit.get('heading', 'Section')}] {hit.get('excerpt', '')}"
            )
        return "\n\n".join(lines)

    def _load_chunks(self) -> list[RuleChunk]:
        if not self.docs_dir.exists():
            return []

        chunks: list[RuleChunk] = []
        for path in sorted(self.docs_dir.glob("*.md")):
            text = self._read_text(path)
            if not text.strip():
                continue
            chunks.extend(self._split_markdown(path.name, text))
        return chunks

    def _split_markdown(self, source: str, text: str, max_chars: int = 1200) -> list[RuleChunk]:
        sections: list[tuple[str, str]] = []
        current_heading = "Overview"
        buffer: list[str] = []

        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                if buffer:
                    sections.append((current_heading, "\n".join(buffer).strip()))
                    buffer = []
                current_heading = line.lstrip("# ").strip() or current_heading
                continue
            buffer.append(line)

        if buffer:
            sections.append((current_heading, "\n".join(buffer).strip()))

        chunks: list[RuleChunk] = []
        for heading, content in sections:
            normalized = self._normalize_excerpt(content)
            if not normalized:
                continue
            for start in range(0, len(normalized), max_chars):
                excerpt = normalized[start:start + max_chars].strip()
                if not excerpt:
                    continue
                chunk_heading = heading if start == 0 else f"{heading} (cont.)"
                chunks.append(
                    RuleChunk(
                        source=source,
                        heading=chunk_heading,
                        content=excerpt,
                        tokens=self._tokenize(f"{source} {heading} {excerpt}"),
                    )
                )
        return chunks

    def _read_text(self, path: Path) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")

    def _tokenize(self, text: str) -> set[str]:
        lowered = (text or "").lower()
        tokens = set(re.findall(r"[a-z0-9_-]+|[\u4e00-\u9fff]{2,}", lowered))
        expanded: set[str] = set()
        for token in tokens:
            expanded.add(token)
            if re.fullmatch(r"[\u4e00-\u9fff]{2,}", token):
                for index in range(0, len(token) - 1):
                    expanded.add(token[index:index + 2])
        return expanded

    def _normalize_excerpt(self, text: str, max_excerpt: int = 420) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        return compact[:max_excerpt]

    def _format_hit(self, chunk: RuleChunk, score: float) -> dict[str, str]:
        return {
            "source": chunk.source,
            "heading": chunk.heading,
            "excerpt": chunk.content,
            "score": f"{score:.2f}",
        }
