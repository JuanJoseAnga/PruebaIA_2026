from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LocationMetadata(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    city: str = Field(min_length=1, max_length=100)


class Transaction(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    transaction_id: str = Field(min_length=1, max_length=100)
    user_id: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    query: str = Field(min_length=1, max_length=10_000)
    llm_model: str | None = Field(default=None, max_length=50)
    tokens_used: int | None = Field(default=None, ge=0)
    response_time_ms: int | None = Field(default=None, ge=0)
    location_metadata: LocationMetadata

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class LLMAnalysis(BaseModel):
    sentiment: Literal["positive", "neutral", "negative"]
    urgency_level: Literal["low", "medium", "high"]
    query_type: Literal["weather", "time", "demographics", "traffic", "general"]
    response: str = Field(min_length=1, max_length=2_000)
    analysis_source: Literal["groq", "heuristic"]
    model: str = Field(min_length=1, max_length=50)
    tokens_used: int = Field(default=0, ge=0)
    response_time_ms: int = Field(default=0, ge=0)


class ProcessingResponse(BaseModel):
    transaction_id: str
    interaction_id: str
    status: Literal["processed", "duplicate", "processed_degraded"]
    sentiment: str
    urgency_level: str
    query_type: str
    agent_response: str
    llm_model: str
    tokens_used: int
    response_time_ms: int
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    database: bool
    mcp_server: bool
    llm_provider: str
    details: dict[str, Any] = Field(default_factory=dict)
