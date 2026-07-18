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

## Estado v0.7

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
- LLM bajo demanda: si `OPENAI_API_KEY` esta configurado usa Responses API con `JOB_RADAR_LLM_MODEL` opcional; si no, cae a analisis heuristico para no bloquear el flujo

## Fuentes activas

- AgentMail: lee `tracking/agentmail-vacancies/processed-vacancies-*.json`
- JobSpy: `linkedin` e `indeed`, con busquedas definidas en el perfil
- GetOnBoard: HTML simple como fuente experimental

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

## Siguiente fase

1. Revisar `entregables/JOB_RADAR_PERSONAL_LATEST.xlsx` o el dashboard local.
2. Ajustar `config/job-radar-profile.json` desde el dashboard segun falsos positivos/falsos negativos.
3. Subir un CV real desde `CV / Perfil`, revisar el Markdown y el JSON generado, y correr el radar para aplicar el perfil.
4. Revisar duplicados ocultos desde el filtro `Duplicadas` si parece que falta alguna vacante.
5. Agregar Bumeran o mejorar GetOnBoard si aportan vacantes reales.
6. Cuando el reporte sea util, crear wrapper cron sin enviar listas largas.
