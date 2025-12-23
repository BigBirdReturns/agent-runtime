from __future__ import annotations
import asyncio
import time
from typing import Any

from agent_runtime.types import Plan, PlanStep, ToolCall, ExecutionResult
from agent_runtime.tools.registry import ToolRegistry
from agent_runtime.tools.base import ToolError

class Executor:
    def __init__(self, registry: ToolRegistry, *, max_tool_calls: int = 10):
        self.registry = registry
        self.max_tool_calls = int(max_tool_calls)
        self._call_count = 0

    async def execute(self, plan: Plan) -> ExecutionResult:
        ctx: dict[str, Any] = {"user_input": plan.user_input, "tool_results": []}

        trace: list[dict] = [{
            "type": "plan",
            "user_input": plan.user_input,
            "steps": [self._serialize_step(s) for s in plan.steps],
        }]

        for step in plan.steps:
            match step.kind:
                case "tool_call":
                    assert step.tool_call is not None
                    out = await self._run_one(step.tool_call, trace)
                    ctx["tool_results"].append({"call": step.tool_call, "result": out})

                case "parallel_tool_calls":
                    assert step.parallel_calls is not None
                    outs = await self._run_parallel(step.parallel_calls)
                    # Merge results in the same order as the calls list (deterministic)
                    for call in step.parallel_calls:
                        ctx["tool_results"].append({"call": call, "result": outs["results"].get(call.call_id, {})})
                    # Merge traces in call order (deterministic)
                    for call in step.parallel_calls:
                        trace.extend(outs["traces"].get(call.call_id, []))

                case "final":
                    output = self._render_final(step.final_template or "default", ctx)
                    return ExecutionResult(output=output, trace=trace)

                case _:
                    return ExecutionResult(output="Invalid plan step.", trace=trace)

        return ExecutionResult(output=self._render_final("default", ctx), trace=trace)

    def _serialize_step(self, step: PlanStep) -> dict[str, Any]:
        if step.kind == "tool_call" and step.tool_call:
            return {
                "kind": "tool_call",
                "tool": step.tool_call.tool_name,
                "call_id": step.tool_call.call_id,
                "arguments": step.tool_call.arguments,
            }
        if step.kind == "parallel_tool_calls" and step.parallel_calls:
            return {
                "kind": "parallel_tool_calls",
                "calls": [
                    {"tool": c.tool_name, "call_id": c.call_id, "arguments": c.arguments}
                    for c in step.parallel_calls
                ],
            }
        if step.kind == "final":
            return {"kind": "final", "template": step.final_template}
        return {"kind": step.kind}

    def _bump_call_budget(self) -> None:
        self._call_count += 1
        if self._call_count > self.max_tool_calls:
            raise ToolError("Max tool calls exceeded", code="rate_limit")

    async def _run_one(self, call: ToolCall, trace: list[dict]) -> dict[str, Any]:
        self._bump_call_budget()
        tool = self.registry.get(call.tool_name)
        started = time.time()
        try:
            result = await tool.run(call.arguments)
            trace.append({
                "type": "tool_call",
                "call_id": call.call_id,
                "tool": call.tool_name,
                "ok": True,
                "ms": int((time.time() - started) * 1000),
            })
            return result
        except ToolError as e:
            trace.append({
                "type": "tool_call",
                "call_id": call.call_id,
                "tool": call.tool_name,
                "ok": False,
                "error": {"code": e.code, "message": str(e)},
                "ms": int((time.time() - started) * 1000),
            })
            return {"error": {"code": e.code, "message": str(e)}}
        except Exception as e:
            trace.append({
                "type": "tool_call",
                "call_id": call.call_id,
                "tool": call.tool_name,
                "ok": False,
                "error": {"code": "exception", "message": str(e)},
                "ms": int((time.time() - started) * 1000),
            })
            return {"error": {"code": "exception", "message": str(e)}}

    async def _run_parallel(self, calls: list[ToolCall]) -> dict[str, Any]:
        async def run_with_local_trace(c: ToolCall):
            local_trace: list[dict] = []
            result = await self._run_one(c, local_trace)
            return c.call_id, result, local_trace

        tasks = [run_with_local_trace(c) for c in calls]
        outputs = await asyncio.gather(*tasks)

        results: dict[str, dict[str, Any]] = {}
        traces: dict[str, list[dict]] = {}
        for call_id, result, local_trace in outputs:
            results[call_id] = result
            traces[call_id] = local_trace

        return {"results": results, "traces": traces}

    def _render_final(self, template: str, ctx: dict[str, Any]) -> str:
        results = ctx.get("tool_results", [])

        def find(tool_name: str) -> dict[str, Any] | None:
            for item in results:
                call = item.get("call")
                if call and call.tool_name == tool_name:
                    return item.get("result", {})
            return None

        if template == "math":
            r = find("math")
            if r is None:
                return "Math tool was not called."
            if "error" in r:
                return f"Math tool failed: {r['error']['message']}"
            return self._format_math(ctx["user_input"], r)

        if template == "weather":
            r = find("weather")
            if r is None:
                return "Weather tool was not called."
            if "error" in r:
                return f"Weather tool failed: {r['error']['message']}"
            return f"Weather for {r.get('location','Unknown')}: {r.get('summary','')}".strip()

        if template == "weather_plus_math":
            wr = find("weather")
            mr = find("math")
            parts: list[str] = []

            if wr is None:
                parts.append("Weather tool was not called.")
            elif "error" in wr:
                parts.append(f"Weather tool failed: {wr['error']['message']}")
            else:
                parts.append(f"Weather for {wr.get('location','Unknown')}: {wr.get('summary','')}".strip())

            if mr is None:
                parts.append("Math tool was not called.")
            elif "error" in mr:
                parts.append(f"Math tool failed: {mr['error']['message']}")
            else:
                parts.append(self._format_math(ctx["user_input"], mr))

            return "\n".join([p for p in parts if p])

        if template == "search_summary":
            r = find("web_search")
            if r is None:
                return "Search tool was not called."
            if "error" in r:
                return f"Search tool failed: {r['error']['message']}"
            items = r.get("results", [])
            if not items:
                return "No results."
            top = items[0]
            title = top.get("title", "Top result")
            snippet = top.get("snippet", "")
            return f"{title}\n{snippet}".strip()

        return "Done."

    def _format_math(self, user_input: str, r: dict[str, Any]) -> str:
        val = r.get("result", None)
        if val is None:
            return "No math result."

        # Render ints cleanly when possible, safely
        if isinstance(val, (int, float)):
            try:
                if abs(float(val) - int(float(val))) < 1e-9:
                    val = int(float(val))
            except (ValueError, OverflowError):
                pass

        expr = user_input.strip()
        if len(expr) > 80:
            expr = "expression"
        return f"{expr} = {val}"
