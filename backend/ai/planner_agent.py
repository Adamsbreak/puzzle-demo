from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.ai.agent_common import ToolAgentResult, run_tool_agent
from backend.ai.case_rag import CaseLibraryRetriever
from backend.ai.modify_control import compile_modify_intent
from backend.ai.prompts import build_planner_system_prompt
from backend.ai.rules_rag import LocalRuleRetriever
from backend.ai.schemas import DesignBrief
from backend.ai.tools import create_runtime_context
from backend.services.level_service import score_level


@dataclass(slots=True)
class PlannerAgentOutput:
    brief: DesignBrief
    rule_context: str
    rule_hits: list[dict[str, str]]
    case_context: str
    case_hits: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]


def plan_design_brief(
    *,
    llm: Any,
    rule_retriever: LocalRuleRetriever,
    case_retriever: CaseLibraryRetriever,
    user_request: str,
    working_level: dict[str, Any],
    rule_pack: dict[str, Any],
    session_context: dict[str, Any],
) -> PlannerAgentOutput:
    rule_hits, rule_context = _retrieve_rule_grounding(
        rule_retriever=rule_retriever,
        user_request=user_request,
        rule_pack=rule_pack,
        session_context=session_context,
    )
    case_hits, case_context = _retrieve_case_grounding(
        case_retriever=case_retriever,
        user_request=user_request,
        working_level=working_level,
        session_context=session_context,
    )
    runtime_context = create_runtime_context(working_level, rule_pack)
    tool_result = run_tool_agent(
        llm=llm,
        agent_role="planner",
        system_prompt=build_planner_system_prompt(rule_pack),
        payload={
            "user_request": user_request,
            "session_context": {
                "last_intent": session_context.get("last_intent", {}),
                "analysis_summary": session_context.get("analysis_summary", {}),
                "suggestions": session_context.get("suggestions", []),
            },
            "retrieved_rules": rule_context,
            "retrieved_cases": case_context,
            "current_level_hint": {
                "board": working_level.get("board", {}),
                "piece_count": len(working_level.get("pieces", []) or []),
                "zone_count": len(working_level.get("zones", []) or []),
            },
        },
        runtime_context=runtime_context,
        max_tool_rounds=4,
        final_json_hint="Return the final design brief JSON now.",
    )
    brief = _build_brief(
        user_request=user_request,
        working_level=working_level,
        rule_pack=rule_pack,
        rule_context=rule_context,
        rule_hits=rule_hits,
        case_context=case_context,
        case_hits=case_hits,
        tool_result=tool_result,
    )
    planner_trace = list(tool_result.tool_trace)
    planner_trace.append(
        {
            "tool_name": "retrieve_rule_docs",
            "arguments": {"query": user_request},
            "result": {"hits": rule_hits},
        }
    )
    planner_trace.append(
        {
            "tool_name": "retrieve_case_library",
            "arguments": {"query": user_request},
            "result": {"hits": case_hits},
        }
    )
    return PlannerAgentOutput(
        brief=brief,
        rule_context=rule_context,
        rule_hits=rule_hits,
        case_context=case_context,
        case_hits=case_hits,
        tool_trace=planner_trace,
    )


def _retrieve_rule_grounding(
    *,
    rule_retriever: LocalRuleRetriever,
    user_request: str,
    rule_pack: dict[str, Any],
    session_context: dict[str, Any],
) -> tuple[list[dict[str, str]], str]:
    query_parts = [
        user_request,
        str((session_context.get("last_intent") or {}).get("raw_user_text") or ""),
        " ".join((session_context.get("suggestions") or [])[:2]),
        json.dumps(rule_pack.get("solver", {}), ensure_ascii=False),
    ]
    query = " | ".join(part for part in query_parts if part)
    hits = rule_retriever.retrieve(query, top_k=4)
    return hits, rule_retriever.format_context(hits)


