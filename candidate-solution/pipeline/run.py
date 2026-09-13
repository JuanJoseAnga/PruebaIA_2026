import asyncio
import json
import logging
import os
import signal
import time

import pandas as pd
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from agent.mcp_client import LocationMCPClient
from pipeline.transform import build_gold_metrics, build_silver_rows, validate_location

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://agent_user:agent_password@postgres:5432/gen_ai_agent_db",
)
INTERVAL_SECONDS = max(1, int(os.getenv("PIPELINE_INTERVAL_SECONDS", "10")))
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp-server:8003/mcp")
MAX_ENRICHMENT_ATTEMPTS = max(1, int(os.getenv("MAX_ENRICHMENT_ATTEMPTS", "3")))
running = True


def _stop(*_: object) -> None:
    global running
    running = False


def _ensure_silver_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE enriched_transactions "
                "ADD COLUMN IF NOT EXISTS enrichment_attempts INTEGER NOT NULL DEFAULT 0"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE enriched_transactions "
                "ADD COLUMN IF NOT EXISTS last_enrichment_attempt_at TIMESTAMP"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_enriched_transactions_interaction_id "
                "ON enriched_transactions(interaction_id)"
            )
        )


async def _retry_missing_enrichments(rows: list[dict]) -> list[dict]:
    client = LocationMCPClient(MCP_SERVER_URL)
    for row in rows:
        metadata = row["raw_metadata"] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        row["raw_metadata"] = metadata
        is_valid, _ = validate_location(metadata.get("enriched_location"))
        if is_valid:
            continue

        source = metadata.get("source_location_metadata") or {}
        latitude = source.get("latitude")
        longitude = source.get("longitude")
        if latitude is None or longitude is None:
            continue
        try:
            metadata["enriched_location"] = await client.by_coordinates(latitude, longitude)
        except Exception as exc:
            logger.warning(
                "silver_enrichment_retry_failed interaction_id=%s error=%s",
                row["interaction_id"],
                type(exc).__name__,
            )
    return rows


def promote_bronze_to_silver(engine: Engine) -> int:
    _ensure_silver_schema(engine)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT ai.interaction_id, ai.user_id, ai.timestamp, ai.raw_metadata,
                       COALESCE(et.enrichment_attempts, 0) AS enrichment_attempts
                FROM agent_interactions ai
                LEFT JOIN enriched_transactions et ON et.interaction_id = ai.interaction_id
                WHERE et.interaction_id IS NULL
                   OR (et.is_valid = FALSE AND et.enrichment_attempts < :max_attempts)
                ORDER BY ai.created_at
                """
            ),
            {"max_attempts": MAX_ENRICHMENT_ATTEMPTS},
        ).mappings().all()

    if not rows:
        return 0
    bronze_rows = [dict(row) for row in rows]
    enriched_rows = asyncio.run(_retry_missing_enrichments(bronze_rows))
    silver_rows = build_silver_rows(pd.DataFrame(enriched_rows))

    with engine.begin() as connection:
        for bronze, silver in zip(enriched_rows, silver_rows, strict=True):
            silver["raw_metadata"] = json.dumps(bronze["raw_metadata"], ensure_ascii=False)
            connection.execute(
                text(
                    """
                    UPDATE agent_interactions
                    SET raw_metadata = CAST(:raw_metadata AS JSONB)
                    WHERE interaction_id = :interaction_id
                    """
                ),
                silver,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO enriched_transactions (
                        interaction_id, user_id, timestamp, city, country, latitude, longitude,
                        timezone, weather_condition, temperature, humidity, wind_speed,
                        observations, population, language, currency, is_valid, validation_errors,
                        enrichment_attempts, last_enrichment_attempt_at
                    ) VALUES (
                        :interaction_id, :user_id, :timestamp, :city, :country,
                        :latitude, :longitude,
                        :timezone, :weather_condition, :temperature, :humidity, :wind_speed,
                        :observations, :population, :language, :currency,
                        :is_valid, :validation_errors, 1, NOW()
                    )
                    ON CONFLICT (interaction_id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        timestamp = EXCLUDED.timestamp,
                        city = EXCLUDED.city,
                        country = EXCLUDED.country,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        timezone = EXCLUDED.timezone,
                        weather_condition = EXCLUDED.weather_condition,
                        temperature = EXCLUDED.temperature,
                        humidity = EXCLUDED.humidity,
                        wind_speed = EXCLUDED.wind_speed,
                        observations = EXCLUDED.observations,
                        population = EXCLUDED.population,
                        language = EXCLUDED.language,
                        currency = EXCLUDED.currency,
                        is_valid = EXCLUDED.is_valid,
                        validation_errors = EXCLUDED.validation_errors,
                        enrichment_attempts = enriched_transactions.enrichment_attempts + 1,
                        last_enrichment_attempt_at = NOW(),
                        processed_at = NOW()
                    """
                ),
                silver,
            )
    return len(silver_rows)


