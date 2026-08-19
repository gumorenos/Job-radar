# Notification planner v1

This stage records notification intent without contacting external services.

Policy:

- `HIGH_PRIORITY`: Dashboard `IMMEDIATE` + Telegram `IMMEDIATE`.
- `REVIEW`: Dashboard `IMMEDIATE` + Telegram `DAILY_REVIEW` at the active candidate profile's configured local review time.
- `DISCARD`: no notification.

The planner runs in the same transaction as the immutable `MatchAnalysis`, is idempotent for that analysis, and stores rows in `notifications` with `PENDING` status.

No `SEND_NOTIFICATION` worker task is created in this stage. Telegram credentials, delivery, retries, grouping of the daily digest, and final sent/failed transitions belong to the delivery stage. This prevents missing external configuration from breaking ingestion or matching.
