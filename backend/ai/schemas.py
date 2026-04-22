from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator


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
    user_id: str = Field(
        default="local-user",
        validation_alias=AliasChoices("user_id", "userId"),
    )
    session_id: str = Field(
        default="default",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    message: str | None = Field(
        default=None,
        validation_alias=AliasChoices("message", "user_request"),
    )
    current_level: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("current_level", "currentLevel", "level"),
    )
    rule_pack: dict[str, Any] | None = Field(
        default=None,
        alias="rulePack",
        validation_alias=AliasChoices("rulePack", "rule_pack"),
    )
    debug: bool = False

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _ensure_required_fields(self) -> "LevelAgentRequest":
        if not self.message or not self.message.strip():
            raise ValueError("message is required.")
        if self.current_level is None:
            raise ValueError("current_level is required.")
        return self

    @property
    def user_request(self) -> str:
        return (self.message or "").strip()

    @property
    def level(self) -> dict[str, Any]:
        return self.current_level or {}


class ToolTraceEntry(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


class ChatMessageEntry(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class SessionSummary(BaseModel):
    session_id: str = Field(alias="sessionId")
    user_id: str = Field(alias="userId")
    title: str = "New chat"
    preview: str = ""
    message_count: int = Field(default=0, alias="messageCount")
    suggestions: list[str] = Field(default_factory=list)
    created_at: float = Field(default=0.0, alias="createdAt")
    updated_at: float = Field(default=0.0, alias="updatedAt")

    model_config = {"populate_by_name": True}


class SessionDetail(SessionSummary):
    messages: list[ChatMessageEntry] = Field(default_factory=list)
    working_level: dict[str, Any] | None = Field(default=None, alias="workingLevel")
    analysis_summary: dict[str, Any] = Field(default_factory=dict, alias="analysisSummary")
    last_intent: dict[str, Any] = Field(default_factory=dict, alias="lastIntent")

    model_config = {"populate_by_name": True}


class SessionCreateRequest(BaseModel):
    user_id: str = Field(
        default="local-user",
        validation_alias=AliasChoices("user_id", "userId"),
    )
    session_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    title: str | None = None
    current_level: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("current_level", "currentLevel", "level"),
    )

    model_config = {"populate_by_name": True}

    @property
    def level(self) -> dict[str, Any]:
        return self.current_level or {}


class AnalysisBundle(BaseModel):
    validation: dict[str, Any] | None = None
    solve: dict[str, Any] | None = None
    score: dict[str, Any] | None = None
    diff: dict[str, Any] | None = None


class DesignBrief(BaseModel):
    intent_type: Literal["analysis", "modify", "create", "query"] = "analysis"
    raw_user_text: str = ""
    design_goal: str = ""
    design_summary: str = Field(default="", alias="designSummary")
    generation_strategy: str = "refine_current_level"
    board_constraints: dict[str, Any] = Field(default_factory=dict)
    difficulty_target: dict[str, Any] = Field(default_factory=dict)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_targets: list[str] = Field(default_factory=list)
    player_experience_goals: list[str] = Field(default_factory=list)
    generation_spec: dict[str, Any] = Field(default_factory=dict, alias="generationSpec")
    mechanic_notes: list[str] = Field(default_factory=list)
    planner_notes: list[str] = Field(default_factory=list)
    retrieved_rule_context: str = Field(default="", alias="retrievedRuleContext")
    retrieved_rule_hits: list[dict[str, str]] = Field(default_factory=list, alias="retrievedRuleHits")
    retrieved_case_context: str = Field(default="", alias="retrievedCaseContext")
    retrieved_case_hits: list[dict[str, Any]] = Field(default_factory=list, alias="retrievedCaseHits")
    acceptance_rubric: dict[str, Any] = Field(default_factory=dict, alias="acceptanceRubric")
    review_rubric: dict[str, Any] = Field(default_factory=dict, alias="reviewRubric")

    model_config = {"populate_by_name": True}


class CriticReport(BaseModel):
    hard_pass: bool = Field(default=False, alias="hardPass")
    fit_to_brief: bool = Field(default=False, alias="fitToBrief")
    critic_score: float = Field(default=0.0, alias="criticScore")
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list, alias="nextActions")

    model_config = {"populate_by_name": True}


class ControllerDecision(BaseModel):
    accepted: bool = False
    should_retry: bool = Field(default=False, alias="shouldRetry")
    stop_reason: str = Field(default="", alias="stopReason")
    selected_attempt: int | None = Field(default=None, alias="selectedAttempt")
    best_score: float = Field(default=0.0, alias="bestScore")
    attempt_limit: int = Field(default=0, alias="attemptLimit")

    model_config = {"populate_by_name": True}


class LevelAgentResponse(BaseModel):
    analysis_summary: str = Field(default="")
    suggestions: list[str] = Field(default_factory=list)
    modify_agent_status: str = "mocked"
    modify_agent_output: dict[str, Any] = Field(default_factory=dict)
    rule_refactor_status: str = "placeholder"
    rule_refactor_output: dict[str, Any] = Field(default_factory=dict)
    intent: dict[str, Any] | None = None

    session_id: str | None = Field(default=None, alias="sessionId")
    user_id: str | None = Field(default=None, alias="userId")

    # Backward-compatible fields for the existing V1 panel.
    message: str
    updated_level: dict[str, Any] | None = Field(default=None, alias="updatedLevel")
    analysis: AnalysisBundle = Field(default_factory=AnalysisBundle)
    warnings: list[str] = Field(default_factory=list)
    messages: list[ChatMessageEntry] = Field(default_factory=list)
    tool_trace: list[ToolTraceEntry] | None = Field(default=None, alias="toolTrace")
    design_brief: DesignBrief | None = Field(default=None, alias="designBrief")
    critic_report: CriticReport | None = Field(default=None, alias="criticReport")
    controller_decision: ControllerDecision | None = Field(default=None, alias="controllerDecision")

    model_config = {"populate_by_name": True}


class ModifyJobStartRequest(LevelAgentRequest):
    intent: dict[str, Any] | None = None


class ModifyJobStatusResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    status: str
    stage: str = ""
    message: str = ""
    attempt: int = 0
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    created_at: float | None = Field(default=None, alias="createdAt")
    updated_at: float | None = Field(default=None, alias="updatedAt")

    model_config = {"populate_by_name": True}


DifficultyLiteral = Literal["easy", "medium", "hard"]
