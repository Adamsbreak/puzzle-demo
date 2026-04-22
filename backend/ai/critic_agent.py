from __future__ import annotations

from typing import Any

from backend.ai.agent_common import run_tool_agent
from backend.ai.prompts import build_critic_system_prompt
from backend.ai.schemas import CriticReport, DesignBrief
from backend.ai.tools import create_runtime_context
from backend.services.level_service import score_level, validate_level
from backend.services.solver_service import build_solve_summary, inspect_level


def review_candidate_level(
    *,
    llm: Any,
    brief: DesignBrief,
    original_level: dict[str, Any],
    candidate_level: dict[str, Any],
    rule_pack: dict[str, Any],
    rule_context: str,
    attempt_index: int,
) -> tuple[CriticReport, list[dict[str, Any]]]:
    runtime_context = create_runtime_context(original_level, rule_pack)
    runtime_context.current_level = candidate_level
    result = run_tool_agent(
        llm=llm,
        agent_role="critic",
        system_prompt=build_critic_system_prompt(rule_pack),
        payload={
            "attempt_index": attempt_index,
            "design_brief": brief.model_dump(mode="python", by_alias=True),
            "retrieved_rules": rule_context,
            "retrieved_cases": brief.retrieved_case_context,
        },
        runtime_context=runtime_context,
        max_tool_rounds=5,
        final_json_hint="Return the final critic JSON now.",
    )
    payload = result.final_json or {}
    fallback = _build_fallback_report(candidate_level=candidate_level, rule_pack=rule_pack)
    report = CriticReport.model_validate(
        {
            "hardPass": payload.get("hard_pass", fallback.hard_pass),
            "fitToBrief": payload.get("fit_to_brief", fallback.fit_to_brief),
            "criticScore": payload.get("critic_score", fallback.critic_score),
            "summary": payload.get("summary", fallback.summary),
            "strengths": payload.get("strengths", fallback.strengths),
            "issues": payload.get("issues", fallback.issues),
            "nextActions": payload.get("next_actions", fallback.next_actions),
        }
    )
    return report, result.tool_trace


def _build_fallback_report(*, candidate_level: dict[str, Any], rule_pack: dict[str, Any]) -> CriticReport:
    validation = validate_level(candidate_level, rule_pack)
    try:
        solve = build_solve_summary(candidate_level, inspect_level(candidate_level, rule_pack))
    except Exception:
        solve = {"solvable": False}
    score = score_level(candidate_level, rule_pack)
    hard_pass = bool(validation.get("valid")) and bool(solve.get("solvable"))
    critic_score = 7.5 if hard_pass else 4.0
    issues: list[str] = []
    if not validation.get("valid"):
        issues.extend(str(item) for item in validation.get("errors", [])[:2])
    if not solve.get("solvable"):
        issues.append("Candidate is not solvable according to the deterministic solver.")
    if not issues and len(score.get("redundant_objects", []) or []) > 1:
        issues.append("Candidate still contains some redundant pieces or zones.")
    strengths: list[str] = []
    if hard_pass:
        strengths.append("Candidate passes the deterministic legality and solver checks.")
    return CriticReport(
        hardPass=hard_pass,
        fitToBrief=hard_pass,
        criticScore=critic_score,
        summary="Fallback critic report based on deterministic validation and scoring.",
        strengths=strengths,
        issues=issues,
        nextActions=["Tighten the puzzle concept and remove redundant blockers."] if issues else [],
    )
