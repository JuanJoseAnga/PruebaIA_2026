FROM ghcr.io/astral-sh/uv:0.8.17 AS uv

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY --chown=app:app agent ./agent
COPY --chown=app:app mcp_server ./mcp_server
COPY --chown=app:app pipeline ./pipeline
COPY --chown=app:app dashboard ./dashboard
USER app

ENV PATH="/app/.venv/bin:$PATH"

FROM runtime AS test
USER root
RUN uv sync --frozen --group dev
COPY --chown=app:app tests ./tests
USER app
CMD ["pytest", "-q"]

FROM runtime AS production
