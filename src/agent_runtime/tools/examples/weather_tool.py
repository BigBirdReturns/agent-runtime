from __future__ import annotations
from typing import Any

from agent_runtime.tools.base import Tool, ToolError

class WeatherTool(Tool):
    name = "weather"
    description = "Stub weather tool. Replace with a real API adapter."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        location = str(arguments.get("location", "")).strip()
        if not location:
            raise ToolError("Missing location", code="bad_input")
        return {"location": location, "summary": "Stub: 72F, clear skies."}
