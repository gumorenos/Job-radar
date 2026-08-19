# Code review del núcleo — 2026-08-18

Revisión del `main` actual y de los bloques de núcleo abiertos (#8–#12), enfocada en corrección de negocio, ciclo de ingestión, persistencia, seguridad operativa, build y mantenibilidad.

## Hallazgos graves corregidos en este branch

### CR-001 — falso descarte de vacantes presenciales válidas en Lima Metropolitana

La regla geográfica solo reconocía un subconjunto pequeño de distritos. Una vacante 100% presencial en distritos válidos como Ate, Los Olivos, San Juan de Lurigancho o Villa El Salvador podía clasificarse como `DISCARD` por estar "fuera de Lima".

**Impacto:** pérdida silenciosa de oportunidades válidas, contradiciendo una regla dura del producto.

**Corrección:** ampliar la cobertura de Lima Metropolitana/Callao y añadir regresiones unitarias para distritos antes no reconocidos, manteniendo Arequipa como caso de descarte.

### CR-002 — redescubrimientos podían generar análisis repetidos y futuras notificaciones duplicadas

Cada `NORMALIZE_INGESTION` encolaba un nuevo `ANALYZE_MATCH`, incluso si la publicación ya existía y no había cambiado. Además, cuando una publicación existente sí cambiaba (por ejemplo salario o descripción), el registro persistido no se refrescaba.

**Impacto:** `MatchAnalysis` redundantes, análisis sobre datos obsoletos y, al conectar envío real, riesgo de múltiples notificaciones para la misma oportunidad sin cambio material.

**Corrección:**

- la normalización ahora informa si hubo cambio material;
- redescubrimientos idénticos solo actualizan sighting/`last_seen`;
- cambios materiales refrescan posting/job y solicitan reanálisis;
- si ya existe un análisis `PENDING` para el job, se reutiliza porque leerá el último estado persistido;
- un análisis `RUNNING` no se reutiliza, para garantizar un follow-up si pudo leer el estado anterior;
- integración de regresión cubre refresh de salario/descripción, coalescing y ausencia de reanálisis idéntico.

## Observaciones importantes no bloqueantes

### CR-003 — build Docker no reproducible

El Dockerfile resolvía dependencias solo desde `pyproject.toml`. Se corrigió para copiar `uv.lock` y ejecutar `uv sync --locked --no-dev`.

### CR-004 — defaults conocidos en Compose

Compose mantiene defaults de desarrollo para PostgreSQL y API key. Hoy la API está diseñada para loopback y no existe despliegue público de Job Radar, pero antes de exponerla mediante Cloudflare debe hacerse obligatorio configurar secretos de producción y activar Cloudflare Access.

### CR-005 — defaults de CandidateProfile duplicados entre PRs abiertos

Los PRs #9/#11 introducen un servicio compartido de perfil, mientras #10 contiene vocabulario ampliado de matching. Antes de integrar esos PRs se debe consolidar una sola fuente de defaults para evitar comportamiento dependiente del orden de creación del perfil.

### CR-006 — Matching v2 todavía puede sobrevalorar títulos genéricos

Términos como `Manager`, `Lead` o `Coordinator` deben exigir señal HR/People suficientemente fuerte para evitar promover puestos no-HR cuya descripción solo mencione RRHH incidentalmente. Se abordará en Matching/Analysis v3.

### CR-007 — consultas Radar N+1

Radar obtiene análisis, feedback, posting y compañía por job mediante consultas separadas. Es aceptable para escala personal inicial; conviene optimizar antes de crecer volumen o multiusuario.

## Seguridad y privacidad revisadas

- PostgreSQL y API se publican en Compose solo sobre `127.0.0.1`.
- Ingestión requiere Bearer token con comparación constante.
- `.gitignore` excluye `.env`, CVs PDF/DOCX, storage, backups y el perfil real local.
- No se detectaron secretos evidentes en los archivos de configuración inspeccionados.
- Los endpoints de UI no tienen auth de aplicación; esto es aceptable mientras permanezcan loopback y el futuro acceso web quede detrás de Cloudflare Access. No se debe publicar el hostname antes de esa protección.

## Criterio de integración

Este branch no se mezcla hasta que CI (Ruff, mypy, unit, Alembic e integración PostgreSQL) esté verde. El smoke ARM64/Oracle se registra aparte en `docs/qa-pending.md` y queda pendiente mientras OpenClaw no esté disponible.
