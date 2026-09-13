from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = (
        "postgresql+psycopg://agent_user:agent_password@postgres:5432/gen_ai_agent_db"
    )
    mcp_server_url: str = "http://mcp-server:8003/mcp"
    llm_provider: str = "groq"
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-20b"
    log_level: str = "INFO"

    mcp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    database_timeout_seconds: int = Field(default=10, gt=0, le=60)

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        provider = value.lower().strip()
        if provider not in {"groq", "heuristic"}:
            raise ValueError("LLM_PROVIDER must be 'groq' or 'heuristic'")
        return provider


@lru_cache
def get_settings() -> Settings:
    return Settings()
