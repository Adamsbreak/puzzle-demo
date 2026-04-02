from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class SolverBridgeError(RuntimeError):
    """Raised when the Node puzzle bridge fails."""


ROOT_DIR = Path(__file__).resolve().parents[2]
NODE_TOOL = ROOT_DIR / "backend" / "node_tools" / "puzzle_bridge.mjs"


def inspect_level(level: dict[str, Any], rule_pack: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "level": level,
        "rulePack": rule_pack,
    }
    process = subprocess.run(
        ["node", str(NODE_TOOL)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        cwd=str(ROOT_DIR),
    )
    if process.returncode != 0:
        raise SolverBridgeError(
            "Node puzzle bridge failed: "
            + (process.stderr.strip() or process.stdout.strip() or f"exit code {process.returncode}")
        )
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as error:
        snippet = process.stdout[:500]
        raise SolverBridgeError(f"Node puzzle bridge returned invalid JSON: {snippet}") from error


def build_solve_summary(level: dict[str, Any], inspect_result: dict[str, Any]) -> dict[str, Any]:
    validation = inspect_result.get("validation", {})
    solve = inspect_result.get("solve") or {}
    shortest = inspect_result.get("shortestSolutions") or {}
    steps = solve.get("steps") or []
    target_piece_ids = {
        piece.get("id")
        for piece in level.get("pieces", [])
        if piece.get("role") == "target"
    }
    critical_steps = [
        index + 1
        for index, step in enumerate(steps)
        if step.get("pieceId") in target_piece_ids
    ]
    if not critical_steps and steps:
        critical_steps = [max(1, len(steps))]
    return {
        "solvable": bool(validation.get("valid")) and solve.get("status") == "solved",
        "min_steps": solve.get("stepCount"),
        "unique_solution": shortest.get("solutionCount") == 1 if shortest.get("shortestStepCount") is not None else None,
        "solution_summary": solve.get("summary", "No solver summary."),
        "critical_steps": critical_steps,
        "status": solve.get("status"),
        "explored_nodes": solve.get("exploredNodes"),
        "raw_steps": steps,
        "shortest_solution_count": shortest.get("solutionCount"),
        "initial_branching_factor": (inspect_result.get("frontier") or {}).get("initialMoveCount"),
    }
