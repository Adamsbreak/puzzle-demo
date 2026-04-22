from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from backend.ai.agent_common import run_tool_agent
from backend.ai.prompts import build_generator_system_prompt
from backend.ai.schemas import DesignBrief
from backend.ai.tools import create_runtime_context
from backend.services.level_service import LevelEditError, apply_level_edits, diff_levels


@dataclass(slots=True)
class GeneratorAgentOutput:
    summary: str
    expected_outcome: str
    generator_notes: list[str]
    updated_level: dict[str, Any]
    operations: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]


def generate_candidate_level(
    *,
    llm: Any,
    brief: DesignBrief,
    working_level: dict[str, Any],
    rule_pack: dict[str, Any],
    rule_context: str,
    previous_feedback: list[str],
    attempt_index: int,
) -> GeneratorAgentOutput:
    runtime_context = create_runtime_context(working_level, rule_pack)
    result = run_tool_agent(
        llm=llm,
        agent_role="generator",
        system_prompt=build_generator_system_prompt(rule_pack),
        payload={
            "attempt_index": attempt_index,
            "design_brief": brief.model_dump(mode="python", by_alias=True),
            "retrieved_rules": rule_context,
            "retrieved_cases": brief.retrieved_case_context,
            "previous_feedback": previous_feedback[-4:],
        },
        runtime_context=runtime_context,
        max_tool_rounds=6,
        final_json_hint="Return the final generator JSON now.",
    )
    payload = result.final_json or {}
    operations: list[dict[str, Any]] = []
    for item in result.tool_trace:
        if item.get("tool_name") != "apply_level_edits":
            continue
        tool_arguments = item.get("arguments") or {}
        tool_operations = tool_arguments.get("operations")
        if isinstance(tool_operations, list):
            operations.extend(tool_operations)
    updated_level = copy.deepcopy(result.current_level)
    if _needs_bootstrap(updated_level):
        bootstrap = _bootstrap_minimal_candidate(updated_level, brief, rule_pack)
        if bootstrap:
            operations.extend(bootstrap["operations"])
            updated_level = bootstrap["level"]
            result.tool_trace.append(
                {
                    "tool_name": "apply_level_edits",
                    "arguments": {"operations": bootstrap["operations"]},
                    "result": {
                        "success": True,
                        "warnings": bootstrap.get("warnings", []),
                        "diff": diff_levels(working_level, updated_level),
                        "bootstrap_seed": True,
                    },
                }
            )
    return GeneratorAgentOutput(
        summary=str(payload.get("summary") or "Generator finished the current candidate."),
        expected_outcome=str(payload.get("expected_outcome") or ""),
        generator_notes=[str(item).strip() for item in payload.get("generator_notes", []) if str(item).strip()],
        updated_level=updated_level,
        operations=operations,
        tool_trace=result.tool_trace,
    )


def _needs_bootstrap(level: dict[str, Any]) -> bool:
    pieces = list(level.get("pieces", []) or [])
    zones = list(level.get("zones", []) or [])
    has_target = any(piece.get("role") == "target" or piece.get("typeId") == "target" for piece in pieces)
    has_goal = any(zone.get("role") == "goal" or zone.get("templateId") == "goal" for zone in zones)
    return not has_target or not has_goal


def _bootstrap_minimal_candidate(
    level: dict[str, Any],
    brief: DesignBrief,
    rule_pack: dict[str, Any],
) -> dict[str, Any] | None:
    board = level.get("board", {}) or {}
    rows = int(board.get("rows") or 0)
    cols = int(board.get("cols") or 0)
    if rows <= 0 or cols <= 0:
        return None

    pieces = list(level.get("pieces", []) or [])
    zones = list(level.get("zones", []) or [])
    has_target = any(piece.get("role") == "target" or piece.get("typeId") == "target" for piece in pieces)
    has_goal = any(zone.get("role") == "goal" or zone.get("templateId") == "goal" for zone in zones)
    if has_target and has_goal:
        return None

    anchor_row = max(0, min(rows - 1, rows // 2))
    anchor_col = max(0, min(cols - 2, max(0, cols // 2 - 1)))
    operations: list[dict[str, Any]] = []

    if not has_target:
        operations.append(
            {
                "action": "add_piece",
                "piece": {
                    "typeId": "target",
                    "role": "target",
                    "name": "Seed Target",
                    "row": anchor_row,
                    "col": anchor_col,
                    "w": 1,
                    "h": 1,
                    "moveRule": "free",
                    "movable": True,
                    "color": "#bc8d16",
                },
            }
        )

    if not has_goal:
        operations.append(
            {
                "action": "add_zone",
                "zone": {
                    "templateId": "goal",
                    "role": "goal",
                    "shapeKind": "edge",
                    "side": "right",
                    "index": anchor_row,
                    "w": 1,
                    "h": 1,
                    "name": "Seed Goal",
                    "goalMode": "partial",
                    "targetFilter": {"roles": ["target"]},
                },
            }
        )

    wants_more_obstacles = "increase_difficulty" in brief.soft_targets or float(
        (brief.generation_spec or {}).get("obstacle_density_target") or 0
    ) >= 0.6
    if wants_more_obstacles:
        blocker_row = max(0, min(rows - 1, anchor_row + 1 if anchor_row + 1 < rows else anchor_row - 1))
        blocker_col = max(0, min(cols - 1, anchor_col))
        if not any(piece.get("row") == blocker_row and piece.get("col") == blocker_col for piece in pieces):
            operations.append(
                {
                    "action": "add_piece",
                    "piece": {
                        "typeId": "block",
                        "role": "block",
                        "name": "Seed Blocker",
                        "row": blocker_row,
                        "col": blocker_col,
                        "w": 1,
                        "h": 1,
                        "moveRule": "free",
                        "movable": True,
                        "color": "#d26a4c",
                    },
                }
            )

    if not operations:
        return None

    try:
        applied = apply_level_edits(level, operations, rule_pack)
    except LevelEditError:
        return None
    return {
        "operations": operations,
        "level": applied["level"],
        "warnings": applied.get("warnings", []),
    }
