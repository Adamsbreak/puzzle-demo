from __future__ import annotations

import copy
import json
import logging
import os
import re
from typing import Any, Iterator, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from backend.ai.case_rag import CaseLibraryRetriever
from backend.ai.controller import run_generation_controller
from backend.ai.planner_agent import plan_design_brief
from backend.ai.rules_rag import LocalRuleRetriever
from backend.ai.session_store import SESSION_CONTEXT_STORE
from backend.ai.schemas import (
    AnalysisBundle,
    ChatMessageEntry,
    ControllerDecision,
    CriticReport,
    DesignBrief,
    LevelAgentRequest,
    LevelAgentResponse,
)
from backend.services.level_service import (
    LevelEditError,
    apply_level_edits,
    diff_levels,
    resolve_rule_pack,
    score_level,
    validate_level,
)
from backend.services.solver_service import build_solve_summary, inspect_level


LOGGER = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    request: LevelAgentRequest
    user_id: str
    session_id: str
    session_context: dict[str, Any]
    resolved_user_request: str
    run_modify_agent: bool
    rule_pack: dict[str, Any]
    history_messages: list[dict[str, str]]
    working_level: dict[str, Any]
    intent: dict[str, Any]
    analysis: dict[str, Any]
    analysis_summary: str
    suggestions: list[str]
    assistant_reply: str
    modify_agent_output: dict[str, Any]
    modify_agent_status: str
    rule_refactor_output: dict[str, Any]
    rule_refactor_status: str
    updated_level: dict[str, Any] | None
    rule_context: str
    rule_hits: list[dict[str, str]]
    tool_trace: list[dict[str, Any]]
    warnings: list[str]
    debug_trace: list[str]
    design_brief: dict[str, Any]
    critic_report: dict[str, Any]
    controller_decision: dict[str, Any]


def modify_agent_call(intent: dict[str, Any], working_level: dict[str, Any]) -> dict[str, Any]:
    _ = working_level
    return {
        "status": "mocked",
        "message": "modify agent called (mock)",
        "intent_type": intent.get("intent_type"),
        "operations": [],
        "updated_level": None,
    }


def rule_refactor_agent_call(intent: dict[str, Any], rule_pack: dict[str, Any]) -> dict[str, Any]:
    _ = intent
    _ = rule_pack
    return {
        "status": "placeholder",
        "message": "rule refactor agent is reserved for future implementation",
        "operations": [],
        "updated_rule_pack": None,
    }


