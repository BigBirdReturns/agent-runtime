from __future__ import annotations
import re
import uuid

from agent_runtime.types import Plan, PlanStep, ToolCall
from agent_runtime.tools.registry import ToolRegistry

class RulesPlanner:
    """
    Deterministic rules-first planner.
    This satisfies "one Agent API" while keeping planning auditable.
    Replace with an LLM planner later if desired, but keep Plan schema stable.
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def plan(self, user_input: str) -> Plan:
        text = user_input.strip()

        wants_weather = self._mentions_weather(text)
        wants_math = self._looks_like_math(text)

        if wants_weather and wants_math:
            city = self._extract_city(text) or "San Francisco"
            calls = [
                ToolCall(tool_name="weather", arguments={"location": city}, call_id=self._cid()),
                ToolCall(tool_name="math", arguments={"expression": self._extract_math_expr(text)}, call_id=self._cid()),
            ]
            steps = [
                PlanStep(kind="parallel_tool_calls", parallel_calls=calls),
                PlanStep(kind="final", final_template="weather_plus_math"),
            ]
            return Plan(user_input=text, steps=steps)

        if wants_math:
            call = ToolCall(tool_name="math", arguments={"expression": self._extract_math_expr(text)}, call_id=self._cid())
            steps = [PlanStep(kind="tool_call", tool_call=call), PlanStep(kind="final", final_template="math")]
            return Plan(user_input=text, steps=steps)

        if wants_weather:
            city = self._extract_city(text) or "San Francisco"
            call = ToolCall(tool_name="weather", arguments={"location": city}, call_id=self._cid())
            steps = [PlanStep(kind="tool_call", tool_call=call), PlanStep(kind="final", final_template="weather")]
            return Plan(user_input=text, steps=steps)

        call = ToolCall(tool_name="web_search", arguments={"query": text}, call_id=self._cid())
        steps = [PlanStep(kind="tool_call", tool_call=call), PlanStep(kind="final", final_template="search_summary")]
        return Plan(user_input=text, steps=steps)

    def _cid(self) -> str:
        return uuid.uuid4().hex[:12]

    def _looks_like_math(self, text: str) -> bool:
        return bool(re.search(r"\d\s*[\+\-\*/\^]\s*\d", text))

    def _mentions_weather(self, text: str) -> bool:
        t = text.lower()
        return "weather" in t or "forecast" in t or "temperature" in t

    def _extract_city(self, text: str) -> str | None:
        m = re.search(r"(?:weather|forecast|temperature)\s+(?:in|for)\s+([A-Za-z .'-]+)", text, flags=re.IGNORECASE)
        if not m:
            return None
        return m.group(1).strip()

    def _extract_math_expr(self, text: str) -> str:
        m = re.search(r"(\d[\d\s\+\-\*/\^\(\)\.]+\d)", text)
        if m:
            return m.group(1).strip()
        return text
