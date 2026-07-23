from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from agent_runtime.api import AgentRunRequest, run_agent


class _Response:
    def __init__(self, payload: object, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class _Client:
    response: _Response
    posted_url: str | None = None
    posted_json: dict | None = None
    timeout: float | None = None

    def __init__(self, *, timeout: float):
        type(self).timeout = timeout

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def post(self, url: str, *, json: dict) -> _Response:
        type(self).posted_url = url
        type(self).posted_json = json
        return type(self).response


class OllamaApiTests(unittest.TestCase):
    def test_ollama_math_executes_one_math_call_and_prepends_provider_trace(self) -> None:
        _Client.response = _Response(
            {
                "model": "qwen3.5:9b-q4_K_M",
                "prompt_eval_count": 73,
                "eval_count": 19,
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_math_17",
                            "function": {"name": "math", "arguments": {"expression": "12*13"}},
                        }
                    ]
                },
            }
        )

        with patch("agent_runtime.api.httpx.AsyncClient", _Client):
            result = asyncio.run(
                run_agent(AgentRunRequest(input="12*13", planner="ollama_math", debug=True))
            )

        self.assertEqual(result.output, "12*13 = 156")
        self.assertEqual(_Client.timeout, 30.0)
        self.assertEqual(_Client.posted_url, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(_Client.posted_json["model"], "qwen3.5:9b-q4_K_M")
        self.assertFalse(_Client.posted_json["stream"])
        self.assertFalse(_Client.posted_json["think"])
        self.assertEqual(_Client.posted_json["options"], {"temperature": 0})
        self.assertEqual([tool["function"]["name"] for tool in _Client.posted_json["tools"]], ["math"])
        self.assertEqual(result.trace[0]["type"], "provider_call")
        self.assertEqual(result.trace[0]["provider"], "ollama")
        self.assertEqual(result.trace[0]["configured_model"], "qwen3.5:9b-q4_K_M")
        self.assertEqual(result.trace[0]["returned_model"], "qwen3.5:9b-q4_K_M")
        self.assertTrue(result.trace[0]["ok"])
        self.assertEqual(result.trace[0]["http_status"], 200)
        self.assertEqual(result.trace[0]["input_tokens"], 73)
        self.assertEqual(result.trace[0]["output_tokens"], 19)
        self.assertEqual(result.trace[0]["total_tokens"], 92)
        self.assertEqual(result.trace[0]["provider_billed_cost_usd"], 0.0)
        self.assertEqual(result.trace[0]["cost_basis"], "local-unbilled")

    def test_ollama_math_does_not_invent_missing_usage(self) -> None:
        _Client.response = _Response(
            {
                "model": "qwen3.5:9b-q4_K_M",
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_math_18",
                            "function": {"name": "math", "arguments": {"expression": "2+2"}},
                        }
                    ]
                },
            }
        )

        with patch("agent_runtime.api.httpx.AsyncClient", _Client):
            result = asyncio.run(
                run_agent(AgentRunRequest(input="2+2", planner="ollama_math", debug=True))
            )

        self.assertIsNone(result.trace[0]["input_tokens"])
        self.assertIsNone(result.trace[0]["output_tokens"])
        self.assertIsNone(result.trace[0]["total_tokens"])

    def test_ollama_math_rejects_returned_model_mismatch(self) -> None:
        _Client.response = _Response({"model": "other", "message": {"tool_calls": []}})

        with patch("agent_runtime.api.httpx.AsyncClient", _Client):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(run_agent(AgentRunRequest(input="12*13", planner="ollama_math")))

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.detail, {"code": "ollama_model_mismatch"})


if __name__ == "__main__":
    unittest.main()
