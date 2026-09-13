from typing import Any

from mcp import Client
from tenacity import retry, stop_after_attempt, wait_exponential


class LocationMCPClient:
    def __init__(self, server_url: str) -> None:
        self.server_url = server_url

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.2, max=2), reraise=True)
    async def by_coordinates(self, latitude: float, longitude: float) -> dict[str, Any]:
        async with Client(self.server_url) as client:
            result = await client.call_tool(
                "get_location_by_coordinates",
                {"latitude": latitude, "longitude": longitude, "tolerance": 0.5},
            )
        if result.is_error:
            raise RuntimeError("MCP location tool returned an error")
        if result.structured_content:
            data = result.structured_content
            return data.get("result", data)
        for item in result.content:
            text_value = getattr(item, "text", None)
            if text_value:
                import json

                return json.loads(text_value)
        raise RuntimeError("MCP location tool returned no data")

    async def healthy(self) -> bool:
        try:
            async with Client(self.server_url) as client:
                tools = await client.list_tools()
            return bool(tools.tools)
        except Exception:
            return False

