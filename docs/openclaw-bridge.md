# OpenClaw -> Job Radar bridge

This bridge is Job Radar code deployed beside OpenClaw. OpenClaw remains an operator/QA surface; it does not own or modify the integration logic.

## Why a separate bridge

The current vacancy pipeline is a deterministic cron workflow under `/home/ubuntu/.openclaw/workspace`:

```text
AgentMail -> processed-vacancies-*.json -> existing cloud sync -> Notion/Supabase/Fast.io
                                      \
                                       -> Job Radar bridge -> localhost API
```

The existing pipeline has no configurable generic HTTP sink. Rather than modify its parser, Notion writer or poller, Job Radar ships a standalone stdlib Python bridge. Existing vacancy scripts remain byte-for-byte untouched.

## Runtime files

The installer deploys:

- script: `/home/ubuntu/.openclaw/workspace/scripts/job_radar_sync.py`
- dedicated secret/config: `/home/ubuntu/.openclaw/workspace/config/job-radar.env` (`0600`)
- state: `tracking/agentmail-vacancies/job-radar-sync-state.json` (`0600`)
- log: `tracking/agentmail-vacancies/job-radar-sync.log`
- crontab backups: `tracking/job-radar-bridge-backups/`

The secret file receives only the Job Radar API key and bridge settings. It does not copy PostgreSQL credentials or the complete production env.

## Activation cutoff

First installation writes `JOB_RADAR_SYNC_NOT_BEFORE` using the install time. Reinstall preserves that original cutoff. Normal cron scans only `processed-vacancies-*.json` files at or after the cutoff, preventing accidental historical import during burn-in.

An explicit `--file` is allowed for controlled QA and bypasses the cutoff.

## Mapping policy

The bridge is intentionally conservative:

- `title`, `company`, `location`, `note/description`, salary text and URL are mapped when present;
- `url_final` is preferred only when it is an HTTP(S) URL;
- explicit `country`, `city`, `work_mode`, `seniority`, `external_id`, `captured_at` and ISO `published_at` are passed through when present;
- relative publication strings such as `hace 40 minutos` are kept in metadata and are **not** converted into invented timestamps;
- missing `work_mode`, `seniority` and `external_id` are not guessed;
- the full processed vacancy row is preserved in the ingestion `raw` field for auditability.

Job Radar remains responsible for normalization, deduplication, matching and classification.

## Idempotency

Each processed file row gets a deterministic UUIDv5 key derived from:

- processed filename;
- row index;
- SHA-256 of the canonical row JSON.

The same file/row/payload therefore reuses the exact key for retries. A later processed batch receives a different key even when it represents the same vacancy; Job Radar deduplication then records the new sighting without confusing transport idempotency with vacancy identity.

## Failure isolation

- HTTP 202: persist success in bridge state.
- network/5xx: bounded retries (2s, 5s, 15s), then retry on the next cron run.
- 401/409/422: terminal for that unchanged event; 401 also aborts the run so a bad secret does not spam the API.
- one bridge failure does not modify or roll back the existing Notion/Supabase/Fast.io path.
- a nonzero bridge cron exit is visible in the dedicated bridge log.

## Staged deployment

The bridge is deliberately installed **disabled**. This prevents automatic traffic before QA has proved the mapping and canary path.

After the bridge code is merged and the exact production commit is present at `/srv/job-radar/app`:

```bash
bash ops/install_openclaw_bridge.sh /srv/job-radar/app/.env.production
```

This command:

- deploys the bridge script;
- creates/updates the dedicated mode-0600 secret file;
- records the activation cutoff;
- backs up the existing crontab;
- does **not** add or change the bridge cron on first install;
- does not restart the OpenClaw gateway.

Run dry-run and explicit synthetic canary QA while the automatic bridge remains disabled. Only after that gate passes, enable real burn-in explicitly:

```bash
bash ops/enable_openclaw_bridge.sh
```

The enable script validates the deployed script, dedicated env permissions, localhost API URL and absence of PostgreSQL credentials, backs up crontab again, then creates exactly one managed cron entry. Existing vacancy cron entries are preserved.

Re-running the installer after an already-enabled deployment preserves the managed cron instead of disabling it unexpectedly.

## Rollback

```bash
bash ops/uninstall_openclaw_bridge.sh
```

Rollback removes only the managed cron entry, deployed bridge script and dedicated secret file. State/log/history are preserved for audit and safe reinstall.

## Burn-in

Keep the existing Notion path enabled. During burn-in compare new real discoveries across both systems for:

- opportunity count and missing/extra rows;
- title/company/location fidelity;
- URL and salary fidelity;
- repeat sightings and deduplication;
- HIGH_PRIORITY / REVIEW / DISCARD outcomes;
- explanation quality.

Do not remove Notion until Job Radar has demonstrated reliable real-world operation and the user explicitly approves cutover.
