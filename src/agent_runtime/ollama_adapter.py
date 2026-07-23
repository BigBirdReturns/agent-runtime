from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_runtime.types import Plan, PlanStep, ToolCall

if TYPE_CHECKING:
    from agent_runtime.tools.registry import ToolRegistry


def plan_from_ollama_response(
    user_input: str,
    response: dict[str, Any],
    registry: ToolRegistry,
) -> Plan:
    """Convert the observed native Ollama single-tool response into a plan."""
    message = response.get("message")
    if not isinstance(message, dict):
        raise ValueError("Ollama response is missing a message object")

    tool_calls = message.get("tool_calls")
    if tool_calls is None:
        tool_calls = []
    if not isinstance(tool_calls, list):
        raise ValueError("Ollama message tool_calls must be a list")
    if len(tool_calls) != 1:
        raise ValueError(
            f"Ollama response must contain exactly one tool call; found {len(tool_calls)}"
        )

    native_call = tool_calls[0]
    if not isinstance(native_call, dict):
        raise ValueError("Ollama tool call must be an object")

    call_id = native_call.get("id")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("Ollama tool call is missing a non-empty id")

    function = native_call.get("function")
    if not isinstance(function, dict):
        raise ValueError("Ollama tool call is missing a function object")

    tool_name = function.get("name")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("Ollama tool call function is missing a non-empty name")

    arguments = function.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("Ollama tool call function arguments must be an object")

    try:
        registry.get(tool_name)
    except KeyError:
        raise ValueError(f"Ollama tool call references unregistered tool: {tool_name}") from None

    tool_call = ToolCall(
        tool_name=tool_name,
        arguments=dict(arguments),
        call_id=call_id,
    )
    return Plan(
        user_input=user_input,
        steps=[
            PlanStep(kind="tool_call", tool_call=tool_call),
            PlanStep(kind="final", final_template=tool_name),
        ],
    )
