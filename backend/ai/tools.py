from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.ai.schemas import ToolTraceEntry
from backend.services.level_service import (
    LevelEditError,
    apply_level_edits,
    diff_levels,
    get_current_level,
    resolve_rule_pack,
    score_level,
    validate_level,
)
from backend.services.solver_service import build_solve_summary, inspect_level


LOGGER = logging.getLogger(__name__)

PLANNER_TOOL_NAMES = (
    "get_current_level",
    "get_rule_pack_capabilities",
)
GENERATOR_TOOL_NAMES = (
    "get_current_level",
    "get_rule_pack_capabilities",
    "validate_level",
    "solve_level",
    "score_level",
    "diff_current_level",
    "apply_level_edits",
)
CRITIC_TOOL_NAMES = (
    "get_current_level",
    "get_rule_pack_capabilities",
    "validate_level",
    "solve_level",
    "score_level",
    "diff_current_level",
)


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot complete its work."""


@dataclass(slots=True)
class ToolRuntimeContext:
    original_level: dict[str, Any]
    current_level: dict[str, Any]
    rule_pack: dict[str, Any]
    trace: list[ToolTraceEntry] = field(default_factory=list)


def tool_names(agent_role: str | None = None) -> tuple[str, ...]:
    if agent_role == "planner":
        return PLANNER_TOOL_NAMES
    if agent_role == "generator":
        return GENERATOR_TOOL_NAMES
    if agent_role == "critic":
        return CRITIC_TOOL_NAMES
    return (
        "get_current_level",
        "get_rule_pack_capabilities",
        "validate_level",
        "solve_level",
        "score_level",
        "diff_current_level",
        "apply_level_edits",
    )


def tool_schemas(agent_role: str | None = None) -> list[dict[str, Any]]:
    operation_properties = {
        "action": {
            "type": "string",
            "enum": [
                "rename_level",
                "update_piece",
                "add_piece",
                "remove_piece",
                "set_cell_tags",
                "add_zone",
                "update_zone",
                "remove_zone",
            ],
        },
        "title": {"type": "string"},
        "piece_id": {"type": "string"},
        "zone_id": {"type": "string"},
        "row": {"type": "integer"},
        "col": {"type": "integer"},
        "w": {"type": "integer"},
        "h": {"type": "integer"},
        "side": {"type": "string", "enum": ["top", "right", "bottom", "left"]},
        "index": {"type": "integer"},
        "name": {"type": "string"},
        "color": {"type": "string"},
        "goalMode": {"type": "string", "enum": ["full", "partial"]},
        "moveRule": {"type": "string", "enum": ["free", "horizontal", "vertical", "blocked", "block-lane", "target-lane"]},
        "movable": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "piece": {"type": "object"},
        "zone": {"type": "object"},
    }
    available = [
        {
            "type": "function",
            "function": {
                "name": "get_current_level",
                "description": "Get the current level and rule-pack-derived metadata. Use this first when you need full context.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "validate_level",
                "description": "Validate the current working level. Use before and after edits.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "solve_level",
                "description": "Solve the current working level. Required before making claims about solvability, min steps, or uniqueness.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "score_level",
                "description": "Analyze difficulty, branching factor, mechanic usage, redundant objects, and teaching-level signals for the current working level.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_rule_pack_capabilities",
                "description": "Return a compact summary of supported cell tags, piece types, zones, and solver behavior.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "diff_current_level",
                "description": "Compare the current working level against the original starting level.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "apply_level_edits",
                "description": "Apply a minimal list of atomic edit operations to the current working level. Never replace the full level directly.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": operation_properties,
                                "required": ["action"],
                            },
                        },
                    },
                    "required": ["operations"],
                },
            },
        },
    ]
    allowed = set(tool_names(agent_role))
    return [item for item in available if item["function"]["name"] in allowed]


def execute_tool(context: ToolRuntimeContext, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handlers: dict[str, Callable[[ToolRuntimeContext, dict[str, Any]], dict[str, Any]]] = {
        "get_current_level": _get_current_level,
        "get_rule_pack_capabilities": _get_rule_pack_capabilities,
        "validate_level": _validate_level,
        "solve_level": _solve_level,
        "score_level": _score_level,
        "diff_current_level": _diff_current_level,
        "apply_level_edits": _apply_level_edits,
    }
    if tool_name not in handlers:
        raise ToolExecutionError(f"Unsupported tool: {tool_name}")

    try:
        result = handlers[tool_name](context, arguments)
    except (LevelEditError, ValueError) as error:
        raise ToolExecutionError(str(error)) from error

    context.trace.append(ToolTraceEntry(tool_name=tool_name, arguments=arguments, result=result))
    LOGGER.info(
        "AI tool call %s args=%s result=%s",
        tool_name,
        json.dumps(arguments, ensure_ascii=False),
        json.dumps(result, ensure_ascii=False),
    )
    return result


def _get_current_level(context: ToolRuntimeContext, _: dict[str, Any]) -> dict[str, Any]:
    return get_current_level(context.current_level, context.rule_pack)


def _get_rule_pack_capabilities(context: ToolRuntimeContext, _: dict[str, Any]) -> dict[str, Any]:
    return {
        "cell_tags": [item.get("id") for item in context.rule_pack.get("cellTags", [])],
        "piece_types": [item.get("id") for item in context.rule_pack.get("pieceTypes", [])],
        "zones": [item.get("id") for item in context.rule_pack.get("zones", [])],
        "solver": copy.deepcopy(context.rule_pack.get("solver", {})),
    }


def _validate_level(context: ToolRuntimeContext, _: dict[str, Any]) -> dict[str, Any]:
    return validate_level(context.current_level, context.rule_pack)


def _solve_level(context: ToolRuntimeContext, _: dict[str, Any]) -> dict[str, Any]:
    inspection = inspect_level(context.current_level, context.rule_pack)
    return build_solve_summary(context.current_level, inspection)


def _score_level(context: ToolRuntimeContext, _: dict[str, Any]) -> dict[str, Any]:
    return score_level(context.current_level, context.rule_pack)


def _diff_current_level(context: ToolRuntimeContext, _: dict[str, Any]) -> dict[str, Any]:
    return diff_levels(context.original_level, context.current_level)


def _apply_level_edits(context: ToolRuntimeContext, arguments: dict[str, Any]) -> dict[str, Any]:
    operations = arguments.get("operations")
    result = apply_level_edits(context.current_level, operations, context.rule_pack)
    context.current_level = result["level"]
    result["diff"] = diff_levels(context.original_level, context.current_level)
    return result


def create_runtime_context(level: dict[str, Any], rule_pack: dict[str, Any] | None) -> ToolRuntimeContext:
    return ToolRuntimeContext(
        original_level=copy.deepcopy(level),
        current_level=copy.deepcopy(level),
        rule_pack=resolve_rule_pack(rule_pack),
    )
