Agent Runtime (No LangChain)

Purpose
- Expose one Agent API endpoint.
- Internally call 2 to 3 tools (HTTP APIs or MCP) based on user input.
- Keep tool APIs and execution invisible to the user by default.

Key properties
- Deterministic planning when using the rules planner.
- Strict tool contracts and bounded execution (timeouts, retries).
- Optional debug mode returns a minimal trace for internal testing only.

Run
  pip install -e .
  uvicorn agent_runtime.main:app --reload

Call
  curl -X POST http://localhost:8000/v1/agent/run \
    -H "Content-Type: application/json" \
    -d '{"input":"What is 12*13 and then add 5?"}'

Response
  {"output":"12*13 = 156. 156 + 5 = 161."}

Debug call (internal only)
  curl -X POST http://localhost:8000/v1/agent/run \
    -H "Content-Type: application/json" \
    -d '{"input":"weather in Seattle and 12*13","debug":true}'

Notes
- Replace the example tools with real HTTP or MCP adapters.
- The executor stays the same. Only tools and the planner change.
