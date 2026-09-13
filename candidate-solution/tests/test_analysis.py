import pytest

from agent.analysis import analyze, classify_query_type, heuristic_analysis
from agent.config import Settings


def test_query_type_is_multilingual() -> None:
    assert classify_query_type("¿Cuál es la población de Bogotá?") == "demographics"
    assert classify_query_type("What's the weather like?") == "weather"
    assert classify_query_type("¿Cuáles son las horas pico?") == "traffic"


def test_heuristic_detects_urgency_and_negative_sentiment() -> None:
    result = heuristic_analysis("Urgente, hay un problema ahora", None)
    assert result.urgency_level == "high"
    assert result.sentiment == "negative"
    assert result.analysis_source == "heuristic"
    assert result.model == "heuristic"
    assert result.tokens_used == 0


@pytest.mark.asyncio
async def test_groq_without_key_uses_heuristic_fallback() -> None:
    settings = Settings(llm_provider="groq", groq_api_key=None)

    result, warning = await analyze("What's the weather?", None, settings)

    assert result.analysis_source == "heuristic"
    assert result.model == "heuristic"
    assert warning == "Groq analysis failed; heuristic fallback used: RuntimeError"
