from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from backend.ai.schemas import DEFAULT_RULE_PACK
from backend.services.solver_service import build_solve_summary, inspect_level


class LevelEditError(ValueError):
    """Raised when an edit operation is invalid."""


@dataclass(slots=True)
class RulePackIndexes:
    cell_tags: set[str]
    piece_types: dict[str, dict[str, Any]]
    zone_templates: dict[str, dict[str, Any]]


def clone_level(level: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(level)


def resolve_rule_pack(rule_pack: dict[str, Any] | None) -> dict[str, Any]:
    return copy.deepcopy(rule_pack or DEFAULT_RULE_PACK)


def build_rulepack_indexes(rule_pack: dict[str, Any]) -> RulePackIndexes:
    return RulePackIndexes(
        cell_tags={item["id"] for item in rule_pack.get("cellTags", [])},
        piece_types={item["id"]: item for item in rule_pack.get("pieceTypes", [])},
        zone_templates={item["id"]: item for item in rule_pack.get("zones", [])},
    )


def get_current_level(level: dict[str, Any], rule_pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "level": clone_level(level),
        "rule_pack_id": rule_pack.get("id"),
        "board_size": {
            "rows": level.get("board", {}).get("rows"),
            "cols": level.get("board", {}).get("cols"),
        },
        "piece_count": len(level.get("pieces", [])),
        "zone_count": len(level.get("zones", [])),
        "supported_cell_tags": sorted(build_rulepack_indexes(rule_pack).cell_tags),
        "note": "Current level comes from the frontend request payload, not from mutable global state.",
    }


def validate_level(level: dict[str, Any], rule_pack: dict[str, Any]) -> dict[str, Any]:
    indexes = build_rulepack_indexes(rule_pack)
    errors: list[str] = []
    warnings: list[str] = []

    board = level.get("board") or {}
    rows = board.get("rows")
    cols = board.get("cols")
    board_rows = rows if isinstance(rows, int) and rows > 0 else 0
    board_cols = cols if isinstance(cols, int) and cols > 0 else 0
    cells = board.get("cells")
    if not isinstance(rows, int) or not isinstance(cols, int) or rows <= 0 or cols <= 0:
        errors.append("Board rows/cols must be positive integers.")
    if not isinstance(cells, list) or len(cells) != rows:
        errors.append("Board cells shape does not match board.rows.")
    else:
        for row_index, row in enumerate(cells):
            if not isinstance(row, list) or len(row) != cols:
                errors.append(f"Board row {row_index} does not match board.cols.")
                continue
            for col_index, cell in enumerate(row):
                tags = (cell or {}).get("tags", [])
                unknown = [tag for tag in tags if tag != "free" and tag not in indexes.cell_tags]
                if unknown:
                    errors.append(f"Cell ({row_index}, {col_index}) has unknown tags: {unknown}.")

    pieces = level.get("pieces", [])
    piece_ids = set()
    occupied: dict[tuple[int, int], str] = {}
    for piece in pieces:
        piece_id = piece.get("id")
        if not piece_id:
            errors.append("Each piece must have an id.")
            continue
        if piece_id in piece_ids:
            errors.append(f"Duplicate piece id: {piece_id}.")
        piece_ids.add(piece_id)

        type_id = piece.get("typeId")
        if type_id not in indexes.piece_types:
            errors.append(f"Piece {piece_id} uses unknown typeId: {type_id}.")

        row = piece.get("row")
        col = piece.get("col")
        width = piece.get("w")
        height = piece.get("h")
        if not all(isinstance(value, int) for value in [row, col, width, height]):
            errors.append(f"Piece {piece_id} must have integer row/col/w/h.")
            continue
        if width <= 0 or height <= 0:
            errors.append(f"Piece {piece_id} must have positive size.")
            continue
        if row < 0 or col < 0 or row + height > board_rows or col + width > board_cols:
            errors.append(f"Piece {piece_id} is out of board bounds.")
            continue

        for current_row in range(row, row + height):
            for current_col in range(col, col + width):
                slot = (current_row, current_col)
                if slot in occupied:
                    errors.append(
                        f"Piece {piece_id} overlaps with {occupied[slot]} at ({current_row}, {current_col})."
                    )
                occupied[slot] = piece_id

    zones = level.get("zones", [])
    zone_ids = set()
    for zone in zones:
        zone_id = zone.get("id")
        if not zone_id:
            errors.append("Each zone must have an id.")
            continue
        if zone_id in zone_ids:
            errors.append(f"Duplicate zone id: {zone_id}.")
        zone_ids.add(zone_id)

        shape_kind = zone.get("shapeKind")
        if shape_kind not in {"rect", "edge"}:
            errors.append(f"Zone {zone_id} has invalid shapeKind: {shape_kind}.")
            continue

        if zone.get("templateId") and zone["templateId"] not in indexes.zone_templates:
            errors.append(f"Zone {zone_id} uses unknown templateId: {zone['templateId']}.")

        if shape_kind == "rect":
            row = zone.get("row")
            col = zone.get("col")
            width = zone.get("w")
            height = zone.get("h")
            if not all(isinstance(value, int) for value in [row, col, width, height]):
                errors.append(f"Zone {zone_id} must have integer row/col/w/h.")
                continue
            if row < 0 or col < 0 or width <= 0 or height <= 0 or row + height > board_rows or col + width > board_cols:
                errors.append(f"Rect zone {zone_id} is out of board bounds.")
        else:
            side = zone.get("side")
            index = zone.get("index")
            width = zone.get("w")
            height = zone.get("h")
            if side not in {"top", "right", "bottom", "left"}:
                errors.append(f"Edge zone {zone_id} has invalid side: {side}.")
                continue
            if not all(isinstance(value, int) for value in [index, width, height]):
                errors.append(f"Edge zone {zone_id} must have integer index/w/h.")
                continue
            span = width if side in {"top", "bottom"} else height
            max_span = board_cols if side in {"top", "bottom"} else board_rows
            if index < 0 or span <= 0 or index + span > max_span:
                errors.append(f"Edge zone {zone_id} exceeds board edge span.")

    try:
        tool_validation = inspect_level(level, rule_pack).get("validation", {})
    except Exception as error:
        tool_validation = {}
        warnings.append(f"Tool-side validation could not run cleanly: {error}")
    for finding in tool_validation.get("findings", []):
        if finding not in errors:
            warnings.append(finding)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def score_level(level: dict[str, Any], rule_pack: dict[str, Any]) -> dict[str, Any]:
    validation = validate_level(level, rule_pack)
    try:
        inspection = inspect_level(level, rule_pack)
        solve_summary = build_solve_summary(level, inspection)
    except Exception as error:
        return {
            "difficulty": "hard",
            "branching_factor": 0,
            "redundant_objects": [],
            "mechanic_usage": {},
            "teaching_signals": {
                "dominant_mechanic": None,
                "single_core_mechanic": False,
                "estimated_teaching_level": False,
            },
            "warnings": validation["warnings"] + [f"Scoring tool could not run cleanly: {error}"],
        }
    mechanics = inspection.get("mechanics", {})
    frontier = inspection.get("frontier", {})
    cell_tag_counts = mechanics.get("cellTagCounts", {})
    total_cells = max(1, mechanics.get("totalCells", 1))
    base_steps = solve_summary.get("min_steps") or 0
    branching_factor = frontier.get("initialMoveCount", 0)
    redundant_objects = _find_redundant_pieces(level, rule_pack, solve_summary)
    mechanic_usage = {
        key: round(value / total_cells, 3)
        for key, value in cell_tag_counts.items()
        if value
    }
    zone_mechanics = mechanics.get("zoneMechanics", {})
    if zone_mechanics.get("edgeGoalZones"):
        mechanic_usage["edge-goal"] = round(zone_mechanics["edgeGoalZones"] / max(1, len(level.get("zones", []))), 3)

    active_mechanics = sorted(mechanic_usage, key=mechanic_usage.get, reverse=True)
    dominant_mechanic = active_mechanics[0] if active_mechanics else None
    estimated_teaching_level = bool(
        validation["valid"]
        and solve_summary["solvable"]
        and base_steps <= 10
        and branching_factor <= 5
        and len(redundant_objects) <= 1
        and dominant_mechanic is not None
    )

    difficulty_score = base_steps + min(branching_factor, 6)
    if solve_summary.get("unique_solution"):
        difficulty_score += 2
    if len(redundant_objects) == 0:
        difficulty_score += 1
    if not solve_summary["solvable"] or not validation["valid"]:
        difficulty = "hard"
    elif difficulty_score <= 7:
        difficulty = "easy"
    elif difficulty_score <= 13:
        difficulty = "medium"
    else:
        difficulty = "hard"

    return {
        "difficulty": difficulty,
        "branching_factor": branching_factor,
        "redundant_objects": redundant_objects,
        "mechanic_usage": mechanic_usage,
        "teaching_signals": {
            "dominant_mechanic": dominant_mechanic,
            "single_core_mechanic": len(active_mechanics[:2]) <= 1 or (
                len(active_mechanics) > 1 and mechanic_usage[active_mechanics[0]] >= mechanic_usage[active_mechanics[1]] * 1.5
            ),
            "estimated_teaching_level": estimated_teaching_level,
        },
        "warnings": validation["warnings"],
    }


def apply_level_edits(
    level: dict[str, Any],
    operations: list[dict[str, Any]],
    rule_pack: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(operations, list) or not operations:
        raise LevelEditError("operations must be a non-empty list.")

    indexes = build_rulepack_indexes(rule_pack)
    updated = clone_level(level)
    warnings: list[str] = []

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise LevelEditError(f"Operation #{index + 1} must be an object.")
        action = operation.get("action")
        if action == "rename_level":
            title = operation.get("title")
            if not isinstance(title, str) or not title.strip():
                raise LevelEditError("rename_level requires a non-empty title.")
            updated.setdefault("meta", {})["title"] = title.strip()
        elif action == "update_piece":
            _update_piece(updated, operation, indexes)
        elif action == "add_piece":
            _add_piece(updated, operation, indexes)
        elif action == "remove_piece":
            _remove_by_id(updated["pieces"], operation.get("piece_id"), "piece")
        elif action == "set_cell_tags":
            _set_cell_tags(updated, operation, indexes)
        elif action == "add_zone":
            _add_zone(updated, operation, indexes)
        elif action == "update_zone":
            _update_zone(updated, operation, indexes)
        elif action == "remove_zone":
            _remove_by_id(updated["zones"], operation.get("zone_id"), "zone")
        else:
            raise LevelEditError(f"Unsupported action at operation #{index + 1}: {action}.")

    validation = validate_level(updated, rule_pack)
    warnings.extend(validation["warnings"])
    if not validation["valid"]:
        raise LevelEditError("Edited level is invalid: " + "; ".join(validation["errors"]))

    return {
        "success": True,
        "level": updated,
        "warnings": warnings,
    }


def diff_levels(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_pieces = {item["id"]: item for item in before.get("pieces", [])}
    after_pieces = {item["id"]: item for item in after.get("pieces", [])}
    before_zones = {item["id"]: item for item in before.get("zones", [])}
    after_zones = {item["id"]: item for item in after.get("zones", [])}
    cell_changes: list[dict[str, Any]] = []

    before_cells = before.get("board", {}).get("cells", [])
    after_cells = after.get("board", {}).get("cells", [])
    for row_index, row in enumerate(after_cells):
        for col_index, cell in enumerate(row):
            before_tags = sorted((before_cells[row_index][col_index] if row_index < len(before_cells) and col_index < len(before_cells[row_index]) else {}).get("tags", []))
            after_tags = sorted((cell or {}).get("tags", []))
            if before_tags != after_tags:
                cell_changes.append(
                    {
                        "row": row_index,
                        "col": col_index,
                        "before": before_tags,
                        "after": after_tags,
                    }
                )

    return {
        "title_changed": (before.get("meta", {}) or {}).get("title") != (after.get("meta", {}) or {}).get("title"),
        "pieces_added": sorted(set(after_pieces) - set(before_pieces)),
        "pieces_removed": sorted(set(before_pieces) - set(after_pieces)),
        "pieces_updated": sorted(
            piece_id
            for piece_id in set(after_pieces).intersection(before_pieces)
            if before_pieces[piece_id] != after_pieces[piece_id]
        ),
        "zones_added": sorted(set(after_zones) - set(before_zones)),
        "zones_removed": sorted(set(before_zones) - set(after_zones)),
        "zones_updated": sorted(
            zone_id
            for zone_id in set(after_zones).intersection(before_zones)
            if before_zones[zone_id] != after_zones[zone_id]
        ),
        "cell_changes": cell_changes[:30],
    }


def _find_redundant_pieces(
    level: dict[str, Any],
    rule_pack: dict[str, Any],
    solve_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    if not solve_summary.get("solvable"):
        return []
    base_steps = solve_summary.get("min_steps")
    moved_piece_ids = {step.get("pieceId") for step in solve_summary.get("raw_steps", [])}
    candidates = [
        piece
        for piece in level.get("pieces", [])
        if piece.get("role") != "target" and piece.get("id") not in moved_piece_ids
    ][:6]
    redundant: list[dict[str, Any]] = []
    for piece in candidates:
        trial = clone_level(level)
        trial["pieces"] = [item for item in trial["pieces"] if item.get("id") != piece.get("id")]
        validation = validate_level(trial, rule_pack)
        if not validation["valid"]:
            continue
        solve = build_solve_summary(trial, inspect_level(trial, rule_pack))
        if solve["solvable"] and (base_steps is None or solve.get("min_steps") is None or solve["min_steps"] <= base_steps):
            redundant.append(
                {
                    "type": "piece",
                    "id": piece["id"],
                    "reason": "Removing this piece keeps the level solvable without increasing the minimum steps.",
                }
            )
    return redundant


def _get_piece(level: dict[str, Any], piece_id: str) -> dict[str, Any]:
    for piece in level.get("pieces", []):
        if piece.get("id") == piece_id:
            return piece
    raise LevelEditError(f"Unknown piece id: {piece_id}.")


def _get_zone(level: dict[str, Any], zone_id: str) -> dict[str, Any]:
    for zone in level.get("zones", []):
        if zone.get("id") == zone_id:
            return zone
    raise LevelEditError(f"Unknown zone id: {zone_id}.")


def _remove_by_id(collection: list[dict[str, Any]], item_id: str | None, item_type: str) -> None:
    if not item_id:
        raise LevelEditError(f"remove_{item_type} requires {item_type}_id.")
    for index, item in enumerate(collection):
        if item.get("id") == item_id:
            collection.pop(index)
            return
    raise LevelEditError(f"Unknown {item_type} id: {item_id}.")


def _set_cell_tags(level: dict[str, Any], operation: dict[str, Any], indexes: RulePackIndexes) -> None:
    row = operation.get("row")
    col = operation.get("col")
    tags = operation.get("tags")
    if not isinstance(row, int) or not isinstance(col, int):
        raise LevelEditError("set_cell_tags requires integer row and col.")
    if not isinstance(tags, list):
        raise LevelEditError("set_cell_tags requires a tags array.")
    unknown = [tag for tag in tags if tag != "free" and tag not in indexes.cell_tags]
    if unknown:
        raise LevelEditError(f"set_cell_tags uses unknown tags: {unknown}.")
    cells = level.get("board", {}).get("cells", [])
    if row < 0 or col < 0 or row >= len(cells) or col >= len(cells[row]):
        raise LevelEditError("set_cell_tags targets a cell outside the board.")
    normalized = []
    for tag in tags:
        if tag == "free":
            continue
        if tag not in normalized:
            normalized.append(tag)
    if "blocked" in normalized:
        normalized = ["blocked"]
    cells[row][col]["tags"] = normalized


def _update_piece(level: dict[str, Any], operation: dict[str, Any], indexes: RulePackIndexes) -> None:
    piece = _get_piece(level, operation.get("piece_id"))
    allowed_fields = {"row", "col", "w", "h", "name", "color", "moveRule", "movable"}
    for key in operation:
        if key not in {"action", "piece_id"} and key not in allowed_fields:
            raise LevelEditError(f"update_piece does not allow field: {key}.")
    for key in allowed_fields:
        if key in operation:
            piece[key] = operation[key]
    if piece.get("typeId") not in indexes.piece_types:
        raise LevelEditError(f"update_piece refers to unknown typeId on piece {piece.get('id')}.")


def _add_piece(level: dict[str, Any], operation: dict[str, Any], indexes: RulePackIndexes) -> None:
    piece = operation.get("piece")
    if not isinstance(piece, dict):
        raise LevelEditError("add_piece requires a piece object.")
    type_id = piece.get("typeId")
    if type_id not in indexes.piece_types:
        raise LevelEditError(f"add_piece uses unknown typeId: {type_id}.")
    template = indexes.piece_types[type_id]
    next_id = piece.get("id") or _next_identifier("piece", level.get("pieces", []))
    new_piece = {
        "id": next_id,
        "name": piece.get("name") or f"{template.get('label', type_id)} {len(level.get('pieces', [])) + 1}",
        "typeId": type_id,
        "role": piece.get("role", template.get("role")),
        "row": piece.get("row"),
        "col": piece.get("col"),
        "w": piece.get("w", (template.get("defaultSize") or {}).get("w", 1)),
        "h": piece.get("h", (template.get("defaultSize") or {}).get("h", 1)),
        "moveRule": piece.get("moveRule", template.get("moveRule", "free")),
        "movable": piece.get("movable", template.get("movable", True)),
        "color": piece.get("color", template.get("defaultColor")),
        "metadata": piece.get("metadata", {}),
    }
    level.setdefault("pieces", []).append(new_piece)


def _add_zone(level: dict[str, Any], operation: dict[str, Any], indexes: RulePackIndexes) -> None:
    zone = operation.get("zone")
    if not isinstance(zone, dict):
        raise LevelEditError("add_zone requires a zone object.")
    template_id = zone.get("templateId", "goal")
    if template_id not in indexes.zone_templates:
        raise LevelEditError(f"add_zone uses unknown templateId: {template_id}.")
    template = indexes.zone_templates[template_id]
    shape_kind = zone.get("shapeKind", template.get("allowedShapes", ["rect"])[0])
    if shape_kind not in set(template.get("allowedShapes", [])):
        raise LevelEditError(f"Zone template {template_id} does not allow shapeKind {shape_kind}.")
    next_id = zone.get("id") or _next_identifier("zone", level.get("zones", []))
    new_zone = {
        "id": next_id,
        "templateId": template_id,
        "name": zone.get("name") or f"{template.get('label', template_id)} {len(level.get('zones', [])) + 1}",
        "role": zone.get("role", template.get("role")),
        "shapeKind": shape_kind,
        "row": zone.get("row", 0),
        "col": zone.get("col", 0),
        "side": zone.get("side", "right"),
        "index": zone.get("index", 0),
        "w": zone.get("w", 1),
        "h": zone.get("h", 1),
        "color": zone.get("color", (template.get("style") or {}).get("color")),
        "goalMode": zone.get("goalMode", template.get("goalMode", "full")),
        "targetFilter": zone.get("targetFilter", copy.deepcopy(template.get("targetFilter"))),
    }
    level.setdefault("zones", []).append(new_zone)


def _update_zone(level: dict[str, Any], operation: dict[str, Any], indexes: RulePackIndexes) -> None:
    zone = _get_zone(level, operation.get("zone_id"))
    allowed_fields = {"row", "col", "w", "h", "side", "index", "name", "color", "goalMode"}
    for key in operation:
        if key not in {"action", "zone_id"} and key not in allowed_fields:
            raise LevelEditError(f"update_zone does not allow field: {key}.")
    for key in allowed_fields:
        if key in operation:
            zone[key] = operation[key]
    if zone.get("templateId") and zone["templateId"] not in indexes.zone_templates:
        raise LevelEditError(f"update_zone refers to unknown templateId on zone {zone.get('id')}.")


def _next_identifier(prefix: str, collection: list[dict[str, Any]]) -> str:
    used = {item.get("id") for item in collection}
    index = 1
    while f"{prefix}-{index}" in used:
        index += 1
    return f"{prefix}-{index}"
