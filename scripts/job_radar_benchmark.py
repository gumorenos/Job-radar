#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from job_radar import APIFY_SOURCE_DEFS, DB_PATH, PROFILE_PATH, clean_text, enabled_sources
except ModuleNotFoundError:
    from scripts.job_radar import APIFY_SOURCE_DEFS, DB_PATH, PROFILE_PATH, clean_text, enabled_sources


ROOT = Path(__file__).resolve().parents[1]
ENTREGABLES = ROOT / "entregables"
APIFY_API = "https://api.apify.com/v2"
LOCAL_SOURCE_KEYS = {"agentmail", "linkedin", "indeed", "getonboard"}


def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def actor_public_info(actor_id: str) -> dict:
    response = requests.get(f"{APIFY_API}/acts/{actor_id.replace('/', '~')}", timeout=30)
    response.raise_for_status()
    data = response.json().get("data") or {}
    pricing = data.get("pricingInfos") or []
    current = pricing[-1] if pricing else {}
    event_price = None
    events = ((current.get("pricingPerEvent") or {}).get("actorChargeEvents") or {})
    result_event = events.get("apify-default-dataset-item") or {}
    if "eventPriceUsd" in result_event:
        event_price = result_event["eventPriceUsd"]
    else:
        tiers = result_event.get("eventTieredPricingUsd") or current.get("tieredPricing") or {}
        free = tiers.get("FREE") or {}
        event_price = free.get("tieredEventPriceUsd") or free.get("tieredPricePerUnitUsd")
    price_per_result = event_price or current.get("pricePerUnitUsd")
    return {
        "actor": actor_id,
        "title": data.get("title"),
        "description": data.get("description"),
        "pricing_model": current.get("pricingModel"),
        "price_per_result_usd": price_per_result,
        "price_per_1000_usd": float(price_per_result) * 1000 if price_per_result is not None else None,
        "runs": (data.get("stats") or {}).get("totalRuns"),
        "users": (data.get("stats") or {}).get("totalUsers"),
        "rating": (data.get("stats") or {}).get("actorReviewRating"),
        "reviews": (data.get("stats") or {}).get("actorReviewCount"),
    }


def local_source_snapshot() -> list[dict]:
    if not DB_PATH.exists():
        return []
    with connect_db() as conn:
        rows = conn.execute(
            """
            select source,
                   count(*) total,
                   sum(case when verdict='priorizar' and status not in ('duplicate','discarded','false_positive') then 1 else 0 end) top,
                   sum(case when verdict='revisar' and status not in ('duplicate','discarded','false_positive') then 1 else 0 end) review,
                   sum(case when status='duplicate' then 1 else 0 end) duplicates,
                   avg(length(coalesce(description,''))) avg_description_len,
                   sum(case when coalesce(url,'') != '' then 1 else 0 end) with_url
            from vacancies
            group by source
            order by total desc
            """
        ).fetchall()
    return [dict(row) for row in rows]


def benchmark_plan(profile: dict, limit: int) -> dict:
    sources = sorted(enabled_sources(profile))
    search_terms = profile.get("search_terms") or []
    locations = profile.get("locations") or []
    max_items = min(int(profile.get("apify_hard_max_items") or limit), limit)
    apify_sources = sorted(set(sources) & set(APIFY_SOURCE_DEFS))
    actors = []
    for source in apify_sources or sorted(APIFY_SOURCE_DEFS):
        info = actor_public_info(APIFY_SOURCE_DEFS[source]["actor"])
        info["source_key"] = source
        info["estimated_cost_for_limit_usd"] = (
            round(float(info["price_per_result_usd"]) * max_items, 4)
            if info.get("price_per_result_usd") is not None
            else None
        )
        actors.append(info)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run",
        "profile_name": profile.get("profile_name"),
        "enabled_sources": sources,
        "search_terms": search_terms,
        "locations": locations,
        "benchmark_limit": max_items,
        "apify_mode": profile.get("apify_mode", "disabled"),
        "apify_actors": actors,
        "local_snapshot": local_source_snapshot(),
        "manual_next_step": "Run paid Apify actors only after explicit cap approval and APIFY_API_TOKEN configuration.",
    }


def write_report(payload: dict) -> dict:
    ENTREGABLES.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    json_path = ENTREGABLES / f"JOB_RADAR_SOURCE_BENCHMARK_PLAN_{stamp}.json"
    md_path = ENTREGABLES / f"JOB_RADAR_SOURCE_BENCHMARK_PLAN_{stamp}.md"
    latest_json = ENTREGABLES / "JOB_RADAR_SOURCE_BENCHMARK_PLAN_LATEST.json"
    latest_md = ENTREGABLES / "JOB_RADAR_SOURCE_BENCHMARK_PLAN_LATEST.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_json.write_bytes(json_path.read_bytes())

    lines = [
        "# Job Radar - Source Benchmark Plan",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Mode: `{payload['mode']}`",
        f"Profile: `{payload.get('profile_name')}`",
        f"Limit: `{payload.get('benchmark_limit')}`",
        "",
        "## Apify Actors",
    ]
    for actor in payload["apify_actors"]:
        lines.extend(
            [
                f"- `{actor['source_key']}` / `{actor['actor']}`",
                f"  - title: {actor.get('title')}",
                f"  - price: ${actor.get('price_per_1000_usd')} / 1K results",
                f"  - estimated cost for limit: ${actor.get('estimated_cost_for_limit_usd')}",
                f"  - runs/users/rating: {actor.get('runs')} / {actor.get('users')} / {actor.get('rating')}",
            ]
        )
    lines.extend(["", "## Local Snapshot"])
    for row in payload["local_snapshot"]:
        lines.append(
            f"- `{row['source']}`: total {row['total']}, top {row['top']}, review {row['review']}, duplicates {row['duplicates']}, with_url {row['with_url']}"
        )
    lines.extend(
        [
            "",
            "## Benchmark Criteria",
            "- real cost",
            "- usable unique jobs",
            "- duplicate rate",
            "- full description availability",
            "- direct URL availability",
            "- Top/Revisar quality after local scoring",
            "",
            f"Next step: {payload['manual_next_step']}",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    latest_md.write_bytes(md_path.read_bytes())
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a safe Job Radar source benchmark plan without paid Apify execution.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--run-apify", action="store_true", help="Reserved; requires explicit cap and APIFY_API_TOKEN.")
    parser.add_argument("--max-spend-usd", type=float, default=0.0)
    args = parser.parse_args()
    if args.run_apify:
        if args.max_spend_usd <= 0:
            raise SystemExit("--run-apify requiere --max-spend-usd > 0")
        if not os.environ.get("APIFY_API_TOKEN"):
            raise SystemExit("--run-apify requiere APIFY_API_TOKEN")
        raise SystemExit("Paid Apify execution is intentionally not implemented in this safe planner yet.")
    payload = benchmark_plan(load_profile(), args.limit)
    outputs = write_report(payload)
    print(json.dumps({"ok": True, "outputs": outputs, "summary": payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
