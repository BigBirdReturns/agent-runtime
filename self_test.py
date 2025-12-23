import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from agent_runtime.planner_rules import RulesPlanner
from agent_runtime.executor import Executor
from agent_runtime.tools.registry import build_default_registry

async def main():
    registry = build_default_registry()
    planner = RulesPlanner(registry)
    executor = Executor(registry, max_tool_calls=10)

    cases = [
        ("What is 12*13 and then add 5?", ["math"]),
        ("weather in Seattle", ["weather"]),
        ("weather in Seattle and 12*13", ["weather", "math"]),
        ("search something obscure", ["web_search"]),
        ("5", ["math"]),  # single number
    ]

    for text, expected_tools in cases:
        plan1 = planner.plan(text)
        plan2 = planner.plan(text)
        assert plan1.steps == plan2.steps, "Planner must be deterministic"

        used = []
        for step in plan1.steps:
            if step.kind == "tool_call" and step.tool_call:
                used.append(step.tool_call.tool_name)
            if step.kind == "parallel_tool_calls" and step.parallel_calls:
                used.extend([c.tool_name for c in step.parallel_calls])

        for t in expected_tools:
            assert t in used, (text, used)

        result = await executor.execute(plan1)
        assert isinstance(result.output, str) and len(result.output) > 0
        # Trace should start with plan
        assert result.trace and result.trace[0].get("type") == "plan"

    # Parallel trace determinism check: ensure trace merges in call order
    plan = planner.plan("weather in Seattle and 12*13")
    result = await executor.execute(plan)
    tool_calls = [t for t in result.trace if t.get("type") == "tool_call"]
    assert len(tool_calls) >= 2
    assert tool_calls[0]["tool"] == "weather"
    assert tool_calls[1]["tool"] == "math"

    print("SELF TEST OK")

if __name__ == "__main__":
    asyncio.run(main())
