from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent_runtime.planner_rules import RulesPlanner
from agent_runtime.executor import Executor
from agent_runtime.tools.registry import build_default_registry

router = APIRouter()

class AgentRunRequest(BaseModel):
    input: str = Field(..., description="User input to the agent.")
    debug: bool = Field(False, description="If true, return internal trace. Use only for internal testing.")

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
    planner = RulesPlanner(registry=registry)
    executor = Executor(registry=registry)

    plan = planner.plan(req.input)
    result = await executor.execute(plan)

    if req.debug:
        return AgentRunResponse(output=result.output, trace=result.trace)

    return AgentRunResponse(output=result.output, trace=None)
