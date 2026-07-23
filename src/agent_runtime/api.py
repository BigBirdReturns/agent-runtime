import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_runtime.ollama_adapter import plan_from_ollama_response
from agent_runtime.planner_rules import RulesPlanner
from agent_runtime.executor import Executor
from agent_runtime.tools.registry import build_default_registry

router = APIRouter()


def _ollama_token_usage(payload: dict[str, Any]) -> dict[str, int | None]:
    """Retain Ollama's observed token counters without inventing missing values."""
    prompt_tokens = payload.get("prompt_eval_count")
    completion_tokens = payload.get("eval_count")
    if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
        prompt_tokens = None
    if not isinstance(completion_tokens, int) or completion_tokens < 0:
        completion_tokens = None
    total_tokens = (
        prompt_tokens + completion_tokens
        if prompt_tokens is not None and completion_tokens is not None
        else None
    )
    return {
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


class AgentRunRequest(BaseModel):
    input: str = Field(..., description="User input to the agent.")
    debug: bool = Field(False, description="If true, return internal trace. Use only for internal testing.")
    planner: Literal["rules", "ollama_math"] = Field(
        "rules",
        description="Planning mode. ollama_math makes one local Ollama math-tool call.",
    )

class AgentRunResponse(BaseModel):
    output: str
    trace: list[dict] | None = None

@router.get("/tools/schemas")
def tool_schemas() -> dict:
    registry = build_default_registry()
    out = {}
    for name, tool in registry.tools.items():
        out[name] = {
            "description": getattr(tool, "description", ""),
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
        }
    return out

@router.post("/agent/run", response_model=AgentRunResponse)
async def run_agent(req: AgentRunRequest) -> AgentRunResponse:
    registry = build_default_registry()
    executor = Executor(registry=registry)

    provider_trace: list[dict[str, Any]] = []
    if req.planner == "rules":
        plan = RulesPlanner(registry=registry).plan(req.input)
    else:
        math_tool = registry.get("math")
        tool_definition = {
            "type": "function",
            "function": {
                "name": "math",
                "description": math_tool.description,
                "parameters": math_tool.input_schema,
            },
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "http://127.0.0.1:11434/api/chat",
                    json={
                        "model": "qwen3.5:9b-q4_K_M",
                        "messages": [{"role": "user", "content": req.input}],
                        "tools": [tool_definition],
                        "stream": False,
                        "think": False,
                        "options": {"temperature": 0},
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail={"code": "ollama_timeout"}) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail={"code": "ollama_status"}) from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail={"code": "ollama_request"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=502, detail={"code": "ollama_decode"}) from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail={"code": "ollama_provider_shape"})
        returned_model = payload.get("model")
        if returned_model != "qwen3.5:9b-q4_K_M":
            raise HTTPException(status_code=502, detail={"code": "ollama_model_mismatch"})
        try:
            plan = plan_from_ollama_response(req.input, payload, registry)
        except ValueError as exc:
            raise HTTPException(status_code=502, detail={"code": "ollama_adapter"}) from exc

        first_step = plan.steps[0] if plan.steps else None
        if (
            first_step is None
            or first_step.kind != "tool_call"
            or first_step.tool_call is None
            or first_step.tool_call.tool_name != "math"
        ):
            raise HTTPException(status_code=502, detail={"code": "ollama_non_math_call"})
        provider_trace.append(
            {
                "type": "provider_call",
                "provider": "ollama",
                "configured_model": "qwen3.5:9b-q4_K_M",
                "returned_model": returned_model,
                "ok": True,
                "http_status": response.status_code,
                "ms": int((time.perf_counter() - started) * 1000),
                **_ollama_token_usage(payload),
                "provider_billed_cost_usd": 0.0,
                "cost_basis": "local-unbilled",
            }
        )

    result = await executor.execute(plan)

    if req.debug:
        return AgentRunResponse(output=result.output, trace=provider_trace + result.trace)

    return AgentRunResponse(output=result.output, trace=None)
