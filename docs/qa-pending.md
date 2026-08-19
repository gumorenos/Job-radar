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
**CI GitHub:** PASS  
**Bloquea merge:** Sí

### Validación estática y runtime

1. `uv sync --locked`.
2. Ruff, mypy y unit tests.
3. Docker Compose config/build y confirmar imagen ARM64.
4. Levantar PostgreSQL aislado, `alembic upgrade head`, API y worker.
5. `/health`, `/ready` y `/app/` deben responder 200.
6. Con `.env` exportado, ejecutar `tests/integration`.
7. Confirmar que existe la tabla `job_applications`.

### Flujo funcional

Ingestar `Strategic HRBP QA CRM`, empresa `QA CRM Corp`, Lima, híbrida, sin salario. Esperar `NORMALIZE_INGESTION` y `ANALYZE_MATCH` en `COMPLETED`; la clasificación debe quedar `REVIEW`.

1. Radar → Revisar → abrir la vacante → Añadir a Postulaciones.
2. Confirmar `Para postular = 1` y una sola fila CRM.
3. Cambiar a `Postulada`; debe crearse `applied_at`.
4. Cambiar `Entrevista → Oferta → Cerrada`; conteos/lista deben seguir el cambio.
5. Reabrir a `Entrevista`; `closed_at = NULL` y `applied_at` se conserva.
6. Intentar añadir de nuevo desde Radar; no debe duplicarse (`job_applications count = 1`).
7. `MatchAnalysis` debe seguir `REVIEW`; el estado CRM nunca altera matching.

### UX

- Desktop 1366×768 y mobile 390×844.
- Consola limpia.
- Confirmar que ya no existe la barra flotante inferior que solapaba el detalle.
- API y PostgreSQL solo localhost.

---

## QA-002 — CV library v1

**Estado:** PENDIENTE  
**PR:** #9 — `CVs: add versioned personal library`  
**Branch:** `feat/cv-library-v1`  
**HEAD esperado:** `5d11f0927db16dcc93026396134291f8c888adcb`  
**CI GitHub:** PASS  
**Bloquea merge:** Sí

### Runtime

1. `uv sync --locked`, Ruff, mypy y unit tests.
2. Build Docker y confirmar `arm64`.
3. PostgreSQL, `alembic upgrade head`, API y worker.
4. `/health`, `/ready`, `/app/` y `/app/cvs.js` = 200.
5. Con `.env` exportado ejecutar `tests/integration`.

### Flujo CV

1. Abrir `/app/#/cvs`; debe cargar `/api/v1/cvs` sin errores.
2. Añadir `CV Base QA`, marcar Base y Activo. Debe quedar `APPROVED`, `is_base=true`, `is_active=true`.
3. Crear Nueva versión; preservar original, crear versión 2 y enlazar `parent_cv_id`.
4. Confirmar que solo una versión queda activa.
5. Crear por API `generated_by_ai=true`: debe quedar `DRAFT`, mostrarse `IA` y no poder activarse (`409`).
6. Intentar crear un borrador IA como Base: debe devolver `409` y no modificar el Base actual.
7. Aprobar el borrador desde UI y activarlo: `APPROVED` y único activo.
8. Crear otro borrador IA y rechazarlo: `REJECTED` e inactivo.
9. PostgreSQL debe conservar intacto el contenido de versiones anteriores.

### UX

- Desktop 1366×768 y mobile 390×844.
- Dialog Añadir/Nueva versión usable sin overflow bloqueante.
- Mensajes de guardado/aprobación/activación visibles.
- Consola limpia y requests sin 4xx/5xx inesperados.
- API/PostgreSQL solo localhost.

---

## QA-003 — Matching positive fit v2

**Estado:** PENDIENTE  
**PR:** #10 — `Matching: add positive-fit high priority signals`  
**Branch:** `feat/matching-fit-v2`  
**HEAD esperado:** `63d53a5509615ff3b69462f4f88b76131334da9a`  
**CI GitHub:** PASS  
**Bloquea merge:** Sí

### Objetivo

Validar que `rules-v2` puede elevar oportunidades realmente fuertes a `HIGH_PRIORITY` sin permitir que señales positivas anulen descartes duros ni warnings.

### Casos

1. Ejecutar estáticos/unit/integration, build ARM64, PostgreSQL/Alembic/API/worker.
2. `Analista Junior de RRHH`, Lima, S/9,000 → `DISCARD` por seniority.
3. `Strategic HR Business Partner`, Lima, híbrido, sin descripción de área foco → `REVIEW`.
4. `Senior People Analytics Analyst`, Lima, híbrido, S/9,000, descripción con People Analytics/HR Analytics → `HIGH_PRIORITY`, `analyzer_version=rules-v2`, `recommendation=PRIORIZAR`.
5. El caso anterior debe guardar `role_matches`, `core_area_matches`, strengths y explicación legible.
6. Mismo encaje fuerte remoto LATAM con salario S/7,500 → `DISCARD`; el hard rule salarial gana.
7. Un rol objetivo con solo área adyacente debe seguir `REVIEW`, no `HIGH_PRIORITY`.
8. Salario desconocido no debe descartar ni borrar un encaje positivo fuerte.
9. Radar debe reflejar correctamente Alta prioridad/Revisar/Descartadas y detalle explicable.
10. Desktop/mobile/console sin errores y exposición solo localhost.

---

## QA-004 — Profile settings v1

**Estado:** PENDIENTE  
**PR:** #11 — `Settings: make search profile editable`  
**Branch:** `feat/profile-settings-v1`  
**HEAD esperado:** `e89d1d9eb64b7824c701feff4939790bd21381bf`  
**CI GitHub:** PASS  
**Bloquea merge:** Sí

### Objetivo

Validar que Configuración permite editar el perfil de búsqueda en una sola pantalla y que esos cambios persisten sin tocar reglas internas ni crear perfiles duplicados.

### Casos

1. Ejecutar estáticos/unit/integration, build ARM64, PostgreSQL/Alembic/API/worker.
2. `/app/`, `/app/settings.js`, `/app/settings.css`, `/api/v1/profile` = 200.
3. Abrir `/app/#/settings`; debe cargar un único perfil activo.
4. Editar nombre, salario local a S/7,200 y multiplicador remoto a 1.15; UI debe mostrar mínimo remoto S/8,280.
5. Editar roles, ubicaciones, áreas foco y adyacentes; duplicados/espacios deben normalizarse al guardar.
6. Cambiar hora de revisión a 20:30 y mantener `America/Lima`.
7. Recargar: todos los valores deben persistir y `candidate_profiles count = 1`.
8. `rules` debe conservarse sin alteración.
9. Multiplicador menor que 1 debe ser rechazado por API con 422.
10. Ingestar una vacante con salario local S/7,100 después del cambio a S/7,200: el siguiente análisis debe usar el nuevo mínimo y descartarla.
11. Desktop 1366×768 y mobile 390×844; save bar, textareas y campos sin solapes; consola limpia.
12. API/PostgreSQL solo localhost.

---

## Cierre de un bloque

Un bloque pasa a PASS solo cuando OpenClaw confirme el HEAD exacto, runtime ARM64, pruebas automatizadas, flujo funcional, UX solicitada, ausencia de cambios de código/producción y limpieza del entorno QA. Hasta entonces el PR correspondiente permanece sin merge.