class LevelAgentOrchestrator:
    def __init__(self) -> None:
        self.model = (
            os.getenv("LLM_MODEL")
            or os.getenv("DASHSCOPE_MODEL")
            or os.getenv("OPENAI_MODEL")
            or "qwen-flash"
        )
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "3000"))
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        self.modify_retry_limit = max(1, int(os.getenv("MODIFY_AGENT_MAX_ATTEMPTS", "3")))
        self.llm, self.provider = self._build_llm()
        self.rule_retriever = LocalRuleRetriever()
        self.case_retriever = CaseLibraryRetriever()
        self.graph = self._build_graph()
        LOGGER.info("LangGraph orchestrator ready provider=%s model=%s", self.provider, self.model)

    def _build_llm(self) -> tuple[Any, str]:
        api_key = (
            os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        if not api_key:
            raise RuntimeError("No API key configured. Set DASHSCOPE_API_KEY or LLM_API_KEY.")

        try:
            from langchain_qwq import ChatQwen  # type: ignore

            llm = ChatQwen(model=self.model, max_tokens=self.max_tokens)
            return llm, "langchain_qwq.ChatQwen"
        except Exception:
            from langchain_openai import ChatOpenAI

            base_url = os.getenv(
                "LLM_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            llm = ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            return llm, "langchain_openai.ChatOpenAI"

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("intent_compiler", self._intent_compiler_node)
        graph.add_node("chat_logic", self._chat_logic_node)
        graph.add_node("modify_agent", self._modify_agent_node)
        graph.add_node("rule_refactor_agent", self._rule_refactor_node)
        graph.add_edge(START, "intent_compiler")
        graph.add_edge("intent_compiler", "chat_logic")
        graph.add_edge("chat_logic", "modify_agent")
        graph.add_edge("modify_agent", "rule_refactor_agent")
        graph.add_edge("rule_refactor_agent", END)
        return graph.compile()

    def _intent_compiler_node(self, state: AgentState) -> AgentState:
        user_text = state["request"].user_request
        resolved_user_text = self._resolve_followup_request(user_text, state.get("session_context", {}))
        planner_output = plan_design_brief(
            llm=self.llm,
            rule_retriever=self.rule_retriever,
            case_retriever=self.case_retriever,
            user_request=resolved_user_text,
            working_level=copy.deepcopy(state.get("working_level") or state["request"].level),
            rule_pack=state["rule_pack"],
            session_context=copy.deepcopy(state.get("session_context") or {}),
        )
        brief = planner_output.brief
        brief_payload = brief.model_dump(mode="python", by_alias=True)
        execution_intent_type = "modify" if brief.intent_type in {"modify", "create"} else brief.intent_type
        intent = {
            "intent_type": execution_intent_type,
            "requested_intent_type": brief.intent_type,
            "hard_constraints": list(brief.hard_constraints),
            "soft_targets": list(brief.soft_targets),
            "raw_user_text": resolved_user_text,
            "design_brief": brief_payload,
        }
        if self._is_confirmation_message(user_text) and resolved_user_text != user_text:
            intent["intent_type"] = "modify"
            intent["design_brief"] = brief_payload

        next_state = dict(state)
        next_state["intent"] = intent
        next_state["resolved_user_request"] = resolved_user_text
        next_state["design_brief"] = brief_payload
        next_state["rule_context"] = planner_output.rule_context
        next_state["rule_hits"] = planner_output.rule_hits
        next_state["tool_trace"] = list(state.get("tool_trace", [])) + planner_output.tool_trace
        next_state["debug_trace"] = list(state.get("debug_trace", [])) + ["planner_agent"]
        return next_state

    def _chat_logic_node(self, state: AgentState) -> AgentState:
        request = state["request"]
        current_user_message = self._current_user_message(state)
        working_level = copy.deepcopy(state.get("working_level") or request.level)
        analysis, warnings, summary_seed = self._analyze_level(
            request=request,
            working_level=working_level,
            rule_pack=state["rule_pack"],
            intent=state.get("intent", {}),
        )

        history_messages = list(state.get("history_messages", []))
        recent_history = history_messages[-8:]
        brief_dict = state.get("design_brief") or (state.get("intent", {}) or {}).get("design_brief") or {}
        brief = DesignBrief.model_validate(brief_dict or {"raw_user_text": current_user_message})
        rule_context = str(state.get("rule_context") or "")
        rule_hits = list(state.get("rule_hits") or [])

        if brief.intent_type in {"modify", "create"}:
            analysis_summary = self._format_analysis_summary(analysis)
            assistant_reply = self._build_modify_acknowledgement(brief, analysis)
            suggestions = self._dedupe(
                list(brief.player_experience_goals or []) + self._fallback_suggestions(state.get("intent", {}), analysis)
            )[:4]
        else:
            if not rule_context:
                rule_context, rule_hits = self._retrieve_rule_context(
                    current_user_message=current_user_message,
                    compiled_intent=state.get("intent", {}),
                    summary_seed=summary_seed,
                    rule_pack=state["rule_pack"],
                )
            llm_text = self._invoke_llm(
                self._build_chat_messages(
                    current_user_message=current_user_message,
                    recent_history=recent_history,
                    compiled_intent=state.get("intent", {}),
                    summary_seed=summary_seed,
                    working_level=working_level,
                    rule_pack=state["rule_pack"],
                    rule_context=rule_context,
                    structured=True,
                )
            )
            llm_json = self._try_parse_json_object(llm_text) or {}
            analysis_summary = str(llm_json.get("analysis_summary") or self._format_analysis_summary(analysis))
            assistant_reply = str(llm_json.get("assistant_reply") or analysis_summary)
            suggestions = self._collect_suggestions(
                llm_json.get("suggestions"),
                assistant_reply,
                state.get("intent", {}),
                analysis,
            )
            if not suggestions:
                suggestions = ["Try one small board change, then compare the new solve metrics."]

        if request.user_request:
            history_messages.append({"role": "user", "content": request.user_request})
        history_messages.append({"role": "assistant", "content": assistant_reply})

        next_state = dict(state)
        next_state["analysis"] = analysis
        next_state["analysis_summary"] = analysis_summary
        next_state["suggestions"] = suggestions
        next_state["assistant_reply"] = assistant_reply
        next_state["warnings"] = warnings
        next_state["history_messages"] = history_messages[-20:]
        next_state["working_level"] = working_level
        next_state["rule_context"] = rule_context
        next_state["rule_hits"] = rule_hits
        next_state["debug_trace"] = list(state.get("debug_trace", [])) + ["chat_logic"]
        return next_state

    def _modify_agent_node(self, state: AgentState, progress_callback: Any | None = None) -> AgentState:
        if not state.get("run_modify_agent"):
            next_state = dict(state)
            next_state["modify_agent_output"] = {
                "status": "skipped",
                "message": "modify agent is handled asynchronously for chat requests",
                "operations": [],
                "updated_level": None,
                "attempts": [],
            }
            next_state["modify_agent_status"] = "skipped"
            next_state["updated_level"] = None
            next_state["debug_trace"] = list(state.get("debug_trace", [])) + ["modify_agent_skipped"]
            return next_state

        brief_dict = state.get("design_brief") or (state.get("intent", {}) or {}).get("design_brief") or {}
        if not brief_dict:
            planner_output = plan_design_brief(
                llm=self.llm,
                rule_retriever=self.rule_retriever,
                case_retriever=self.case_retriever,
                user_request=self._current_user_message(state),
                working_level=copy.deepcopy(state.get("working_level") or state["request"].level),
                rule_pack=state["rule_pack"],
                session_context=copy.deepcopy(state.get("session_context") or {}),
            )
            brief = planner_output.brief
            brief_dict = brief.model_dump(mode="python", by_alias=True)
            state = dict(state)
            state["design_brief"] = brief_dict
            state["rule_context"] = planner_output.rule_context
            state["rule_hits"] = planner_output.rule_hits
            state["tool_trace"] = list(state.get("tool_trace", [])) + planner_output.tool_trace
            state["intent"] = {
                "intent_type": "modify" if brief.intent_type in {"modify", "create"} else brief.intent_type,
                "requested_intent_type": brief.intent_type,
                "hard_constraints": list(brief.hard_constraints),
                "soft_targets": list(brief.soft_targets),
                "raw_user_text": brief.raw_user_text,
                "design_brief": brief_dict,
            }
        brief = DesignBrief.model_validate(brief_dict)
        controller_result = run_generation_controller(
            llm=self.llm,
            brief=brief,
            working_level=copy.deepcopy(state.get("working_level") or state["request"].level),
            rule_pack=state["rule_pack"],
            rule_context=str(state.get("rule_context") or ""),
            max_attempts=self.modify_retry_limit,
            progress_callback=progress_callback,
        )
        modify_output = {
            "status": controller_result.status,
            "message": controller_result.message,
            "intent_type": state.get("intent", {}).get("intent_type"),
            "operations": controller_result.operations,
            "updated_level": controller_result.updated_level,
            "analysis": controller_result.analysis,
            "warnings": controller_result.warnings,
            "attempts": controller_result.attempts,
            "critic_report": (
                controller_result.critic_report.model_dump(mode="python", by_alias=True)
                if controller_result.critic_report
                else {}
            ),
            "controller_decision": controller_result.controller_decision.model_dump(mode="python", by_alias=True),
        }
        next_state = dict(state)
        next_state["modify_agent_output"] = modify_output
        next_state["modify_agent_status"] = str(modify_output.get("status", "mocked"))
        next_state["updated_level"] = modify_output.get("updated_level")
        if modify_output.get("updated_level"):
            next_state["working_level"] = copy.deepcopy(modify_output.get("updated_level"))
        if modify_output.get("analysis"):
            next_state["analysis"] = modify_output.get("analysis")
        next_state["warnings"] = self._dedupe(list(state.get("warnings", [])) + list(modify_output.get("warnings", [])))
        next_state["critic_report"] = modify_output.get("critic_report", {})
        next_state["controller_decision"] = modify_output.get("controller_decision", {})
        next_state["tool_trace"] = self._append_tool_trace(
            list(state.get("tool_trace", [])),
            "modify_level_loop",
            {
                "intent_type": state.get("intent", {}).get("intent_type"),
                "attempt_limit": self.modify_retry_limit,
            },
            {
                "status": modify_output.get("status"),
                "attempts": modify_output.get("attempts", []),
                "accepted": bool(modify_output.get("updated_level")),
                "controller_decision": modify_output.get("controller_decision", {}),
            },
        )
        next_state["debug_trace"] = list(state.get("debug_trace", [])) + ["modify_agent"]
        return next_state

    def _rule_refactor_node(self, state: AgentState) -> AgentState:
        rule_refactor_output = rule_refactor_agent_call(state.get("intent", {}), state.get("rule_pack", {}))
        next_state = dict(state)
        next_state["rule_refactor_output"] = rule_refactor_output
        next_state["rule_refactor_status"] = str(rule_refactor_output.get("status", "placeholder"))
        next_state["debug_trace"] = list(state.get("debug_trace", [])) + ["rule_refactor_agent"]
        return next_state

    def _invoke_llm(self, messages: list[Any]) -> str:
        try:
            response = self.llm.invoke(messages)
        except Exception as error:
            LOGGER.warning("LLM invoke failed: %s", error)
            return ""
        return self._coerce_message_content(response)

    def _stream_llm_text(self, messages: list[Any]) -> Iterator[str]:
        try:
            for chunk in self.llm.stream(messages):
                delta = self._coerce_stream_content(chunk)
                if delta:
                    yield delta
        except Exception as error:
            LOGGER.warning("LLM stream failed: %s", error)

    def _stream_reply_chunks(self, messages: list[Any]) -> Iterator[str]:
        use_true_stream = str(os.getenv("PUZZLE_AI_TRUE_STREAM", "")).strip().lower() in {"1", "true", "yes", "on"}
        if use_true_stream:
            yielded_any = False
            for chunk in self._stream_llm_text(messages):
                yielded_any = True
                yield chunk
            if yielded_any:
                return

        # Default to invoke-then-chunk because some providers finish the text
        # but keep the streaming socket open, which leaves the UI stuck in a
        # perpetual "Thinking/Writing" state.
        full_text = self._invoke_llm(messages)
        for chunk in self._chunk_text(full_text, chunk_size=24):
            if chunk:
                yield chunk

    def _coerce_stream_content(self, response: Any) -> str:
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    text_value = item.get("text")
                    if text_value is not None:
                        text_parts.append(str(text_value))
            return "".join(text_parts)
        return str(content)

    def _coerce_message_content(self, response: Any) -> str:
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    text_value = item.get("text")
                    if text_value:
                        text_parts.append(str(text_value))
            return "".join(text_parts).strip()
        return str(content).strip()

    def _build_rule_query(
        self,
        current_user_message: str,
        compiled_intent: dict[str, Any],
        summary_seed: dict[str, Any],
    ) -> str:
        return " | ".join(
            [
                current_user_message,
                " ".join(compiled_intent.get("hard_constraints", []) or []),
                " ".join(compiled_intent.get("soft_targets", []) or []),
                str(summary_seed.get("difficulty") or ""),
                str(summary_seed.get("solvable") or ""),
            ]
        )

    def _retrieve_rule_context(
        self,
        current_user_message: str,
        compiled_intent: dict[str, Any],
        summary_seed: dict[str, Any],
        rule_pack: dict[str, Any],
    ) -> tuple[str, list[dict[str, str]]]:
        query = self._build_rule_query(current_user_message, compiled_intent, summary_seed)
        hits = self.rule_retriever.retrieve(
            query + " " + json.dumps(rule_pack.get("solver", {}), ensure_ascii=False),
            top_k=3,
        )
        return self.rule_retriever.format_context(hits), hits

    def _append_tool_trace(
        self,
        trace: list[dict[str, Any]],
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        next_trace = list(trace)
        next_trace.append(
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
            }
        )
        return next_trace

    def _build_chat_messages(
        self,
        current_user_message: str,
        recent_history: list[dict[str, str]],
        compiled_intent: dict[str, Any],
        summary_seed: dict[str, Any],
        working_level: dict[str, Any],
        rule_pack: dict[str, Any],
        rule_context: str,
        structured: bool,
    ) -> list[Any]:
        if structured:
            system_prompt = (
                "You are the main chat agent for a puzzle editor.\n"
                "Stay strictly within puzzle level design, validation, solving, rule packs, and edit guidance.\n"
                "If the user asks about unrelated topics, politely say you only help with the puzzle editor and invite a puzzle-related question.\n"
                "You are given the current board JSON directly in the `current_level` field and the active rule pack in `rule_pack`.\n"
                "You are also given retrieved rule excerpts in `retrieved_rules`. Use them as high-priority guidance when they are relevant.\n"
                "Do not claim that you cannot see the board, cannot access the current level, or need the user to paste the JSON again unless `current_level` is missing or empty.\n"
                "Base your answer on the provided board data and the precomputed analysis.\n"
                "If the compiled intent is `modify`, do not invent a second concrete board-edit plan. Summarize the goal and constraints briefly because the actual board update is produced by the background modify agent.\n"
                "Return JSON only with keys:\n"
                '{"assistant_reply":"...","analysis_summary":"...","suggestions":["..."]}\n'
                "suggestions should have 1-4 items.\n"
                "Do not include markdown."
            )
        else:
            system_prompt = (
                "You are the main chat agent for a puzzle editor.\n"
                "Stay strictly within puzzle level design, validation, solving, rule packs, and edit guidance.\n"
                "If the user asks about unrelated topics, politely redirect them back to puzzle-editor questions.\n"
                "You are given the current board JSON directly in the `current_level` field and the active rule pack in `rule_pack`.\n"
                "You are also given retrieved rule excerpts in `retrieved_rules`. Use them as high-priority guidance when they are relevant.\n"
                "Do not claim that you cannot see the board, cannot access the current level, or need the user to paste the JSON again unless `current_level` is missing or empty.\n"
                "Base your answer on the provided board data and the precomputed analysis.\n"
                "If the compiled intent is `modify`, do not invent a second concrete board-edit plan. Summarize the goal and constraints briefly because the actual board update is produced by the background modify agent.\n"
                "Write a direct assistant reply in plain text only. Do not output JSON."
            )

        user_payload = {
            "history": recent_history,
            "current_user_message": current_user_message,
            "compiled_intent": compiled_intent,
            "analysis": summary_seed,
            "current_level": working_level,
            "rule_pack": rule_pack,
            "retrieved_rules": rule_context,
        }
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
        ]

    def _format_analysis_summary(self, analysis: dict[str, Any]) -> str:
        validation = analysis.get("validation", {})
        solve = analysis.get("solve", {})
        score = analysis.get("score", {})
        return (
            f"valid={validation.get('valid')}, "
            f"solvable={solve.get('solvable')}, "
            f"min_steps={solve.get('min_steps')}, "
            f"difficulty={score.get('difficulty')}"
        )

    def _build_modify_acknowledgement(self, brief: DesignBrief, analysis: dict[str, Any]) -> str:
        focus_bits: list[str] = []
        action_label = "build a new puzzle from the current blank baseline"
        if brief.intent_type == "modify":
            action_label = "modify the current puzzle"
        elif brief.intent_type not in {"create", "modify"}:
            action_label = "prepare the next puzzle-design step"
        if brief.design_summary:
            focus_bits.append("planner summary: " + brief.design_summary)
        if brief.player_experience_goals:
            focus_bits.append("player goals: " + ", ".join(brief.player_experience_goals[:3]))
        if brief.hard_constraints:
            focus_bits.append("hard constraints: " + ", ".join(brief.hard_constraints[:3]))
        if brief.soft_targets:
            focus_bits.append("soft targets: " + ", ".join(brief.soft_targets[:3]))
        if brief.mechanic_notes:
            focus_bits.append("mechanic notes: " + "; ".join(brief.mechanic_notes[:2]))
        focus_text = " ".join(focus_bits).strip()
        analysis_summary = self._format_analysis_summary(analysis)
        return (
            f"I understand the request as: {brief.design_goal or brief.raw_user_text}. "
            f"I will {action_label} using a structured brief for the generator and critic loop. "
            f"Current board baseline: {analysis_summary}. "
            f"{focus_text}".strip()
        )

    def _analyze_level(
        self,
        request: LevelAgentRequest,
        working_level: dict[str, Any],
        rule_pack: dict[str, Any],
        intent: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
        warnings: list[str] = []

        validation = validate_level(working_level, rule_pack)
        warnings.extend(validation.get("warnings", []))

        try:
            inspection = inspect_level(working_level, rule_pack)
            solve = build_solve_summary(working_level, inspection)
        except Exception as error:
            solve = {
                "solvable": False,
                "min_steps": None,
                "unique_solution": None,
                "solution_summary": f"solve tool failed: {error}",
                "critical_steps": [],
                "status": "tool-error",
                "explored_nodes": None,
                "raw_steps": [],
                "shortest_solution_count": None,
                "initial_branching_factor": None,
            }
            warnings.append(str(error))

        score = score_level(working_level, rule_pack)
        warnings.extend(score.get("warnings", []))

        analysis = {
            "validation": validation,
            "solve": solve,
            "score": score,
            "diff": diff_levels(request.level, working_level),
        }
        summary_seed = {
            "valid": validation.get("valid"),
            "errors": validation.get("errors", [])[:5],
            "solvable": solve.get("solvable"),
            "min_steps": solve.get("min_steps"),
            "difficulty": score.get("difficulty"),
            "branching_factor": score.get("branching_factor"),
            "intent": intent,
        }
        return analysis, self._dedupe(warnings), summary_seed

    def _build_modify_messages(
        self,
        request: LevelAgentRequest,
        intent: dict[str, Any],
        working_level: dict[str, Any],
        rule_pack: dict[str, Any],
        analysis: dict[str, Any],
        rule_context: str,
        previous_failures: list[str],
        attempt_index: int,
    ) -> list[Any]:
        bootstrap_summary = self._summarize_level_bootstrap_state(working_level)
        system_prompt = (
            "You are the board modification agent for a puzzle editor.\n"
            "Return JSON only with keys:\n"
            '{"summary":"...","operations":[{"action":"..."}],"expected_outcome":"..."}\n'
            "Supported actions are only: rename_level, update_piece, add_piece, remove_piece, set_cell_tags, add_zone, update_zone, remove_zone.\n"
            "Do not resize the board or invent unsupported actions.\n"
            "Respect the active rule pack, the retrieved rule excerpts, and the user's hard constraints.\n"
            "Prefer small, high-confidence edits over large rewrites.\n"
            "If the current board is empty or missing required core elements such as target pieces or goal zones, you should bootstrap a playable puzzle from scratch.\n"
            "A valid bootstrap usually means: add at least one target piece, add at least one goal zone, and optionally add block/fixed pieces or lane tags to satisfy the user's request.\n"
            "For `add_piece`, you must return an operation like {\"action\":\"add_piece\",\"piece\":{...}}.\n"
            "For `add_zone`, you must return an operation like {\"action\":\"add_zone\",\"zone\":{...}}.\n"
            "For `update_piece`, use {\"action\":\"update_piece\",\"piece_id\":\"...\", ...fields }.\n"
            "For `update_zone`, use {\"action\":\"update_zone\",\"zone_id\":\"...\", ...fields }.\n"
            "If you cannot find a safe edit, return an empty operations list and explain why in summary.\n"
            "Do not include markdown."
        )
        payload = {
            "attempt_index": attempt_index,
            "user_request": intent.get("raw_user_text") or request.user_request,
            "intent": intent,
            "current_level": working_level,
            "rule_pack": rule_pack,
            "analysis": analysis,
            "bootstrap_state": bootstrap_summary,
            "retrieved_rules": rule_context,
            "previous_failures": previous_failures[-4:],
            "operation_examples": {
                "add_piece": {
                    "action": "add_piece",
                    "piece": {
                        "typeId": "target",
                        "name": "Target 1",
                        "row": 0,
                        "col": 0,
                        "w": 2,
                        "h": 1,
                    },
                },
                "add_zone": {
                    "action": "add_zone",
                    "zone": {
                        "templateId": "goal",
                        "shapeKind": "edge",
                        "side": "right",
                        "index": 0,
                        "w": 1,
                        "h": 1,
                    },
                },
            },
        }
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ]

    def _run_modify_agent_loop(
        self,
        state: AgentState,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        def emit(stage: str, message: str, **extra: Any) -> None:
            if progress_callback:
                progress_callback({"stage": stage, "message": message, **extra})

        intent = state.get("intent", {})
        if intent.get("intent_type") != "modify":
            return {
                "status": "skipped",
                "message": "modify agent was skipped because the current intent is not modify",
                "intent_type": intent.get("intent_type"),
                "operations": [],
                "updated_level": None,
                "attempts": [],
            }

        request = state["request"]
        working_level = copy.deepcopy(state.get("working_level") or request.level)
        rule_pack = state["rule_pack"]
        base_analysis = state.get("analysis", {})
        rule_context = state.get("rule_context", "")
        previous_failures: list[str] = []
        attempts: list[dict[str, Any]] = []

        for attempt_index in range(1, self.modify_retry_limit + 1):
            emit(
                "modify_generate",
                f"Generating modification attempt {attempt_index}/{self.modify_retry_limit}...",
                attempt=attempt_index,
            )
            llm_text = self._invoke_llm(
                self._build_modify_messages(
                    request=request,
                    intent=intent,
                    working_level=working_level,
                    rule_pack=rule_pack,
                    analysis=base_analysis,
                    rule_context=rule_context,
                    previous_failures=previous_failures,
                    attempt_index=attempt_index,
                )
            )
            llm_json = self._try_parse_json_object(llm_text) or {}
            operations = self._normalize_modify_operations(llm_json.get("operations"))

            if not isinstance(operations, list) or not operations:
                reason = str(llm_json.get("summary") or "modify agent returned no operations")
                emit("modify_retry", reason, attempt=attempt_index)
                attempts.append(
                    {
                        "attempt": attempt_index,
                        "accepted": False,
                        "reason": reason,
                        "operations": [],
                    }
                )
                previous_failures.append(reason)
                continue

            try:
                edited = apply_level_edits(working_level, operations, rule_pack)
                candidate_level = edited["level"]
            except LevelEditError as error:
                reason = f"edit application failed: {error}"
                emit("modify_validate", reason, attempt=attempt_index)
                attempts.append(
                    {
                        "attempt": attempt_index,
                        "accepted": False,
                        "reason": reason,
                        "operations": operations,
                    }
                )
                previous_failures.append(reason)
                continue

            emit("modify_validate", "Validating and solving the candidate board...", attempt=attempt_index)
            candidate_analysis, candidate_warnings, _ = self._analyze_level(
                request=request,
                working_level=candidate_level,
                rule_pack=rule_pack,
                intent=intent,
            )
            acceptance = self._evaluate_modify_candidate(
                intent=intent,
                before_level=working_level,
                before_analysis=base_analysis,
                after_level=candidate_level,
                after_analysis=candidate_analysis,
            )
            attempts.append(
                {
                    "attempt": attempt_index,
                    "accepted": acceptance["accepted"],
                    "reason": acceptance["reason"],
                    "operations": operations,
                    "summary": llm_json.get("summary", ""),
                    "expected_outcome": llm_json.get("expected_outcome", ""),
                }
            )

            if acceptance["accepted"]:
                emit("modify_complete", "A validated board update is ready to apply.", attempt=attempt_index)
                return {
                    "status": "proposed",
                    "message": str(llm_json.get("summary") or acceptance["reason"]),
                    "intent_type": intent.get("intent_type"),
                    "operations": operations,
                    "updated_level": candidate_level,
                    "analysis": candidate_analysis,
                    "warnings": candidate_warnings,
                    "attempts": attempts,
                }

            emit("modify_retry", acceptance["reason"], attempt=attempt_index)
            previous_failures.append(acceptance["reason"])

        emit("modify_failed", previous_failures[-1] if previous_failures else "No valid modification was found.")
        return {
            "status": "rejected",
            "message": previous_failures[-1] if previous_failures else "modify agent could not produce a valid change",
            "intent_type": intent.get("intent_type"),
            "operations": [],
            "updated_level": None,
            "attempts": attempts,
        }

    def _evaluate_modify_candidate(
        self,
        intent: dict[str, Any],
        before_level: dict[str, Any],
        before_analysis: dict[str, Any],
        after_level: dict[str, Any],
        after_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        before_board = before_level.get("board", {})
        after_board = after_level.get("board", {})
        before_solve = (before_analysis or {}).get("solve", {})
        after_solve = (after_analysis or {}).get("solve", {})
        before_score = (before_analysis or {}).get("score", {})
        after_score = (after_analysis or {}).get("score", {})
        hard_constraints = set(intent.get("hard_constraints", []) or [])
        soft_targets = list(intent.get("soft_targets", []) or [])

        if before_board.get("rows") != after_board.get("rows") or before_board.get("cols") != after_board.get("cols"):
            return {"accepted": False, "reason": "candidate changed the board size, which is not allowed"}

        if "keep_map_size" in hard_constraints:
            if before_board.get("rows") != after_board.get("rows") or before_board.get("cols") != after_board.get("cols"):
                return {"accepted": False, "reason": "candidate violated keep_map_size"}

        if "keep_solvable" in hard_constraints and not after_solve.get("solvable"):
            return {"accepted": False, "reason": "candidate violated keep_solvable"}

        if before_solve.get("solvable") and not after_solve.get("solvable"):
            return {"accepted": False, "reason": "candidate made a previously solvable level unsolved"}

        if "increase_difficulty" in soft_targets:
            if self._difficulty_rank(after_score.get("difficulty")) < self._difficulty_rank(before_score.get("difficulty")):
                return {"accepted": False, "reason": "candidate did not preserve or increase difficulty"}

        if "decrease_difficulty" in soft_targets:
            if self._difficulty_rank(after_score.get("difficulty")) > self._difficulty_rank(before_score.get("difficulty")):
                return {"accepted": False, "reason": "candidate did not preserve or decrease difficulty"}

        if "teaching_level" in soft_targets:
            teaching_signals = after_score.get("teaching_signals", {})
            if not teaching_signals.get("estimated_teaching_level"):
                return {"accepted": False, "reason": "candidate did not meet the teaching-level target"}

        if diff_levels(before_level, after_level) == {
            "title_changed": False,
            "pieces_added": [],
            "pieces_removed": [],
            "pieces_updated": [],
            "zones_added": [],
            "zones_removed": [],
            "zones_updated": [],
            "cell_changes": [],
        }:
            return {"accepted": False, "reason": "candidate produced no effective change"}

        return {"accepted": True, "reason": "candidate passed validation and solver checks"}

    def _difficulty_rank(self, difficulty: str | None) -> int:
        mapping = {"easy": 1, "medium": 2, "hard": 3}
        return mapping.get(str(difficulty or "").lower(), 0)

    def _summarize_level_bootstrap_state(self, level: dict[str, Any]) -> dict[str, Any]:
        pieces = list(level.get("pieces", []))
        zones = list(level.get("zones", []))
        target_count = len([piece for piece in pieces if piece.get("role") == "target"])
        goal_count = len([zone for zone in zones if zone.get("role") == "goal"])
        return {
            "piece_count": len(pieces),
            "zone_count": len(zones),
            "target_count": target_count,
            "goal_count": goal_count,
            "needs_bootstrap": len(pieces) == 0 or target_count == 0 or goal_count == 0,
        }

    def _normalize_modify_operations(self, operations: Any) -> Any:
        if not isinstance(operations, list):
            return operations

        normalized: list[Any] = []
        for item in operations:
            if not isinstance(item, dict):
                normalized.append(item)
                continue

            action = item.get("action")
            if action == "add_piece" and "piece" not in item:
                piece_fields = {
                    key: value
                    for key, value in item.items()
                    if key in {"id", "name", "typeId", "role", "row", "col", "w", "h", "moveRule", "movable", "color", "metadata"}
                }
                remainder = {key: value for key, value in item.items() if key not in piece_fields}
                normalized.append(dict(remainder, piece=piece_fields))
                continue

            if action == "add_zone" and "zone" not in item:
                zone_fields = {
                    key: value
                    for key, value in item.items()
                    if key in {"id", "templateId", "name", "role", "shapeKind", "row", "col", "side", "index", "w", "h", "color", "goalMode", "targetFilter"}
                }
                remainder = {key: value for key, value in item.items() if key not in zone_fields}
                normalized.append(dict(remainder, zone=zone_fields))
                continue

            normalized.append(item)

        return normalized

    def _current_user_message(self, state: AgentState) -> str:
        return str(state.get("resolved_user_request") or state["request"].user_request).strip()

    def _is_confirmation_message(self, text: str) -> bool:
        compact = re.sub(r"[\s\.\!\?,~]+", "", str(text or "").strip().lower())
        for marker in ("\u3002", "\uFF01", "\uFF1F", "\uFF5E", "\uFF0C"):
            compact = compact.replace(marker, "")
        if not compact:
            return False
        exact_matches = {
            "\u505A\u5427",
            "\u6539\u5427",
            "\u6267\u884C\u5427",
            "\u5F00\u59CB\u5427",
            "\u5F00\u59CB\u6539",
            "\u76F4\u63A5\u6539",
            "\u5C31\u8FD9\u4E48\u505A",
            "\u5C31\u8FD9\u6837\u5427",
            "\u6309\u8FD9\u4E2A\u6765",
            "\u7167\u8FD9\u4E2A\u6539",
            "\u7528\u8FD9\u4E2A\u65B9\u6848",
            "doit",
            "applyit",
            "goahead",
        }
        if compact in exact_matches:
            return True
        return any(
            compact.startswith(prefix)
            for prefix in (
                "\u6309\u521A\u624D\u7684\u5EFA\u8BAE",
                "\u6309\u8FD9\u4E2A\u65B9\u6848",
                "\u6309\u521A\u624D\u90A3\u4E2A",
                "makethechange",
                "applythechange",
            )
        )

    def _looks_like_query(self, user_text: str) -> bool:
        lowered = str(user_text or "").strip().lower()
        if not lowered:
            return False
        if lowered.endswith("?"):
            return True
        return any(token in lowered for token in ("why", "what", "query", "explain", "how", "which")) or any(
            token in user_text
            for token in (
                "\u4E3A\u4EC0\u4E48",
                "\u600E\u4E48",
                "\u5982\u4F55",
                "\u4EC0\u4E48",
                "\u54EA\u4E2A",
                "\u539F\u56E0",
            )
        )

    def _looks_like_modify_request(self, user_text: str) -> bool:
        value = str(user_text or "").strip()
        lowered = value.lower()
        if not value:
            return False
        if self._is_confirmation_message(value):
            return True

        explicit_phrases = (
            "modify",
            "edit",
            "change",
            "adjust",
            "optimize",
            "apply",
            "increase",
            "decrease",
            "remove",
            "add",
            "restore",
            "simplify",
            "make this",
            "make the level",
            "try ",
        )
        explicit_cn = (
            "\u4FEE\u6539",
            "\u8C03\u6574",
            "\u4F18\u5316",
            "\u5E94\u7528",
            "\u589E\u52A0",
            "\u6DFB\u52A0",
            "\u5220\u9664",
            "\u79FB\u9664",
            "\u51CF\u5C11",
            "\u6062\u590D",
            "\u63D0\u9AD8",
            "\u964D\u4F4E",
        )
        imperative_prefixes = (
            "please modify",
            "please edit",
            "please change",
            "make this level",
            "make the level",
            "add ",
            "remove ",
            "increase ",
            "decrease ",
            "restore ",
            "try ",
            "apply ",
        )
        imperative_cn_prefixes = (
            "\u4FEE\u6539",
            "\u8C03\u6574",
            "\u4F18\u5316",
            "\u6DFB\u52A0",
            "\u589E\u52A0",
            "\u5220\u9664",
            "\u79FB\u9664",
            "\u51CF\u5C11",
            "\u6062\u590D",
            "\u63D0\u9AD8",
            "\u964D\u4F4E",
            "\u8BA9\u8FD9\u4E2A\u5173\u5361",
        )

        has_explicit_modify = any(token in lowered for token in explicit_phrases) or any(token in value for token in explicit_cn)
        if any(lowered.startswith(prefix) for prefix in imperative_prefixes) or any(
            value.startswith(prefix) for prefix in imperative_cn_prefixes
        ):
            return True
        if self._looks_like_query(value) and not has_explicit_modify:
            return False
        return has_explicit_modify

    def _pick_actionable_suggestion(self, suggestions: Any) -> str | None:
        candidates = [str(item or "").strip() for item in suggestions or [] if str(item or "").strip()]
        for item in candidates:
            if self._looks_like_modify_request(item):
                return item
        return candidates[0] if candidates else None

    def _resolve_followup_request(self, user_text: str, session_context: dict[str, Any]) -> str:
        value = str(user_text or "").strip()
        if not self._is_confirmation_message(value):
            return value

        last_intent = session_context.get("last_intent") or {}
        previous_modify_request = str(last_intent.get("raw_user_text") or "").strip()
        if last_intent.get("intent_type") == "modify" and previous_modify_request:
            return previous_modify_request

        suggestions = session_context.get("suggestions") or (session_context.get("analysis_summary") or {}).get("suggestions") or []
        carried = self._pick_actionable_suggestion(suggestions)
        if carried:
            return f"Apply this suggestion to the current level: {carried}"
        return value

    def _extract_suggestions_from_reply(self, assistant_reply: str) -> list[str]:
        suggestions: list[str] = []
        lines = [line.strip() for line in re.split(r"[\r\n]+", assistant_reply or "") if line.strip()]
        for line in lines:
            clean = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
            lowered = clean.lower()
            if len(clean) < 12 or len(clean) > 140:
                continue
            if self._looks_like_modify_request(clean) or any(
                token in lowered for token in ("suggest", "recommend", "consider", "you can")
            ) or any(token in clean for token in ("\u5EFA\u8BAE", "\u53EF\u4EE5", "\u5C1D\u8BD5")):
                suggestions.append(clean.rstrip(".!?\u3002\uFF01\uFF1F"))

        if suggestions:
            return self._dedupe(suggestions)[:4]

        sentences = [part.strip() for part in re.split("(?<=[\\u3002.!?\\uFF01\\uFF1F])\\s*", assistant_reply or "") if part.strip()]
        for sentence in sentences:
            lowered = sentence.lower()
            if len(sentence) < 12 or len(sentence) > 140:
                continue
            if self._looks_like_modify_request(sentence) or any(
                token in lowered for token in ("try ", "consider ", "you can", "recommend")
            ) or any(token in sentence for token in ("\u5EFA\u8BAE", "\u5C1D\u8BD5", "\u53EF\u4EE5")):
                suggestions.append(sentence.rstrip(".!?\u3002\uFF01\uFF1F"))
        return self._dedupe(suggestions)[:4]

    def _collect_suggestions(
        self,
        llm_suggestions: Any,
        assistant_reply: str,
        intent: dict[str, Any],
        analysis: dict[str, Any],
    ) -> list[str]:
        output: list[str] = []
        if isinstance(llm_suggestions, list):
            output.extend(str(item).strip() for item in llm_suggestions if str(item).strip())
        output.extend(self._extract_suggestions_from_reply(assistant_reply))
        output.extend(self._fallback_suggestions(intent, analysis))
        return self._dedupe(output)[:4]

    def _compile_intent_heuristic(self, user_text: str) -> dict[str, Any]:
        lowered = user_text.lower()
        intent_type = "analysis"

        if self._looks_like_modify_request(user_text):
            intent_type = "modify"
        elif self._looks_like_query(user_text):
            intent_type = "query"

        hard_constraints: list[str] = []
        if any(
            token in lowered for token in ("same map size", "no map expansion", "don't enlarge", "do not enlarge")
        ) or any(
            token in user_text for token in ("\u4e0d\u589e\u52a0\u5730\u56fe", "\u4e0d\u8981\u52a0\u5927\u5730\u56fe")
        ):
            hard_constraints.append("keep_map_size")
        if "solvable" in lowered or "\u53ef\u89e3" in user_text:
            hard_constraints.append("keep_solvable")

        soft_targets: list[str] = []
        if "harder" in lowered or "\u66f4\u96be" in user_text:
            soft_targets.append("increase_difficulty")
        if "easier" in lowered or "\u66f4\u7b80\u5355" in user_text or "\u6559\u5b66" in user_text:
            soft_targets.append("decrease_difficulty")
        if "teaching" in lowered or "\u6559\u5b66" in user_text:
            soft_targets.append("teaching_level")

        return {
            "intent_type": intent_type,
            "hard_constraints": hard_constraints,
            "soft_targets": soft_targets,
            "raw_user_text": user_text,
        }

    def _fallback_suggestions(self, intent: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
        solve = analysis.get("solve", {})
        score = analysis.get("score", {})
        suggestions: list[str] = []
        if not solve.get("solvable"):
            suggestions.append("Add one clearer lane or remove one blocking piece to restore solvability.")
        if score.get("difficulty") == "easy":
            suggestions.append("Increase branching around the target path to make the level less trivial.")
        if intent.get("intent_type") == "modify":
            suggestions.append("Apply one minimal board edit that preserves solvability, then compare the new solve metrics.")
        if not suggestions:
            suggestions.append("Try one small board change, then compare the solve metrics.")
        return suggestions

    def _try_parse_json_object(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None
        raw = text.strip()
        candidates = [raw]
        fenced_match = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fenced_match:
            candidates.append(fenced_match.group(1).strip())
        plain_match = re.search(r"(\{.*\})", raw, re.DOTALL)
        if plain_match:
            candidates.append(plain_match.group(1).strip())
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return None

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            value = str(value).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            output.append(value)
        return output

    def _build_initial_state(self, request: LevelAgentRequest, run_modify_agent: bool = False) -> AgentState:
        user_id = request.user_id
        session_id = request.session_id
        session_context = SESSION_CONTEXT_STORE.get_context(user_id, session_id, request.level)
        working_level = copy.deepcopy(request.level or session_context.get("working_level") or {})
        rule_pack = resolve_rule_pack(request.rule_pack)
        return {
            "request": request,
            "user_id": user_id,
            "session_id": session_id,
            "session_context": copy.deepcopy(session_context),
            "resolved_user_request": request.user_request,
            "run_modify_agent": run_modify_agent,
            "rule_pack": rule_pack,
            "history_messages": list(session_context.get("messages", [])),
            "working_level": working_level,
            "rule_context": "",
            "rule_hits": [],
            "tool_trace": [],
            "warnings": [],
            "debug_trace": [],
            "design_brief": {},
            "critic_report": {},
            "controller_decision": {},
        }

    def _finalize_response(self, request: LevelAgentRequest, result: AgentState) -> LevelAgentResponse:
        user_id = request.user_id
        session_id = request.session_id
        session_context = result.get("session_context", {})
        updated_level = result.get("updated_level")
        if not updated_level:
            updated_level = None

        history_messages = result.get("history_messages", [])
        response_warnings = list(result.get("warnings", []))
        response_warnings.extend(result.get("modify_agent_output", {}).get("warnings", []))
        response_warnings = self._dedupe(response_warnings)
        new_context = {
            "title": session_context.get("title") or "New chat",
            "messages": history_messages,
            "working_level": copy.deepcopy(result.get("working_level") or request.level),
            "analysis_summary": {
                "text": result.get("analysis_summary", ""),
                "suggestions": result.get("suggestions", []),
            },
            "last_intent": result.get("intent", {}),
            "suggestions": result.get("suggestions", []),
        }
        SESSION_CONTEXT_STORE.save_context(user_id, session_id, new_context)

        chat_messages = [
            ChatMessageEntry(role=item.get("role", "assistant"), content=str(item.get("content", "")))
            for item in history_messages
            if item.get("role") in {"user", "assistant", "system"} and str(item.get("content", "")).strip()
        ]

        response = LevelAgentResponse(
            analysis_summary=result.get("analysis_summary", ""),
            suggestions=result.get("suggestions", []),
            modify_agent_status=result.get("modify_agent_status", "mocked"),
            modify_agent_output=result.get("modify_agent_output", {}),
            rule_refactor_status=result.get("rule_refactor_status", "placeholder"),
            rule_refactor_output=result.get("rule_refactor_output", {}),
            intent=result.get("intent", {}),
            userId=user_id,
            sessionId=session_id,
            message=result.get("assistant_reply", result.get("analysis_summary", "")),
            updatedLevel=updated_level,
            analysis=AnalysisBundle(**(result.get("analysis", {}))),
            warnings=response_warnings,
            messages=chat_messages,
            toolTrace=result.get("tool_trace", []),
            designBrief=(
                DesignBrief.model_validate(result.get("design_brief", {}))
                if result.get("design_brief")
                else None
            ),
            criticReport=(
                CriticReport.model_validate(result.get("critic_report", {}))
                if result.get("critic_report")
                else None
            ),
            controllerDecision=(
                ControllerDecision.model_validate(result.get("controller_decision", {}))
                if result.get("controller_decision")
                else None
            ),
        )
        if request.debug:
            LOGGER.info("LangGraph debug trace session=%s: %s", session_id, result.get("debug_trace", []))
        return response

    def _chunk_text(self, text: str, chunk_size: int = 20) -> list[str]:
        value = text or ""
        return [value[index:index + chunk_size] for index in range(0, len(value), chunk_size)] or [""]

    def run(self, request: LevelAgentRequest) -> LevelAgentResponse:
        result: AgentState = self.graph.invoke(self._build_initial_state(request))
        return self._finalize_response(request, result)

    def run_modify_job(
        self,
        request: LevelAgentRequest,
        intent: dict[str, Any] | None = None,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        def emit(stage: str, message: str, **extra: Any) -> None:
            if progress_callback:
                progress_callback({"stage": stage, "message": message, **extra})

        state = self._build_initial_state(request, run_modify_agent=True)
        if intent and intent.get("design_brief"):
            state["design_brief"] = dict(intent.get("design_brief") or {})
            state["intent"] = {
                "intent_type": intent.get("intent_type", "modify"),
                "hard_constraints": list(intent.get("hard_constraints", []) or []),
                "soft_targets": list(intent.get("soft_targets", []) or []),
                "raw_user_text": intent.get("raw_user_text") or request.user_request,
                "design_brief": dict(intent.get("design_brief") or {}),
            }
            brief = DesignBrief.model_validate(state["design_brief"])
            state["rule_context"] = brief.retrieved_rule_context
            state["rule_hits"] = list(brief.retrieved_rule_hits)
            emit("planner", "Loaded the design brief from the chat request.")
        else:
            emit("intent_compiler", "Compiling the modification intent...")
            state = self._intent_compiler_node(state)

        current_user_message = self._current_user_message(state)
        emit("validate", "Checking the current board before modification...")
        analysis, warnings, summary_seed = self._analyze_level(
            request=request,
            working_level=copy.deepcopy(state.get("working_level") or request.level),
            rule_pack=state["rule_pack"],
            intent=state.get("intent", {}),
        )
        state["analysis"] = analysis
        state["warnings"] = warnings
        if not state.get("rule_context"):
            emit("retrieve_rules", "Loading relevant rule notes...")
            rule_context, rule_hits = self._retrieve_rule_context(
                current_user_message=current_user_message,
                compiled_intent=state.get("intent", {}),
                summary_seed=summary_seed,
                rule_pack=state["rule_pack"],
            )
            state["rule_context"] = rule_context
            state["rule_hits"] = rule_hits
            state["tool_trace"] = self._append_tool_trace(
                list(state.get("tool_trace", [])),
                "retrieve_rule_docs",
                {"query": self._build_rule_query(current_user_message, state.get("intent", {}), summary_seed)},
                {"hits": rule_hits},
            )

        emit("modify_agent", "Running the multi-agent generation loop...")
        state = self._modify_agent_node(state, progress_callback=progress_callback)
        modify_output = state.get("modify_agent_output", {})
        response_warnings = self._dedupe(list(state.get("warnings", [])))
        return {
            "message": modify_output.get("message", ""),
            "intent": state.get("intent", {}),
            "analysis": modify_output.get("analysis") or state.get("analysis") or analysis,
            "warnings": response_warnings,
            "modifyAgentStatus": state.get("modify_agent_status", modify_output.get("status", "rejected")),
            "modifyAgentOutput": modify_output,
            "updatedLevel": modify_output.get("updated_level"),
            "toolTrace": state.get("tool_trace", []),
            "designBrief": state.get("design_brief", {}),
            "criticReport": state.get("critic_report", {}),
            "controllerDecision": state.get("controller_decision", {}),
        }

    def run_stream(self, request: LevelAgentRequest) -> Iterator[dict[str, Any]]:
        yield {"type": "status", "stage": "start", "message": "Connecting to the assistant..."}
        state = self._build_initial_state(request)
        yield {"type": "status", "stage": "planner", "message": "Planning the request and loading rule grounding..."}
        state = self._intent_compiler_node(state)
        yield {"type": "status", "stage": "analysis", "message": "Checking the current level and summarizing the request..."}
        state = self._chat_logic_node(state)
        state = self._modify_agent_node(state)
        state = self._rule_refactor_node(state)
        response = self._finalize_response(request, state)

        yield {"type": "message_start", "message": ""}
        for chunk in self._chunk_text(response.message, chunk_size=24):
            if chunk:
                yield {"type": "message_delta", "delta": chunk}

        yield {"type": "complete", "payload": response.model_dump(by_alias=True)}
