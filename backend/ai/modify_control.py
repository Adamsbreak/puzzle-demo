from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any

from backend.services.level_service import score_level, validate_level
from backend.services.solver_service import build_solve_summary, inspect_level


ZH_MODIFY = "\u4fee\u6539"
ZH_ADJUST = "\u8c03\u6574"
ZH_CHANGE_TO = "\u6539\u6210"
ZH_HARDER = "\u6539\u96be"
ZH_EASIER = "\u6539\u7b80\u5355"
ZH_OPTIMIZE = "\u4f18\u5316"
ZH_NO_MAP_GROW = "\u4e0d\u8981\u589e\u52a0\u5730\u56fe\u5c3a\u5bf8"
ZH_NO_MAP_GROW_ALT = "\u4e0d\u8981\u52a0\u5927\u5730\u56fe"
ZH_MORE_DIFFICULT = "\u66f4\u96be"
ZH_MORE_EASY = "\u66f4\u7b80\u5355"
ZH_EASY_A_BIT = "\u7b80\u5355\u4e00\u70b9"
ZH_TEACHING = "\u6559\u5b66\u5173"
ZH_WIND = "\u98ce"
ZH_STEP = "\u6b65"

_MODIFY_KEYWORDS = (
    "modify",
    "refine",
    "edit",
    "change",
    ZH_MODIFY,
    ZH_ADJUST,
    ZH_CHANGE_TO,
    ZH_HARDER,
    ZH_EASIER,
    ZH_OPTIMIZE,
)


@dataclass(slots=True)
class ModifyIntent:
    hard_constraints: list[str]
    soft_targets: list[str]
    target_min_steps_low: int | None = None
    target_min_steps_high: int | None = None
    requested_direction: str = "neutral"
    wants_teaching_level: bool = False
    keep_map_size: bool = False
    require_mechanic_proxy: str | None = None


@dataclass(slots=True)
class AnalysisSnapshot:
    level: dict[str, Any]
    validation: dict[str, Any]
    solve: dict[str, Any]
    score: dict[str, Any]


@dataclass(slots=True)
class ConstraintEvaluation:
    satisfied: bool
    improvement: bool
    details: dict[str, Any]


@dataclass(slots=True)
class ModifyLoopState:
    intent: ModifyIntent
    previous_snapshot: AnalysisSnapshot
    best_snapshot: AnalysisSnapshot
    max_iterations: int = 2
    edit_iterations: int = 0
    seen_operation_hashes: set[str] = field(default_factory=set)


def is_modify_request(user_request: str) -> bool:
    request_lower = user_request.lower()
    return any(keyword in request_lower for keyword in ("modify", "refine", "edit", "change")) or any(
        keyword in user_request
        for keyword in (ZH_MODIFY, ZH_ADJUST, ZH_CHANGE_TO, ZH_HARDER, ZH_EASIER, ZH_OPTIMIZE)
    )


def compile_modify_intent(user_request: str, initial_score: dict[str, Any]) -> ModifyIntent:
    request_lower = user_request.lower()
    hard_constraints = ["keep_solvable"]
    soft_targets: list[str] = []

    keep_map_size = (
        ZH_NO_MAP_GROW in user_request
        or ZH_NO_MAP_GROW_ALT in user_request
        or "same map size" in request_lower
    )
    if keep_map_size:
        hard_constraints.append("keep_map_size")

    requested_direction = "neutral"
    if any(keyword in user_request for keyword in (ZH_MORE_DIFFICULT, ZH_HARDER)) or "harder" in request_lower:
        requested_direction = "harder"
        soft_targets.append("increase_difficulty")
    elif any(keyword in user_request for keyword in (ZH_MORE_EASY, ZH_EASY_A_BIT, ZH_TEACHING)) or "easier" in request_lower:
        requested_direction = "easier"
        soft_targets.append("decrease_difficulty")

    wants_teaching_level = ZH_TEACHING in user_request or "teaching" in request_lower
    if wants_teaching_level:
        for target in ("teaching_level", "single_core_mechanic", "reduce_redundancy"):
            if target not in soft_targets:
                soft_targets.append(target)

    target_min_steps_low, target_min_steps_high = _extract_step_range(user_request)
    if target_min_steps_low is not None:
        soft_targets.append("target_step_range")

    require_mechanic_proxy = None
    if ZH_WIND in user_request or "wind" in request_lower:
        require_mechanic_proxy = "directional-lane"
        soft_targets.append("mechanic_proxy_required")

    if not soft_targets:
        current_difficulty = initial_score.get("difficulty")
        if current_difficulty == "easy":
            soft_targets.append("increase_difficulty")
            requested_direction = "harder"
        else:
            soft_targets.append("preserve_valid_improvement")

    return ModifyIntent(
        hard_constraints=hard_constraints,
        soft_targets=soft_targets,
        target_min_steps_low=target_min_steps_low,
        target_min_steps_high=target_min_steps_high,
        requested_direction=requested_direction,
        wants_teaching_level=wants_teaching_level,
        keep_map_size=keep_map_size,
        require_mechanic_proxy=require_mechanic_proxy,
    )


def build_analysis_snapshot(level: dict[str, Any], rule_pack: dict[str, Any]) -> AnalysisSnapshot:
    validation = validate_level(level, rule_pack)
    inspection = inspect_level(level, rule_pack)
    solve = build_solve_summary(level, inspection)
    score = score_level(level, rule_pack)
    return AnalysisSnapshot(
        level=copy.deepcopy(level),
        validation=validation,
        solve=solve,
        score=score,
    )


def normalize_operations(operations: list[dict[str, Any]]) -> str:
    return json.dumps(operations, ensure_ascii=False, sort_keys=True)


