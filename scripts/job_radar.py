#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

try:
    from job_radar_candidate import load_candidate_profile
except ModuleNotFoundError:
    from scripts.job_radar_candidate import load_candidate_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "config" / "job-radar-profile.json"
TRACKING = ROOT / "tracking" / "job-radar"
RUNS = TRACKING / "runs"
DB_PATH = TRACKING / "job_radar.sqlite"
AGENTMAIL_TRACKING = ROOT / "tracking" / "agentmail-vacancies"
ENTREGABLES = ROOT / "entregables"

TRACKING_PARAMS_PREFIX = ("utm_", "trk")
TRACKING_PARAMS = {
    "source",
    "ref",
    "refid",
    "trackingid",
    "lipi",
    "gb_medium",
    "gb_name",
}

COMPANY_STOPWORDS = {
    "sac",
    "s.a.c",
    "sa",
    "s.a",
    "inc",
    "ltd",
    "llc",
    "corp",
    "corporation",
    "company",
    "co",
    "group",
    "peru",
    "perú",
    "finland",
}

TITLE_STOPWORDS = {
    "lima",
    "peru",
    "perú",
    "published",
    "on",
}

VERDICT_RANK = {"priorizar": 3, "revisar": 2, "backup": 1}
SOURCE_RANK = {
    "indeed": 5,
    "linkedin": 4,
    "agentmail": 3,
    "getonboard": 2,
    "apify_valig": 2,
    "apify_cheap_scraper": 2,
    "apify_curious_coder": 2,
}

