from __future__ import annotations
from typing import Any

from agent_runtime.tools.base import Tool, ToolError

class WebSearchTool(Tool):
    name = "web_search"
    description = "Stub search tool. Replace with a real search provider."

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ToolError("Missing query", code="bad_input")
        return {"query": query, "results": [{"title": "Stub result", "snippet": f"Search results for: {query}"}]}
