from __future__ import annotations
from typing import Any, Dict, List
from pydantic import BaseModel, Field, ValidationError

from agent_runtime.tools.base import Tool, ToolError

class WebSearchToolInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=300)

class WebSearchItem(BaseModel):
    title: str
    snippet: str

class WebSearchToolOutput(BaseModel):
    query: str
    results: List[WebSearchItem]

class WebSearchTool(Tool):
    name = "web_search"
    description = "Stub search tool. Replace with a real search provider."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return WebSearchToolInput.model_json_schema()

    @property
    def output_schema(self) -> Dict[str, Any]:
        return WebSearchToolOutput.model_json_schema()

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            inputs = WebSearchToolInput(**arguments)
        except ValidationError as e:
            raise ToolError(f"Invalid input: {e.errors()}", code="bad_input")

        return WebSearchToolOutput(
            query=inputs.query.strip(),
            results=[WebSearchItem(title="Stub result", snippet=f"Search results for: {inputs.query.strip()}")],
        ).model_dump()
