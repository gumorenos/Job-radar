# QA pendiente — Job Radar

Este archivo mantiene solo gates operativos pendientes. OpenClaw actúa como QA/operador: no desarrolla ni corrige código. Cada mensaje enviado por Discord debe tener menos de 2.000 caracteres.

## Historial cerrado

Los antiguos QA-001 a QA-006 quedaron absorbidos por el QA consolidado del PR #14 (`docs/qa-core-completion.md`). El núcleo v1 pasó finalmente en Oracle ARM64 y navegador real sobre HEAD `1a84ac19a012561b83c98ef9a43314cd2170fb2a` y fue mergeado a `main` mediante commit `585d8739f8f49b52b3d928fcdc0f7da5a1cfe6f0`.

No repetir esos bloques salvo regresión específica.

---

## QA-007 — Production rollout + OpenClaw canary

**Estado:** PENDIENTE  
**Ámbito:** despliegue real Oracle ARM64, sin migración histórica todavía  
**Runbook:** `docs/deployment.md`  
**Contrato OpenClaw:** `docs/openclaw-ingestion.md`

### Gate A — preflight VPS

Antes de modificar producción, OpenClaw debe reportar:

- arquitectura, RAM/disco y Docker/Compose;
- puertos/listeners y servicios/contenedores existentes;
- estado del `cloudflared` systemd principal;
- disponibilidad de `127.0.0.1:8000` y `127.0.0.1:5432`;
- salud de servicios ajenos a Job Radar;
- posibilidad de obtener la imagen GHCR ARM64 del commit objetivo.

No tocar el túnel/contenedor independiente del loan calculator ni otros servicios.

### Gate B — deploy localhost-only

1. Crear `/srv/job-radar/{app,storage,backups}` con permisos apropiados.
2. Checkout exacto de `main` y `.env.production` 0600 con secretos aleatorios URL-safe.
3. Telegram deshabilitado.
4. Pin de `JOB_RADAR_IMAGE=ghcr.io/gumorenos/job-radar:sha-<main-commit>`.
5. Ejecutar `bash ops/deploy.sh .env.production`.
6. Ejecutar `bash ops/smoke.sh .env.production`.
7. Confirmar API/PostgreSQL solo loopback, worker sin puerto y Alembic head.
8. Ejecutar `bash ops/backup.sh .env.production /srv/job-radar/backups 14` y verificar dump no vacío/0600.
9. Confirmar que servicios ajenos permanecen sin cambios.

### Gate C — canary OpenClaw

Con Job Radar aún localhost-only:

1. Configurar el API key como secreto/runtime de OpenClaw, nunca en prompt/código/log.
2. Mantener OpenClaw -> Notion en paralelo.
3. Enviar una vacante canary identificable a `POST http://127.0.0.1:8000/api/v1/ingestions/jobs`.
4. Verificar 202, procesamiento completo, Radar y explicación.
5. Repetir exactamente la misma request con mismo idempotency key: `already_accepted`, sin duplicados.
6. Enviar una segunda observación real con nueva key y comprobar dedupe/sighting según corresponda.

### Gate D — exposición dashboard

Solo tras PASS de A-C:

- añadir hostname Job Radar al `cloudflared` systemd existente apuntando a `127.0.0.1:8000`;
- protegerlo con Cloudflare Access o control equivalente antes de uso externo;
- validar `/app/` por HTTPS;
- confirmar que PostgreSQL nunca es accesible externamente.

### Resultado esperado

Reporte final: PASS/FAIL por gate, commit e imagen exactos, health/ready, migración, bindings, backup, canary, idempotencia/dedupe, servicios ajenos sin cambios, Cloudflare/Access si se ejecutó y rollback image registrado.
