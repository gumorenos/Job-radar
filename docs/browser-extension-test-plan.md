# Browser extension v1 — acceptance gate

The v1 browser capture feature is accepted only when the following behavior is verified against a deployed Job Radar instance.

## Security

- No persistent `content_scripts` and no mandatory `<all_urls>` host permission.
- Page extraction occurs only after the user invokes the extension on the active tab.
- Remote API origins require HTTPS; HTTP is allowed only for localhost/127.0.0.1 testing.
- API key is sent only in the `Authorization` header to the configured Job Radar origin.
- PostgreSQL remains loopback-only and is never accessed by the extension.

## Capture

Test at least:

1. one page with Schema.org `JobPosting` JSON-LD;
2. one LinkedIn vacancy;
3. one non-LinkedIn page that needs the DOM fallback.

For each page verify that title, company, location, modality, salary and description are either captured correctly or left for explicit human correction. Incorrect guesses must never be silently treated as verified facts.

## Ingestion and matching

- Submitting the reviewed form returns an accepted ingestion.
- Repeated submit of the same reviewed capture is idempotent.
- Worker normalizes the ingestion and does not create an unnecessary duplicate Job/Posting.
- Result polling moves from pending to the current matching result.
- A pending reanalysis does not expose an older classification as if it were the new result.
- `HIGH_PRIORITY`, `REVIEW` and `DISCARD` render correctly when produced by the existing matching rules.

## Radar handoff

- **Abrir en Radar** opens `/app/#/radar/<job-id>`.
- Radar loads that job's detail even when it is not in the currently visible classification list.
- Existing Radar search, paging, feedback, Applications, CVs, duplicates and notifications remain functional.

## First deployment topology

Use the existing Oracle deployment with API/dashboard on `127.0.0.1:8010`. Reach it from the test workstation through an SSH local-forward. Do not add a public hostname merely to perform this first acceptance test.
