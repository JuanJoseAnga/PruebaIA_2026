from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent.models import Transaction


def valid_transaction() -> dict:
    return {
        "transaction_id": "txn_000001",
        "user_id": "user_123",
        "timestamp": datetime.now(UTC).isoformat(),
        "query": "What's the weather like here?",
        "llm_model": "gpt-4",
        "tokens_used": 100,
        "response_time_ms": 900,
        "location_metadata": {"latitude": 19.4326, "longitude": -99.1332, "city": "CDMX"},
    }


def test_transaction_accepts_generator_contract() -> None:
    transaction = Transaction.model_validate(valid_transaction())
    assert transaction.transaction_id == "txn_000001"


def test_transaction_rejects_naive_timestamp() -> None:
    payload = valid_transaction()
    payload["timestamp"] = "2026-01-01T00:00:00"
    with pytest.raises(ValidationError):
        Transaction.model_validate(payload)


def test_transaction_rejects_invalid_coordinates() -> None:
    payload = valid_transaction()
    payload["location_metadata"]["latitude"] = 100
    with pytest.raises(ValidationError):
        Transaction.model_validate(payload)
