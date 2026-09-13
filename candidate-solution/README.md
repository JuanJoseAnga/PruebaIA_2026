# GeoAI AI & Data Agent

Solución reproducible para la evaluación de Ingeniería de Datos e IA. Integra los servicios
proporcionados sin modificarlos y construye un servidor MCP, un agente FastAPI, un pipeline
medallón con pandas y un dashboard Streamlit.

## Arquitectura

```text
Transaction Service ──POST──> Agent ──MCP──> MCP Server ──HTTP──> Location Service
                                 │
                                 └──> PostgreSQL Bronze
                                           │
                                      pandas ETL
                                           ▼
                                      Silver → Gold ──> Streamlit
```

| Componente | Puerto | Propósito |
|---|---:|---|
| Agent API | 8000 | Recibe, analiza y persiste transacciones |
| Location Service | 8001 | Fuente simulada proporcionada |
| Transaction Service | 8002 | Generador proporcionado |
| MCP Server | 8003 | Herramientas estandarizadas de ubicación |
| PostgreSQL | 5432 | Capas Bronze, Silver y Gold |
| Dashboard | 8501 | Indicadores operativos sobre Gold |
| pgAdmin (opcional) | 5050 | Administración visual de PostgreSQL |

## Requisitos

- Docker Desktop con Docker Compose.
- Aproximadamente 3 GB libres para imágenes y volúmenes.
- Una API key de Groq para la inferencia LLM real.

No es necesario instalar Python ni PostgreSQL localmente para ejecutar la solución.

## Inicio rápido

Ejecutar desde esta carpeta:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Si el puerto 5432 ya está ocupado, cambiar únicamente la publicación al host antes de levantar:

```powershell
$env:POSTGRES_PORT="5433"
docker compose up --build -d
```

Los demás contenedores continúan conectándose internamente a PostgreSQL por el puerto 5432.

El proveedor predeterminado es Groq con GPT-OSS 20B. Para cumplir el flujo con inferencia real, editar
`.env`:

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=tu_clave_de_groq
GROQ_MODEL=openai/gpt-oss-20b
```

El agente consulta Groq mediante su SDK oficial, usa razonamiento medio y Structured Outputs en
modo estricto, y vuelve a validar la respuesta con Pydantic. Ante una indisponibilidad, utiliza el
clasificador heurístico y deja la advertencia en `raw_metadata.processing_warnings`. Una API key
nunca debe confirmarse en Git.

Para una demostración completamente offline se puede establecer `LLM_PROVIDER=heuristic`.

## Probar el flujo

### 1. Comprobar salud

```powershell
Invoke-RestMethod http://localhost:8001/
Invoke-RestMethod http://localhost:8002/status
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8003/health
```

### 2. Enviar transacciones

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8002/send-one"
Invoke-RestMethod -Method Post -Uri "http://localhost:8002/send-batch?count=20"
```

Estos endpoints aceptan únicamente `POST`. Abrirlos desde la barra del navegador envía un `GET`
y devuelve `405 Method Not Allowed`. Como alternativa visual, abrir
<http://localhost:8002/docs>, seleccionar el endpoint, pulsar **Try it out** y luego **Execute**.

El pipeline se ejecuta cada 10 segundos. Abrir el dashboard en:

<http://localhost:8501>

### 3. Verificar las capas

```powershell
docker compose exec postgres psql -U agent_user -d gen_ai_agent_db -c "SELECT COUNT(*) FROM agent_interactions;"
docker compose exec postgres psql -U agent_user -d gen_ai_agent_db -c "SELECT COUNT(*) FROM enriched_transactions;"
docker compose exec postgres psql -U agent_user -d gen_ai_agent_db -c "SELECT * FROM analytics_metrics ORDER BY metric_date DESC, total_transactions DESC;"
```

## Endpoints del agente

- `POST /transactions`: contrato consumido por Transaction Service.
- `GET /health`: estado de PostgreSQL, MCP y configuración LLM.
- `GET /docs`: OpenAPI interactivo.

Los duplicados por `transaction_id` se reconocen antes de insertar. Los errores de enriquecimiento
o del proveedor LLM se preservan como advertencias; un error de persistencia produce HTTP 503 para
no confirmar datos que no llegaron a Bronze.

## Herramientas MCP

- `list_locations`
- `get_location_by_id`
- `get_location_by_city`
- `get_location_by_country`
- `get_location_by_coordinates`

El endpoint MCP utiliza Streamable HTTP en `http://localhost:8003/mcp` y el SDK oficial de MCP.
Las búsquedas se realizan sobre la colección devuelta por `/locations`: esto evita depender del
orden de rutas específicas del servicio proporcionado, sin modificar dicho servicio.

## Pipeline

El proceso continuo realiza:

1. Bronze → Silver: carga las interacciones en pandas, aplana `raw_metadata` con
   `json_normalize`, normaliza texto, convierte fechas y valores numéricos, valida rangos y
   conserva los errores de calidad en `validation_errors`. Si falta el enriquecimiento, reintenta
   la consulta MCP hasta `MAX_ENRICHMENT_ATTEMPTS` veces y actualiza la fila Silver de forma
   idempotente.
2. Silver → Gold: recalcula los grupos válidos por fecha y ciudad y hace `UPSERT` contra la clave
   `(metric_date, city)`. Reejecutarlo no duplica métricas.

Una ejecución manual puede lanzarse así:

```powershell
docker compose run --rm pipeline python -c "from sqlalchemy import create_engine; from pipeline.run import run_once, DATABASE_URL; print(run_once(create_engine(DATABASE_URL)))"
```

## Calidad y pruebas

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace `
  ghcr.io/astral-sh/uv:0.8.17-python3.11-bookworm-slim `
  uv run --frozen --group dev pytest -q

docker run --rm -v "${PWD}:/workspace" -w /workspace `
  ghcr.io/astral-sh/uv:0.8.17-python3.11-bookworm-slim `
  uv run --frozen --group dev ruff check .
```

Las pruebas cubren validación del contrato, timestamps, coordenadas, clasificación multilingüe,
fallback heurístico, normalización pandas y validación Silver, y agregaciones Gold.

## Operación

Ver logs:

```powershell
docker compose logs -f agent mcp-server pipeline
```

Detener sin borrar datos:

```powershell
docker compose down
```

Borrar también el volumen de PostgreSQL (acción destructiva):

```powershell
docker compose down -v
```

Iniciar pgAdmin opcionalmente:

```powershell
docker compose --profile tools up -d pgadmin
```

## Decisiones técnicas

- Dependencias fijadas y lockfile para builds repetibles.
- Procesos sin privilegios dentro del contenedor.
- Health checks y orden de arranque basado en salud.
- Configuración tipo twelve-factor mediante variables de entorno.
- Timeouts, reintentos acotados y logs estructurados por evento.
- Validación Pydantic en el borde de entrada.
- SQL parametrizado y transacciones atómicas.
- Dashboard desacoplado que consulta solamente Gold.
