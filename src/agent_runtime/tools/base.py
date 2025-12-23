from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict

class Tool(ABC):
    name: str
    description: str

    @property
    def input_schema(self) -> Dict[str, Any]:
        """JSON Schema for tool inputs (best-effort). Override when available."""
        return {"type": "object"}

    @property
    def output_schema(self) -> Dict[str, Any]:
        """JSON Schema for tool outputs (best-effort). Override when available."""
        return {"type": "object"}

    @abstractmethod
    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

class ToolError(Exception):
    def __init__(self, message: str, *, code: str = "tool_error"):
        super().__init__(message)
        self.code = code
