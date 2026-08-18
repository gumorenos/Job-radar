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
