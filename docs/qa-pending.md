# QA pendiente — Job Radar

Este archivo mantiene solo gates operativos pendientes. OpenClaw actúa como QA/operador: no desarrolla ni corrige código. Cada mensaje enviado por Discord debe tener menos de 2.000 caracteres.

## Historial cerrado

Los antiguos QA-001 a QA-006 quedaron absorbidos por el QA consolidado del PR #14 (`docs/qa-core-completion.md`). El núcleo v1 pasó finalmente en Oracle ARM64 y navegador real sobre HEAD `1a84ac19a012561b83c98ef9a43314cd2170fb2a` y fue mergeado a `main` mediante commit `585d8739f8f49b52b3d928fcdc0f7da5a1cfe6f0`.

El preflight inicial de producción detectó que `127.0.0.1:8000` pertenece a `oraculo-prod-api-1`; no debe tocarse. Job Radar selecciona `127.0.0.1:8010` como puerto candidato y debe revalidarlo justo antes del deploy. PostgreSQL `127.0.0.1:5432` estaba libre. El `cloudflared` systemd principal corre por token y no tiene ingress config local; su exposición pública queda separada del deploy localhost-only.

---

## QA-007 — Production rollout + OpenClaw canary

**Estado:** PENDIENTE  
**Ámbito:** despliegue real Oracle ARM64, sin migración histórica todavía  
**Runbook:** `docs/deployment.md`  
**Contrato OpenClaw:** `docs/openclaw-ingestion.md`

### Gate A — preflight final

Antes de modificar producción:

- confirmar exacto `main` e imagen GHCR ARM64;
- ejecutar `bash ops/preflight.sh .env.production`;
- `127.0.0.1:8010` y `127.0.0.1:5432` deben estar libres salvo servicios Job Radar ya existentes;
- servicios ajenos deben seguir sanos;
- no tocar `oraculo-prod-api-1`, loan calculator, OpenClaw ni cloudflared.

### Gate B — deploy localhost-only

1. Crear `/srv/job-radar/{app,storage,backups}` con permisos apropiados.
2. Checkout exacto de `main` y `.env.production` 0600 con secretos aleatorios URL-safe.
3. `JOB_RADAR_PORT=8010`, Telegram deshabilitado y pin de imagen `sha-<main-commit>`.
4. Ejecutar `bash ops/deploy.sh .env.production`.
5. Ejecutar `bash ops/smoke.sh .env.production`.
6. Confirmar API `127.0.0.1:8010`, PostgreSQL `127.0.0.1:5432`, worker sin puerto y Alembic head.
7. Ejecutar `bash ops/backup.sh .env.production /srv/job-radar/backups 14` y verificar dump no vacío/0600.
8. Confirmar que servicios ajenos permanecen sin cambios.

### Gate C — canary OpenClaw

Con Job Radar aún localhost-only:

1. Configurar el API key como secreto/runtime de OpenClaw, nunca en prompt/código/log.
2. Mantener OpenClaw -> Notion en paralelo.
3. Enviar una vacante canary a `POST http://127.0.0.1:8010/api/v1/ingestions/jobs`.
4. Verificar 202, procesamiento completo, Radar y explicación.
5. Repetir exactamente la misma request con mismo idempotency key: `already_accepted`, sin duplicados.
6. Enviar una segunda observación con nueva key y comprobar dedupe/sighting.

### Gate D — exposición dashboard

Solo tras PASS de A-C. El `cloudflared` principal actual es token-run y no usa config local, por lo que no editar `/etc/cloudflared/config.*` ni reiniciar el servicio para Job Radar. Crear la ruta/hostname desde el control plane de Cloudflare que administra ese túnel, apuntando a `http://127.0.0.1:8010`, y protegerla con Cloudflare Access antes del uso externo.

El warning existente de unit file cambiado/`daemon-reload` es deuda operativa ajena a este rollout; no corregirlo dentro de QA-007 salvo aprobación separada.

### Resultado esperado

Reporte final: PASS/FAIL por gate, commit e imagen exactos, health/ready, migración, bindings, backup, canary, idempotencia/dedupe, servicios ajenos sin cambios, Cloudflare/Access si se ejecutó y rollback image registrado.
