from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

from agent_runtime.tools.base import Tool
from agent_runtime.tools.examples.math_tool import MathTool
from agent_runtime.tools.examples.weather_tool import WeatherTool
from agent_runtime.tools.examples.web_search_tool import WebSearchTool

@dataclass(frozen=True)
class ToolRegistry:
    tools: Dict[str, Tool]

    def get(self, name: str) -> Tool:
        if name not in self.tools:
            raise KeyError(f"Unknown tool: {name}")
        return self.tools[name]

def build_default_registry() -> ToolRegistry:
    tools = {
        "math": MathTool(),
        "weather": WeatherTool(),
        "web_search": WebSearchTool(),
    }
    return ToolRegistry(tools=tools)
