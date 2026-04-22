from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.ai.critic_agent import review_candidate_level
from backend.ai.generator_agent import generate_candidate_level
from backend.ai.modify_control import (
    AnalysisSnapshot,
    ModifyIntent,
    build_analysis_snapshot,
    evaluate_constraints,
)
from backend.ai.schemas import ControllerDecision, CriticReport, DesignBrief
from backend.services.level_service import diff_levels


@dataclass(slots=True)
class ControllerLoopResult:
    status: str
    message: str
    updated_level: dict[str, Any] | None
    analysis: dict[str, Any] | None
    warnings: list[str]
    attempts: list[dict[str, Any]]
    operations: list[dict[str, Any]]
    critic_report: CriticReport | None
    controller_decision: ControllerDecision


def run_generation_controller(
    *,
    llm: Any,
    brief: DesignBrief,
    working_level: dict[str, Any],
    rule_pack: dict[str, Any],
    rule_context: str,
    max_attempts: int,
    critic_threshold: float | None = None,
    progress_callback: Any | None = None,
) -> ControllerLoopResult:
    baseline_snapshot = _safe_build_snapshot(working_level, rule_pack)
    intent = _brief_to_modify_intent(brief)
    threshold = float(critic_threshold if critic_threshold is not None else brief.acceptance_rubric.get("critic_min_score", 8.0))
    attempts: list[dict[str, Any]] = []
    previous_feedback: list[str] = []
    best_attempt: dict[str, Any] | None = None

    def emit(stage: str, message: str, **extra: Any) -> None:
        if progress_callback:
            progress_callback({"stage": stage, "message": message, **extra})

    for attempt_index in range(1, max_attempts + 1):
        emit("generator", f"Planner brief ready. Generating candidate {attempt_index}/{max_attempts}...", attempt=attempt_index)
        generator_output = generate_candidate_level(
            llm=llm,
            brief=brief,
            working_level=working_level,
            rule_pack=rule_pack,
            rule_context=rule_context,
            previous_feedback=previous_feedback,
            attempt_index=attempt_index,
        )

        candidate_level = generator_output.updated_level
        candidate_snapshot = _safe_build_snapshot(candidate_level, rule_pack)
        constraint_eval = evaluate_constraints(
            baseline_snapshot,
            candidate_snapshot,
            intent,
            working_level,
        )

        emit("critic", "Reviewing the candidate board with deterministic tools and the critic agent...", attempt=attempt_index)
        critic_report, critic_trace = review_candidate_level(
            llm=llm,
            brief=brief,
            original_level=working_level,
            candidate_level=candidate_level,
            rule_pack=rule_pack,
            rule_context=rule_context,
            attempt_index=attempt_index,
        )

        diff = diff_levels(working_level, candidate_level)
        changed = diff != {
            "title_changed": False,
            "pieces_added": [],
            "pieces_removed": [],
            "pieces_updated": [],
            "zones_added": [],
            "zones_removed": [],
            "zones_updated": [],
            "cell_changes": [],
        }
        attempted_edit = bool(generator_output.operations)
        combined_score = _combined_score(constraint_eval, critic_report, changed)
        accepted = (
            attempted_edit
            and changed
            and constraint_eval.satisfied
            and constraint_eval.improvement
            and critic_report.hard_pass
            and critic_report.fit_to_brief
            and critic_report.critic_score >= threshold
        )
        reason = _build_attempt_reason(
            attempted_edit=attempted_edit,
            changed=changed,
            constraint_eval=constraint_eval,
            critic_report=critic_report,
            threshold=threshold,
        )
        analysis = {
            "validation": candidate_snapshot.validation,
            "solve": candidate_snapshot.solve,
            "score": candidate_snapshot.score,
            "diff": diff,
        }
        warnings = list(candidate_snapshot.validation.get("warnings", [])) + list(candidate_snapshot.score.get("warnings", []))
        attempt_record = {
            "attempt": attempt_index,
            "accepted": accepted,
            "reason": reason,
            "summary": generator_output.summary,
            "expected_outcome": generator_output.expected_outcome,
            "attemptedEdit": attempted_edit,
            "changed": changed,
            "operations": generator_output.operations,
            "updatedLevel": candidate_level,
            "analysis": analysis,
            "warnings": warnings,
            "constraintEvaluation": constraint_eval.details,
            "criticReport": critic_report.model_dump(mode="python", by_alias=True),
            "generatorToolTrace": generator_output.tool_trace,
            "criticToolTrace": critic_trace,
            "combinedScore": combined_score,
        }
        attempts.append(attempt_record)

        if best_attempt is None or combined_score > float(best_attempt.get("combinedScore", 0.0)):
            best_attempt = attempt_record

        if accepted:
            emit("controller", "The candidate passed the controller checks and is ready to apply.", attempt=attempt_index)
            return ControllerLoopResult(
                status="proposed",
                message=generator_output.summary or "A validated candidate level is ready.",
                updated_level=candidate_level,
                analysis=analysis,
                warnings=warnings,
                attempts=attempts,
                operations=generator_output.operations,
                critic_report=critic_report,
                controller_decision=ControllerDecision(
                    accepted=True,
                    shouldRetry=False,
                    stopReason="candidate accepted",
                    selectedAttempt=attempt_index,
                    bestScore=combined_score,
                    attemptLimit=max_attempts,
                ),
            )

        previous_feedback = _build_feedback_messages(reason, constraint_eval.details, critic_report)
        emit("controller", reason, attempt=attempt_index)

    best_score = float(best_attempt.get("combinedScore", 0.0)) if best_attempt else 0.0
    best_level = best_attempt.get("updatedLevel") if best_attempt else None
    returned_best_attempt = bool(best_level) and bool(best_attempt and best_attempt.get("changed"))
    return ControllerLoopResult(
        status="proposed_with_warnings" if returned_best_attempt else "rejected",
        message=(
            f"{best_attempt.get('reason')} Returning the best generated candidate for manual review."
            if returned_best_attempt and best_attempt
            else str(best_attempt.get("reason") if best_attempt else "No candidate satisfied the controller checks.")
        ),
        updated_level=best_level,
        analysis=best_attempt.get("analysis") if best_attempt else None,
        warnings=list(best_attempt.get("warnings", [])) if best_attempt else [],
        attempts=attempts,
        operations=list(best_attempt.get("operations", [])) if best_attempt else [],
        critic_report=CriticReport.model_validate(best_attempt.get("criticReport", {})) if best_attempt else None,
        controller_decision=ControllerDecision(
            accepted=False,
            shouldRetry=False,
            stopReason=(
                "attempt limit reached; returning best candidate with warnings"
                if returned_best_attempt
                else "attempt limit reached without an accepted candidate"
            ),
            selectedAttempt=best_attempt.get("attempt") if best_attempt else None,
            bestScore=best_score,
            attemptLimit=max_attempts,
        ),
    )


