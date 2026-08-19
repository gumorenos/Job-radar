# QA consolidada — cierre del núcleo Job Radar

Este es el único bloque de QA que debe ejecutarse para validar el PR consolidado de cierre del núcleo. Sustituye la necesidad de ejecutar por separado QA-001 a QA-006 antes de este PR; aquellos bloques quedan como historial de los PRs que originaron sus funcionalidades.

## Alcance

- **PR:** #14 — `Core completion: integrate personal Job Radar workflows`
- **Branch:** `feat/core-completion`
- **HEAD:** usar y reportar el HEAD exacto indicado en el prompt de QA.
- **Producción:** prohibido modificar/desplegar durante esta validación.
- **Rol de OpenClaw:** solo QA/operación; no corregir código.

## Entorno aislado

- Docker project: `job-radar-qa`
- API: `127.0.0.1:18000`
- PostgreSQL: `127.0.0.1:15432`
- secretos aleatorios de QA
- `JOB_RADAR_DATABASE_URL` debe apuntar explícitamente al PostgreSQL QA al ejecutar tests desde host
- Telegram deshabilitado salvo en la prueba controlada específica
- cleanup completo al finalizar

## Gate automatizado/runtime

1. Confirmar repo, branch y HEAD exacto; working tree limpio.
2. `uv sync --locked`.
3. Ruff, mypy y unit tests.
4. Build Docker ARM64 y confirmar arquitectura.
5. Levantar PostgreSQL 18 aislado.
6. Ejecutar `alembic upgrade head` y confirmar revisiones 0001 → 0002 → 0003.
7. Levantar API + worker; `/health`, `/ready`, `/app/` = 200.
8. Exportar `.env` QA y ejecutar todos `tests/integration`.
9. Confirmar API/PostgreSQL expuestos solo en loopback.

## Flujos funcionales obligatorios

### Ingesta / matching / rediscovery

- HR junior, Lima, salario alto → `DISCARD` por seniority.
- ONSITE Ate/SJL → no descartar por geografía.
- ONSITE Arequipa → `DISCARD`.
- Strong People Analytics + rol senior + S/9,000 → `HIGH_PRIORITY`, `rules-v3`.
- Strong Remote LATAM + S/7,500 PEN mensual → `DISCARD` por mínimo remoto.
- Strong Remote LATAM + `country=Peru` debe seguir usando mínimo remoto.
- Strong Remote LATAM + `USD 1,000 monthly` no convertido → `REVIEW`, nunca High Priority ni hard discard inventado.
- `Operations Manager` cuya descripción menciona People Analytics → `REVIEW`, no High Priority.
- Redescubrimiento idéntico: nuevo sighting, sin nuevo análisis.
- Redescubrimiento material S/8,500 → S/6,500 antes del análisis: un solo análisis pendiente y resultado final `DISCARD`.

### Duplicados inciertos

- Dos títulos muy similares de la misma empresa, URLs distintas → 1 `DuplicateCandidate` pendiente.
- `Mantener separadas` elimina el pendiente y conserva ambos jobs.
- Repetir y elegir `Unir`: consolidar postings en survivor, cerrar duplicate y preservar los `MatchAnalysis` históricos con sus job ids originales.
- Dos vacantes similares de `Empresa Confidencial` no deben asumirse misma empresa ni generar ruido por ese solo hecho.

### Feedback / CRM

- Cambiar clasificación humana y comprobar que el análisis original no se modifica.
- Añadir desde Radar a Postulaciones dos veces → una sola fila.
- `TO_APPLY → APPLIED → INTERVIEW → OFFER → CLOSED`; timestamps correctos.
- Reabrir CLOSED a INTERVIEW: `closed_at=NULL`, `applied_at` preservado.
- El stage CRM no altera clasificación matching.

### CVs / Configuración

- Crear Base manual aprobado/activo.
- Crear nueva versión sin sobrescribir original.
- Crear CV IA → `DRAFT`; activación previa a aprobación devuelve 409.
- Aprobar y activar; solo un CV activo.
- Rechazar otro borrador IA → inactivo.
- Crear CV especializado People Analytics aprobado y confirmar que un nuevo análisis compatible lo recomienda.
- Editar perfil: salario, multiplicador, roles/áreas, 21:00 `America/Lima`; recargar y comprobar persistencia/un solo perfil.

### Notificaciones

Con Telegram deshabilitado:
- `DISCARD` → ninguna notificación.
- High Priority → dashboard `SENT` + Telegram immediate `PENDING`; cero tráfico externo.
- Review → dashboard `SENT` + Telegram daily review `PENDING` a hora local configurada.

Prueba controlada de delivery sin usar producción:
- usar token/chat QA solo si están disponibles y autorizados;
- habilitar Telegram únicamente en entorno QA;
- confirmar una immediate y un daily batch sin duplicados;
- si no existen credenciales QA, validar dispatcher/delivery mediante suite automatizada y reportar el envío real como `NOT RUN`, no como FAIL.

### Seguridad / UX

- `JOB_RADAR_APP_ENV=production` + API key default debe impedir startup.
- producción con password `job_radar_dev` debe impedir startup.
- UI desktop 1366×768 y mobile 390×844: Radar, Duplicados, Postulaciones, CVs, Configuración sin overflow/solapes bloqueantes.
- consola del navegador limpia y assets 200.
- logs sin tokens, CV completo ni raw payloads sensibles.

## Resultado

Reportar exactamente:

- Overall PASS/FAIL
- HEAD probado
- CI/runtime/tests
- ARM64
- migraciones
- cada bloque funcional resumido
- UX desktop/mobile
- seguridad/exposición
- Telegram real: PASS / NOT RUN / FAIL
- cambios de código: NO
- cambios de producción: NO
- cleanup: PASS/FAIL

No hacer merge ni corregir nada. Un FAIL debe incluir comando/caso exacto, resultado esperado, resultado real y log mínimo sanitizado.
