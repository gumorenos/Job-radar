#!/usr/bin/env python3
import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from job_radar_candidate import CANDIDATE_PROFILE_PATH, CV_MARKDOWN_PATH, load_candidate_profile
except ModuleNotFoundError:
    from scripts.job_radar_candidate import CANDIDATE_PROFILE_PATH, CV_MARKDOWN_PATH, load_candidate_profile


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "tracking" / "job-radar" / "job_radar.sqlite"
ENTREGABLES = ROOT / "entregables"
PROMPT_VERSION = "job-radar-match-v1"
DEFAULT_PROVIDER = os.environ.get("JOB_RADAR_LLM_PROVIDER", "openrouter").lower()
DEFAULT_MODEL_BY_PROVIDER = {
    "openrouter": "deepseek/deepseek-v4-flash",
    "deepseek": "deepseek-chat",
    "openai": "gpt-5.1",
}
DEFAULT_MODEL = os.environ.get("JOB_RADAR_LLM_MODEL", DEFAULT_MODEL_BY_PROVIDER.get(DEFAULT_PROVIDER, "deepseek/deepseek-v4-flash"))

COURSE_CATALOG = {
    "people analytics": [
        "People Analytics - University of Pennsylvania (Coursera)",
        "People Analytics and Evidence-Based Management - AIHR",
    ],
    "power bi": [
        "Microsoft Power BI Data Analyst - Microsoft Learn",
        "PL-300: Power BI Data Analyst Associate certification",
    ],
    "sql": [
        "SQL for Data Science - UC Davis (Coursera)",
        "Databases and SQL for Data Science with Python - IBM (Coursera)",
    ],
    "python": [
        "Python for Everybody - University of Michigan (Coursera)",
        "Python for Data Analysis - freeCodeCamp / pandas practice",
    ],
    "hris": [
        "HRIS Implementation and Digital HR - AIHR",
        "Workday HCM basics or vendor-specific HRIS training",
    ],
    "compensation": [
        "Compensation and Benefits - AIHR",
        "WorldatWork Total Rewards certification path",
    ],
    "labor relations": [
        "Labor Relations / Employee Relations specialization - LinkedIn Learning",
        "Employment Law and Employee Relations refreshers for target geography",
    ],
    "change management": [
        "Change Management - University of Illinois (Coursera)",
        "Prosci Change Management certification",
    ],
    "shrm": [
        "SHRM-CP / SHRM-SCP certification",
        "HRCI PHR / SPHR certification",
    ],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any, limit: int = 6000) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())[:limit]


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_analysis_db(conn)
    return conn