def _brief_to_modify_intent(brief: DesignBrief) -> ModifyIntent:
    target_min_steps_low = None
    target_min_steps_high = None
    if brief.difficulty_target:
        low = brief.difficulty_target.get("min_steps_low")
        high = brief.difficulty_target.get("min_steps_high")
        if isinstance(low, int):
            target_min_steps_low = low
        if isinstance(high, int):
            target_min_steps_high = high
    difficulty_level = str(brief.difficulty_target.get("level") or "").lower()
    requested_direction = "neutral"
    if difficulty_level == "hard" or "increase_difficulty" in brief.soft_targets:
        requested_direction = "harder"
    elif difficulty_level == "easy" or "decrease_difficulty" in brief.soft_targets:
        requested_direction = "easier"
    mechanic_proxy = None
    for note in brief.mechanic_notes:
        if "proxy" in note:
            mechanic_proxy = note
            break
    return ModifyIntent(
        hard_constraints=list(brief.hard_constraints),
        soft_targets=list(brief.soft_targets),
        target_min_steps_low=target_min_steps_low,
        target_min_steps_high=target_min_steps_high,
        requested_direction=requested_direction,
        wants_teaching_level="teaching_level" in brief.soft_targets,
        keep_map_size=bool(brief.board_constraints.get("keep_map_size")) or "keep_map_size" in brief.hard_constraints,
        require_mechanic_proxy=mechanic_proxy,
    )


def _combined_score(constraint_eval: Any, critic_report: CriticReport, changed: bool) -> float:
    score = float(critic_report.critic_score)
    if changed:
        score += 0.5
    if constraint_eval.improvement:
        score += 0.75
    if constraint_eval.satisfied:
        score += 1.0
    if critic_report.hard_pass:
        score += 0.75
    return score


def _build_attempt_reason(
    *,
    attempted_edit: bool,
    changed: bool,
    constraint_eval: Any,
    critic_report: CriticReport,
    threshold: float,
) -> str:
    if not attempted_edit:
        return "Generator did not successfully call apply_level_edits, so no candidate board was produced."
    if not changed:
        return "Candidate produced no effective board change."
    if not constraint_eval.satisfied:
        return "Candidate failed the deterministic hard constraints or soft target checks."
    if not constraint_eval.improvement:
        return "Candidate did not improve enough relative to the current baseline."
    if not critic_report.hard_pass:
        return "Critic rejected the candidate after the read-only validation pass."
    if critic_report.critic_score < threshold:
        return f"Critic score {critic_report.critic_score:.1f} is below the acceptance threshold {threshold:.1f}."
    if not critic_report.fit_to_brief:
        return "Candidate does not match the planner brief closely enough."
    return "Candidate passed all controller checks."


def _build_feedback_messages(reason: str, details: dict[str, Any], critic_report: CriticReport) -> list[str]:
    feedback = [reason]
    hard = details.get("hard_constraints", {})
    for key, value in hard.items():
        if not value:
            feedback.append(f"Fix hard constraint: {key}.")
    soft = details.get("soft_targets", {})
    for key, value in soft.items():
        if not value:
            feedback.append(f"Move the candidate closer to soft target: {key}.")
    feedback.extend(critic_report.issues[:3])
    feedback.extend(critic_report.next_actions[:3])
    deduped: list[str] = []
    seen: set[str] = set()
    for item in feedback:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _safe_build_snapshot(level: dict[str, Any], rule_pack: dict[str, Any]) -> AnalysisSnapshot:
    try:
        return build_analysis_snapshot(level, rule_pack)
    except Exception as error:
        return AnalysisSnapshot(
            level=level,
            validation={
                "valid": False,
                "errors": [f"snapshot build failed: {error}"],
                "warnings": [],
            },
            solve={
                "solvable": False,
                "min_steps": None,
                "status": "tool-error",
            },
            score={
                "difficulty": "unknown",
                "branching_factor": None,
                "redundant_objects": [],
                "warnings": [str(error)],
            },
        )
