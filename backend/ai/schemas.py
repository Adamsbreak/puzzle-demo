from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DEFAULT_RULE_PACK: dict[str, Any] = {
    "id": "basic-static",
    "name": "Basic Static",
    "version": "1.0.0",
    "board": {
        "rows": {"min": 2, "max": 20, "default": 6},
        "cols": {"min": 2, "max": 20, "default": 6},
        "cellSize": {"min": 36, "max": 96, "default": 64},
    },
    "cellTags": [
        {"id": "free", "label": "Free"},
        {"id": "horizontal", "label": "Horizontal"},
        {"id": "vertical", "label": "Vertical"},
        {"id": "block-lane", "label": "Block Lane"},
        {"id": "target-lane", "label": "Target Lane"},
        {"id": "blocked", "label": "Blocked"},
    ],
    "pieceTypes": [
        {
            "id": "target",
            "label": "Target",
            "role": "target",
            "defaultSize": {"w": 1, "h": 1},
            "defaultColor": "#bc8d16",
            "movable": True,
            "moveRule": "free",
        },
        {
            "id": "block",
            "label": "Block",
            "role": "block",
            "defaultSize": {"w": 1, "h": 1},
            "defaultColor": "#d26a4c",
            "movable": True,
            "moveRule": "free",
        },
        {
            "id": "fixed",
            "label": "Fixed",
            "role": "fixed",
            "defaultSize": {"w": 1, "h": 1},
            "defaultColor": "#5a5148",
            "movable": False,
            "moveRule": "blocked",
        },
    ],
    "zones": [
        {
            "id": "spawn",
            "label": "Spawn",
            "role": "spawn",
            "allowedShapes": ["rect", "edge"],
            "style": {"color": "#6b9f5a"},
        },
        {
            "id": "goal",
            "label": "Goal",
            "role": "goal",
            "allowedShapes": ["rect", "edge"],
            "goalMode": "full",
            "targetFilter": {"roles": ["target"]},
            "style": {"color": "#3f7dd1"},
        },
    ],
    "goals": [{"type": "all-targets-reach-goals"}],
    "solver": {
        "enabled": True,
        "objective": "min-operations",
        "maxNodes": 50000,
        "behavior": {
            "targetLanePriority": "absolute",
            "edgeGoalRelaxation": "final-step-only",
            "stopGeneration": "all-legal-stops",
        },
    },
}


class LevelAgentRequest(BaseModel):
    user_request: str = Field(..., min_length=1)
    level: dict[str, Any]
    rule_pack: dict[str, Any] | None = Field(default=None, alias="rulePack")
    debug: bool = False

    model_config = {"populate_by_name": True}


class ToolTraceEntry(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


class AnalysisBundle(BaseModel):
    validation: dict[str, Any] | None = None
    solve: dict[str, Any] | None = None
    score: dict[str, Any] | None = None
    diff: dict[str, Any] | None = None


class LevelAgentResponse(BaseModel):
    message: str
    updated_level: dict[str, Any] | None = Field(default=None, alias="updatedLevel")
    analysis: AnalysisBundle
    warnings: list[str] = Field(default_factory=list)
    tool_trace: list[ToolTraceEntry] | None = Field(default=None, alias="toolTrace")

    model_config = {"populate_by_name": True}


DifficultyLiteral = Literal["easy", "medium", "hard"]


class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, alias="topK", ge=1, le=20)
    include_rules: bool = Field(default=True, alias="includeRules")
    include_cases: bool = Field(default=True, alias="includeCases")
    build_context: bool = Field(default=True, alias="buildContext")

    model_config = {"populate_by_name": True}


class RagSearchHit(BaseModel):
    id: str
    type: Literal["rule_doc", "case"]
    title: str
    summary: str
    score: float
    source_path: str = Field(..., alias="sourcePath")
    matched_keywords: list[str] = Field(default_factory=list, alias="matchedKeywords")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class RagSearchResponse(BaseModel):
    query: str
    total_hits: int = Field(..., alias="totalHits")
    hits: list[RagSearchHit]
    context: str | None = None
    source_counts: dict[str, int] = Field(default_factory=dict, alias="sourceCounts")

    model_config = {"populate_by_name": True}


class RagEvalRequest(BaseModel):
    dataset_path: str | None = Field(default=None, alias="datasetPath")
    top_k_values: list[int] = Field(default_factory=lambda: [1, 3, 5], alias="topKValues")
    include_rules: bool = Field(default=True, alias="includeRules")
    include_cases: bool = Field(default=True, alias="includeCases")

    model_config = {"populate_by_name": True}


class RagEvalResponse(BaseModel):
    result: dict[str, Any]
    summary: str
