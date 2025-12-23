from __future__ import annotations
from typing import Any

from agent_runtime.tools.base import Tool, ToolError

class McpTool(Tool):
    """
    MCP adapter placeholder.
    Implement your MCP transport (stdio, websocket, or an HTTP bridge) here.
    Keep this Tool interface stable so the executor never changes.
    """

    def __init__(self, *, name: str, description: str, server: str, tool: str, timeout_s: float = 10.0):
        self.name = name
        self.description = description
        self.server = server
        self.tool = tool
        self.timeout_s = timeout_s

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raise ToolError("MCP adapter not implemented. Wire your MCP transport here.", code="not_implemented")