LOCAL_SOURCE_KEYS = {"agentmail", "linkedin", "indeed", "getonboard"}
APIFY_SOURCE_DEFS = {
    "apify_valig": {
        "actor": "valig/linkedin-jobs-scraper",
        "label": "Apify Valig LinkedIn Jobs",
        "price_per_1000_usd": 0.40,
    },
    "apify_cheap_scraper": {
        "actor": "cheap_scraper/linkedin-job-scraper",
        "label": "Apify Cheap Scraper LinkedIn Jobs",
        "price_per_1000_usd": 0.35,
    },
    "apify_curious_coder": {
        "actor": "curious_coder/linkedin-jobs-scraper",
        "label": "Apify Curious Coder LinkedIn Jobs",
        "price_per_1000_usd": 1.00,
    },
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def clean_text(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())[:limit]


def clean_url(url: str) -> str:
    if not url:
        return ""
    if not isinstance(url, str):
        return ""
    parsed = urlsplit(url.strip())
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        low = key.lower()
        if low in TRACKING_PARAMS or any(low.startswith(prefix) for prefix in TRACKING_PARAMS_PREFIX):
            continue
        query.append((key, value))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def canonical_tokens(value: Any, stopwords: set[str] | None = None) -> list[str]:
    text = clean_text(value, 500).lower()
    text = re.sub(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", " ", text)
    text = re.sub(r"[^a-z0-9áéíóúñü]+", " ", text)
    words = [word for word in text.split() if len(word) > 1]
    if stopwords:
        words = [word for word in words if word not in stopwords]
    return words


def canonical_text(value: Any, stopwords: set[str] | None = None) -> str:
    return " ".join(canonical_tokens(value, stopwords))


def canonical_company(value: Any) -> str:
    aliases = {
        "a p moller maersk": "maersk",
        "maersk": "maersk",
        "michael page": "michael page",
        "michael page peru": "michael page",
        "statkraft": "statkraft",
        "statkraft group": "statkraft",
    }
    text = canonical_text(value, COMPANY_STOPWORDS)
    return aliases.get(text, text)


def canonical_title(value: Any) -> str:
    text = canonical_text(value, TITLE_STOPWORDS)
    text = re.sub(r"\b\d{4}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def duplicate_key_for(item: dict) -> str:
    title = canonical_title(item.get("title"))
    company = canonical_company(item.get("company"))
    if not title:
        return ""
    return f"{company}|{title}" if company else title


def load_profile() -> dict:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile["candidate_profile"] = load_candidate_profile()
    return profile


def enabled_sources(profile: dict) -> set[str]:
    sources = profile.get("enabled_sources") or profile.get("enabled_portals")
    if not sources:
        sources = ["agentmail", "linkedin", "indeed", "getonboard"]
    return {clean_text(source, 80).lower() for source in sources if clean_text(source, 80)}


def enabled_portals(profile: dict) -> set[str]:
    return enabled_sources(profile)


def init_db(path: Path = DB_PATH) -> sqlite3.Connection:
    TRACKING.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        create table if not exists vacancies (
          id text primary key,
          external_key text not null unique,
          source text not null,
          source_detail text,
          title text not null,
          company text,
          location text,
          remote text,
          published text,
          salary_text text,
          salary_min real,
          salary_max real,
          salary_currency text,
          url text,
          clean_url text,
          description text,
          score integer not null default 0,
          verdict text not null,
          status text not null default 'new',
          first_seen_at text not null,
          last_seen_at text not null,
          run_id text not null,
          raw_json text not null
        )
        """
    )
    conn.execute("create index if not exists vacancies_score_idx on vacancies(status, score desc, last_seen_at desc)")
    conn.execute("create index if not exists vacancies_source_idx on vacancies(source)")
    existing_columns = {
        row["name"]
        for row in conn.execute("pragma table_info(vacancies)").fetchall()
    }
    if "duplicate_key" not in existing_columns:
        conn.execute("alter table vacancies add column duplicate_key text")
    if "duplicate_of" not in existing_columns:
        conn.execute("alter table vacancies add column duplicate_of text")
    conn.execute("create index if not exists vacancies_duplicate_key_idx on vacancies(duplicate_key)")
    conn.execute(
        """
        create table if not exists runs (
          id text primary key,
          started_at text not null,
          finished_at text,
          profile_name text,
          imported integer default 0,
          inserted integer default 0,
          updated integer default 0,
          blockers_json text not null default '[]'
        )
        """
    )
    run_columns = {
        row["name"]
        for row in conn.execute("pragma table_info(runs)").fetchall()
    }
    if "duplicate_groups" not in run_columns:
        conn.execute("alter table runs add column duplicate_groups integer default 0")
    if "duplicates_hidden" not in run_columns:
        conn.execute("alter table runs add column duplicates_hidden integer default 0")
    conn.commit()
    return conn


def external_key(item: dict) -> str:
    url = clean_url(item.get("url") or "")
    if url:
        return url.lower()
    raw = "|".join(
        clean_text(item.get(k), 200).lower()
        for k in ("source", "title", "company", "location")
    )
    return raw


def row_id(item: dict) -> str:
    return hashlib.sha1(external_key(item).encode("utf-8")).hexdigest()


def detect_salary_text(item: dict) -> str:
    parts = [
        item.get("salary_text"),
        item.get("salary_detail"),
        item.get("title"),
        item.get("description"),
        item.get("note"),
    ]
    blob = " ".join(clean_text(part, 1000) for part in parts if part)
    matches = re.findall(r"(?:s/|s\.|pen|soles|\$|usd)\s*[0-9][0-9.,]*(?:\s*(?:-|a|hasta|to)\s*(?:s/|s\.|pen|soles|\$|usd)?\s*[0-9][0-9.,]*)?", blob, re.I)
    return "; ".join(dict.fromkeys(m.strip() for m in matches))[:500]


def numeric_salary(item: dict) -> tuple[float | None, float | None, str]:
    min_amount = item.get("salary_min")
    max_amount = item.get("salary_max")
    currency = clean_text(item.get("salary_currency"), 20)
    for key in ("salary_max_pen",):
        if item.get(key) and not max_amount:
            max_amount = item.get(key)
            currency = "PEN"
    try:
        min_amount = float(min_amount) if min_amount not in (None, "") else None
    except (TypeError, ValueError):
        min_amount = None
    try:
        max_amount = float(max_amount) if max_amount not in (None, "") else None
    except (TypeError, ValueError):
        max_amount = None
    return min_amount, max_amount, currency


def score_item(item: dict, profile: dict) -> tuple[int, str]:
    role_text = " ".join(
        clean_text(item.get(field), 1000).lower()
        for field in ("title", "company", "location")
    )
    body_text = " ".join(
        clean_text(item.get(field), 3000).lower()
        for field in ("description", "note")
    )
    text = f"{role_text} {body_text}"
    score = 0
    role_hits = 0
    body_hits = 0
    for term in profile["must_review_terms"]:
        if term in role_text:
            score += 6
            role_hits += 1
        elif term in body_text:
            score += 2
            body_hits += 1
    for term in profile["positive_terms"]:
        if term in role_text:
            score += 2
        elif term in body_text:
            score += 1
    for term in profile["remote_terms"]:
        if term in role_text:
            score += 1
    for term in profile["negative_terms"]:
        if term in role_text:
            score -= 10
        elif term in body_text:
            score -= 4

    candidate = profile.get("candidate_profile") or {}
    if candidate:
        candidate_role_hits = 0
        for term in candidate.get("target_roles", []) + candidate.get("role_terms", []):
            needle = clean_text(term, 120).lower()
            if not needle:
                continue
            if needle in role_text:
                score += 3
                candidate_role_hits += 1
            elif needle in body_text:
                score += 1
        skill_bonus = 0
        for term in candidate.get("skills", []):
            needle = clean_text(term, 120).lower()
            if needle and needle in text:
                skill_bonus += 1
        score += min(skill_bonus, 4)
        industry_bonus = 0
        for term in candidate.get("industries", []):
            needle = clean_text(term, 120).lower()
            if needle and needle in text:
                industry_bonus += 1
        score += min(industry_bonus, 3)
        for term in candidate.get("negative_terms", []):
            needle = clean_text(term, 120).lower()
            if needle and needle in role_text:
                score -= 8
            elif needle and needle in body_text:
                score -= 3
        if candidate_role_hits:
            role_hits += 1

    salary_min, salary_max, currency = numeric_salary(item)
    target = profile.get("salary_target_pen", 7000)
    if currency.upper() in {"PEN", "S/", "SOLES"} and salary_max and salary_max >= target:
        score += 4
    elif currency.upper() in {"USD", "$"} and salary_max and salary_max >= 1900:
        score += 4

    if not role_hits:
        score = min(score, 6 if body_hits else 5)

    if role_hits and score >= 13:
        verdict = "priorizar"
    elif (role_hits or body_hits) and score >= 7:
        verdict = "revisar"
    else:
        verdict = "backup"
    return score, verdict


def normalize_agentmail(item: dict, path: Path) -> dict:
    salary_min, salary_max, currency = numeric_salary(item)
    return {
        "source": "agentmail",
        "source_detail": clean_text(item.get("source"), 120),
        "title": clean_text(item.get("title"), 300),
        "company": clean_text(item.get("company"), 200),
        "location": clean_text(item.get("location"), 200),
        "remote": "",
        "published": clean_text(item.get("published"), 120),
        "salary_text": detect_salary_text(item) or clean_text(item.get("salary_detail"), 500),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": currency,
        "url": clean_url(item.get("url") or item.get("url_final") or ""),
        "description": clean_text(item.get("note"), 4000),
        "raw": {"agentmail_file": str(path), **item},
    }


def import_agentmail(days: int) -> tuple[list[dict], list[str]]:
    cutoff = now_utc() - timedelta(days=days)
    items = []
    blockers = []
    for path in sorted(AGENTMAIL_TRACKING.glob("processed-vacancies-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(str(payload.get("created_at")).replace("Z", "+00:00"))
        except Exception as exc:
            blockers.append(f"agentmail:{path.name}: {type(exc).__name__}: {exc}")
            continue
        if created < cutoff:
            continue
        for vacancy in payload.get("vacancies") or []:
            normalized = normalize_agentmail(vacancy, path)
            if normalized["title"]:
                items.append(normalized)
    return items, blockers


def import_jobspy(profile: dict, limit_per_query: int) -> tuple[list[dict], list[str]]:
    try:
        from jobspy import scrape_jobs
    except Exception as exc:
        return [], [f"jobspy_not_available: {type(exc).__name__}: {exc}"]

    items = []
    blockers = []
    sites = profile.get("jobspy_sites") or []
    if not sites:
        return [], []
    for term in profile["search_terms"]:
        for location in profile["locations"]:
            try:
                df = scrape_jobs(
                    site_name=sites,
                    search_term=term,
                    location=location,
                    results_wanted=limit_per_query,
                    country_indeed=profile.get("jobspy_country_indeed", "peru"),
                    linkedin_fetch_description=False,
                    verbose=0,
                )
            except Exception as exc:
                blockers.append(f"jobspy:{term}:{location}: {type(exc).__name__}: {exc}")
                continue
            for record in df.to_dict(orient="records"):
                url = clean_url(record.get("job_url_direct") or record.get("job_url") or "")
                description = clean_text(record.get("description"), 4000)
                salary_min = record.get("min_amount")
                salary_max = record.get("max_amount")
                item = {
                    "source": clean_text(record.get("site"), 80) or "jobspy",
                    "source_detail": f"jobspy:{term}:{location}",
                    "title": clean_text(record.get("title"), 300),
                    "company": clean_text(record.get("company"), 200),
                    "location": clean_text(record.get("location"), 200),
                    "remote": str(bool(record.get("is_remote"))).lower() if record.get("is_remote") is not None else "",
                    "published": clean_text(record.get("date_posted"), 120),
                    "salary_text": detect_salary_text({"description": description}),
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "salary_currency": clean_text(record.get("currency"), 20),
                    "url": url,
                    "description": description,
                    "raw": record,
                }
                if item["title"]:
                    items.append(item)
    return items, blockers


def import_getonboard(profile: dict, limit_per_query: int) -> tuple[list[dict], list[str]]:
    items = []
    blockers = []
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0"}
    for term in profile["search_terms"][:4]:
        url = f"https://www.getonbrd.com.pe/empleos?query={quote_plus(term)}"
        try:
            response = session.get(url, headers=headers, timeout=25)
            response.raise_for_status()
        except Exception as exc:
            blockers.append(f"getonboard:{term}: {type(exc).__name__}: {exc}")
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        seen = set()
        for link in soup.select('a[href*="/empleos/"]'):
            href = link.get("href") or ""
            if "/empleos/" not in href:
                continue
            full_url = clean_url(href if href.startswith("http") else f"https://www.getonbrd.com{href}")
            if full_url in seen:
                continue
            seen.add(full_url)
            title_el = link.select_one("h4, h3, .gb-results-list__title")
            company_el = link.select_one(".gb-results-list__company, .company, [class*=company]")
            location_el = link.select_one("[class*=location], .remote, .gb-results-list__location")
            text = clean_text(link.get_text(" "), 1500)
            title = clean_text(title_el.get_text(" "), 300) if title_el else text.split(" en ")[0][:300]
            company = clean_text(company_el.get_text(" "), 200) if company_el else ""
            location = clean_text(location_el.get_text(" "), 200) if location_el else ""
            items.append(
                {
                    "source": "getonboard",
                    "source_detail": f"getonboard:{term}",
                    "title": title,
                    "company": company,
                    "location": location,
                    "remote": "remote" if "remote" in text.lower() or "remoto" in text.lower() else "",
                    "published": "",
                    "salary_text": detect_salary_text({"description": text}),
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "",
                    "url": full_url,
                    "description": text,
                    "raw": {"query": term, "text": text},
                }
            )
            if len(seen) >= limit_per_query:
                break
    return items, blockers


def apify_search_input(profile: dict, limit_per_query: int) -> dict:
    terms = profile.get("search_terms") or []
    locations = profile.get("locations") or []
    max_items = min(
        int(profile.get("apify_max_items") or limit_per_query * max(1, len(terms)) * max(1, len(locations))),
        int(profile.get("apify_hard_max_items") or 200),
    )
    return {
        "search_terms": terms,
        "locations": locations,
        "max_items": max_items,
        "note": "Dry-run payload. Actor-specific input mapping is applied only when Apify is explicitly enabled.",
    }


def import_apify_source(profile: dict, source_key: str, limit_per_query: int) -> tuple[list[dict], list[str]]:
    source_def = APIFY_SOURCE_DEFS[source_key]
    mode = clean_text(profile.get("apify_mode") or "disabled", 40).lower()
    if mode != "enabled":
        payload = apify_search_input(profile, limit_per_query)
        return [], [
            f"apify:{source_key}: {mode or 'disabled'}; no se ejecuto actor {source_def['actor']}; "
            f"payload_preview={json.dumps(payload, ensure_ascii=False)}"
        ]
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        return [], [f"apify:{source_key}: APIFY_API_TOKEN no configurado; no se ejecuto {source_def['actor']}"]
    return [], [
        f"apify:{source_key}: interfaz lista para {source_def['actor']}, pero el mapeo de input/output real queda bloqueado hasta benchmark aprobado con cap de gasto"
    ]


def upsert_items(conn: sqlite3.Connection, run_id: str, items: list[dict], profile: dict) -> tuple[int, int]:
    inserted = 0
    updated = 0
    at = now_utc().isoformat()
    for item in items:
        item["clean_url"] = clean_url(item.get("url") or "")
        item["salary_text"] = item.get("salary_text") or detect_salary_text(item)
        item["salary_min"], item["salary_max"], item["salary_currency"] = numeric_salary(item)
        item["score"], item["verdict"] = score_item(item, profile)
        item["duplicate_key"] = duplicate_key_for(item)
        key = external_key(item)
        rid = row_id(item)
        existing = conn.execute("select id from vacancies where external_key = ?", (key,)).fetchone()
        payload = (
            rid,
            key,
            item["source"],
            item.get("source_detail", ""),
            item["title"],
            item.get("company", ""),
            item.get("location", ""),
            item.get("remote", ""),
            item.get("published", ""),
            item.get("salary_text", ""),
            item.get("salary_min"),
            item.get("salary_max"),
            item.get("salary_currency", ""),
            item.get("url", ""),
            item.get("clean_url", ""),
            item.get("description", ""),
            item["score"],
            item["verdict"],
            at,
            run_id,
            json.dumps(item.get("raw") or item, ensure_ascii=False, default=str),
            item["duplicate_key"],
        )
        if existing:
            conn.execute(
                """
                update vacancies set
                  source=?, source_detail=?, title=?, company=?, location=?, remote=?,
                  published=?, salary_text=?, salary_min=?, salary_max=?, salary_currency=?,
                  url=?, clean_url=?, description=?, score=?, verdict=?,
                  last_seen_at=?, run_id=?, raw_json=?, duplicate_key=?, duplicate_of=null,
                  status=case when status='duplicate' then 'new' else status end
                where external_key=?
                """,
                payload[2:] + (key,),
            )
            updated += 1
        else:
            conn.execute(
                """
                insert into vacancies (
                  id, external_key, source, source_detail, title, company, location, remote,
                  published, salary_text, salary_min, salary_max, salary_currency, url, clean_url,
                  description, score, verdict, first_seen_at, last_seen_at, run_id, raw_json,
                  duplicate_key, duplicate_of
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, null)
                """,
                payload[:18] + (at,) + payload[18:],
            )
            inserted += 1
    conn.commit()
    return inserted, updated


def duplicate_sort_key(row: sqlite3.Row) -> tuple:
    source = (row["source"] or "").lower()
    url = row["clean_url"] or row["url"] or ""
    direct_url = bool(url and "jobsora.com" not in url)
    return (
        VERDICT_RANK.get(row["verdict"], 0),
        row["score"] or 0,
        1 if row["status"] in {"review", "apply", "applied"} else 0,
        1 if direct_url else 0,
        SOURCE_RANK.get(source, 0),
        row["last_seen_at"] or "",
    )


def fuzzy_duplicate_groups(rows: list[sqlite3.Row]) -> list[list[sqlite3.Row]]:
    groups: list[list[sqlite3.Row]] = []
    for row in rows:
        title = canonical_title(row["title"])
        company = canonical_company(row["company"])
        placed = False
        for group in groups:
            head = group[0]
            head_title = canonical_title(head["title"])
            head_company = canonical_company(head["company"])
            if company and head_company and company != head_company:
                continue
            title_ratio = SequenceMatcher(None, title, head_title).ratio()
            if title == head_title or title_ratio >= 0.88:
                group.append(row)
                placed = True
                break
        if not placed:
            groups.append([row])
    return [group for group in groups if len(group) > 1]


def dedupe_existing(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        select id, source, title, company, location, score, verdict, status,
               clean_url, url, last_seen_at
        from vacancies
        where status not in ('discarded', 'false_positive')
        """
    ).fetchall()
    for row in rows:
        conn.execute("update vacancies set duplicate_key=? where id=?", (duplicate_key_for(dict(row)), row["id"]))

    buckets: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        title = canonical_title(row["title"])
        if not title:
            continue
        company = canonical_company(row["company"])
        bucket = company or title.split(" ", 1)[0]
        buckets.setdefault(bucket, []).append(row)

    duplicate_ids: set[str] = set()
    keep_ids: set[str] = set()
    for bucket_rows in buckets.values():
        if len(bucket_rows) < 2:
            continue
        for group in fuzzy_duplicate_groups(bucket_rows):
            keeper = sorted(group, key=duplicate_sort_key, reverse=True)[0]
            keep_ids.add(keeper["id"])
            for row in group:
                if row["id"] != keeper["id"] and row["status"] not in {"apply", "applied"}:
                    duplicate_ids.add(row["id"])
                    conn.execute("update vacancies set status='duplicate', duplicate_of=? where id=?", (keeper["id"], row["id"]))

    if keep_ids:
        conn.executemany(
            "update vacancies set duplicate_of=null, status=case when status='duplicate' then 'new' else status end where id=?",
            [(keep_id,) for keep_id in keep_ids],
        )
    conn.commit()
    return {"groups": len(keep_ids), "duplicates": len(duplicate_ids)}


def rescore_existing(conn: sqlite3.Connection, profile: dict) -> int:
    rows = conn.execute(
        """
        select id, source, source_detail, title, company, location, remote, description,
               salary_text, salary_min, salary_max, salary_currency
        from vacancies
        """
    ).fetchall()
    for row in rows:
        item = dict(row)
        score, verdict = score_item(item, profile)
        conn.execute(
            "update vacancies set score=?, verdict=?, duplicate_key=? where id=?",
            (score, verdict, duplicate_key_for(item), row["id"]),
        )
    conn.commit()
    return len(rows)


def fetch_current_rows(conn: sqlite3.Connection, limit: int = 300) -> list[dict]:
    rows = conn.execute(
        """
        select source, title, company, location, remote, published, salary_text,
               salary_min, salary_max, salary_currency, url, score, verdict, status,
               first_seen_at, last_seen_at
        from vacancies
        where status not in ('discarded', 'duplicate', 'false_positive')
        order by score desc, last_seen_at desc
        limit ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def write_reports(conn: sqlite3.Connection, run_id: str, run_payload: dict) -> tuple[Path, Path, Path]:
    import pandas as pd

    rows = fetch_current_rows(conn)
    stamp = run_id
    out_json = RUNS / f"job-radar-{stamp}.json"
    out_md = RUNS / f"job-radar-{stamp}.md"
    out_xlsx = ENTREGABLES / f"JOB_RADAR_PERSONAL_{stamp}.xlsx"
    latest_xlsx = ENTREGABLES / "JOB_RADAR_PERSONAL_LATEST.xlsx"
    ENTREGABLES.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps({"run": run_payload, "vacancies": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    top = [row for row in rows if row["verdict"] == "priorizar"][:15]
    review = [row for row in rows if row["verdict"] == "revisar"][:20]
    backup = [row for row in rows if row["verdict"] == "backup"][:20]
    lines = [
        "# Job Radar Personal",
        "",
        f"Run: `{run_id}`",
        f"Importadas esta corrida: {run_payload['imported']} | nuevas: {run_payload['inserted']} | actualizadas: {run_payload['updated']}",
        f"Bloqueos/incidencias de fuente: {len(run_payload['blockers'])}",
        "",
        "## Top oportunidades",
    ]
    if not top:
        lines.append("- Sin top prioritario todavía.")
    for item in top:
        lines.append(f"- score {item['score']} | {item['title']} - {item.get('company') or 'empresa no clara'} ({item.get('location') or 'ubicación no clara'})")
        if item.get("url"):
            lines.append(f"  {item['url']}")
    lines.extend(["", "## Para revisar"])
    for item in review:
        lines.append(f"- score {item['score']} | {item['title']} - {item.get('company') or 'empresa no clara'} ({item.get('source')})")
        if item.get("url"):
            lines.append(f"  {item['url']}")
    lines.extend(["", "## Backup reciente"])
    for item in backup[:10]:
        lines.append(f"- score {item['score']} | {item['title']} - {item.get('company') or 'empresa no clara'} ({item.get('source')})")
    if run_payload["blockers"]:
        lines.extend(["", "## Incidencias"])
        lines.extend(f"- {blocker}" for blocker in run_payload["blockers"][:30])
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    df = pd.DataFrame(rows)
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        pd.DataFrame([run_payload]).drop(columns=["blockers"], errors="ignore").to_excel(writer, index=False, sheet_name="Resumen")
        df[df["verdict"] == "priorizar"].to_excel(writer, index=False, sheet_name="Top")
        df[df["verdict"] == "revisar"].to_excel(writer, index=False, sheet_name="Revisar")
        df.to_excel(writer, index=False, sheet_name="Todas")
        pd.DataFrame({"incidencia": run_payload["blockers"]}).to_excel(writer, index=False, sheet_name="Incidencias")
    latest_xlsx.write_bytes(out_xlsx.read_bytes())
    return out_json, out_md, out_xlsx


def main() -> int:
    parser = argparse.ArgumentParser(description="Local-first job radar for Gus.")
    parser.add_argument("--agentmail-days", type=int, default=14)
    parser.add_argument("--limit-per-query", type=int, default=10)
    parser.add_argument("--no-agentmail", action="store_true")
    parser.add_argument("--no-jobspy", action="store_true")
    parser.add_argument("--no-getonboard", action="store_true")
    args = parser.parse_args()

    profile = load_profile()
    run_id = now_utc().strftime("%Y%m%dT%H%M%SZ")
    conn = init_db()
    conn.execute(
        "insert or replace into runs(id, started_at, profile_name, blockers_json) values (?, ?, ?, '[]')",
        (run_id, now_utc().isoformat(), profile.get("profile_name")),
    )
    conn.commit()

    all_items: list[dict] = []
    blockers: list[str] = []
    sources = enabled_sources(profile)
    if not args.no_agentmail and "agentmail" in sources:
        items, issues = import_agentmail(args.agentmail_days)
        all_items.extend(items)
        blockers.extend(issues)
    jobspy_profile = dict(profile)
    jobspy_profile["jobspy_sites"] = [
        site for site in profile.get("jobspy_sites", [])
        if clean_text(site, 80).lower() in sources
    ]
    if not args.no_jobspy and jobspy_profile["jobspy_sites"]:
        items, issues = import_jobspy(jobspy_profile, args.limit_per_query)
        all_items.extend(items)
        blockers.extend(issues)
    if not args.no_getonboard and "getonboard" in sources:
        items, issues = import_getonboard(profile, args.limit_per_query)
        all_items.extend(items)
        blockers.extend(issues)
    for source_key in sorted(sources & set(APIFY_SOURCE_DEFS)):
        items, issues = import_apify_source(profile, source_key, args.limit_per_query)
        all_items.extend(items)
        blockers.extend(issues)

    inserted, updated = upsert_items(conn, run_id, all_items, profile)
    rescore_existing(conn, profile)
    dedupe = dedupe_existing(conn)
    run_payload = {
        "id": run_id,
        "started_at": run_id,
        "finished_at": now_utc().isoformat(),
        "profile_name": profile.get("profile_name"),
        "imported": len(all_items),
        "inserted": inserted,
        "updated": updated,
        "duplicate_groups": dedupe["groups"],
        "duplicates_hidden": dedupe["duplicates"],
        "blockers": blockers,
    }
    conn.execute(
        """
        update runs
        set finished_at=?, imported=?, inserted=?, updated=?, duplicate_groups=?,
            duplicates_hidden=?, blockers_json=?
        where id=?
        """,
        (
            run_payload["finished_at"],
            len(all_items),
            inserted,
            updated,
            dedupe["groups"],
            dedupe["duplicates"],
            json.dumps(blockers, ensure_ascii=False),
            run_id,
        ),
    )
    conn.commit()
    out_json, out_md, out_xlsx = write_reports(conn, run_id, run_payload)

    rows = fetch_current_rows(conn)
    top = [row for row in rows if row["verdict"] == "priorizar"]
    review = [row for row in rows if row["verdict"] == "revisar"]
    print(f"JOB_RADAR_OK run={run_id} imported={len(all_items)} inserted={inserted} updated={updated} duplicates_hidden={dedupe['duplicates']} top={len(top)} review={len(review)} blockers={len(blockers)}")
    print(f"JSON={out_json}")
    print(f"MD={out_md}")
    print(f"XLSX={out_xlsx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
