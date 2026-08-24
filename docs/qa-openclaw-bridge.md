# QA — OpenClaw -> Job Radar bridge

OpenClaw executes this checklist only as QA/deployment operator. It must not modify source code, existing vacancy scripts, the Notion/Supabase/Fast.io sync, Cloudflare, or unrelated services.

## Context

Job Radar production already runs on the Oracle ARM64 VPS at `127.0.0.1:8010`; PostgreSQL is loopback-only at `127.0.0.1:5432`. The current OpenClaw vacancy workflow is cron-driven and writes processed JSON under `/home/ubuntu/.openclaw/workspace/tracking/agentmail-vacancies/`. Existing cloud sync must stay intact during burn-in.

The bridge code is authored in the Job Radar repository and deployed by `ops/install_openclaw_bridge.sh`. OpenClaw does not write the bridge logic.

## Gate 1 — exact release

- checkout exact merged `main` commit in `/srv/job-radar/app`;
- verify the corresponding immutable GHCR ARM64 image exists;
- run existing Job Radar smoke checks before touching the bridge;
- record existing OpenClaw crontab and hashes of the current vacancy scripts.

## Gate 2 — controlled install

Run:

```bash
bash ops/install_openclaw_bridge.sh /srv/job-radar/app/.env.production
```

Verify:

- current vacancy scripts have identical hashes before/after;
- existing AgentMail and daily-summary cron entries are unchanged;
- exactly one `JOB_RADAR_BRIDGE_MANAGED` cron entry exists;
- bridge script exists and is executable;
- dedicated `config/job-radar.env` is mode `0600` and contains no PostgreSQL password;
- API URL points only to `127.0.0.1:8010`;
- activation cutoff is at install time so historical processed files are not imported;
- OpenClaw gateway was not restarted.

## Gate 3 — dry run

Use one known processed JSON with `--file ... --dry-run` and confirm mapping succeeds without HTTP traffic or state mutation. Check that missing work mode, seniority, external ID and relative publication timestamps are not invented.

## Gate 4 — synthetic canary through the deployed bridge

Create one temporary processed-vacancy JSON fixture matching the real observed shape, after the activation cutoff. Run the deployed bridge explicitly on that file.

Expected:

- one Job Radar `202 accepted`;
- worker completes normalization and analysis;
- Radar shows the canary;
- bridge state records one accepted event;
- rerunning the same file reports skipped/already-state behavior and creates no additional ingestion/job/posting/sighting/analysis;
- Notion/Supabase/Fast.io paths remain untouched by the bridge test.

Delete only the temporary fixture after evidence is collected; preserve bridge state/log.

## Gate 5 — real burn-in activation

Allow the managed bridge cron to run alongside the existing vacancy cron. Validate at least the first real processed batch:

- existing cloud sync still succeeds;
- every post-cutoff processed vacancy is attempted once by the bridge;
- Job Radar receives and processes expected rows;
- titles/companies/locations/URLs/salary text match the processed JSON;
- duplicate/reappearance behavior is owned by Job Radar, not by the transport state;
- bridge log contains no API key or database secret.

Do not disable Notion yet.

## Rollback test

If install/canary fails, run:

```bash
bash ops/uninstall_openclaw_bridge.sh
```

Confirm only the managed bridge cron/script/secret are removed and existing vacancy cron/cloud sync remains healthy. State/log/history may remain for audit.

## Report

Return PASS/FAIL for: exact release, install isolation, secret isolation, dry run, synthetic canary, retry/idempotency, existing cloud sync unchanged, real burn-in first batch (if executed), logs/secrets, and rollback readiness. Include exact commit and evidence, but never secret values.
