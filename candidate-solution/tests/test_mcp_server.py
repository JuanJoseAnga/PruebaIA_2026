import pytest

from mcp_server import server


@pytest.fixture
def locations() -> list[dict]:
    return [
        {
            "location_id": "loc_bog_001",
            "city": "Bogotá",
            "country": "Colombia",
            "latitude": 4.711,
            "longitude": -74.0721,
        },
        {
            "location_id": "loc_med_001",
            "city": "Medellín",
            "country": "Colombia",
            "latitude": 6.2442,
            "longitude": -75.5812,
        },
    ]


@pytest.mark.asyncio
async def test_coordinates_are_resolved_from_location_collection(monkeypatch, locations) -> None:
    async def fake_locations() -> list[dict]:
        return locations

    monkeypatch.setattr(server, "_all_locations", fake_locations)
    result = await server.get_location_by_coordinates(4.71, -74.07)
    assert result["location_id"] == "loc_bog_001"


@pytest.mark.asyncio
async def test_country_lookup_is_case_insensitive(monkeypatch, locations) -> None:
    async def fake_locations() -> list[dict]:
        return locations

    monkeypatch.setattr(server, "_all_locations", fake_locations)
    result = await server.get_location_by_country("COLOMBIA")
    assert len(result) == 2

