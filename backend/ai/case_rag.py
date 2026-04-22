from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("simple", "easy", "\u7b80\u5355", "\u6e05\u6670", "\u6613\u89c2\u5bdf", "\u4f4e\u8026\u5408"),
    ("complex", "hard", "\u590d\u6742", "\u96be\u89c2\u5bdf", "\u8054\u52a8\u591a", "\u9ad8\u8026\u5408"),
    ("internal-goal", "internal goal", "\u5185\u90e8\u7ec8\u70b9", "\u5185\u90e8\u76ee\u6807"),
    ("edge-goal", "edge goal", "\u8fb9\u7f18\u7ec8\u70b9", "\u8fb9\u7f18\u76ee\u6807"),
    ("target-lane", "target lane", "\u76ee\u6807\u8f68\u9053"),
    ("block-lane", "block lane", "\u969c\u788d\u8f68\u9053"),
    ("single-target", "single target", "\u5355\u76ee\u6807", "\u76ee\u6807\u7269"),
    ("no-obstacle", "no obstacle", "\u65e0\u969c\u788d", "\u6ca1\u6709\u969c\u788d"),
    ("fixed", "fixed block", "\u56fa\u5b9a\u969c\u788d", "\u56fa\u5b9a\u5757"),
    ("blocked", "blocked-cell", "blocked cell", "\u7981\u5165\u683c", "\u5c01\u9501\u683c"),
    ("unsolvable", "no-solution", "\u4e0d\u53ef\u89e3", "\u65e0\u89e3"),
    ("invalid", "\u4e0d\u5408\u6cd5", "\u975e\u6cd5"),
    ("create", "new puzzle", "from scratch", "\u65b0\u5efa", "\u521b\u5efa", "\u7a7a\u767d\u68cb\u76d8"),
)


@dataclass(slots=True)
class CaseEntry:
    case_id: str
    title: str
    case_type: str
    negative_kind: str | None
    status: str
    meta: dict[str, Any]
    doc_text: str
    level_preview: dict[str, Any]
    excerpt: str
    tokens: set[str]


