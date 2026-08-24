# QA — OpenClaw -> Job Radar bridge

OpenClaw executes this checklist only as QA/deployment operator. It must not modify source code, existing vacancy scripts, the Notion/Supabase/Fast.io sync, Cloudflare, or unrelated services.

## Context

Job Radar production already runs on the Oracle ARM64 VPS at `127.0.0.1:8010`; PostgreSQL is loopback-only at `127.0.0.1:5432`. The current OpenClaw vacancy workflow is cron-driven and writes processed JSON under `/home/ubuntu/.openclaw/workspace/tracking/agentmail-vacancies/`. Existing cloud sync must stay intact during burn-in.

The bridge code is authored in the Job Radar repository. OpenClaw only deploys and validates it.

## Gate 1 — exact release

- checkout exact merged `main` commit in `/srv/job-radar/app`;
- run existing Job Radar smoke checks;
- record current OpenClaw crontab and SHA-256 hashes of existing vacancy scripts;
- do not restart the OpenClaw gateway.

## Gate 2 — staged install, automatic bridge still OFF

Run:

```bash
bash ops/install_openclaw_bridge.sh /srv/job-radar/app/.env.production
```

Verify:

- existing vacancy script hashes are identical before/after;
- existing AgentMail and daily-summary cron entries are unchanged;
- **zero** `JOB_RADAR_BRIDGE_MANAGED` cron entries exist after a first install;
- bridge script exists and is executable;
- dedicated `config/job-radar.env` is mode `0600` and contains no PostgreSQL password;
- API URL is exactly localhost `127.0.0.1:8010`;
- activation cutoff is install time so historical processed files are not imported;
- OpenClaw gateway was not restarted.

If a bridge cron already existed from a prior enabled deployment, STOP and report instead of changing its state during this first-deploy QA.

## Gate 3 — dry run while automatic bridge is OFF

Use one known processed JSON with `--file ... --dry-run`. Confirm mapping succeeds without HTTP traffic or state mutation. Missing work mode, seniority, external ID and relative publication timestamps must not be invented.

## Gate 4 — synthetic canary while automatic bridge is OFF

Create one temporary processed-vacancy JSON fixture matching the real observed shape and run the deployed bridge explicitly with `--file`.

Expected:

- one Job Radar `202 accepted`;
- worker completes normalization and analysis;
- Radar shows the canary;
- bridge state records one accepted event;
- rerunning the exact same file is skipped from state and creates no additional ingestion/job/posting/sighting/analysis;
- existing Notion/Supabase/Fast.io paths are untouched by this explicit bridge test.

Delete only the temporary fixture after collecting evidence. Preserve state/log.

## Gate 5 — explicit enable only after Gate 4 PASS

Run:

```bash
bash ops/enable_openclaw_bridge.sh
```

Verify exactly one `JOB_RADAR_BRIDGE_MANAGED` cron entry exists and all pre-existing cron entries remain unchanged.

Then allow real burn-in alongside the existing vacancy cron. Validate the first real post-cutoff processed batch if one arrives during the QA window:

- existing cloud sync still succeeds;
- every new processed vacancy is attempted once by the bridge;
- Job Radar receives/processes expected rows;
- title/company/location/URL/salary text match processed JSON;
- bridge log contains no API key/database secret.

If no real vacancy arrives in a reasonable QA window, report real burn-in as `NOT RUN`, not FAIL. Do not fabricate traffic and do not disable Notion.

## Rollback readiness

If install/canary fails, run:

```bash
bash ops/uninstall_openclaw_bridge.sh
```

Confirm only managed bridge cron/script/secret are removed and existing vacancy cron/cloud sync remains healthy. State/log/history may remain for audit.

## Report

Return PASS/FAIL for exact release, staged install isolation, secret isolation, dry run, synthetic canary, retry/idempotency, explicit cron enable, existing cloud sync unchanged, first real burn-in batch PASS/NOT RUN, logs/secrets and rollback readiness. Include exact commit and evidence, never secret values.
