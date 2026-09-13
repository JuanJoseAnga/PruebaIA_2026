from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from agent.analysis import classify_query_type


def validate_location(location: Any) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(location, dict):
        return False, ["enriched_location is missing"]

    required = (
        "city",
        "country",
        "latitude",
        "longitude",
        "timezone",
        "weather",
        "demographics",
    )
    for key in required:
        if location.get(key) is None:
            errors.append(f"missing {key}")

    latitude = _number(location.get("latitude"), "latitude", errors)
    longitude = _number(location.get("longitude"), "longitude", errors)
    weather = location.get("weather")
    humidity = weather.get("humidity") if isinstance(weather, dict) else None
    humidity = _number(humidity, "humidity", errors)
    if latitude is not None and not -90 <= latitude <= 90:
        errors.append("latitude outside valid range")
    if longitude is not None and not -180 <= longitude <= 180:
        errors.append("longitude outside valid range")
    if humidity is not None and not 0 <= humidity <= 100:
        errors.append("humidity outside valid range")
    return not errors, errors


def _number(value: Any, field: str, errors: list[str]) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} is not numeric")
        return None


def build_silver_rows(rows: pd.DataFrame) -> list[dict[str, Any]]:
    """Flatten, type and validate Bronze metadata with pandas."""
    if rows.empty:
        return []

    frame = rows.copy().reset_index(drop=True)
    metadata = frame["raw_metadata"].map(_as_dict)
    locations = metadata.map(lambda value: value.get("enriched_location") or {})
    location_frame = pd.json_normalize(locations, sep="_")

    expected_columns = {
        "city": None,
        "country": None,
        "latitude": None,
        "longitude": None,
        "timezone": None,
        "weather_condition": None,
        "weather_temperature": None,
        "weather_humidity": None,
        "weather_wind_speed": None,
        "observations": None,
        "demographics_population": None,
        "demographics_language": None,
        "demographics_currency": None,
    }
    for column, default in expected_columns.items():
        if column not in location_frame:
            location_frame[column] = default

    for column in ("city", "country", "timezone", "weather_condition"):
        location_frame[column] = location_frame[column].map(_clean_text)
    for column in ("demographics_language", "demographics_currency"):
        location_frame[column] = location_frame[column].map(_clean_text)

    numeric_columns = (
        "latitude",
        "longitude",
        "weather_temperature",
        "weather_humidity",
        "weather_wind_speed",
        "demographics_population",
    )
    for column in numeric_columns:
        location_frame[column] = pd.to_numeric(location_frame[column], errors="coerce")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    output: list[dict[str, Any]] = []
    for index, source in frame.iterrows():
        flat = location_frame.iloc[index]
        location = locations.iloc[index]
        is_valid, errors = validate_location(location)
        if pd.isna(source["timestamp"]):
            errors.append("invalid timestamp")
            is_valid = False

        output.append(
            {
                "interaction_id": source["interaction_id"],
                "user_id": _clean_text(source["user_id"]),
                "timestamp": (
                    None
                    if pd.isna(source["timestamp"])
                    else source["timestamp"].to_pydatetime()
                ),
                "city": flat["city"],
                "country": flat["country"],
                "latitude": _optional_float(flat["latitude"]),
                "longitude": _optional_float(flat["longitude"]),
                "timezone": flat["timezone"],
                "weather_condition": flat["weather_condition"],
                "temperature": _optional_float(flat["weather_temperature"]),
                "humidity": _optional_int(flat["weather_humidity"]),
                "wind_speed": _optional_float(flat["weather_wind_speed"]),
                "observations": _clean_observations(flat["observations"]),
                "population": _optional_int(flat["demographics_population"]),
                "language": flat["demographics_language"],
                "currency": flat["demographics_currency"],
                "is_valid": is_valid,
                "validation_errors": errors,
            }
        )
    return output


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _clean_observations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [cleaned for item in value if (cleaned := _clean_text(item))]


def _optional_int(value: Any) -> int | None:
    return None if pd.isna(value) else int(value)


def most_common(values: Iterable[Any]) -> Any:
    series = pd.Series(list(values)).dropna()
    return None if series.empty else series.mode().iloc[0]


def build_gold_metrics(rows: pd.DataFrame) -> list[dict[str, Any]]:
    if rows.empty:
        return []

    frame = rows.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["metric_date"] = frame["timestamp"].dt.date
    frame["hour"] = frame["timestamp"].dt.hour
    frame["query_type"] = frame["user_query"].map(classify_query_type)

    metrics: list[dict[str, Any]] = []
    for (metric_date, city, country), group in frame.groupby(
        ["metric_date", "city", "country"], dropna=False
    ):
        sentiment = group["sentiment"].value_counts()
        urgency = group["urgency_level"].value_counts()
        metrics.append(
            {
                "metric_date": metric_date,
                "city": city,
                "country": country,
                "total_transactions": int(len(group)),
                "avg_response_time_ms": _optional_float(group["response_time_ms"].mean()),
                "total_tokens_used": int(group["tokens_used"].fillna(0).sum()),
                "unique_users": int(group["user_id"].nunique()),
                "most_common_query_type": most_common(group["query_type"]),
                "peak_hour": int(most_common(group["hour"])),
                "avg_temperature": _optional_float(group["temperature"].mean()),
                "most_common_weather": most_common(group["weather_condition"]),
                "positive_sentiment_count": int(sentiment.get("positive", 0)),
                "neutral_sentiment_count": int(sentiment.get("neutral", 0)),
                "negative_sentiment_count": int(sentiment.get("negative", 0)),
                "high_urgency_count": int(urgency.get("high", 0)),
                "medium_urgency_count": int(urgency.get("medium", 0)),
                "low_urgency_count": int(urgency.get("low", 0)),
            }
        )
    return metrics


def _optional_float(value: Any) -> float | None:
    return None if pd.isna(value) else float(value)
