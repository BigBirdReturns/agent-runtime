from __future__ import annotations
from typing import TypedDict, Literal, Any

class PlanStepTrace(TypedDict, total=False):
    kind: str
    tool: str
    call_id: str
    arguments: dict[str, Any]
    calls: list[dict[str, Any]]
    template: str

class PlanTraceItem(TypedDict):
    type: Literal["plan"]
    user_input: str
    steps: list[PlanStepTrace]

class ToolErrorTrace(TypedDict):
    code: str
    message: str

class ToolCallTraceItem(TypedDict, total=False):
    type: Literal["tool_call"]
    call_id: str
    tool: str
    ok: bool
    ms: int
    error: ToolErrorTrace
