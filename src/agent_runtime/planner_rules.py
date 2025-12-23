from __future__ import annotations
import re
import json
import hashlib

from agent_runtime.types import Plan, PlanStep, ToolCall
from agent_runtime.tools.registry import ToolRegistry

class RulesPlanner:
    """
    Deterministic rules-first planner.
    Produces stable call_ids so plans can be compared and audited without re-running.
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def plan(self, user_input: str) -> Plan:
        text = user_input.strip()

        wants_weather = self._mentions_weather(text)
        wants_math = self._looks_like_math(text) or self._contains_numbers(text)

        if wants_weather and wants_math:
            city = self._extract_city(text) or "San Francisco"
            expr = self._extract_math_expr(text)

            call_weather = self._call(text, 0, "weather", {"location": city})
            call_math = self._call(text, 1, "math", {"expression": expr})

            steps = [
                PlanStep(kind="parallel_tool_calls", parallel_calls=[call_weather, call_math]),
                PlanStep(kind="final", final_template="weather_plus_math"),
            ]
            return Plan(user_input=text, steps=steps)

        if wants_math:
            expr = self._extract_math_expr(text)
            call = self._call(text, 0, "math", {"expression": expr})
            steps = [PlanStep(kind="tool_call", tool_call=call), PlanStep(kind="final", final_template="math")]
            return Plan(user_input=text, steps=steps)

        if wants_weather:
            city = self._extract_city(text) or "San Francisco"
            call = self._call(text, 0, "weather", {"location": city})
            steps = [PlanStep(kind="tool_call", tool_call=call), PlanStep(kind="final", final_template="weather")]
            return Plan(user_input=text, steps=steps)

        call = self._call(text, 0, "web_search", {"query": text})
        steps = [PlanStep(kind="tool_call", tool_call=call), PlanStep(kind="final", final_template="search_summary")]
        return Plan(user_input=text, steps=steps)

    def _call(self, user_input: str, ordinal: int, tool_name: str, arguments: dict) -> ToolCall:
        call_id = self._make_call_id(user_input, ordinal, tool_name, arguments)
        return ToolCall(tool_name=tool_name, arguments=arguments, call_id=call_id)

    def _make_call_id(self, user_input: str, ordinal: int, tool_name: str, arguments: dict) -> str:
        payload = {
            "user_input": user_input,
            "ordinal": ordinal,
            "tool": tool_name,
            "arguments": arguments,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(blob).hexdigest()[:12]
        return f"{tool_name}_{ordinal}_{digest}"

    def _looks_like_math(self, text: str) -> bool:
        return bool(re.search(r"\d\s*[\+\-\*/\^]\s*\d", text))

    def _contains_numbers(self, text: str) -> bool:
        return bool(re.search(r"\d", text))

    def _mentions_weather(self, text: str) -> bool:
        t = text.lower()
        return "weather" in t or "forecast" in t or "temperature" in t

    def _extract_city(self, text: str) -> str | None:
        m = re.search(r"(?:weather|forecast|temperature)\s+(?:in|for)\s+([A-Za-z .'-]+)", text, flags=re.IGNORECASE)
        if not m:
            return None
        return m.group(1).strip()

    def _extract_math_expr(self, text: str) -> str:
        candidates = re.findall(r"[0-9\s\+\-\*/\^\(\)\.]+", text)
        candidates = [c.strip() for c in candidates if c.strip()]
        for c in candidates:
            if any(op in c for op in ["+", "-", "*", "/", "^"]) and re.search(r"\d", c):
                return c
        nums = re.findall(r"\d+(?:\.\d+)?", text)
        if nums:
            return nums[0]
        return "0"
