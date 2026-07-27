from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_radar_app.models import IngestionRun, Vacancy
from job_radar_app.schemas import IngestionBatchIn, JobSummary
from job_radar_app.settings import get_settings
from scripts.job_radar import (
    SOURCE_RANK,
    VERDICT_RANK,
    canonical_company,
    canonical_title,
    clean_text,
    clean_url,
    detect_salary_text,
    duplicate_key_for,
    external_key as legacy_external_key,
    numeric_salary,
    score_item,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_profile_data() -> dict:
    settings = get_settings()
    profile_path = settings.profile_path
    if not profile_path.exists():
        example = profile_path.with_name("job-radar-profile.example.json")
        if example.exists():
            profile_path = example
        else:
            raise FileNotFoundError(f"Job Radar profile not found: {settings.profile_path}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    candidate_path: Path = settings.candidate_profile_path
    if candidate_path.exists():
        profile["candidate_profile"] = json.loads(candidate_path.read_text(encoding="utf-8"))
    else:
        profile["candidate_profile"] = {}
    return profile


def _posting_external_key(item: dict, external_id: str | None) -> str:
    normalized_url = clean_url(item.get("url") or "")
    if normalized_url:
        return normalized_url.lower()
    if external_id:
        return f"{item.get('source', 'unknown')}:{external_id}".lower()
    return legacy_external_key(item)


def _row_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _normalize_posting(batch: IngestionBatchIn, posting: object) -> tuple[dict, str]:
    raw = posting.model_dump(mode="json")
    source = clean_text(raw.get("source") or batch.source, 80).lower()
    remote_value = raw.get("remote")
    if isinstance(remote_value, bool):
        remote_value = str(remote_value).lower()
    remote_value = clean_text(remote_value or raw.get("modality"), 80)
    published = clean_text(raw.get("published_at") or raw.get("published"), 120)

    item = {
        "source": source,
        "source_detail": f"api:{batch.source_run_id}",
        "title": clean_text(raw.get("title"), 300),
        "company": clean_text(raw.get("company"), 200),
        "location": clean_text(raw.get("location"), 200),
        "remote": remote_value,
        "published": published,
        "salary_text": clean_text(raw.get("salary_text"), 500),
        "salary_min": raw.get("salary_min"),
        "salary_max": raw.get("salary_max"),
        "salary_currency": clean_text(raw.get("salary_currency"), 20),
        "url": clean_url(raw.get("url") or ""),
        "description": clean_text(raw.get("description"), 12000),
        "raw": {
            "ingestion_source": batch.source,
            "source_run_id": batch.source_run_id,
            **raw,
        },
    }
    item["clean_url"] = clean_url(item["url"])
    item["salary_text"] = item["salary_text"] or detect_salary_text(item)
    item["salary_min"], item["salary_max"], item["salary_currency"] = numeric_salary(item)
    key = _posting_external_key(item, clean_text(raw.get("external_id"), 300) or None)
    return item, key


def _apply_item(vacancy: Vacancy, item: dict, run_id: str, at: str) -> None:
    vacancy.source = item["source"]
    vacancy.source_detail = item.get("source_detail", "")
    vacancy.title = item["title"]
    vacancy.company = item.get("company", "")
    vacancy.location = item.get("location", "")
    vacancy.remote = item.get("remote", "")
    vacancy.published = item.get("published", "")
    vacancy.salary_text = item.get("salary_text", "")
    vacancy.salary_min = item.get("salary_min")
    vacancy.salary_max = item.get("salary_max")
    vacancy.salary_currency = item.get("salary_currency", "")
    vacancy.url = item.get("url", "")
    vacancy.clean_url = item.get("clean_url", "")
    vacancy.description = item.get("description", "")
    vacancy.score = item["score"]
    vacancy.verdict = item["verdict"]
    vacancy.last_seen_at = at
    vacancy.run_id = run_id
    vacancy.raw_json = json.dumps(item.get("raw") or item, ensure_ascii=False, default=str)
    vacancy.duplicate_key = item["duplicate_key"]
    vacancy.duplicate_of = None
    if vacancy.status == "duplicate":
        vacancy.status = "new"


def _duplicate_sort_key(row: Vacancy) -> tuple:
    url = row.clean_url or row.url or ""
    direct_url = bool(url and "jobsora.com" not in url)
    return (
        VERDICT_RANK.get(row.verdict, 0),
        row.score or 0,
        1 if row.status in {"review", "apply", "applied"} else 0,
        1 if direct_url else 0,
        SOURCE_RANK.get((row.source or "").lower(), 0),
        row.last_seen_at or "",
    )


def dedupe_vacancies(session: Session) -> int:
    rows = list(
        session.scalars(
            select(Vacancy).where(Vacancy.status.notin_({"discarded", "false_positive"}))
        )
    )
    buckets: dict[str, list[Vacancy]] = {}
    for row in rows:
        title = canonical_title(row.title)
        if not title:
            continue
        company = canonical_company(row.company)
        bucket = company or title.split(" ", 1)[0]
        buckets.setdefault(bucket, []).append(row)

    changed = 0
    keep_ids: set[str] = set()
    for bucket_rows in buckets.values():
        groups: list[list[Vacancy]] = []
        for row in bucket_rows:
            title = canonical_title(row.title)
            company = canonical_company(row.company)
            placed = False
            for group in groups:
                head = group[0]
                head_company = canonical_company(head.company)
                if company and head_company and company != head_company:
                    continue
                ratio = SequenceMatcher(None, title, canonical_title(head.title)).ratio()
                if title == canonical_title(head.title) or ratio >= 0.88:
                    group.append(row)
                    placed = True
                    break
            if not placed:
                groups.append([row])

        for group in (group for group in groups if len(group) > 1):
            keeper = sorted(group, key=_duplicate_sort_key, reverse=True)[0]
            keep_ids.add(keeper.id)
            for row in group:
                if row.id == keeper.id or row.status in {"apply", "applied"}:
                    continue
                if row.status != "duplicate" or row.duplicate_of != keeper.id:
                    changed += 1
                row.status = "duplicate"
                row.duplicate_of = keeper.id

    for row in rows:
        if row.id in keep_ids:
            row.duplicate_of = None
            if row.status == "duplicate":
                row.status = "new"
    session.flush()
    return changed


def _job_summary(vacancy: Vacancy) -> dict:
    return JobSummary(
        id=vacancy.id,
        source=vacancy.source,
        title=vacancy.title,
        company=vacancy.company,
        location=vacancy.location,
        remote=vacancy.remote,
        published=vacancy.published,
        salary_text=vacancy.salary_text,
        url=vacancy.url,
        score=vacancy.score,
        verdict=vacancy.verdict,
        status=vacancy.status,
        first_seen_at=vacancy.first_seen_at,
        last_seen_at=vacancy.last_seen_at,
    ).model_dump()


def ingest_batch(session: Session, batch: IngestionBatchIn) -> dict:
    existing_run = session.scalar(
        select(IngestionRun).where(
            IngestionRun.source == batch.source,
            IngestionRun.source_run_id == batch.source_run_id,
        )
    )
    if existing_run and existing_run.status == "done" and existing_run.result_json:
        result = json.loads(existing_run.result_json)
        result["idempotent_replay"] = True
        return result

    run = existing_run or IngestionRun(
        id=str(uuid4()),
        source=batch.source,
        source_run_id=batch.source_run_id,
        started_at=now_iso(),
        status="pending",
        received=len(batch.postings),
        request_json=batch.model_dump_json(),
    )
    if existing_run:
        run.status = "pending"
        run.started_at = now_iso()
        run.finished_at = None
        run.error = None
        run.request_json = batch.model_dump_json()
        run.received = len(batch.postings)
    else:
        session.add(run)
    session.commit()

    profile = load_profile_data()
    at = now_iso()
    created_ids: list[str] = []
    created = 0
    updated = 0

    try:
        for posting in batch.postings:
            item, key = _normalize_posting(batch, posting)
            if not item["title"]:
                continue
            item["score"], item["verdict"] = score_item(item, profile)
            item["duplicate_key"] = duplicate_key_for(item)

            vacancy = session.scalar(select(Vacancy).where(Vacancy.external_key == key))
            if vacancy is None:
                vacancy = Vacancy(
                    id=_row_id(key),
                    external_key=key,
                    source=item["source"],
                    title=item["title"],
                    score=item["score"],
                    verdict=item["verdict"],
                    status="new",
                    first_seen_at=at,
                    last_seen_at=at,
                    run_id=run.id,
                    raw_json="{}",
                )
                session.add(vacancy)
                created_ids.append(vacancy.id)
                created += 1
            else:
                updated += 1
            _apply_item(vacancy, item, run.id, at)

        session.flush()
        duplicates = dedupe_vacancies(session)
        session.commit()

        relevant_rows = []
        if created_ids:
            relevant_rows = list(
                session.scalars(
                    select(Vacancy).where(
                        Vacancy.id.in_(created_ids),
                        Vacancy.verdict.in_({"priorizar", "revisar"}),
                        Vacancy.status.notin_({"duplicate", "discarded", "false_positive"}),
                    )
                )
            )
        relevant = [_job_summary(row) for row in relevant_rows]
        result = {
            "ingestion_run_id": run.id,
            "source": batch.source,
            "source_run_id": batch.source_run_id,
            "received": len(batch.postings),
            "created": created,
            "updated": updated,
            "duplicates": duplicates,
            "new_relevant": relevant,
            "idempotent_replay": False,
        }

        run = session.get(IngestionRun, run.id)
        assert run is not None
        run.status = "done"
        run.finished_at = now_iso()
        run.created_count = created
        run.updated_count = updated
        run.duplicates_count = duplicates
        run.new_relevant_count = len(relevant)
        run.result_json = json.dumps(result, ensure_ascii=False)
        session.commit()
        return result
    except Exception as exc:
        session.rollback()
        failed_run = session.get(IngestionRun, run.id)
        if failed_run is not None:
            failed_run.status = "error"
            failed_run.finished_at = now_iso()
            failed_run.error = f"{type(exc).__name__}: {exc}"
            session.commit()
        raise
