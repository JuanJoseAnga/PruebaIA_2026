import pandas as pd

from pipeline.transform import build_gold_metrics, build_silver_rows, validate_location


def location() -> dict:
    return {
        "city": "Bogotá",
        "country": "Colombia",
        "latitude": 4.7,
        "longitude": -74.1,
        "timezone": "America/Bogota",
        "weather": {"temperature": 18, "condition": "Rain", "humidity": 80},
        "demographics": {"population": 8_000_000, "language": "Spanish", "currency": "COP"},
    }


def test_validate_location() -> None:
    assert validate_location(location()) == (True, [])
    valid, errors = validate_location(None)
    assert not valid
    assert errors


def test_build_silver_rows_flattens_cleans_and_types_metadata() -> None:
    metadata = {
        "enriched_location": {
            **location(),
            "city": "  Bogotá  ",
            "latitude": "4.7",
            "longitude": "-74.1",
            "weather": {
                "temperature": "18.5",
                "condition": "  Light Rain ",
                "humidity": "80",
                "wind_speed": "7.2",
            },
            "observations": ["  Zona urbana ", ""],
        }
    }
    frame = pd.DataFrame(
        [
            {
                "interaction_id": "interaction-1",
                "user_id": " user-1 ",
                "timestamp": "2026-09-13T10:00:00Z",
                "raw_metadata": metadata,
            }
        ]
    )

    row = build_silver_rows(frame)[0]

    assert row["city"] == "Bogotá"
    assert row["user_id"] == "user-1"
    assert row["latitude"] == 4.7
    assert row["temperature"] == 18.5
    assert row["humidity"] == 80
    assert row["observations"] == ["Zona urbana"]
    assert row["is_valid"] is True
    assert row["validation_errors"] == []


def test_build_silver_rows_quarantines_invalid_values() -> None:
    invalid_location = location()
    invalid_location["latitude"] = "not-a-number"
    invalid_location["weather"]["humidity"] = 120
    frame = pd.DataFrame(
        [
            {
                "interaction_id": "interaction-2",
                "user_id": "user-2",
                "timestamp": "invalid-date",
                "raw_metadata": {"enriched_location": invalid_location},
            }
        ]
    )

    row = build_silver_rows(frame)[0]

    assert row["is_valid"] is False
    assert "latitude is not numeric" in row["validation_errors"]
    assert "humidity outside valid range" in row["validation_errors"]
    assert "invalid timestamp" in row["validation_errors"]


def test_build_gold_metrics_aggregates_counts() -> None:
    frame = pd.DataFrame(
        [
            {
                "user_id": "u1",
                "timestamp": "2026-09-13T10:00:00Z",
                "user_query": "weather please",
                "tokens_used": 10,
                "response_time_ms": 100,
                "sentiment": "neutral",
                "urgency_level": "low",
                "city": "Bogotá",
                "country": "Colombia",
                "temperature": 18,
                "weather_condition": "Rain",
            },
            {
                "user_id": "u2",
                "timestamp": "2026-09-13T10:30:00Z",
                "user_query": "temperature now",
                "tokens_used": 20,
                "response_time_ms": 300,
                "sentiment": "positive",
                "urgency_level": "high",
                "city": "Bogotá",
                "country": "Colombia",
                "temperature": 20,
                "weather_condition": "Rain",
            },
        ]
    )
    metric = build_gold_metrics(frame)[0]
    assert metric["total_transactions"] == 2
    assert metric["unique_users"] == 2
    assert metric["avg_response_time_ms"] == 200
    assert metric["peak_hour"] == 10