def refresh_gold(engine: Engine) -> int:
    query = text(
        """
        SELECT ai.user_id, ai.timestamp, ai.user_query, ai.tokens_used, ai.response_time_ms,
               ai.sentiment, ai.urgency_level, et.city, et.country, et.temperature,
               et.weather_condition
        FROM enriched_transactions et
        JOIN agent_interactions ai ON ai.interaction_id = et.interaction_id
        WHERE et.is_valid = TRUE AND et.city IS NOT NULL
        """
    )
    with engine.connect() as connection:
        rows = pd.read_sql(query, connection)
    metrics = build_gold_metrics(rows)
    if not metrics:
        return 0

    statement = text(
        """
        INSERT INTO analytics_metrics (
            metric_date, city, country, total_transactions, avg_response_time_ms,
            total_tokens_used, unique_users, most_common_query_type, peak_hour,
            avg_temperature, most_common_weather, positive_sentiment_count,
            neutral_sentiment_count, negative_sentiment_count, high_urgency_count,
            medium_urgency_count, low_urgency_count, aggregated_at
        ) VALUES (
            :metric_date, :city, :country, :total_transactions, :avg_response_time_ms,
            :total_tokens_used, :unique_users, :most_common_query_type, :peak_hour,
            :avg_temperature, :most_common_weather, :positive_sentiment_count,
            :neutral_sentiment_count, :negative_sentiment_count, :high_urgency_count,
            :medium_urgency_count, :low_urgency_count, NOW()
        )
        ON CONFLICT (metric_date, city) DO UPDATE SET
            country = EXCLUDED.country,
            total_transactions = EXCLUDED.total_transactions,
            avg_response_time_ms = EXCLUDED.avg_response_time_ms,
            total_tokens_used = EXCLUDED.total_tokens_used,
            unique_users = EXCLUDED.unique_users,
            most_common_query_type = EXCLUDED.most_common_query_type,
            peak_hour = EXCLUDED.peak_hour,
            avg_temperature = EXCLUDED.avg_temperature,
            most_common_weather = EXCLUDED.most_common_weather,
            positive_sentiment_count = EXCLUDED.positive_sentiment_count,
            neutral_sentiment_count = EXCLUDED.neutral_sentiment_count,
            negative_sentiment_count = EXCLUDED.negative_sentiment_count,
            high_urgency_count = EXCLUDED.high_urgency_count,
            medium_urgency_count = EXCLUDED.medium_urgency_count,
            low_urgency_count = EXCLUDED.low_urgency_count,
            aggregated_at = NOW()
        """
    )
    with engine.begin() as connection:
        connection.execute(statement, metrics)
    return len(metrics)


def run_once(engine: Engine) -> dict[str, int]:
    silver_rows = promote_bronze_to_silver(engine)
    gold_rows = refresh_gold(engine)
    return {"silver_rows_created": silver_rows, "gold_groups_upserted": gold_rows}


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    logger.info("pipeline_started interval_seconds=%s", INTERVAL_SECONDS)
    while running:
        try:
            result = run_once(engine)
            logger.info("pipeline_cycle_complete %s", result)
        except SQLAlchemyError:
            logger.exception("pipeline_database_error")
        except Exception:
            logger.exception("pipeline_unexpected_error")
        time.sleep(INTERVAL_SECONDS)
    engine.dispose()
    logger.info("pipeline_stopped")


if __name__ == "__main__":
    main()
