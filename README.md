
# AI & DATA Evaluation

### Contexto

Bienvenido a la evaluacion de Ingeniero de Datos e IA. Eres parte del equipo de ingeniería de **GeoAI Analytics**, una startup que proporciona análisis de ubicación contextual mediante IA a empresas de logística y retail.

### El Problema

A las **3:47 AM del viernes**, el agente principal de procesamiento de consultas sufrió un **fallo crítico** y quedó completamente inoperativo. El sistema de respaldo no se activó correctamente debido a una configuración errónea en producción.

**Situación actual**:
```
✗ Failed to send transaction txn_000042: All connection attempts failed
✗ Failed to send transaction txn_000043: All connection attempts failed  
✗ Failed to send transaction txn_000044: All connection attempts failed
✗ Failed to send transaction txn_000045: All connection attempts failed
```

### Tu Misión

El CTO te ha asignado como **AI & Data Developer de recuperación**. Tu objetivo es construir un **agente de reemplazo funcional** que:

1. Reciba las transacciones acumuladas (ya hay un servicio generador funcionando)
2. Enriquezca cada consulta con datos de ubicación contextual (ya hay un servicio que proporciona estos datos)
3. Analice sentimiento y urgencia con LLM (requisito del cliente)
4. Persista los datos en la base de datos para auditoría y análisis (requisito del cliente)
5. Genere métricas en tiempo real para el equipo de operaciones (requisito del cliente)

**Deadline**: Tienes **6-8 horas** antes de la reunión con stakeholders.

**Recursos disponibles**:
- Location Service operativo (puerto 8001)
- Transaction Generator listo (puerto 8002)
- PostgreSQL con schema correcto (puerto 5432)

---

# AI & Data Agent Evaluation - Simulated Services

Este proyecto proporciona los **servicios simulados** necesarios para la evaluación técnica del rol de **Ingeniero de Datos e IA**. Los candidatos deben integrar estos servicios con su implementación de agente, MCP Server, pipeline ETL y dashboard.

## Descripción General

Este repositorio contiene:

1. **Location Service** (PROPORCIONADO) - Servicio REST con datos de ubicaciones
2. **Transaction Service** (PROPORCIONADO) - Generador de transacciones simuladas
3. **PostgreSQL Database** - Base de datos con esquema medallón (Bronze/Silver/Gold)
4. **Docker Compose** - Orquestación de servicios

## Requisitos Previos

Antes de comenzar con la evaluación, asegúrate de tener instaladas las siguientes herramientas:

### 1. Python 3.10+

Si no tienes Python instalado, descárgalo desde el sitio oficial:

