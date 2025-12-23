from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal

@dataclass(frozen=True)
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    call_id: str

@dataclass(frozen=True)
class PlanStep:
    kind: Literal["tool_call", "parallel_tool_calls", "final"]
    tool_call: ToolCall | None = None
    parallel_calls: list[ToolCall] | None = None
    final_template: str | None = None

@dataclass(frozen=True)
class Plan:
    user_input: str
    steps: list[PlanStep]

@dataclass
class ExecutionResult:
    output: str
    trace: list[dict] = field(default_factory=list)
