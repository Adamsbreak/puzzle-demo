from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from backend.ai.tools import ToolExecutionError, ToolRuntimeContext, execute_tool, tool_names, tool_schemas


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolAgentResult:
    final_text: str
    final_json: dict[str, Any] | None
    current_level: dict[str, Any]
    tool_trace: list[dict[str, Any]]


def coerce_message_content(response: Any) -> str:
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


def try_parse_json_object(text: str) -> dict[str, Any] | None:
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


def run_tool_agent(
    *,
    llm: Any,
    agent_role: str,
    system_prompt: str,
    payload: dict[str, Any],
    runtime_context: ToolRuntimeContext,
    max_tool_rounds: int = 6,
    final_json_hint: str | None = None,
) -> ToolAgentResult:
    messages: list[Any] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]

    bound_llm = None
    if hasattr(llm, "bind_tools"):
        try:
            bound_llm = llm.bind_tools(tool_schemas(agent_role))
        except Exception as error:  # pragma: no cover - depends on runtime provider
            LOGGER.warning("bind_tools failed for %s agent: %s", agent_role, error)

    if bound_llm is None:
        fallback_prompt = system_prompt
        if final_json_hint:
            fallback_prompt += "\n\nFinal output reminder:\n" + final_json_hint
        response = llm.invoke(
            [
                SystemMessage(content=fallback_prompt),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        text = coerce_message_content(response)
        return ToolAgentResult(
            final_text=text,
            final_json=try_parse_json_object(text),
            current_level=runtime_context.current_level,
            tool_trace=[entry.model_dump(mode="python", by_alias=True) for entry in runtime_context.trace],
        )

    allowed_tools = set(tool_names(agent_role))

    for _ in range(max_tool_rounds):
        response = bound_llm.invoke(messages)
        messages.append(response)
        tool_calls = list(getattr(response, "tool_calls", []) or [])
        if tool_calls:
            for call in tool_calls:
                tool_name = str(call.get("name") or "").strip()
                arguments = call.get("args") if isinstance(call.get("args"), dict) else {}
                if tool_name not in allowed_tools:
                    tool_result: dict[str, Any] = {"ok": False, "error": f"Tool {tool_name} is not allowed."}
                else:
                    try:
                        tool_result = execute_tool(runtime_context, tool_name, arguments)
                    except ToolExecutionError as error:
                        tool_result = {"ok": False, "error": str(error)}
                messages.append(
                    ToolMessage(
                        content=json.dumps(tool_result, ensure_ascii=False),
                        tool_call_id=str(call.get("id") or tool_name),
                    )
                )
            continue

        text = coerce_message_content(response)
        return ToolAgentResult(
            final_text=text,
            final_json=try_parse_json_object(text),
            current_level=runtime_context.current_level,
            tool_trace=[entry.model_dump(mode="python", by_alias=True) for entry in runtime_context.trace],
        )

    reminder = final_json_hint or "Return the final JSON object now."
    response = bound_llm.invoke(messages + [HumanMessage(content=reminder)])
    text = coerce_message_content(response)
    return ToolAgentResult(
        final_text=text,
        final_json=try_parse_json_object(text),
        current_level=runtime_context.current_level,
        tool_trace=[entry.model_dump(mode="python", by_alias=True) for entry in runtime_context.trace],
    )
