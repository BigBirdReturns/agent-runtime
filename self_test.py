import asyncio
import sys
from pathlib import Path

# Allow running without installation
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from agent_runtime.planner_rules import RulesPlanner
from agent_runtime.executor import Executor
from agent_runtime.tools.registry import build_default_registry

async def main():
    registry = build_default_registry()
    planner = RulesPlanner(registry)
    executor = Executor(registry)

    cases = [
        ("What is 12*13 and then add 5?", ["math"]),
        ("weather in Seattle", ["weather"]),
        ("weather in Seattle and 12*13", ["weather", "math"]),
        ("search something obscure", ["web_search"]),
    ]

    for text, expected_tools in cases:
        plan = planner.plan(text)
        used = []
        for step in plan.steps:
            if step.kind == "tool_call" and step.tool_call:
                used.append(step.tool_call.tool_name)
            if step.kind == "parallel_tool_calls" and step.parallel_calls:
                used.extend([c.tool_name for c in step.parallel_calls])

        for t in expected_tools:
            assert t in used, (text, used)

        result = await executor.execute(plan)
        assert isinstance(result.output, str) and len(result.output) > 0

    print("SELF TEST OK")

if __name__ == "__main__":
    asyncio.run(main())