def _retrieve_case_grounding(
    *,
    case_retriever: CaseLibraryRetriever,
    user_request: str,
    working_level: dict[str, Any],
    session_context: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    query_parts = [
        user_request,
        str((session_context.get("last_intent") or {}).get("raw_user_text") or ""),
        " ".join((session_context.get("suggestions") or [])[:2]),
    ]
    pieces = list(working_level.get("pieces", []) or [])
    zones = list(working_level.get("zones", []) or [])
    if not pieces or not zones:
        query_parts.append("create blank board seed")

    request_lower = user_request.lower()
    prefers_negative = (
        "invalid" in request_lower
        or "unsolvable" in request_lower
        or "\u4e0d\u53ef\u89e3" in user_request
        or "\u65e0\u89e3" in user_request
        or "\u4e0d\u5408\u6cd5" in user_request
    )
    query = " | ".join(part for part in query_parts if part)

    positive_hits = case_retriever.retrieve(query, top_k=3, preferred_case_type="positive")
    if prefers_negative:
        negative_hits = case_retriever.retrieve(query, top_k=2, preferred_case_type="negative")
        return negative_hits, case_retriever.format_context(negative_hits)

    negative_hits = case_retriever.retrieve(query, top_k=1, preferred_case_type="negative")
    combined_hits = list(positive_hits) + list(negative_hits)
    return combined_hits, case_retriever.format_context(combined_hits)


def _build_brief(
    *,
    user_request: str,
    working_level: dict[str, Any],
    rule_pack: dict[str, Any],
    rule_context: str,
    rule_hits: list[dict[str, str]],
    case_context: str,
    case_hits: list[dict[str, Any]],
    tool_result: ToolAgentResult,
) -> DesignBrief:
    brief_json = tool_result.final_json or {}
    fallback = _build_fallback_brief(user_request=user_request, working_level=working_level, rule_pack=rule_pack)
    payload = {
        "intent_type": brief_json.get("intent_type") or fallback.intent_type,
        "raw_user_text": user_request,
        "design_goal": str(brief_json.get("design_goal") or fallback.design_goal or user_request),
        "design_summary": str(brief_json.get("design_summary") or fallback.design_summary or ""),
        "generation_strategy": brief_json.get("generation_strategy") or fallback.generation_strategy,
        "board_constraints": brief_json.get("board_constraints") or fallback.board_constraints,
        "difficulty_target": brief_json.get("difficulty_target") or fallback.difficulty_target,
        "hard_constraints": list(brief_json.get("hard_constraints") or fallback.hard_constraints),
        "soft_targets": list(brief_json.get("soft_targets") or fallback.soft_targets),
        "player_experience_goals": list(
            brief_json.get("player_experience_goals") or fallback.player_experience_goals
        ),
        "generationSpec": brief_json.get("generation_spec") or fallback.generation_spec,
        "mechanic_notes": list(brief_json.get("mechanic_notes") or fallback.mechanic_notes),
        "planner_notes": list(brief_json.get("planner_notes") or fallback.planner_notes),
        "retrievedRuleContext": rule_context,
        "retrievedRuleHits": rule_hits,
        "retrievedCaseContext": case_context,
        "retrievedCaseHits": case_hits,
        "acceptanceRubric": brief_json.get("acceptance_rubric") or fallback.acceptance_rubric,
        "reviewRubric": brief_json.get("review_rubric") or fallback.review_rubric,
    }
    return DesignBrief.model_validate(payload)


def _build_fallback_brief(
    *,
    user_request: str,
    working_level: dict[str, Any],
    rule_pack: dict[str, Any],
) -> DesignBrief:
    baseline_score = score_level(working_level, rule_pack)
    heuristic = compile_modify_intent(user_request, baseline_score)
    pieces = list(working_level.get("pieces", []) or [])
    zones = list(working_level.get("zones", []) or [])
    strategy = "refine_current_level"
    request_lower = user_request.lower()
    is_empty_board = not pieces or not zones
    create_keywords = (
        "\u521b\u5efa",
        "\u65b0\u5efa",
        "\u751f\u6210\u4e00\u4e2a\u65b0",
        "\u4ece\u5934",
        "\u7a7a\u767d",
        "create",
        "new puzzle",
        "fresh level",
        "from scratch",
        "blank board",
    )
    intent_type = "modify"
    if is_empty_board or any(keyword in request_lower or keyword in user_request for keyword in create_keywords):
        intent_type = "create"
    if not pieces or not zones:
        strategy = "bootstrap_from_empty"

    mechanic_notes: list[str] = []
    if heuristic.require_mechanic_proxy:
        mechanic_notes.append(
            f"Requested mechanic is not literal in this rule pack; use proxy `{heuristic.require_mechanic_proxy}`."
        )

    difficulty_target: dict[str, Any] = {}
    if heuristic.requested_direction == "harder":
        difficulty_target["level"] = "hard"
    elif heuristic.requested_direction == "easier" or heuristic.wants_teaching_level:
        difficulty_target["level"] = "easy"
    if heuristic.target_min_steps_low is not None:
        difficulty_target["min_steps_low"] = heuristic.target_min_steps_low
        difficulty_target["min_steps_high"] = heuristic.target_min_steps_high

    player_goals = ["respect current rule-pack"]
    design_summary = "Produce a grounded puzzle brief that matches the user's request."
    generation_spec: dict[str, Any] = {
        "difficulty_direction": heuristic.requested_direction,
        "keep_map_size": heuristic.keep_map_size,
        "bootstrap_from_empty": strategy == "bootstrap_from_empty",
    }
    review_rubric: dict[str, Any] = {
        "must_be_solvable": True,
        "require_teaching_level": heuristic.wants_teaching_level,
        "prefer_higher_branching": heuristic.requested_direction == "harder",
        "allow_more_obstacles": "increase_difficulty" in heuristic.soft_targets,
        "penalize_redundancy_aggressively": heuristic.wants_teaching_level,
    }
    if heuristic.wants_teaching_level:
        player_goals.extend(["one clear puzzle concept", "one clear first move", "low redundancy"])
        design_summary = "Shape the level as a readable teaching puzzle with a clear first move."
    elif heuristic.requested_direction == "harder":
        player_goals.extend(["more intricate decisions", "higher pressure from blockers", "still readable"])
        design_summary = "Increase challenge and path pressure while keeping the level solvable."
        generation_spec["complexity_target"] = 0.75
        generation_spec["obstacle_density_target"] = 0.7
    elif heuristic.requested_direction == "easier":
        player_goals.extend(["fewer distractions", "clear core mechanic"])
        design_summary = "Reduce difficulty and improve readability without breaking the core puzzle idea."
        generation_spec["complexity_target"] = 0.35
        generation_spec["obstacle_density_target"] = 0.3
    else:
        player_goals.extend(["one clear puzzle concept", "stable player readability"])
    if intent_type == "create":
        generation_spec["bootstrap_from_empty"] = True
        generation_spec["preferred_seed"] = "create_playable_core"
        design_summary = (
            "Create a fresh playable puzzle from an empty or incomplete board, then shape it toward the user's goal."
        )

    return DesignBrief(
        intent_type=intent_type,
        raw_user_text=user_request,
        design_goal=user_request,
        designSummary=design_summary,
        generation_strategy=strategy,
        board_constraints={
            "keep_map_size": heuristic.keep_map_size,
            "allow_resize": not heuristic.keep_map_size,
        },
        difficulty_target=difficulty_target,
        hard_constraints=heuristic.hard_constraints,
        soft_targets=heuristic.soft_targets,
        player_experience_goals=player_goals,
        generationSpec=generation_spec,
        mechanic_notes=mechanic_notes,
        planner_notes=["Fallback planner brief was derived from heuristic intent compilation."],
        acceptanceRubric={"critic_min_score": 8.0, "must_be_solvable": True},
        reviewRubric=review_rubric,
    )
