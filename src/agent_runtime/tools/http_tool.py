from __future__ import annotations
from typing import Any
import httpx

from agent_runtime.tools.base import Tool, ToolError

class HttpTool(Tool):
    def __init__(self, *, name: str, description: str, url: str, timeout_s: float = 10.0, retries: int = 1):
        self.name = name
        self.description = description
        self.url = url
        self.timeout_s = timeout_s
        self.retries = max(0, int(retries))

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    r = await client.post(self.url, json=arguments)
                    r.raise_for_status()
                    return r.json()
            except httpx.TimeoutException as e:
                last_err = e
            except httpx.HTTPStatusError as e:
                raise ToolError(f"HTTP status {e.response.status_code}", code="http_error")
            except Exception as e:
                last_err = e
        raise ToolError(f"HTTP timeout or exception: {last_err}", code="timeout")
