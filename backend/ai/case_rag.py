from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from backend.ai.retrieval import CorpusEntry, LexicalRetriever, keyword_union


ROOT_DIR = Path(__file__).resolve().parents[2]
CORPUS_MANIFEST_PATH = ROOT_DIR / "docs" / "light_rag_corpus.json"
MANUAL_CASES_DIR = ROOT_DIR / "v1" / "java-solver" / "manual-cases"


def load_case_entries() -> list[CorpusEntry]:
    manifest_entries = {entry.id: entry for entry in _load_manifest_case_entries()}
    generated_entries = _build_case_entries_from_manual_cases()
    entries: list[CorpusEntry] = []
    for entry in generated_entries:
        manifest_entry = manifest_entries.get(entry.id)
        if manifest_entry is None:
            entries.append(entry)
            continue
        entries.append(
            CorpusEntry(
                id=entry.id,
                type=entry.type,
                title=manifest_entry.title or entry.title,
                summary=manifest_entry.summary or entry.summary,
                source_path=entry.source_path,
                keywords=keyword_union(entry.keywords, manifest_entry.keywords),
                content=entry.content,
                metadata={**entry.metadata, **manifest_entry.metadata, "origin": "manual-case+manifest"},
            )
        )
    return entries


class CaseRAG:
    def __init__(self, entries: Iterable[CorpusEntry] | None = None) -> None:
        self.entries = list(entries) if entries is not None else load_case_entries()
        self.retriever = LexicalRetriever(self.entries)

    def search(self, query: str, top_k: int = 5):
        return self.retriever.search(query, top_k=top_k)


def _load_manifest_case_entries() -> list[CorpusEntry]:
    if not CORPUS_MANIFEST_PATH.exists():
        return []
    payload = json.loads(CORPUS_MANIFEST_PATH.read_text(encoding="utf-8"))
    entries: list[CorpusEntry] = []
    for item in payload.get("entries", []):
        if item.get("type") != "case":
            continue
        entries.append(
            CorpusEntry(
                id=item["id"],
                type="case",
                title=item.get("title", item["id"]),
                summary=item.get("summary", ""),
                source_path=item.get("source_path", ""),
                keywords=tuple(item.get("keywords", []) or []),
                metadata={"origin": "manifest"},
            )
        )
    return entries


def _build_case_entries_from_manual_cases() -> list[CorpusEntry]:
    entries: list[CorpusEntry] = []
    for path in sorted(MANUAL_CASES_DIR.glob("tc*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        title = (payload.get("meta") or {}).get("title") or path.stem
        summary = _build_case_summary(payload)
        keywords = _build_case_keywords(payload, path.stem)
        metadata = _build_case_metadata(payload, path)
        entries.append(
            CorpusEntry(
                id=f"case.{path.stem}",
                type="case",
                title=title,
                summary=summary,
                source_path=str(path.relative_to(ROOT_DIR)).replace("\\", "/"),
                keywords=keywords,
                content=json.dumps(payload, ensure_ascii=False)[:2000],
                metadata=metadata,
            )
        )
    return entries


def _build_case_summary(payload: dict[str, Any]) -> str:
    board = payload.get("board") or {}
    pieces = payload.get("pieces") or []
    zones = payload.get("zones") or []
    title = (payload.get("meta") or {}).get("title") or "Manual case"
    edge_goal = any(zone.get("shapeKind") == "edge" for zone in zones)
    large_piece = any((piece.get("w", 1) > 1 or piece.get("h", 1) > 1) for piece in pieces)
    return (
        f"{title}. Board {board.get('rows', '?')}x{board.get('cols', '?')}, "
        f"{len(pieces)} pieces, {len(zones)} zones."
        + (" Contains an edge goal." if edge_goal else "")
        + (" Includes a large-piece footprint check." if large_piece else "")
    )


def _build_case_keywords(payload: dict[str, Any], stem: str) -> tuple[str, ...]:
    board = payload.get("board") or {}
    pieces = payload.get("pieces") or []
    zones = payload.get("zones") or []
    tokens = stem.split("_")
    roles = [str(piece.get("role", "")) for piece in pieces if piece.get("role")]
    tags = sorted(
        {
            tag
            for row in board.get("cells", []) or []
            for cell in row or []
            for tag in (cell or {}).get("tags", [])
            if tag
        }
    )
    zone_kinds = [str(zone.get("shapeKind", "")) for zone in zones if zone.get("shapeKind")]
    goal_modes = [str(zone.get("goalMode", "")) for zone in zones if zone.get("goalMode")]
    heuristics: list[str] = []
    if any(zone.get("shapeKind") == "edge" for zone in zones):
        heuristics.extend(["edge goal", "edge"])
    if any(piece.get("w", 1) > 1 or piece.get("h", 1) > 1 for piece in pieces):
        heuristics.extend(["large piece", "footprint"])
    if "horizontal" in tags and "vertical" not in tags:
        heuristics.append("horizontal forbids vertical")
    if "target-lane" in tags:
        heuristics.append("target-lane priority")
    if "blocked" in tags:
        heuristics.append("blocked")
    if any(role == "fixed" for role in roles):
        heuristics.extend(["fixed", "fixed blocker"])
    return keyword_union(tokens, roles, tags, zone_kinds, goal_modes, heuristics, [f"{board.get('rows')}x{board.get('cols')}"])


def _build_case_metadata(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    board = payload.get("board") or {}
    pieces = payload.get("pieces") or []
    zones = payload.get("zones") or []
    return {
        "boardRows": board.get("rows"),
        "boardCols": board.get("cols"),
        "pieceCount": len(pieces),
        "zoneCount": len(zones),
        "roles": sorted({piece.get("role") for piece in pieces if piece.get("role")}),
        "zoneKinds": sorted({zone.get("shapeKind") for zone in zones if zone.get("shapeKind")}),
        "goalModes": sorted({zone.get("goalMode") for zone in zones if zone.get("goalMode")}),
        "fileName": path.name,
        "title": (payload.get("meta") or {}).get("title"),
    }
