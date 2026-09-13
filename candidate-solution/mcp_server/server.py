import os
from typing import Any

import httpx
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from tenacity import retry, stop_after_attempt, wait_exponential

LOCATION_SERVICE_URL = os.getenv("LOCATION_SERVICE_URL", "http://location-service:8001").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("LOCATION_REQUEST_TIMEOUT_SECONDS", "5"))

mcp = MCPServer(
    "geoai-location-tools",
    instructions="Tools for retrieving contextual location information from the GeoAI service.",
)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.2, max=2), reraise=True)
async def _request(path: str, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{LOCATION_SERVICE_URL}{path}", params=params)
        response.raise_for_status()
        return response.json()


async def _all_locations() -> list[dict[str, Any]]:
    data = await _request("/locations")
    if not isinstance(data, list):
        raise RuntimeError("Location Service returned an invalid locations payload")
    return data


@mcp.tool()
async def list_locations() -> list[dict[str, Any]]:
    """List all supported locations with weather, timezone and demographic context."""
    return await _all_locations()


@mcp.tool()
async def get_location_by_id(location_id: str) -> dict[str, Any]:
    """Get one supported location by its unique location identifier."""
    for location in await _all_locations():
        if location.get("location_id") == location_id:
            return location
    raise ValueError(f"Location with ID '{location_id}' not found")


@mcp.tool()
async def get_location_by_city(city: str) -> dict[str, Any]:
    """Find a supported location using a case-insensitive city name."""
    city_normalized = city.casefold()
    for location in await _all_locations():
        if str(location.get("city", "")).casefold() == city_normalized:
            return location
    raise ValueError(f"Location for city '{city}' not found")


@mcp.tool()
async def get_location_by_country(country: str) -> list[dict[str, Any]]:
    """List supported locations for a case-insensitive country name."""
    country_normalized = country.casefold()
    matches = [
        location
        for location in await _all_locations()
        if str(location.get("country", "")).casefold() == country_normalized
    ]
    if not matches:
        raise ValueError(f"No locations found for country '{country}'")
    return matches


@mcp.tool()
async def get_location_by_coordinates(
    latitude: float, longitude: float, tolerance: float = 0.5
) -> dict[str, Any]:
    """Find a supported location close to latitude/longitude within a degree tolerance."""
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")
    if not 0 <= tolerance <= 5:
        raise ValueError("tolerance must be between 0 and 5")
    matches = [
        location
        for location in await _all_locations()
        if abs(float(location["latitude"]) - latitude) <= tolerance
        and abs(float(location["longitude"]) - longitude) <= tolerance
    ]
    if not matches:
        raise ValueError(
            f"No location found within {tolerance} degrees of ({latitude}, {longitude})"
        )
    return min(
        matches,
        key=lambda location: (float(location["latitude"]) - latitude) ** 2
        + (float(location["longitude"]) - longitude) ** 2,
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    try:
        await _request("/")
        return JSONResponse({"status": "healthy", "location_service": True})
    except Exception:
        return JSONResponse({"status": "degraded", "location_service": False}, status_code=503)


transport_security = TransportSecuritySettings(
    allowed_hosts=["mcp-server", "mcp-server:*", "localhost", "localhost:*", "127.0.0.1:*"],
    allowed_origins=[],
)
app = mcp.streamable_http_app(host="0.0.0.0", transport_security=transport_security)
