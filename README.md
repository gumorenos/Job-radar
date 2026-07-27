# Job Radar Personal

MVP local-first para buscar, normalizar, deduplicar y rankear vacantes para Gus.

## Setup rapido

```bash
cp config/job-radar-profile.example.json config/job-radar-profile.json
uv venv tracking/job-radar/.venv
uv pip install --python tracking/job-radar/.venv/bin/python -r requirements.txt
tracking/job-radar/.venv/bin/python scripts/job_radar_dashboard.py --host 127.0.0.1 --port 8765
```

Abrir `http://127.0.0.1:8765`.

## Estado v0.8 - API foundation

La rama de fundaciones agrega una capa desplegable sin reemplazar todavía el dashboard local:

- FastAPI en `job_radar_app/api.py`.
- SQLAlchemy compatible con el SQLite existente y preparado para PostgreSQL mediante `JOB_RADAR_DATABASE_URL`.
- Migraciones con Alembic.
- Autenticación por `X-API-Key`.
- Ingesta idempotente para OpenClaw, futuros servidores MCP, n8n y extensiones de navegador.
- Registro de cada lote en `ingestion_runs`.
- Reutilización del scoring, normalización salarial y deduplicación del radar actual.
- Docker Compose ligado a `127.0.0.1` por defecto.

### Ejecutar la API localmente

```bash
cp .env.example .env
# Cambiar JOB_RADAR_API_KEY en .env
uv pip install --python tracking/job-radar/.venv/bin/python -r requirements.txt
JOB_RADAR_API_KEY='tu-token' tracking/job-radar/.venv/bin/python -m uvicorn job_radar_app.api:app --host 127.0.0.1 --port 8766
```

Documentación interactiva: `http://127.0.0.1:8766/docs`.

### Ejecutar con Docker Compose

```bash
cp .env.example .env
# Cambiar JOB_RADAR_API_KEY en .env
docker compose up -d --build
curl http://127.0.0.1:8766/health
```

La API queda solo en localhost. Para acceso remoto usa Tailscale, Cloudflare Access o un reverse proxy autenticado; no expongas directamente el puerto.

### Ingestar resultados de OpenClaw

```bash
curl -X POST http://127.0.0.1:8766/api/v1/postings/ingest \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: tu-token' \
  -d '{
    "source": "openclaw",
    "source_run_id": "daily-2026-07-26",
    "postings": [
      {
        "external_id": "linkedin-123456",
        "title": "HR Business Partner",
        "company": "Empresa X",
        "location": "Lima, Peru",
        "modality": "hybrid",
        "published_at": "2026-07-26",
        "salary_text": "S/ 8,000",
        "url": "https://example.com/job/123456",
        "description": "Strategic HRBP role..."
      }
    ]
  }'
```

Repetir exactamente `source + source_run_id` devuelve el resultado guardado sin insertar otra vez. Cada publicación también conserva una clave externa, URL limpia, `first_seen_at`, `last_seen_at`, score y veredicto.

Endpoints iniciales:

```text
GET  /health
POST /api/v1/postings/ingest
GET  /api/v1/jobs
GET  /api/v1/jobs/new-relevant
```

### Migraciones y pruebas

```bash
alembic upgrade head
uv pip install --python tracking/job-radar/.venv/bin/python -r requirements-dev.txt
tracking/job-radar/.venv/bin/python -m pytest
```

La migración base conserva las tablas SQLite existentes y agrega las que falten. Antes de migrar una base real, guarda una copia de `tracking/job-radar/job_radar.sqlite`.

### Alcance de esta primera etapa

La API y el dashboard antiguo comparten el mismo SQLite. El cambio definitivo a PostgreSQL, el modelo separado de `jobs`, `job_postings`, `applications`, contactos e entrevistas, y el servidor MCP quedan para las siguientes iteraciones. La API se diseña ahora como única puerta de entrada para evitar que OpenClaw, MCP y la extensión escriban directamente en la base.

## Estado v0.7 heredado

