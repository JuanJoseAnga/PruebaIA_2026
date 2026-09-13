import asyncio
import logging

from fastapi import FastAPI, HTTPException, status

from agent.analysis import analyze
from agent.config import get_settings
from agent.database import InteractionRepository
from agent.mcp_client import LocationMCPClient
from agent.models import HealthResponse, ProcessingResponse, Transaction

settings = get_settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GeoAI Transaction Analysis Agent",
    description="Receives, enriches, analyzes and persists simulated transactions.",
    version="1.0.0",
)
repository = InteractionRepository(settings.database_url)
location_client = LocationMCPClient(settings.mcp_server_url)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "GeoAI Agent", "status": "running"}


@app.get("/health", response_model=HealthResponse, tags=["Operations"])
async def health() -> HealthResponse:
    database_ok, mcp_ok = await asyncio.gather(
        asyncio.to_thread(repository.healthy), location_client.healthy()
    )
    llm_configured = settings.llm_provider == "heuristic" or bool(settings.groq_api_key)
    healthy = database_ok and mcp_ok and llm_configured
    return HealthResponse(
        status="healthy" if healthy else "degraded",
        database=database_ok,
        mcp_server=mcp_ok,
        llm_provider=settings.llm_provider,
        details={"groq_configured": bool(settings.groq_api_key)},
    )


@app.post(
    "/transactions",
    response_model=ProcessingResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Transactions"],
)
async def process_transaction(transaction: Transaction) -> ProcessingResponse:
    warnings: list[str] = []
    location = None
    try:
        location = await location_client.by_coordinates(
            transaction.location_metadata.latitude,
            transaction.location_metadata.longitude,
        )
    except Exception as exc:
        logger.exception("Location enrichment failed for %s", transaction.transaction_id)
        warnings.append(f"Location enrichment failed: {type(exc).__name__}")

    analysis, analysis_warning = await analyze(transaction.query, location, settings)
    if analysis_warning:
        warnings.append(analysis_warning)

    try:
        stored = await asyncio.to_thread(
            repository.save, transaction, analysis, location, warnings
        )
    except Exception as exc:
        logger.exception("Persistence failed for %s", transaction.transaction_id)
        raise HTTPException(status_code=503, detail="Database persistence unavailable") from exc

    processing_status = "duplicate" if stored.duplicate else "processed"
    if warnings and not stored.duplicate:
        processing_status = "processed_degraded"
    logger.info(
        "transaction_processed transaction_id=%s interaction_id=%s status=%s",
        transaction.transaction_id,
        stored.interaction_id,
        processing_status,
    )
    return ProcessingResponse(
        transaction_id=transaction.transaction_id,
        interaction_id=str(stored.interaction_id),
        status=processing_status,
        sentiment=analysis.sentiment,
        urgency_level=analysis.urgency_level,
        query_type=analysis.query_type,
        agent_response=analysis.response,
        llm_model=analysis.model,
        tokens_used=analysis.tokens_used,
        response_time_ms=analysis.response_time_ms,
        warnings=warnings,
    )
