from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from backend.ai.retrieval import CorpusEntry, LexicalRetriever, keyword_union, slugify, split_markdown_sections


ROOT_DIR = Path(__file__).resolve().parents[2]
CORPUS_MANIFEST_PATH = ROOT_DIR / "docs" / "light_rag_corpus.json"
RULE_DOC_SOURCES = [
    ROOT_DIR / "v1" / "docs" / "static_solver_rules.md",
    ROOT_DIR / "v1" / "docs" / "solver_design_v1.md",
    ROOT_DIR / "v1" / "docs" / "java_solver_contract.md",
]


def load_rule_entries() -> list[CorpusEntry]:
    manifest_entries = _load_manifest_rule_entries()
    if manifest_entries:
        return manifest_entries
    return _build_rule_entries_from_sources()


class RulesRAG:
    def __init__(self, entries: Iterable[CorpusEntry] | None = None) -> None:
        self.entries = list(entries) if entries is not None else load_rule_entries()
        self.retriever = LexicalRetriever(self.entries)

    def search(self, query: str, top_k: int = 5):
        return self.retriever.search(query, top_k=top_k)


def _load_manifest_rule_entries() -> list[CorpusEntry]:
    if not CORPUS_MANIFEST_PATH.exists():
        return []
    payload = json.loads(CORPUS_MANIFEST_PATH.read_text(encoding="utf-8"))
    entries: list[CorpusEntry] = []
    for item in payload.get("entries", []):
        if item.get("type") != "rule_doc":
            continue
        entries.append(
            CorpusEntry(
                id=item["id"],
                type="rule_doc",
                title=item.get("title", item["id"]),
                summary=item.get("summary", ""),
                source_path=item.get("source_path", ""),
                keywords=tuple(item.get("keywords", []) or []),
                metadata={"origin": "manifest"},
            )
        )
    return entries


def _build_rule_entries_from_sources() -> list[CorpusEntry]:
    entries: list[CorpusEntry] = []
    for path in RULE_DOC_SOURCES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for index, (title, body) in enumerate(split_markdown_sections(text, path.stem), start=1):
            summary = " ".join(line.strip() for line in body.splitlines()[:3]).strip()
            if not summary:
                continue
            keywords = keyword_union(
                title.split(),
                [path.stem.replace("_", "-"), path.name],
            )
            entries.append(
                CorpusEntry(
                    id=f"rules.{slugify(path.stem)}.{index}",
                    type="rule_doc",
                    title=title,
                    summary=summary[:320],
                    source_path=str(path.relative_to(ROOT_DIR)).replace("\\", "/"),
                    keywords=keywords,
                    content=body[:1500],
                    metadata={"origin": "source"},
                )
            )
    return entries
