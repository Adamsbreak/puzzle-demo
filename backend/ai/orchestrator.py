from __future__ import annotations

from typing import Any

from backend.ai.rag_service import PuzzleRAGService
from backend.ai.schemas import AnalysisBundle, LevelAgentRequest, LevelAgentResponse, ToolTraceEntry
from backend.services.level_service import get_current_level, resolve_rule_pack, score_level, validate_level
from backend.services.solver_service import build_solve_summary, inspect_level


class LevelAgentOrchestrator:
    """Minimal source-backed orchestrator that keeps the backend runnable.

    The original richer agent stack is not present in this source snapshot, so this
    implementation focuses on deterministic analysis plus RAG grounding. It leaves
    a clean seam for future planner / generator / critic expansion.
    """

    def __init__(self, rag_service: PuzzleRAGService | None = None) -> None:
        self.rag_service = rag_service or PuzzleRAGService()

    def run(self, request: LevelAgentRequest) -> LevelAgentResponse:
        rule_pack = resolve_rule_pack(request.rule_pack)
        current_level = get_current_level(request.level, rule_pack)
        validation = validate_level(request.level, rule_pack)
        inspection = inspect_level(request.level, rule_pack)
        solve = build_solve_summary(request.level, inspection)
        score = score_level(request.level, rule_pack)
        rag_result = self.rag_service.search(request.user_request, top_k=5, include_rules=True, include_cases=True)

        warnings = list(validation.get("warnings", []))
        if _looks_like_edit_request(request.user_request):
            warnings.append(
                "This source-backed fallback orchestrator is analysis-first. It retrieved relevant rules and cases but did not auto-apply edits."
            )

        message = self._build_message(
            user_request=request.user_request,
            current_level=current_level,
            validation=validation,
            solve=solve,
            score=score,
            rag_result=rag_result,
            warnings=warnings,
        )

        tool_trace = [
            ToolTraceEntry(tool_name="get_current_level", arguments={}, result=current_level),
            ToolTraceEntry(tool_name="validate_level", arguments={}, result=validation),
            ToolTraceEntry(tool_name="inspect_level", arguments={}, result=inspection),
            ToolTraceEntry(tool_name="score_level", arguments={}, result=score),
            ToolTraceEntry(tool_name="rag_search", arguments={"query": request.user_request, "topK": 5}, result=rag_result),
        ]

        return LevelAgentResponse(
            message=message,
            updatedLevel=None,
            analysis=AnalysisBundle(validation=validation, solve=solve, score=score, diff=None),
            warnings=warnings,
            toolTrace=tool_trace,
        )

    def _build_message(
        self,
        *,
        user_request: str,
        current_level: dict[str, Any],
        validation: dict[str, Any],
        solve: dict[str, Any],
        score: dict[str, Any],
        rag_result: dict[str, Any],
        warnings: list[str],
    ) -> str:
        lines = [
            f"Request: {user_request}",
            f"Board: {current_level['board_size']['rows']}x{current_level['board_size']['cols']}, pieces={current_level['piece_count']}, zones={current_level['zone_count']}",
            f"Validation: {'valid' if validation.get('valid') else 'invalid'}",
            f"Solvable: {'yes' if solve.get('solvable') else 'no'}",
            f"Min steps: {solve.get('min_steps')}",
            f"Difficulty: {score.get('difficulty')}",
        ]
        if rag_result.get("hits"):
            lines.append("Relevant retrieved knowledge:")
            for hit in rag_result["hits"][:3]:
                lines.append(f"- {hit['id']}: {hit['title']}")
        if warnings:
            lines.append("Warnings:")
            for warning in warnings[:5]:
                lines.append(f"- {warning}")
        return "\n".join(lines)


def _looks_like_edit_request(text: str) -> bool:
    lowered = text.lower()
    keywords = (
        "make",
        "change",
        "edit",
        "create",
        "add",
        "remove",
        "update",
        "move",
        "generate",
        "optimize",
        "harder",
        "easier",
    )
    return any(keyword in lowered for keyword in keywords)
