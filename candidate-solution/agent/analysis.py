import json
from time import perf_counter
from typing import Literal

from groq import APIConnectionError, APITimeoutError, AsyncGroq, InternalServerError, RateLimitError
from pydantic import BaseModel, ConfigDict
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent.config import Settings
from agent.models import LLMAnalysis


class AnalysisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentiment: Literal["positive", "neutral", "negative"]
    urgency_level: Literal["low", "medium", "high"]
    query_type: Literal["weather", "time", "demographics", "traffic", "general"]
    response: str


def classify_query_type(query: str) -> str:
    normalized = query.casefold()
    categories = {
        "weather": ("weather", "clima", "temperature", "temperatura", "humidity", "humedad"),
        "time": ("what time", "qué hora", "que hora", "timezone", "zona horaria"),
        "demographics": ("population", "población", "poblacion", "demographic"),
        "traffic": (
            "peak hour",
            "peak hours",
            "hora pico",
            "horas pico",
            "traffic",
            "tráfico",
            "trafico",
        ),
    }
    for category, keywords in categories.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return "general"


def heuristic_analysis(query: str, location: dict | None) -> LLMAnalysis:
    normalized = query.casefold()
    urgent_words = ("urgent", "urgente", "emergency", "emergencia", "immediately", "ahora")
    medium_words = ("soon", "pronto", "important", "importante", "need", "necesito")
    negative_words = ("bad", "terrible", "problema", "error", "fail", "falla", "molesto")
    positive_words = ("great", "good", "excelente", "gracias", "perfecto", "bien")

    urgency = "high" if any(word in normalized for word in urgent_words) else "low"
    if urgency == "low" and any(word in normalized for word in medium_words):
        urgency = "medium"
    sentiment = "negative" if any(word in normalized for word in negative_words) else "neutral"
    if sentiment == "neutral" and any(word in normalized for word in positive_words):
        sentiment = "positive"

    query_type = classify_query_type(query)
    if location:
        city = location.get("city", "la ubicación indicada")
        weather = location.get("weather") or {}
        demographics = location.get("demographics") or {}
        facts = {
            "weather": (
                f"En {city}, la condición es {weather.get('condition', 'desconocida')} con "
                f"{weather.get('temperature', 'N/D')} °C y "
                f"{weather.get('humidity', 'N/D')}% de humedad."
            ),
            "time": f"La zona horaria de {city} es {location.get('timezone', 'desconocida')}.",
            "demographics": (
                f"{city} registra una población de "
                f"{demographics.get('population', 'N/D')} habitantes; "
                f"idioma: {demographics.get('language', 'N/D')}; moneda: "
                f"{demographics.get('currency', 'N/D')}."
            ),
            "traffic": "Observaciones locales: " + "; ".join(location.get("observations") or []),
            "general": f"Se encontró información contextual para {city}.",
        }
        response = facts[query_type]
    else:
        response = "No fue posible obtener el contexto de ubicación en este momento."

    return LLMAnalysis(
        sentiment=sentiment,
        urgency_level=urgency,
        query_type=query_type,
        response=response,
        analysis_source="heuristic",
        model="heuristic",
        tokens_used=0,
        response_time_ms=0,
    )


@retry(
    retry=retry_if_exception_type(
        (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
    ),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
async def analyze_with_groq(
    query: str, location: dict | None, settings: Settings
) -> LLMAnalysis:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required when LLM_PROVIDER=groq")

    prompt = {
        "query": query,
        "location_context": location,
    }
    instruction = (
        "Classify the query and answer concisely using only the supplied location context. "
        "Allowed sentiment: positive, neutral, negative. Allowed urgency_level: low, medium, "
        "high. Allowed query_type: weather, time, demographics, traffic, general. "
        "Return the response in the requested JSON schema.\n\nInput:\n"
        f"{json.dumps(prompt, ensure_ascii=False)}"
    )
    started_at = perf_counter()
    async with AsyncGroq(
        api_key=settings.groq_api_key.get_secret_value(),
        max_retries=0,
        timeout=30,
    ) as client:
        completion = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[{"role": "user", "content": instruction}],
            temperature=0,
            max_completion_tokens=2048,
            top_p=1,
            reasoning_effort="medium",
            include_reasoning=False,
            stream=False,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "geoai_analysis",
                    "strict": True,
                    "schema": AnalysisPayload.model_json_schema(),
                },
            },
        )
    response_time_ms = round((perf_counter() - started_at) * 1_000)
    content = completion.choices[0].message.content
    if not content:
        raise RuntimeError("Groq returned an empty response")
    payload = AnalysisPayload.model_validate_json(content)
    tokens_used = completion.usage.total_tokens if completion.usage else 0
    return LLMAnalysis(
        **payload.model_dump(),
        analysis_source="groq",
        model=settings.groq_model,
        tokens_used=tokens_used,
        response_time_ms=response_time_ms,
    )


async def analyze(
    query: str, location: dict | None, settings: Settings
) -> tuple[LLMAnalysis, str | None]:
    if settings.llm_provider == "groq":
        try:
            return await analyze_with_groq(query, location, settings), None
        except Exception as exc:
            fallback = heuristic_analysis(query, location)
            warning = "Groq analysis failed; heuristic fallback used: " f"{type(exc).__name__}"
            return fallback, warning
    return heuristic_analysis(query, location), None