class CaseLibraryRetriever:
    def __init__(self, library_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.library_dir = library_dir or (root / "backend" / "data" / "case-library" / "minimal")
        self._entries = self._load_entries()

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 3,
        preferred_case_type: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._entries:
            return []

        query_text = self._expand_alias_text(query)
        query_tokens = self._tokenize(query_text)
        pool = [entry for entry in self._entries if entry.status == "validated"] or list(self._entries)

        scored: list[tuple[float, CaseEntry]] = []
        for entry in pool:
            score = float(len(query_tokens.intersection(entry.tokens)))
            if preferred_case_type:
                if entry.case_type == preferred_case_type:
                    score += 2.0
                else:
                    score -= 0.75
            score += self._complexity_bonus(query_text, entry)
            if entry.status == "validated":
                score += 0.3
            if score <= 0:
                continue
            scored.append((score, entry))

        if not scored:
            fallback_pool = [entry for entry in pool if not preferred_case_type or entry.case_type == preferred_case_type] or pool
            return [self._format_hit(entry, 0.0) for entry in fallback_pool[:top_k]]

        scored.sort(key=lambda item: item[0], reverse=True)
        return [self._format_hit(entry, score) for score, entry in scored[:top_k]]

    def format_context(self, hits: Iterable[dict[str, Any]]) -> str:
        lines: list[str] = []
        for hit in hits:
            lines.append(
                (
                    f"[{hit.get('case_id', 'case')} :: {hit.get('case_type', 'case')} :: "
                    f"{hit.get('complexity', 'unknown')}] "
                    f"mechanics={', '.join(hit.get('mechanic_tags', [])[:3]) or 'none'}; "
                    f"structures={', '.join(hit.get('structure_tags', [])[:3]) or 'none'}; "
                    f"excerpt={hit.get('excerpt', '')}; "
                    f"preview={json.dumps(hit.get('level_preview', {}), ensure_ascii=False)}"
                )
            )
        return "\n\n".join(lines)

    def _load_entries(self) -> list[CaseEntry]:
        if not self.library_dir.exists():
            return []

        catalog_path = self.library_dir / "catalog.json"
        if catalog_path.exists():
            try:
                catalog = json.loads(self._read_text(catalog_path))
            except json.JSONDecodeError:
                catalog = []
        else:
            catalog = []

        entries: list[CaseEntry] = []
        for item in catalog:
            if not isinstance(item, dict):
                continue
            path = self.library_dir / str(item.get("path") or "")
            meta_path = path / "meta.json"
            level_path = path / "level.json"
            doc_path = path / "case.md"
            if not meta_path.exists() or not level_path.exists():
                continue
            try:
                meta = json.loads(self._read_text(meta_path))
                level = json.loads(self._read_text(level_path))
            except json.JSONDecodeError:
                continue
            doc_text = self._read_text(doc_path) if doc_path.exists() else ""
            level_preview = self._build_level_preview(level)
            excerpt = self._build_excerpt(meta, level_preview)
            search_text = self._build_search_text(meta, doc_text, excerpt, level_preview)
            entries.append(
                CaseEntry(
                    case_id=str(meta.get("case_id") or item.get("case_id") or path.name),
                    title=str(meta.get("title") or item.get("title") or path.name),
                    case_type=str(meta.get("case_type") or item.get("case_type") or "positive"),
                    negative_kind=(str(meta.get("negative_kind")) if meta.get("negative_kind") else item.get("negative_kind")),
                    status=str(meta.get("status") or item.get("status") or "draft"),
                    meta=meta,
                    doc_text=doc_text,
                    level_preview=level_preview,
                    excerpt=excerpt,
                    tokens=self._tokenize(search_text),
                )
            )
        return entries

    def _build_search_text(
        self,
        meta: dict[str, Any],
        doc_text: str,
        excerpt: str,
        level_preview: dict[str, Any],
    ) -> str:
        derived_terms = self._derive_level_terms(level_preview)
        parts: list[str] = [
            str(meta.get("case_id") or ""),
            str(meta.get("title") or ""),
            str(meta.get("case_type") or ""),
            str(meta.get("negative_kind") or ""),
            str((meta.get("complexity_profile") or {}).get("type") or ""),
            " ".join(str(item) for item in (meta.get("retrieval_hints") or [])),
            " ".join(str(item) for item in ((meta.get("tags") or {}).get("mechanic") or [])),
            " ".join(str(item) for item in ((meta.get("tags") or {}).get("structure") or [])),
            " ".join(str(item) for item in ((meta.get("tags") or {}).get("review") or [])),
            derived_terms,
            excerpt,
            json.dumps(level_preview, ensure_ascii=False),
            doc_text[:300],
        ]
        return self._expand_alias_text(" | ".join(part for part in parts if part))

    def _build_excerpt(self, meta: dict[str, Any], level_preview: dict[str, Any]) -> str:
        expected = meta.get("expected") or {}
        complexity = meta.get("complexity_profile") or {}
        mechanic_tags = ", ".join(((meta.get("tags") or {}).get("mechanic") or [])[:3]) or "none"
        structure_tags = ", ".join(((meta.get("tags") or {}).get("structure") or [])[:3]) or "none"
        return (
            f"case_type={meta.get('case_type', 'positive')}; "
            f"expected_valid={expected.get('valid')}; "
            f"expected_solvable={expected.get('solvable')}; "
            f"complexity={complexity.get('type', 'unknown')}; "
            f"mechanics={mechanic_tags}; "
            f"structures={structure_tags}; "
            f"board={json.dumps(level_preview.get('board_size', {}), ensure_ascii=False)}"
        )

    def _build_level_preview(self, level: dict[str, Any]) -> dict[str, Any]:
        board = level.get("board", {}) or {}
        pieces_preview = [
            {
                "typeId": piece.get("typeId"),
                "role": piece.get("role"),
                "row": piece.get("row"),
                "col": piece.get("col"),
                "w": piece.get("w"),
                "h": piece.get("h"),
                "moveRule": piece.get("moveRule"),
            }
            for piece in (level.get("pieces", []) or [])[:6]
        ]
        zones_preview = [
            {
                "templateId": zone.get("templateId"),
                "role": zone.get("role"),
                "shapeKind": zone.get("shapeKind"),
                "row": zone.get("row"),
                "col": zone.get("col"),
                "side": zone.get("side"),
                "index": zone.get("index"),
                "w": zone.get("w"),
                "h": zone.get("h"),
                "goalMode": zone.get("goalMode"),
            }
            for zone in (level.get("zones", []) or [])[:4]
        ]
        tagged_cells: list[dict[str, Any]] = []
        for row_index, row in enumerate((board.get("cells") or [])[:8]):
            for col_index, cell in enumerate((row or [])[:8]):
                tags = list((cell or {}).get("tags") or [])
                if tags:
                    tagged_cells.append({"row": row_index, "col": col_index, "tags": tags})
        return {
            "board_size": {
                "rows": board.get("rows"),
                "cols": board.get("cols"),
            },
            "pieces": pieces_preview,
            "zones": zones_preview,
            "tagged_cells": tagged_cells[:8],
        }

    def _complexity_bonus(self, query_text: str, entry: CaseEntry) -> float:
        lowered = query_text.lower()
        complexity_type = str((entry.meta.get("complexity_profile") or {}).get("type") or "")
        pieces = list((entry.level_preview or {}).get("pieces") or [])
        has_obstacle = any(piece.get("role") in {"block", "fixed"} or piece.get("typeId") in {"block", "fixed"} for piece in pieces)
        bonus = 0.0
        if any(token in lowered for token in ("simple", "easy", "\u7b80\u5355", "\u6e05\u6670")) and complexity_type == "simple":
            bonus += 1.0
        if any(token in lowered for token in ("complex", "hard", "\u590d\u6742", "\u969c\u788d", "\u8054\u52a8")) and complexity_type == "complex":
            bonus += 1.0
        if any(token in lowered for token in ("obstacle", "blocker", "\u969c\u788d", "\u6321\u4f4f")) and has_obstacle:
            bonus += 1.5
        if any(token in lowered for token in ("invalid", "\u4e0d\u5408\u6cd5")) and entry.negative_kind == "invalid":
            bonus += 1.0
        if any(token in lowered for token in ("unsolvable", "no-solution", "\u4e0d\u53ef\u89e3", "\u65e0\u89e3")) and entry.negative_kind == "unsolvable":
            bonus += 1.0
        return bonus

    def _derive_level_terms(self, level_preview: dict[str, Any]) -> str:
        terms: list[str] = []
        pieces = list(level_preview.get("pieces") or [])
        zones = list(level_preview.get("zones") or [])
        tagged_cells = list(level_preview.get("tagged_cells") or [])

        non_target_count = 0
        for piece in pieces:
            role = str(piece.get("role") or "")
            type_id = str(piece.get("typeId") or "")
            move_rule = str(piece.get("moveRule") or "")
            if role in {"block", "fixed"} or type_id in {"block", "fixed"}:
                non_target_count += 1
                terms.extend(["obstacle", "blocker", "\u969c\u788d"])
            if role == "fixed" or type_id == "fixed":
                terms.extend(["fixed", "fixed-blocker", "\u56fa\u5b9a\u969c\u788d"])
            if move_rule in {"horizontal", "vertical", "target-lane", "block-lane"}:
                terms.append(move_rule)

        if non_target_count == 0:
            terms.extend(["no-obstacle", "clean-seed", "\u65e0\u969c\u788d"])
        elif non_target_count >= 2:
            terms.extend(["dense-obstacle", "complex", "\u590d\u6742"])

        for zone in zones:
            if zone.get("role") == "goal":
                if zone.get("shapeKind") == "edge":
                    terms.extend(["edge-goal", "\u8fb9\u7f18\u7ec8\u70b9"])
                elif zone.get("shapeKind") == "rect":
                    terms.extend(["internal-goal", "\u5185\u90e8\u7ec8\u70b9"])

        for cell in tagged_cells:
            for tag in cell.get("tags") or []:
                terms.append(str(tag))

        return " ".join(dict.fromkeys(terms))

    def _read_text(self, path: Path) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")

    def _expand_alias_text(self, text: str) -> str:
        expanded_parts = [text or ""]
        lowered = (text or "").lower()
        original = text or ""
        for group in _ALIAS_GROUPS:
            if any(alias.lower() in lowered or alias in original for alias in group):
                expanded_parts.extend(group)
        return " ".join(part for part in expanded_parts if part)

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

    def _format_hit(self, entry: CaseEntry, score: float) -> dict[str, Any]:
        complexity = (entry.meta.get("complexity_profile") or {}).get("type", "unknown")
        tags = entry.meta.get("tags") or {}
        return {
            "case_id": entry.case_id,
            "title": entry.title,
            "case_type": entry.case_type,
            "negative_kind": entry.negative_kind,
            "status": entry.status,
            "complexity": complexity,
            "mechanic_tags": list(tags.get("mechanic") or []),
            "structure_tags": list(tags.get("structure") or []),
            "review_tags": list(tags.get("review") or []),
            "retrieval_hints": list(entry.meta.get("retrieval_hints") or []),
            "excerpt": entry.excerpt,
            "level_preview": entry.level_preview,
            "score": f"{score:.2f}",
        }