def init_analysis_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists vacancy_analyses (
          id text primary key,
          vacancy_id text not null,
          status text not null default 'pending',
          model text,
          prompt_version text not null,
          match_score integer,
          created_at text not null,
          updated_at text not null,
          analysis_json text,
          error text,
          foreign key(vacancy_id) references vacancies(id)
        )
        """
    )
    conn.execute("create index if not exists vacancy_analyses_vacancy_idx on vacancy_analyses(vacancy_id, updated_at desc)")
    conn.commit()


def analysis_id(vacancy_id: str) -> str:
    return f"{vacancy_id}:{PROMPT_VERSION}"


def get_vacancy(conn: sqlite3.Connection, vacancy_id: str) -> dict:
    row = conn.execute(
        """
        select id, source, source_detail, title, company, location, remote, published,
               salary_text, url, description, score, verdict, status
        from vacancies
        where id=?
        """,
        (vacancy_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Vacante no encontrada: {vacancy_id}")
    return dict(row)


def latest_analysis(conn: sqlite3.Connection, vacancy_id: str) -> dict | None:
    row = conn.execute(
        """
        select id, vacancy_id, status, model, prompt_version, match_score,
               created_at, updated_at, analysis_json, error
        from vacancy_analyses
        where vacancy_id=?
        order by updated_at desc
        limit 1
        """,
        (vacancy_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    if data.get("analysis_json"):
        data["analysis"] = json.loads(data["analysis_json"])
    data.pop("analysis_json", None)
    return data


def upsert_analysis(conn: sqlite3.Connection, vacancy_id: str, status: str, model: str, analysis: dict | None = None, error: str = "") -> dict:
    existing = conn.execute("select created_at from vacancy_analyses where id=?", (analysis_id(vacancy_id),)).fetchone()
    created_at = existing["created_at"] if existing else now_iso()
    updated_at = now_iso()
    match_score = None
    if analysis:
        try:
            match_score = int(analysis.get("match_score"))
        except (TypeError, ValueError):
            match_score = None
    conn.execute(
        """
        insert into vacancy_analyses (
          id, vacancy_id, status, model, prompt_version, match_score,
          created_at, updated_at, analysis_json, error
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(id) do update set
          status=excluded.status,
          model=excluded.model,
          match_score=excluded.match_score,
          updated_at=excluded.updated_at,
          analysis_json=excluded.analysis_json,
          error=excluded.error
        """,
        (
            analysis_id(vacancy_id),
            vacancy_id,
            status,
            model,
            PROMPT_VERSION,
            match_score,
            created_at,
            updated_at,
            json.dumps(analysis, ensure_ascii=False, indent=2) if analysis else None,
            error,
        ),
    )
    conn.commit()
    return latest_analysis(conn, vacancy_id) or {}


def load_context() -> tuple[str, dict]:
    cv_markdown = CV_MARKDOWN_PATH.read_text(encoding="utf-8") if CV_MARKDOWN_PATH.exists() else ""
    candidate_profile = load_candidate_profile() if CANDIDATE_PROFILE_PATH.exists() else {}
    if not cv_markdown and not candidate_profile:
        raise ValueError("No hay CV/perfil cargado. Sube o guarda un CV primero.")
    return cv_markdown, candidate_profile


def normalize_terms(items: list[Any]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        text = clean_text(item, 120).lower()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def term_present(term: str, text: str) -> bool:
    if not term:
        return False
    if len(term) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def extract_job_requirements(vacancy: dict) -> dict:
    text = " ".join(clean_text(vacancy.get(field), 6000) for field in ("title", "company", "location", "description")).lower()
    skill_terms = [
        "people analytics",
        "power bi",
        "sql",
        "python",
        "excel",
        "hris",
        "workday",
        "successfactors",
        "sap",
        "compensation",
        "benefits",
        "total rewards",
        "labor relations",
        "employee relations",
        "change management",
        "talent management",
        "hr business partner",
        "english",
        "ingles",
    ]
    seniority_terms = ["senior", "jefe", "manager", "lead", "head", "specialist", "analyst", "analista", "coordinator"]
    return {
        "skills": [term for term in skill_terms if term_present(term, text)],
        "seniority": [term for term in seniority_terms if term_present(term, text)],
        "language": [term for term in ("english", "ingles") if term_present(term, text)],
    }


def heuristic_analysis(vacancy: dict, cv_markdown: str, candidate_profile: dict) -> dict:
    job_text = " ".join(clean_text(vacancy.get(field), 6000) for field in ("title", "company", "location", "description")).lower()
    cv_text = f"{cv_markdown} {json.dumps(candidate_profile, ensure_ascii=False)}".lower()
    requirements = extract_job_requirements(vacancy)
    candidate_roles = normalize_terms(candidate_profile.get("target_roles", []) + candidate_profile.get("role_terms", []))
    candidate_skills = normalize_terms(candidate_profile.get("skills", []))
    candidate_industries = normalize_terms(candidate_profile.get("industries", []))

    role_hits = [term for term in candidate_roles if term_present(term, job_text)]
    skill_hits = [term for term in candidate_skills if term_present(term, job_text)]
    industry_hits = [term for term in candidate_industries if term_present(term, job_text)]
    requirement_hits = [term for term in requirements["skills"] if term_present(term, cv_text)]
    missing = [term for term in requirements["skills"] if not term_present(term, cv_text)]

    score = 45
    score += min(len(role_hits) * 8, 24)
    score += min(len(skill_hits) * 5, 20)
    score += min(len(industry_hits) * 4, 8)
    score += min(len(requirement_hits) * 4, 16)
    score -= min(len(missing) * 6, 24)
    if vacancy.get("verdict") == "priorizar":
        score += 8
    elif vacancy.get("verdict") == "revisar":
        score += 3
    score = max(0, min(100, score))

    suggested_terms = missing[:8]
    courses = []
    for gap in suggested_terms:
        for key, values in COURSE_CATALOG.items():
            if key in gap or gap in key:
                courses.extend(values)
    if "people analytics" in job_text and not courses:
        courses.extend(COURSE_CATALOG["people analytics"])
    if "shrm" in job_text or "human resources" in job_text:
        courses.extend(COURSE_CATALOG["shrm"][:1])

    return {
        "match_score": score,
        "probability": "alta" if score >= 78 else "media" if score >= 58 else "baja",
        "summary": f"Match heurístico para {vacancy.get('title') or 'vacante'} en {vacancy.get('company') or 'empresa no clara'}.",
        "strengths": [
            f"Encaje de rol: {', '.join(role_hits[:5])}" if role_hits else "El perfil HR/People puede ser relevante, pero el título no confirma un encaje fuerte.",
            f"Skills alineadas: {', '.join(skill_hits[:6])}" if skill_hits else "No se detectaron muchas skills explícitas del CV en la vacante.",
            f"Industria relacionada: {', '.join(industry_hits[:3])}" if industry_hits else "No hay señal clara de industria compartida.",
        ],
        "critical_gaps": missing[:4],
        "minor_gaps": [term for term in requirements["seniority"] + requirements["language"] if not term_present(term, cv_text)][:5],
        "cv_adjustments": [
            "Refuerza en el resumen las palabras exactas del puesto que ya estén respaldadas por experiencia real.",
            "Sube bullets de People/HR Operations, analytics, compensaciones o labor relations según aparezcan en la vacante.",
            "No agregues herramientas o certificaciones que no tengas; mejor mostrar proyectos, métricas o alcance comprobable.",
        ],
        "missing_keywords": suggested_terms,
        "recommended_courses": list(dict.fromkeys(courses))[:6],
        "job_requirements_detected": requirements,
        "method": "heuristic_fallback",
    }


def prompt_payload(vacancy: dict, cv_markdown: str, candidate_profile: dict) -> list[dict]:
    job = {
        "title": vacancy.get("title"),
        "company": vacancy.get("company"),
        "location": vacancy.get("location"),
        "salary_text": vacancy.get("salary_text"),
        "url": vacancy.get("url"),
        "description": clean_text(vacancy.get("description"), 6000),
        "radar_score": vacancy.get("score"),
        "radar_verdict": vacancy.get("verdict"),
    }
    schema = {
        "match_score": "integer 0-100",
        "probability": "alta|media|baja",
        "summary": "short Spanish summary",
        "strengths": ["concrete strengths backed by the CV"],
        "critical_gaps": ["must-have gaps"],
        "minor_gaps": ["nice-to-have gaps"],
        "cv_adjustments": ["truthful CV tailoring suggestions; do not invent experience"],
        "missing_keywords": ["keywords missing from CV/profile"],
        "recommended_courses": ["course, MOOC, or certification suggestions"],
        "job_requirements_detected": {
            "must_have": [],
            "nice_to_have": [],
            "skills": [],
            "seniority": "",
            "languages": [],
        },
    }
    user_text = {
        "candidate_profile": candidate_profile,
        "cv_markdown_excerpt": cv_markdown[:12000],
        "job": job,
        "required_json_schema": schema,
    }
    return [
        {
            "role": "system",
            "content": (
                "Eres un career coach senior para roles HR/People. Compara CV/perfil contra una vacante. "
                "Responde solo JSON valido, en español, sin markdown. No inventes experiencia, herramientas, "
                "certificaciones ni logros que no esten en el CV/perfil."
            ),
        },
        {"role": "user", "content": json.dumps(user_text, ensure_ascii=False)},
    ]


def parse_llm_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start : end + 1]
    data = json.loads(text)
    if "match_score" not in data:
        raise ValueError("Respuesta LLM sin match_score")
    data["match_score"] = max(0, min(100, int(data["match_score"])))
    data["method"] = "llm"
    return data


def chat_completion_analysis(
    vacancy: dict,
    cv_markdown: str,
    candidate_profile: dict,
    url: str,
    api_key: str,
    model: str,
    provider: str,
    extra_headers: dict | None = None,
) -> dict:
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **(extra_headers or {}),
        },
        json={
            "model": model,
            "messages": prompt_payload(vacancy, cv_markdown, candidate_profile),
            "temperature": 0.2,
            "max_tokens": 1800,
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload["choices"][0]["message"]["content"]
    data = parse_llm_json(text)
    data["method"] = f"llm:{provider}"
    if payload.get("usage"):
        data["llm_usage"] = payload["usage"]
    return data


def openai_responses_analysis(vacancy: dict, cv_markdown: str, candidate_profile: dict, model: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no configurado")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "input": prompt_payload(vacancy, cv_markdown, candidate_profile),
            "temperature": 0.2,
            "max_output_tokens": 1800,
        },
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("output_text") or ""
    if not text:
        parts = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    parts.append(content.get("text", ""))
        text = "\n".join(parts)
    data = parse_llm_json(text)
    data["method"] = "llm:openai"
    if payload.get("usage"):
        data["llm_usage"] = payload["usage"]
    return data


def llm_analysis(vacancy: dict, cv_markdown: str, candidate_profile: dict, model: str = DEFAULT_MODEL, provider: str = DEFAULT_PROVIDER) -> dict:
    provider = provider.lower()
    if provider == "openai":
        return openai_responses_analysis(vacancy, cv_markdown, candidate_profile, model)
    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY no configurado")
        return chat_completion_analysis(
            vacancy,
            cv_markdown,
            candidate_profile,
            "https://openrouter.ai/api/v1/chat/completions",
            api_key,
            model,
            provider,
            {
                "HTTP-Referer": os.environ.get("JOB_RADAR_OPENROUTER_REFERER", "http://localhost/job-radar"),
                "X-Title": os.environ.get("JOB_RADAR_OPENROUTER_TITLE", "Job Radar Personal"),
            },
        )
    if provider == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY no configurado")
        return chat_completion_analysis(
            vacancy,
            cv_markdown,
            candidate_profile,
            "https://api.deepseek.com/chat/completions",
            api_key,
            model,
            provider,
        )
    raise RuntimeError(f"Proveedor LLM no soportado: {provider}")


def analyze_vacancy(vacancy_id: str, force: bool = False, offline: bool = False, provider: str = DEFAULT_PROVIDER, model: str = DEFAULT_MODEL) -> dict:
    cv_markdown, candidate_profile = load_context()
    with connect_db() as conn:
        if not force:
            current = latest_analysis(conn, vacancy_id)
            if current and current.get("status") == "done":
                return current
        vacancy = get_vacancy(conn, vacancy_id)
        model_label = f"{provider}:{model}"
        upsert_analysis(conn, vacancy_id, "pending", model_label)
        try:
            if offline:
                raise RuntimeError("offline mode")
            analysis = llm_analysis(vacancy, cv_markdown, candidate_profile, model, provider)
            return upsert_analysis(conn, vacancy_id, "done", model_label, analysis=analysis)
        except Exception as exc:
            fallback = heuristic_analysis(vacancy, cv_markdown, candidate_profile)
            fallback["llm_error"] = str(exc)
            return upsert_analysis(conn, vacancy_id, "done", "heuristic-fallback", analysis=fallback)


def export_analyses(vacancy_ids: list[str] | None = None) -> dict:
    ENTREGABLES.mkdir(parents=True, exist_ok=True)
    params: list[Any] = []
    where = ""
    if vacancy_ids:
        where = "where v.id in (%s)" % ",".join("?" for _ in vacancy_ids)
        params.extend(vacancy_ids)
    with connect_db() as conn:
        rows = conn.execute(
            f"""
            select v.id vacancy_id, v.title, v.company, v.location, v.url, v.score radar_score,
                   v.verdict radar_verdict, a.status analysis_status, a.model, a.match_score,
                   a.updated_at, a.analysis_json, a.error
            from vacancies v
            join vacancy_analyses a on a.vacancy_id = v.id
            {where}
            order by a.match_score desc, v.score desc, a.updated_at desc
            """,
            params,
        ).fetchall()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = ENTREGABLES / f"JOB_RADAR_ANALISIS_MATCH_{stamp}.md"
    latest_md = ENTREGABLES / "JOB_RADAR_ANALISIS_MATCH_LATEST.md"
    lines = ["# Job Radar - Analisis de Match", "", f"Generado: `{stamp}`", ""]
    export_rows = []
    for row in rows:
        data = dict(row)
        analysis = json.loads(data.pop("analysis_json") or "{}")
        export_rows.append({**data, **analysis})
        lines.extend(
            [
                f"## {data['title']} - {data.get('company') or 'empresa no clara'}",
                "",
                f"- Match: {analysis.get('match_score', data.get('match_score'))}/100 ({analysis.get('probability', 'n/d')})",
                f"- Radar: {data.get('radar_score')} / {data.get('radar_verdict')}",
                f"- URL: {data.get('url') or 'sin URL'}",
                f"- Resumen: {analysis.get('summary', '')}",
                "",
                "### Fortalezas",
                *[f"- {item}" for item in analysis.get("strengths", [])],
                "",
                "### Brechas criticas",
                *[f"- {item}" for item in analysis.get("critical_gaps", []) or ["Sin brechas criticas detectadas."]],
                "",
                "### Cursos / certificaciones",
                *[f"- {item}" for item in analysis.get("recommended_courses", []) or ["Sin recomendacion especifica."]],
                "",
            ]
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    latest_md.write_bytes(md_path.read_bytes())

    xlsx_path = None
    try:
        import pandas as pd

        xlsx_path = ENTREGABLES / f"JOB_RADAR_ANALISIS_MATCH_{stamp}.xlsx"
        latest_xlsx = ENTREGABLES / "JOB_RADAR_ANALISIS_MATCH_LATEST.xlsx"
        pd.DataFrame(export_rows).to_excel(xlsx_path, index=False)
        latest_xlsx.write_bytes(xlsx_path.read_bytes())
    except Exception:
        xlsx_path = None
    return {"count": len(rows), "markdown": str(md_path), "latest_markdown": str(latest_md), "xlsx": str(xlsx_path) if xlsx_path else ""}


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze selected Job Radar vacancies against the candidate CV/profile.")
    parser.add_argument("vacancy_ids", nargs="*")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["openrouter", "deepseek", "openai"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    results = []
    for vacancy_id in args.vacancy_ids:
        results.append(analyze_vacancy(vacancy_id, force=args.force, offline=args.offline, provider=args.provider, model=args.model))
    payload = {"analyses": results}
    if args.export:
        payload["export"] = export_analyses(args.vacancy_ids or None)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
