from __future__ import annotations

import asyncio
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from agent_runtime.ollama_adapter import plan_from_ollama_response
from agent_runtime.executor import Executor
from agent_runtime.tools.registry import build_default_registry
from agent_runtime.types import Plan, PlanStep, ToolCall


class _Registry:
    def __init__(self, names: set[str]):
        self.names = names

    def get(self, name: str) -> object:
        if name not in self.names:
            raise KeyError(f"Unknown tool: {name}")
        return object()


OBSERVED_RESPONSE = {
    "message": {
        "tool_calls": [
            {
                "id": "call_math_17",
                "function": {
                    "index": 0,
                    "name": "math",
                    "arguments": {"expression": "12*13"},
                },
            }
        ]
    }
}


class OllamaAdapterTests(unittest.TestCase):
    def test_observed_single_registered_tool_call_becomes_plan(self) -> None:
        plan = plan_from_ollama_response(
            "What is 12*13?",
            OBSERVED_RESPONSE,
            _Registry({"math"}),
        )

        self.assertEqual(
            plan,
            Plan(
                user_input="What is 12*13?",
                steps=[
                    PlanStep(
                        kind="tool_call",
                        tool_call=ToolCall(
                            tool_name="math",
                            arguments={"expression": "12*13"},
                            call_id="call_math_17",
                        ),
                    ),
                    PlanStep(kind="final", final_template="math"),
                ],
            ),
        )
    def test_observed_math_call_executes_with_semantic_output_and_trace(self) -> None:
        registry = build_default_registry()
        plan = plan_from_ollama_response("12*13", OBSERVED_RESPONSE, registry)

        result = asyncio.run(Executor(registry).execute(plan))

        self.assertEqual(result.output, "12*13 = 156")
        self.assertEqual(len(result.trace), 2)
        self.assertEqual(
            result.trace[0]["steps"][-1],
            {"kind": "final", "template": "math"},
        )
        self.assertEqual(
            {key: result.trace[1][key] for key in ("type", "call_id", "tool", "ok")},
            {
                "type": "tool_call",
                "call_id": "call_math_17",
                "tool": "math",
                "ok": True,
            },
        )
        self.assertNotIn("error", result.trace[1])

    def test_missing_tool_call_is_rejected(self) -> None:
        response = {"message": {"tool_calls": []}}

        with self.assertRaisesRegex(
            ValueError,
            r"^Ollama response must contain exactly one tool call; found 0$",
        ):
            plan_from_ollama_response("hello", response, _Registry({"math"}))

    def test_multiple_tool_calls_are_rejected(self) -> None:
        response = copy.deepcopy(OBSERVED_RESPONSE)
        response["message"]["tool_calls"].append(
            {
                "id": "call_math_18",
                "function": {
                    "index": 1,
                    "name": "math",
                    "arguments": {"expression": "1+1"},
                },
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            r"^Ollama response must contain exactly one tool call; found 2$",
        ):
            plan_from_ollama_response("hello", response, _Registry({"math"}))

    def test_missing_native_call_id_is_rejected(self) -> None:
        response = copy.deepcopy(OBSERVED_RESPONSE)
        del response["message"]["tool_calls"][0]["id"]

        with self.assertRaisesRegex(
            ValueError,
            r"^Ollama tool call is missing a non-empty id$",
        ):
            plan_from_ollama_response("hello", response, _Registry({"math"}))

    def test_unregistered_tool_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"^Ollama tool call references unregistered tool: math$",
        ):
            plan_from_ollama_response("hello", OBSERVED_RESPONSE, _Registry(set()))


if __name__ == "__main__":
    unittest.main()
