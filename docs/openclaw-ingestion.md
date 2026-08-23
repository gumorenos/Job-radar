# OpenClaw -> Job Radar ingestion

OpenClaw discovers vacancies. Job Radar owns persistence, normalization, deduplication, matching, classification and notification planning.

OpenClaw must never connect directly to PostgreSQL.

## Endpoint

Use the loopback API port configured in Job Radar production. On the current Oracle VPS the selected port is `8010` because `8000` is already used by another application.

```http
POST http://127.0.0.1:8010/api/v1/ingestions/jobs
Authorization: Bearer <JOB_RADAR_API_KEY>
Idempotency-Key: <stable-key-for-this-http-discovery-event>
Content-Type: application/json
```

Do not route host-local ingestion through Cloudflare. If `JOB_RADAR_PORT` changes later, update the OpenClaw runtime endpoint accordingly rather than hard-coding a public hostname.

## Idempotency

The idempotency key represents one discovery event / HTTP operation, not the logical vacancy.

- generate a unique key when OpenClaw creates the ingestion event;
- reuse that exact key and payload for retries of the same operation;
- use a new key when the source is observed again later, even if it is the same vacancy;
- Job Radar deduplication decides whether separate discoveries represent one posting/job.

A UUID is appropriate. Do not derive the key solely from `external_id`, because a later changed payload with the same key correctly returns `409`.

## Payload

Example:

```json
{
  "ingestion_source": "openclaw",
  "posting_source": "linkedin",
  "external_id": "linkedin-12345",
  "captured_at": "2026-08-21T15:00:00Z",
  "job": {
    "title": "Senior People Analytics Analyst",
    "company": "Example Corp",
    "location": "Lima, Peru",
    "country": "Peru",
    "city": "Lima",
    "work_mode": "hybrid",
    "seniority": "Senior",
    "description": "...",
    "salary_text": "S/ 9,000",
    "url": "https://example.com/jobs/12345",
    "published_at": "2026-08-21"
  },
  "metadata": {
    "openclaw_agent": "job-search"
  }
}
```

Unknown extra fields are preserved in the raw ingestion payload, but stable semantic fields should use the documented schema when available.

## Response handling

- `202 accepted`: persisted and queued.
- `202 already_accepted`: retry was already persisted; treat as success.
- `401`: authentication/configuration error; do not retry indefinitely.
- `409`: same idempotency key was reused with a different payload; create/fix the event identity rather than hiding the conflict.
- `422`: invalid payload; log sanitized validation details and do not retry unchanged.
- network error / `5xx`: retry the same key + same payload with bounded exponential backoff.

Recommended initial retry policy: 3 retries after approximately 2s, 5s and 15s. Keep request timeouts bounded.

## Secrets and logs

- provision the API key as an OpenClaw runtime secret/environment value, not in prompts or source code;
- never log the Bearer token;
- do not log full CVs or unnecessary full raw payloads;
- log source, external id, idempotency key, Job Radar ingestion id/status and sanitized errors.

## Burn-in

For the initial production burn-in:

```text
OpenClaw discovery
   |-> existing Notion write
   `-> Job Radar ingestion API
```

Keep both paths temporarily. Compare a real sample for missing/extra opportunities, data fidelity, repeat discovery behavior, classification/explanations and notification intents.

Do not remove the Notion path until Job Radar has demonstrated reliable real-world ingestion and the user explicitly approves cutover.

## Canary validation

The first canary should submit one clearly identifiable non-sensitive test vacancy, wait for worker completion, and verify:

1. one `IngestionEvent` exists;
2. normalization creates/reuses the expected Job/JobPosting;
3. a `PostingSighting` is recorded;
4. `ANALYZE_MATCH` completes;
5. Radar shows the expected classification/explanation;
6. retrying the exact request with the same key returns `already_accepted` without duplication.
