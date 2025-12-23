from __future__ import annotations
from typing import Any, Dict
from pydantic import BaseModel, Field, ValidationError

from agent_runtime.tools.base import Tool, ToolError

class WeatherToolInput(BaseModel):
    location: str = Field(..., min_length=1, max_length=120)

class WeatherToolOutput(BaseModel):
    location: str
    summary: str

class WeatherTool(Tool):
    name = "weather"
    description = "Stub weather tool. Replace with a real API adapter."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return WeatherToolInput.model_json_schema()

    @property
    def output_schema(self) -> Dict[str, Any]:
        return WeatherToolOutput.model_json_schema()

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            inputs = WeatherToolInput(**arguments)
        except ValidationError as e:
            raise ToolError(f"Invalid input: {e.errors()}", code="bad_input")

        # Replace with a real API call.
        return WeatherToolOutput(location=inputs.location.strip(), summary="Stub: 72F, clear skies.").model_dump()
