# Production preflight findings — 2026-08-22

OpenClaw inspected the Oracle ARM64 VPS without making changes.

## Confirmed

- Ubuntu 24.04.4 LTS, aarch64.
- 23 GiB RAM, 4 GiB swap, 72 GiB free on `/`.
- Docker 29.7.2 and Docker Compose v5.5.0.
- `127.0.0.1:8000` is occupied by `oraculo-prod-api-1` and must not be touched.
- `127.0.0.1:5432` is free.
- Existing OpenClaw, loan calculator and unrelated containers/services are healthy.
- Main cloudflared runs as a token-based systemd service with no local ingress config discovered.
- GHCR image for main commit `c4e354ecf04bf7f665e95aaa05b3fc23e46359e8` exists for linux/arm64.

## Decisions

- Job Radar production API moves to loopback port `8010`, subject to immediate recheck before first deploy.
- PostgreSQL remains on loopback `5432`.
- First deploy is localhost-only.
- Cloudflare exposure is deferred until localhost smoke + OpenClaw canary pass.
- Do not touch the cloudflared systemd warning (`daemon-reload`) during Job Radar rollout; treat it as separate operational debt.

## Follow-up

The deployment scripts now include an explicit port preflight and the production env/runbooks use `8010` instead of assuming `8000`.
