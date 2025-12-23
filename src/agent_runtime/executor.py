from __future__ import annotations
import asyncio
import time
from typing import Any

from agent_runtime.types import Plan, PlanStep, ToolCall, ExecutionResult
from agent_runtime.tools.registry import ToolRegistry
from agent_runtime.tools.base import ToolError

class Executor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, plan: Plan) -> ExecutionResult:
        ctx: dict[str, Any] = {"user_input": plan.user_input, "tool_results": []}
        trace: list[dict] = []

        for step in plan.steps:
            if step.kind == "tool_call" and step.tool_call:
                out = await self._run_one(step.tool_call, trace)
                ctx["tool_results"].append({"call": step.tool_call, "result": out})

            elif step.kind == "parallel_tool_calls" and step.parallel_calls:
                outs = await self._run_parallel(step.parallel_calls, trace)
                for call in step.parallel_calls:
                    ctx["tool_results"].append({"call": call, "result": outs.get(call.call_id, {})})

            elif step.kind == "final":
                output = self._render_final(step.final_template or "default", ctx)
                return ExecutionResult(output=output, trace=trace)

        return ExecutionResult(output=self._render_final("default", ctx), trace=trace)

    async def _run_one(self, call: ToolCall, trace: list[dict]) -> dict[str, Any]:
        tool = self.registry.get(call.tool_name)
        started = time.time()
        try:
            result = await tool.run(call.arguments)
            trace.append({"call_id": call.call_id, "tool": call.tool_name, "ok": True, "ms": int((time.time() - started) * 1000)})
            return result
        except ToolError as e:
            trace.append({"call_id": call.call_id, "tool": call.tool_name, "ok": False, "error": {"code": e.code, "message": str(e)}, "ms": int((time.time() - started) * 1000)})
            return {"error": {"code": e.code, "message": str(e)}}
        except Exception as e:
            trace.append({"call_id": call.call_id, "tool": call.tool_name, "ok": False, "error": {"code": "exception", "message": str(e)}, "ms": int((time.time() - started) * 1000)})
            return {"error": {"code": "exception", "message": str(e)}}

    async def _run_parallel(self, calls: list[ToolCall], trace: list[dict]) -> dict[str, dict[str, Any]]:
        tasks = [self._run_one(c, trace) for c in calls]
        results = await asyncio.gather(*tasks)
        return {calls[i].call_id: results[i] for i in range(len(calls))}

    def _render_final(self, template: str, ctx: dict[str, Any]) -> str:
        results = ctx.get("tool_results", [])

        def find(tool_name: str) -> dict[str, Any]:
            for item in results:
                call = item.get("call")
                if call and call.tool_name == tool_name:
                    return item.get("result", {})
            return {}

        if template == "math":
            r = find("math")
            if "error" in r:
                return f"Math tool failed: {r['error']['message']}"
            return self._format_math(ctx["user_input"], r)

        if template == "weather":
            r = find("weather")
            if "error" in r:
                return f"Weather tool failed: {r['error']['message']}"
            return f"Weather for {r.get('location','Unknown')}: {r.get('summary','')}".strip()

        if template == "weather_plus_math":
            wr = find("weather")
            mr = find("math")
            parts: list[str] = []
            if "error" in wr:
                parts.append(f"Weather tool failed: {wr['error']['message']}")
            else:
                parts.append(f"Weather for {wr.get('location','Unknown')}: {wr.get('summary','')}".strip())
            if "error" in mr:
                parts.append(f"Math tool failed: {mr['error']['message']}")
            else:
                parts.append(self._format_math(ctx["user_input"], mr))
            return "\n".join([p for p in parts if p])

        if template == "search_summary":
            r = find("web_search")
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
        expr = user_input.strip()
        if len(expr) > 80:
            expr = "expression"
        # Render ints cleanly when possible
        try:
            if abs(val - int(val)) < 1e-9:
                val = int(val)
        except Exception:
            pass
        return f"{expr} = {val}"