**🔗 [Descargar Python](https://www.python.org/downloads/)**

Verifica la instalación:
```bash
python --version
# o
python3 --version
```

### 2. Gestor de Paquetes uv

Este proyecto utiliza **uv** como gestor de paquetes y entornos virtuales (venv).

**Instalación de uv:**

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# O con pip (si prefieres)
pip install uv
```

Verifica la instalación:
```bash
uv --version
```

**[Documentación de uv](https://docs.astral.sh/uv/)**

### 3. Docker y Docker Compose

Docker es **bastante recomendable pero no obligatorio**. Facilita la ejecución de los servicios proporcionados para el desarrollo de este ejercicio (Location Service, Transaction Service y PostgreSQL con las tablas pre configuradas).

**Instalación de Docker:**

- **macOS/Windows**: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Linux**: [Docker Engine](https://docs.docker.com/engine/install/)

Verifica la instalación:
```bash
docker --version
docker-compose --version
```

---

## Inicio Rápido

### Prerrequisitos Verificados

Asegúrate de haber completado la sección **Requisitos Previos** antes de continuar.

### 1. Configurar variables de entorno

```bash
# Copiar variables de entorno
cp .env.example .env

# Editar .env con tus configuraciones
nano .env
```

### 2. Iniciar Servicios con Docker Compose

```bash
# Iniciar todos los servicios
docker-compose up -d

# Ver logs
docker-compose logs -f

# Verificar estado
docker-compose ps
```

### 3. Verificar Servicios

```bash
# Location Service
curl http://localhost:8001/

# Transaction Service
curl http://localhost:8002/

# PostgreSQL (requiere cliente psql)
psql -h localhost -U agent_user -d gen_ai_agent_db
```

## Servicios Proporcionados

### 1. Location Service (Puerto 8001)

Servicio REST que proporciona datos de 12 ubicaciones globales con información contextual.

#### Endpoints Disponibles

```bash
# Listar todas las ubicaciones
GET http://localhost:8001/locations

# Obtener ubicación por ID
GET http://localhost:8001/locations/loc_cdmx_001

# Buscar por ciudad
GET http://localhost:8001/locations/by-city/Tokyo

# Buscar por coordenadas
GET http://localhost:8001/locations/by-coordinates?latitude=19.4326&longitude=-99.1332

# Buscar por país
GET http://localhost:8001/locations/by-country/Mexico
```

#### Ejemplo de Respuesta

```json
{
  "location_id": "loc_cdmx_001",
  "city": "Ciudad de México",
  "country": "México",
  "latitude": 19.4326,
  "longitude": -99.1332,
  "timezone": "America/Mexico_City",
  "weather": {
    "temperature": 22,
    "condition": "Soleado",
    "humidity": 45,
    "wind_speed": 12
  },
  "observations": [
    "Alta densidad poblacional",
    "Zona metropolitana",
    "Horario pico: 7-9 AM, 6-8 PM"
  ],
  "demographics": {
    "population": 9200000,
    "language": "Español",
    "currency": "MXN"
  }
}
```



### 2. Transaction Service (Puerto 8002)

Servicio que genera y envía transacciones simuladas al agente.

#### Modos de Operación

**Modo Continuo**: Envía transacciones automáticamente a intervalos regulares
**Modo Manual**: Permite enviar transacciones bajo demanda

#### Endpoints de Control

```bash
# Ver estado del servicio
GET http://localhost:8002/status

# Configurar endpoint del agente
POST http://localhost:8002/configure
{
  "agent_endpoint": "http://localhost:8000/transactions",
  "interval_seconds": 5
}

# Iniciar envío continuo
POST http://localhost:8002/start

# Detener envío continuo
POST http://localhost:8002/stop

# Enviar una transacción manual
POST http://localhost:8002/send-one

# Enviar lote de transacciones
POST http://localhost:8002/send-batch?count=10

# Reiniciar contador
POST http://localhost:8002/reset
```

#### Formato de Transacción

```json
{
  "transaction_id": "txn_000001",
  "user_id": "user_a1b2c3d4",
  "timestamp": "2024-01-15T10:30:00Z",
  "query": "¿Cuál es el clima en mi ubicación?",
  "llm_model": "gpt-4",
  "tokens_used": 150,
  "response_time_ms": 1200,
  "location_metadata": {
    "latitude": 19.4326,
    "longitude": -99.1332,
    "city": "Ciudad de México"
  }
}
```

### 3. PostgreSQL Database (Puerto 5432)

Base de datos con esquema medallón pre-configurado.

#### Credenciales por Defecto

```
Host: localhost
Port: 5432
Database: gen_ai_agent_db
User: agent_user
Password: agent_password
```

#### Esquema de Tablas

**Bronze Layer**: `agent_interactions` - Datos crudos del agente
**Silver Layer**: `enriched_transactions` - Datos enriquecidos y validados
**Gold Layer**: `analytics_metrics` - Métricas agregadas

Ver detalles completos en `database/schema.sql`

## Tareas del Candidato

Los candidatos deben implementar este ejercicio de acuerdo al Stack manejado en la organización:

### 1. MCP Server
- Consumir el Location Service
- Implementar y exponer herramientas MCP para el agente
- Implementar con el SDK oficial para MCP

### 2. Agente Analizador
- Recibir transacciones en `POST /transactions`
- Usar MCP Server para enriquecer datos
- Persistir en PostgreSQL (tabla `agent_interactions`)
- Implementar con FastAPI, LangGraph o LangChain

### 3. Pipeline ETL
- Bronze → Silver: Enriquecer con datos de ubicación
- Silver → Gold: Agregar métricas
- Implementar transformaciones para cada capa usando Python con pandas

### 4. Dashboard
- Implementar dashboard usando Streamlit con 3+ visualizaciones
- Conectar a capa Gold
- KPIs y gráficos analíticos

## Estructura minima esperada de entrega

```
candidate-solution/                
    ├── mcp_server/                   
    ├── agent/                          
    ├── pipeline/                         
    ├── dashboard/
    ├── docker-compose.yml                  (Orquestación completa de componentes del sistema SIN modificar los servicios proporcionados.)
    ├── pyproject.toml                        
    └── README.md                           (Breve documentación de la implementación y ejecución del sistema cubriendo el objetivo del ejercicio)
```

## El candidato NO debe modificar:

- transaction_service/
- location_service/ 
- Dockerfile.location-service
- Dockerfile.transaction-service
- database/

Estos componentes son proporcionados por el evaluador.
La implementación debe desarrollarse dentro de candidate-solution.
La solución debe ser completamente reproducible. El evaluador debe poder ejecutar:

```bash
docker compose up --build
```

Una vez desplegada la solución, el evaluador deberá poder:

- Ejecutar el flujo completo de procesamiento de transacciones con los servicios proporcionados.
- Validar la persistencia de información en PostgreSQL en el esquema de base de datos proporcionado.
- Acceder al dashboard y visualizar los indicadores, métricas y gráficos construidos sobre la capa Gold.


## Recursos sobre el Stack indicado

- [Documentación de uv](https://docs.astral.sh/uv/)
- [Documentación de MCP](https://modelcontextprotocol.io/)
- [LangChain Documentation](https://python.langchain.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Streamlit Documentation](https://docs.streamlit.io/)


