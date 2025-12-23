from __future__ import annotations
from typing import Any
import json
import httpx

from agent_runtime.tools.base import Tool, ToolError

class HttpTool(Tool):
    def __init__(self, *, name: str, description: str, url: str, timeout_s: float = 10.0, retries: int = 1):
        self.name = name
        self.description = description
        self.url = url
        self.timeout_s = float(timeout_s)
        self.retries = max(0, int(retries))

    async def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    r = await client.post(self.url, json=arguments)
                    r.raise_for_status()
                    try:
                        return r.json()
                    except json.JSONDecodeError as e:
                        raise ToolError(f"Invalid JSON response: {e}", code="http_invalid_response")
            except httpx.TimeoutException as e:
                last_err = e
            except ToolError as e:
                # Invalid JSON should not retry by default; treat as terminal.
                raise e
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if 400 <= status < 500:
                    raise ToolError(f"HTTP {status}", code="http_client_error")
                last_err = e
            except Exception as e:
                last_err = e

        raise ToolError(f"HTTP failed after retries: {last_err}", code="http_retry_exhausted")