- Base local: `tracking/job-radar/job_radar.sqlite`
- Runner: `scripts/job_radar.py`
- Dashboard local: `scripts/job_radar_dashboard.py`
- Perfil editable: `config/job-radar-profile.json`
- Entregable latest: `entregables/JOB_RADAR_PERSONAL_LATEST.xlsx`
- Runs: `tracking/job-radar/runs/job-radar-*.{json,md}`
- Dedupe fuzzy: agrupa por titulo/empresa normalizados, conserva el mejor registro y oculta duplicados con `status='duplicate'`
- Calibracion inicial: baja matches fuertes que aparecen solo en la descripcion y penaliza roles comerciales como `account executive` / `key account manager`
- Perfil por CV: el dashboard acepta PDF/DOCX/Markdown/TXT, convierte a Markdown en `tracking/job-radar/profile/cv.md`, genera `tracking/job-radar/profile/candidate-profile.json` y el runner usa ese perfil como bonus de matching
- Match profundo: el dashboard permite seleccionar vacantes, pedir analisis CV/perfil vs puesto, guardar el resultado en SQLite (`vacancy_analyses`) y exportarlo a Markdown/XLSX (`entregables/JOB_RADAR_ANALISIS_MATCH_LATEST.*`)
- LLM bajo demanda: `JOB_RADAR_LLM_PROVIDER=openrouter|deepseek|openai`; por defecto usa OpenRouter + `deepseek/deepseek-v4-flash` si existe `OPENROUTER_API_KEY`; si no, cae a analisis heuristico para no bloquear el flujo
- Fuentes intercambiables: `enabled_sources` reemplaza/compatibiliza `enabled_portals`; soporta fuentes locales (`agentmail`, `linkedin`, `indeed`, `getonboard`) y aliases Apify (`apify_valig`, `apify_cheap_scraper`, `apify_curious_coder`) en modo disabled/dry-run hasta configurar token/cap de gasto
- Benchmark seguro: `scripts/job_radar_benchmark.py` genera plan dry-run, precios Apify publicos y snapshot local sin ejecutar actores pagados
- Cron wrapper preparado: `scripts/job_radar_cron.py --dry-run` muestra el comando L-V 07:00 Lima; no instala crontab ni envia Telegram por si solo

## Fuentes activas

- AgentMail: lee `tracking/agentmail-vacancies/processed-vacancies-*.json`
- JobSpy/local: `linkedin` e `indeed`, con busquedas definidas en el perfil
- GetOnBoard: HTML simple como fuente experimental
- Apify aliases preparados: `valig/linkedin-jobs-scraper`, `cheap_scraper/linkedin-job-scraper`, `curious_coder/linkedin-jobs-scraper`; no se ejecutan mientras `apify_mode` no sea `enabled`

## Fuentes probeadas

- Bumeran Peru: HTTP 200, pero requiere adaptar parser/API JS.
- Computrabajo Peru: HTTP 403 por requests simple.
- Buscojobs Peru: HTTP 403 por requests simple.

## Comandos

```bash
tracking/job-radar/.venv/bin/python scripts/job_radar.py --limit-per-query 5
```

Dashboard:

```bash
tracking/job-radar/.venv/bin/python scripts/job_radar_dashboard.py --host 127.0.0.1 --port 8765
```

Abrir:

```text
http://127.0.0.1:8765
```

El dashboard permite ver metricas activas, contar duplicados ocultos y falsos positivos, seleccionar portales incluidos, filtrar por fuente/veredicto/estado, abrir enlaces, descargar el Excel latest, marcar estados, editar el perfil JSON, subir/editar CV, seleccionar vacantes, analizar match CV/puesto y lanzar una nueva corrida. Por defecto queda solo en localhost; para usarlo desde otra maquina conviene tunel o Tailscale, no exposicion publica.

El venv vive dentro de `tracking/job-radar/.venv`. Si se recrea con `uv venv`, instalar dependencias con:

```bash
uv pip install --python tracking/job-radar/.venv/bin/python python-jobspy pandas openpyxl beautifulsoup4 pymupdf python-docx
```

Analisis de match por CLI:

```bash
tracking/job-radar/.venv/bin/python scripts/job_radar_match_analysis.py --export <vacancy_id>
```

Benchmark dry-run de fuentes:

```bash
tracking/job-radar/.venv/bin/python scripts/job_radar_benchmark.py --limit 200
```

Wrapper cron sin instalarlo:

```bash
tracking/job-radar/.venv/bin/python scripts/job_radar_cron.py --dry-run
```

## Siguiente fase

1. Conectar OpenClaw al endpoint de ingesta y retirar la escritura a Notion.
2. Probar despliegue persistente en el VPS mediante Tailscale o Cloudflare Access.
3. Separar `jobs`, `job_postings` y `applications`, y migrar a PostgreSQL.
4. Crear servidor MCP sobre la API, sin acceso SQL directo.
5. Validar un actor Apify con cap de gasto y normalizador real.
6. Crear bookmarklet y después extensión Chrome/Firefox.
