#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

DEFAULT_API_URL = "http://127.0.0.1:8010/api/v1/ingestions/jobs"
DEFAULT_TRACKING_DIR = Path("/home/ubuntu/.openclaw/workspace/tracking/agentmail-vacancies")
DEFAULT_STATE_PATH = DEFAULT_TRACKING_DIR / "job-radar-sync-state.json"
TRANSIENT_RETRY_DELAYS = (2, 5, 15)
TERMINAL_HTTP_STATUSES = {401, 409, 422}


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_document(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def extract_vacancies(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [item for item in document if isinstance(item, dict)]
    if isinstance(document, dict):
        for key in ("vacancies", "items", "jobs", "results"):
            value = document.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("Processed vacancy JSON must be a list or contain vacancies/items/jobs/results.")


def _text(value: Any, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if limit is not None:
        return text[:limit]
    return text


def _http_url(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return None


def normalize_posting_source(value: Any) -> str | None:
    text = _text(value, limit=80)
    if text is None:
        return None
    lowered = text.casefold()
    if "linkedin" in lowered:
        return "linkedin"
    if "jobsora" in lowered:
        return "jobsora"
    if "agentmail" in lowered:
        return "agentmail"
    return text


def _salary_text(record: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in ("salary_detail", "salary_condition"):
        value = _text(record.get(key))
        if value and value not in parts:
            parts.append(value)
    if not parts:
        return None
    return " | ".join(parts)[:500]


def _iso_datetime(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_ingestion_payload(record: dict[str, Any], source_file: Path, index: int) -> dict[str, Any]:
    final_url = _http_url(record.get("url_final"))
    source_url = _http_url(record.get("url"))
    published_at = _iso_datetime(record.get("published_at"))

    job: dict[str, Any] = {
        "title": _text(record.get("title"), limit=300),
        "company": _text(record.get("company"), limit=255),
        "location": _text(record.get("location"), limit=255),
        "description": _text(record.get("description")) or _text(record.get("note")),
        "salary_text": _salary_text(record),
        "url": final_url or source_url,
    }

    for key, limit in (("country", 100), ("city", 120), ("work_mode", 80), ("seniority", 120)):
        value = _text(record.get(key), limit=limit)
        if value is not None:
            job[key] = value
    if published_at is not None:
        job["published_at"] = published_at

    metadata_keys = (
        "published",
        "detail_status",
        "score",
        "verdict",
        "salary_condition",
        "salary_detail",
        "salary_max_pen",
        "url_status_code",
        "url_title",
        "url_validity",
    )
    metadata: dict[str, Any] = {
        "openclaw_processed_file": source_file.name,
        "openclaw_event_index": index,
    }
    for key in metadata_keys:
        value = record.get(key)
        if value not in (None, ""):
            metadata[key] = value

    external_id = _text(record.get("external_id"), limit=300)
    captured_at = _iso_datetime(record.get("captured_at"))
    if captured_at is None:
        captured_at = datetime.fromtimestamp(source_file.stat().st_mtime, UTC).isoformat().replace(
            "+00:00", "Z"
        )

    payload: dict[str, Any] = {
        "ingestion_source": "openclaw",
        "posting_source": normalize_posting_source(record.get("source")),
        "captured_at": captured_at,
        "job": job,
        "metadata": metadata,
        "raw": record,
    }
    if external_id is not None:
        payload["external_id"] = external_id
    return payload


def event_idempotency_key(source_file: Path, index: int, record: dict[str, Any]) -> str:
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    identity = f"job-radar:openclaw:{source_file.name}:{index}:{digest}"
    return str(uuid5(NAMESPACE_URL, identity))


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "events": {}}
    document = load_document(path)
    if not isinstance(document, dict) or not isinstance(document.get("events"), dict):
        raise ValueError(f"Invalid state file: {path}")
    return document


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
    os.chmod(path, 0o600)


def post_ingestion(api_url: str, api_key: str, idempotency_key: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            parsed = json.loads(response_body) if response_body else None
            return response.status, parsed if isinstance(parsed, dict) else None
    except urllib.error.HTTPError as exc:
        return exc.code, None


def send_with_retries(api_url: str, api_key: str, key: str, payload: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None, str | None]:
    attempts = 1 + len(TRANSIENT_RETRY_DELAYS)
    for attempt in range(attempts):
        try:
            status, response = post_ingestion(api_url, api_key, key, payload)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == attempts - 1:
                return None, None, type(exc).__name__
            time.sleep(TRANSIENT_RETRY_DELAYS[attempt])
            continue

        if status == 202:
            return status, response, None
        if status in TERMINAL_HTTP_STATUSES:
            return status, response, f"terminal_http_{status}"
        if 500 <= status <= 599:
            if attempt == attempts - 1:
                return status, response, f"http_{status}"
            time.sleep(TRANSIENT_RETRY_DELAYS[attempt])
            continue
        return status, response, f"http_{status}"

    return None, None, "unexpected_retry_exit"


def _parse_not_before(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def candidate_files(tracking_dir: Path, explicit_file: Path | None, not_before: datetime | None) -> list[Path]:
    if explicit_file is not None:
        return [explicit_file]
    files = sorted(tracking_dir.glob("processed-vacancies-*.json"), key=lambda path: (path.stat().st_mtime, path.name))
    if not_before is None:
        return files
    return [path for path in files if datetime.fromtimestamp(path.stat().st_mtime, UTC) >= not_before]


def run_sync(
    *,
    api_url: str,
    api_key: str,
    tracking_dir: Path,
    state_path: Path,
    not_before: datetime | None,
    explicit_file: Path | None,
    dry_run: bool,
    max_files: int,
) -> int:
    state = load_state(state_path)
    events = state["events"]
    files = candidate_files(tracking_dir, explicit_file, not_before)[-max_files:]

    accepted = 0
    skipped = 0
    failed = 0
    terminal = 0

    for source_file in files:
        vacancies = extract_vacancies(load_document(source_file))
        for index, record in enumerate(vacancies):
            key = event_idempotency_key(source_file, index, record)
            previous = events.get(key)
            if isinstance(previous, dict) and previous.get("status") in {"accepted", "terminal_error"}:
                skipped += 1
                continue

            payload = build_ingestion_payload(record, source_file, index)
            title = _text(payload["job"].get("title"), limit=80) or "(sin título)"
            if dry_run:
                print(f"DRY_RUN file={source_file.name} index={index} title={title!r} key={key}")
                continue

            status, response, error = send_with_retries(api_url, api_key, key, payload)
            now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            if status == 202 and response is not None:
                events[key] = {
                    "status": "accepted",
                    "http_status": status,
                    "ingestion_id": response.get("ingestion_id"),
                    "job_radar_status": response.get("status"),
                    "source_file": source_file.name,
                    "index": index,
                    "updated_at": now,
                }
                save_state(state_path, state)
                accepted += 1
                print(
                    "SYNC_OK "
                    f"file={source_file.name} index={index} title={title!r} "
                    f"status={response.get('status')} ingestion_id={response.get('ingestion_id')}"
                )
                continue

            if status in TERMINAL_HTTP_STATUSES:
                events[key] = {
                    "status": "terminal_error",
                    "http_status": status,
                    "error": error,
                    "source_file": source_file.name,
                    "index": index,
                    "updated_at": now,
                }
                save_state(state_path, state)
                terminal += 1
                print(
                    f"SYNC_TERMINAL file={source_file.name} index={index} title={title!r} http={status}",
                    file=sys.stderr,
                )
                if status == 401:
                    return 2
                continue

            failed += 1
            print(
                f"SYNC_RETRY_LATER file={source_file.name} index={index} title={title!r} http={status} error={error}",
                file=sys.stderr,
            )

    print(f"SYNC_SUMMARY accepted={accepted} skipped={skipped} failed={failed} terminal={terminal} files={len(files)}")
    return 1 if failed or terminal else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync processed OpenClaw vacancies into Job Radar.")
    parser.add_argument("--env", type=Path, required=True, help="Dedicated Job Radar bridge env file.")
    parser.add_argument("--file", type=Path, help="Process exactly one JSON file, bypassing cutoff scan.")
    parser.add_argument("--dry-run", action="store_true", help="Map events without sending HTTP requests.")
    parser.add_argument("--max-files", type=int, default=20, help="Maximum newest candidate files per run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_files < 1:
        raise SystemExit("--max-files must be >= 1")

    env = parse_env_file(args.env)
    api_url = env.get("JOB_RADAR_API_URL", DEFAULT_API_URL).strip()
    api_key = env.get("JOB_RADAR_API_KEY", "").strip()
    tracking_dir = Path(env.get("JOB_RADAR_TRACKING_DIR", str(DEFAULT_TRACKING_DIR)))
    state_path = Path(env.get("JOB_RADAR_SYNC_STATE_PATH", str(DEFAULT_STATE_PATH)))
    not_before = _parse_not_before(env.get("JOB_RADAR_SYNC_NOT_BEFORE"))

    if not api_key and not args.dry_run:
        raise SystemExit("JOB_RADAR_API_KEY is required unless --dry-run is used.")
    if not api_url.startswith("http://127.0.0.1:"):
        raise SystemExit("JOB_RADAR_API_URL must use host-local 127.0.0.1.")
    if args.file is not None and not args.file.is_file():
        raise SystemExit(f"Input file does not exist: {args.file}")

    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("SYNC_SKIPPED another bridge run is active")
            return 0
        return run_sync(
            api_url=api_url,
            api_key=api_key,
            tracking_dir=tracking_dir,
            state_path=state_path,
            not_before=not_before,
            explicit_file=args.file,
            dry_run=args.dry_run,
            max_files=args.max_files,
        )


if __name__ == "__main__":
    raise SystemExit(main())
