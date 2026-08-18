# QA pendiente — Job Radar

Este archivo registra validaciones que requieren el VPS Oracle/ARM64, navegador real u operaciones que no debe ejecutar el desarrollo normal. El código se sigue validando con GitHub Actions; estas pruebas quedan pendientes hasta que OpenClaw vuelva a estar disponible.

## Reglas de ejecución

- OpenClaw actúa solo como QA/operador: no desarrolla ni corrige código.
- No hacer merge, despliegue de producción ni cambios a OpenClaw, Cloudflare, Notion u otros servicios durante QA.
- Usar proyecto Docker aislado `job-radar-qa`.
- Preferir API `127.0.0.1:18000` y PostgreSQL `127.0.0.1:15432`.
- Crear `.env` de QA con secretos aleatorios; nunca versionarlo.
- Exportar `.env` antes de ejecutar integration tests.
- Limpiar contenedores, volúmenes y storage QA al finalizar.
- Cada prompt enviado por Discord debe tener menos de 2.000 caracteres.

---

## QA-001 — Applications CRM v1

**Estado:** PENDIENTE  
**PR:** #8 — `CRM: add applications lifecycle`  
**Branch:** `feat/applications-crm-v1`  
**HEAD esperado:** `125dc42d25f006ff58b06deed669f3f89e273ac8`  
**Bloquea merge:** Sí

### Validación estática y runtime

1. `uv sync --locked`
2. Ruff, mypy y unit tests.
3. Docker Compose config/build.
4. Confirmar imagen ARM64.
5. Levantar PostgreSQL aislado.
6. `alembic upgrade head`.
7. Levantar API y worker.
8. `/health`, `/ready` y `/app/` deben responder 200.
9. Con `.env` exportado, ejecutar `tests/integration`.
10. Confirmar que existe la tabla `job_applications`.

### Flujo funcional

Ingestar una vacante ficticia `Strategic HRBP QA CRM`, empresa `QA CRM Corp`, Lima, híbrida, sin salario. Esperar `NORMALIZE_INGESTION` y `ANALYZE_MATCH` en `COMPLETED`; la clasificación debe quedar `REVIEW`.

Desde `/app/`:

1. Radar → Revisar → abrir la vacante.
2. Añadir a Postulaciones.
3. Confirmar `Para postular = 1` y una sola fila CRM.
4. Cambiar a `Postulada`; debe crearse `applied_at`.
5. Cambiar `Entrevista → Oferta → Cerrada`; conteos y lista deben seguir el cambio.
6. Reabrir a `Entrevista`; `closed_at` debe volver a `NULL` y `applied_at` conservarse.
7. Intentar añadir de nuevo desde Radar; no debe duplicarse (`job_applications count = 1`).
8. `MatchAnalysis` debe seguir `REVIEW`; el estado CRM nunca altera la clasificación de matching.

### UX

- Desktop 1366×768.
- Mobile 390×844.
- Consola del navegador limpia.
- Confirmar que ya no existe la barra flotante inferior que solapaba el panel de detalle.
- API y PostgreSQL expuestos solo en localhost.

### Criterio de cierre

PASS únicamente si runtime, migración, integración, flujo CRM, timestamps, idempotencia, separación matching/CRM y UX pasan sin cambios de código ni de producción.

---

## QA-002 — CV library v1

**Estado:** PENDIENTE  
**PR:** #9 — `CVs: add versioned personal library`  
**Branch:** `feat/cv-library-v1`  
**HEAD esperado:** `486eaa5e253f505aa2e84502730c6a52197b2384`  
**CI GitHub:** PASS  
**Bloquea merge:** Sí

### Runtime

1. Ejecutar `uv sync --locked`, Ruff, mypy y unit tests.
2. Build Docker y confirmar `arm64`.
3. Levantar PostgreSQL, ejecutar `alembic upgrade head`, API y worker.
4. Confirmar `/health`, `/ready`, `/app/` y `/app/cvs.js` = 200.
5. Con `.env` exportado ejecutar `tests/integration`.

### Flujo CV

1. Abrir `/app/#/cvs`; inicialmente debe cargar desde `/api/v1/cvs` sin errores.
2. Añadir `CV Base QA`, marcarlo Base y Activo. Debe quedar `APPROVED`, `is_base=true`, `is_active=true`.
3. Crear `Nueva versión`; debe conservar la original, crear versión 2 y `parent_cv_id` debe apuntar a la versión 1.
4. Confirmar que solo una versión queda activa.
5. Crear por API un CV con `generated_by_ai=true`. Debe quedar `DRAFT`, mostrarse como `IA` y no poder activarse (`409`).
6. Aprobar el borrador desde la UI y luego activarlo. Debe quedar `APPROVED` y pasar a ser el único activo.
7. Crear otro borrador IA y rechazarlo; debe quedar `REJECTED` e inactivo.
8. Confirmar en PostgreSQL que ninguna creación/versionado sobrescribió el contenido de versiones anteriores.

### UX

- Desktop 1366×768 y mobile 390×844.
- Dialog de Añadir/Nueva versión usable sin overflow bloqueante.
- Mensajes de guardado/aprobación/activación visibles.
- Consola limpia y requests de CVs sin 4xx/5xx inesperados.
- API/PostgreSQL solo localhost.

### Criterio de cierre

PASS si versionado, aprobación explícita de IA, activación única, preservación del original, API, UI y ARM64 funcionan sin modificar código ni producción.