def evaluate_constraints(
    previous_snapshot: AnalysisSnapshot,
    current_snapshot: AnalysisSnapshot,
    intent: ModifyIntent,
    original_level: dict[str, Any],
) -> ConstraintEvaluation:
    details: dict[str, Any] = {
        "hard_constraints": {},
        "soft_targets": {},
    }
    hard_ok = True

    if "keep_solvable" in intent.hard_constraints:
        ok = bool(current_snapshot.solve.get("solvable"))
        details["hard_constraints"]["keep_solvable"] = ok
        hard_ok = hard_ok and ok

    if "keep_map_size" in intent.hard_constraints:
        original_board = original_level.get("board", {})
        current_board = current_snapshot.level.get("board", {})
        ok = (
            original_board.get("rows") == current_board.get("rows")
            and original_board.get("cols") == current_board.get("cols")
        )
        details["hard_constraints"]["keep_map_size"] = ok
        hard_ok = hard_ok and ok

    improvement = _compute_improvement(previous_snapshot, current_snapshot, intent, details)
    satisfied = hard_ok and _soft_targets_satisfied(current_snapshot, intent, details)
    return ConstraintEvaluation(satisfied=satisfied, improvement=improvement, details=details)


def _extract_step_range(user_request: str) -> tuple[int | None, int | None]:
    match = re.search(r"(\d+)\s*[-~\u301c]\s*(\d+)\s*" + ZH_STEP, user_request)
    if match:
        low = int(match.group(1))
        high = int(match.group(2))
        return min(low, high), max(low, high)
    single = re.search(r"(\d+)\s*" + ZH_STEP, user_request)
    if single:
        value = int(single.group(1))
        return value, value
    return None, None


def _difficulty_rank(value: str | None) -> int:
    mapping = {"easy": 1, "medium": 2, "hard": 3}
    return mapping.get(value or "", 0)


def _compute_improvement(
    previous_snapshot: AnalysisSnapshot,
    current_snapshot: AnalysisSnapshot,
    intent: ModifyIntent,
    details: dict[str, Any],
) -> bool:
    previous_score = previous_snapshot.score
    current_score = current_snapshot.score
    previous_difficulty = _difficulty_rank(previous_score.get("difficulty"))
    current_difficulty = _difficulty_rank(current_score.get("difficulty"))
    previous_steps = previous_snapshot.solve.get("min_steps") or 0
    current_steps = current_snapshot.solve.get("min_steps") or 0
    previous_branching = previous_score.get("branching_factor") or 0
    current_branching = current_score.get("branching_factor") or 0

    if intent.requested_direction == "harder":
        improved = (
            current_steps > previous_steps
            or current_difficulty > previous_difficulty
            or current_branching > previous_branching
        )
    elif intent.requested_direction == "easier" or intent.wants_teaching_level:
        improved = (
            current_steps < previous_steps
            or current_difficulty < previous_difficulty
            or len(current_score.get("redundant_objects", [])) < len(previous_score.get("redundant_objects", []))
            or current_branching < previous_branching
            or bool(current_score.get("teaching_signals", {}).get("estimated_teaching_level"))
        )
    elif intent.require_mechanic_proxy:
        improved = _mechanic_proxy_score(current_score) > _mechanic_proxy_score(previous_score)
    else:
        improved = current_snapshot.level != previous_snapshot.level

    details["improvement"] = {
        "previous_min_steps": previous_steps,
        "current_min_steps": current_steps,
        "previous_difficulty": previous_score.get("difficulty"),
        "current_difficulty": current_score.get("difficulty"),
        "previous_branching_factor": previous_branching,
        "current_branching_factor": current_branching,
        "improved": improved,
    }
    return improved


def _soft_targets_satisfied(
    current_snapshot: AnalysisSnapshot,
    intent: ModifyIntent,
    details: dict[str, Any],
) -> bool:
    if not intent.soft_targets:
        return True

    score = current_snapshot.score
    solve = current_snapshot.solve
    target_results: dict[str, bool] = {}

    for target in intent.soft_targets:
        if target == "target_step_range":
            min_steps = solve.get("min_steps")
            target_results[target] = (
                min_steps is not None
                and intent.target_min_steps_low is not None
                and intent.target_min_steps_high is not None
                and intent.target_min_steps_low <= min_steps <= intent.target_min_steps_high
            )
        elif target == "increase_difficulty":
            target_results[target] = score.get("difficulty") in {"medium", "hard"} and bool(solve.get("solvable"))
        elif target == "decrease_difficulty":
            target_results[target] = score.get("difficulty") in {"easy", "medium"} and bool(solve.get("solvable"))
        elif target == "teaching_level":
            target_results[target] = bool(score.get("teaching_signals", {}).get("estimated_teaching_level"))
        elif target == "single_core_mechanic":
            target_results[target] = bool(score.get("teaching_signals", {}).get("single_core_mechanic"))
        elif target == "reduce_redundancy":
            target_results[target] = len(score.get("redundant_objects", [])) <= 1
        elif target == "mechanic_proxy_required":
            target_results[target] = _mechanic_proxy_score(score) >= 0.2
        elif target == "preserve_valid_improvement":
            target_results[target] = bool(current_snapshot.validation.get("valid")) and bool(solve.get("solvable"))
        else:
            target_results[target] = False

    details["soft_targets"] = target_results
    return all(target_results.values())


def _mechanic_proxy_score(score: dict[str, Any]) -> float:
    usage = score.get("mechanic_usage", {})
    return max(
        float(usage.get("horizontal", 0.0)),
        float(usage.get("vertical", 0.0)),
        float(usage.get("target-lane", 0.0)),
        float(usage.get("edge-goal", 0.0)),
    )
