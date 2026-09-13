import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, create_engine, text

from agent.models import LLMAnalysis, Transaction


@dataclass(frozen=True)
class StoredInteraction:
    interaction_id: UUID
    duplicate: bool


class InteractionRepository:
    def __init__(self, database_url: str) -> None:
        self.engine: Engine = create_engine(database_url, pool_pre_ping=True, pool_size=5)

    def healthy(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def save(
        self,
        transaction: Transaction,
        analysis: LLMAnalysis,
        enriched_location: dict[str, Any] | None,
        warnings: list[str],
    ) -> StoredInteraction:
        metadata = {
            "source_location_metadata": transaction.location_metadata.model_dump(),
            "enriched_location": enriched_location,
            "query_type": analysis.query_type,
            "analysis_source": analysis.analysis_source,
            "processing_warnings": warnings,
            "upstream_llm_metrics": {
                "model": transaction.llm_model,
                "tokens_used": transaction.tokens_used,
                "response_time_ms": transaction.response_time_ms,
            },
        }
        with self.engine.begin() as connection:
            # Serialize concurrent deliveries of the same transaction without altering
            # the evaluator-owned schema. The lock is released with this transaction.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:transaction_id))"),
                {"transaction_id": transaction.transaction_id},
            )
            existing = connection.execute(
                text(
                    "SELECT interaction_id FROM agent_interactions "
                    "WHERE transaction_id = :transaction_id ORDER BY created_at LIMIT 1"
                ),
                {"transaction_id": transaction.transaction_id},
            ).scalar_one_or_none()
            if existing:
                return StoredInteraction(interaction_id=existing, duplicate=True)

            interaction_id = connection.execute(
                text(
                    """
                    INSERT INTO agent_interactions (
                        transaction_id, user_id, timestamp, user_query, agent_response,
                        llm_model, tokens_used, response_time_ms, sentiment, urgency_level,
                        raw_metadata
                    ) VALUES (
                        :transaction_id, :user_id, :timestamp, :user_query, :agent_response,
                        :llm_model, :tokens_used, :response_time_ms, :sentiment, :urgency_level,
                        CAST(:raw_metadata AS JSONB)
                    ) RETURNING interaction_id
                    """
                ),
                {
                    "transaction_id": transaction.transaction_id,
                    "user_id": transaction.user_id,
                    "timestamp": transaction.timestamp,
                    "user_query": transaction.query,
                    "agent_response": analysis.response,
                    "llm_model": analysis.model,
                    "tokens_used": analysis.tokens_used,
                    "response_time_ms": analysis.response_time_ms,
                    "sentiment": analysis.sentiment,
                    "urgency_level": analysis.urgency_level,
                    "raw_metadata": json.dumps(metadata, ensure_ascii=False),
                },
            ).scalar_one()
        return StoredInteraction(interaction_id=interaction_id, duplicate=False)
