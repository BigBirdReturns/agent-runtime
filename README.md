Agent Runtime (No LangChain)

Purpose
- Expose one Agent API endpoint.
- Internally call 2 to 3 tools (HTTP APIs or MCP) based on user input.
- Keep tool APIs and execution invisible to the user by default.

Key properties
- Deterministic planning with a rules planner (auditable).
- Plan is serialized into trace for replay/audit when debug is enabled.
- Parallel tool calls collect trace deterministically (no shared mutable trace races).
- Strict tool input validation (Pydantic) and bounded execution (timeouts, retries, call budget).
- Optional debug mode returns a minimal trace for internal inspection only.
- Tool schemas are exposed for integration/audit via /v1/tools/schemas.

Run
  pip install -e .
  uvicorn agent_runtime.main:app --reload

Call
  curl -X POST http://localhost:8000/v1/agent/run \
    -H "Content-Type: application/json" \
    -d '{"input":"What is 12*13 and then add 5?"}'

Response
  {"output":"What is 12*13 and then add 5? = 161"}

Debug call (internal only)
  curl -X POST http://localhost:8000/v1/agent/run \
    -H "Content-Type: application/json" \
    -d '{"input":"weather in Seattle and 12*13","debug":true}'

Schemas
  curl http://localhost:8000/v1/tools/schemas
