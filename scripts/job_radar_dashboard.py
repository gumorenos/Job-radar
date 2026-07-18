#!/usr/bin/env python3
import argparse
import warnings

warnings.filterwarnings("ignore", message="'cgi' is deprecated.*", category=DeprecationWarning)
import cgi
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from job_radar_candidate import (
        CANDIDATE_PROFILE_PATH,
        CV_MARKDOWN_PATH,
        extract_candidate_profile,
        load_candidate_profile,
        process_cv_upload,
        save_candidate_profile,
    )
    from job_radar_match_analysis import analyze_vacancy, export_analyses, init_analysis_db, latest_analysis
except ModuleNotFoundError:
    from scripts.job_radar_candidate import (
        CANDIDATE_PROFILE_PATH,
        CV_MARKDOWN_PATH,
        extract_candidate_profile,
        load_candidate_profile,
        process_cv_upload,
        save_candidate_profile,
    )
    from scripts.job_radar_match_analysis import analyze_vacancy, export_analyses, init_analysis_db, latest_analysis


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "config" / "job-radar-profile.json"
DB_PATH = ROOT / "tracking" / "job-radar" / "job_radar.sqlite"
RUNS_DIR = ROOT / "tracking" / "job-radar" / "runs"
LATEST_XLSX = ROOT / "entregables" / "JOB_RADAR_PERSONAL_LATEST.xlsx"
RUNNER = ROOT / "scripts" / "job_radar.py"

LIST_FIELDS = {
    "search_terms",
    "locations",
    "jobspy_sites",
    "enabled_sources",
    "enabled_portals",
    "must_review_terms",
    "positive_terms",
    "negative_terms",
    "remote_terms",
}

SOURCES = [
    ("agentmail", "AgentMail"),
    ("linkedin", "LinkedIn"),
    ("indeed", "Indeed"),
    ("getonboard", "GetOnBoard"),
    ("apify_valig", "Apify Valig"),
    ("apify_cheap_scraper", "Apify Cheap Scraper"),
    ("apify_curious_coder", "Apify Curious Coder"),
]


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if not length:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def read_cv_upload(handler: BaseHTTPRequestHandler) -> tuple[str, bytes]:
    form = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
        },
    )
    field = form["cv"] if "cv" in form else None
    if field is None or not getattr(field, "filename", ""):
        raise ValueError("Sube un archivo en el campo `cv`.")
    return Path(field.filename).name, field.file.read()


def send_json(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_file(handler: BaseHTTPRequestHandler, path: Path, mime_type: str) -> None:
    if not path.exists():
        send_json(handler, {"error": "not_found"}, 404)
        return
    body = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", mime_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
    handler.end_headers()
    handler.wfile.write(body)


def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def save_profile(payload: dict) -> dict:
    current = load_profile()
    updated = dict(current)
    for key, value in payload.items():
        if key in LIST_FIELDS:
            if isinstance(value, str):
                values = [line.strip() for line in value.splitlines()]
            else:
                values = [str(item).strip() for item in value]
            updated[key] = [item for item in values if item]
        elif key == "salary_target_pen":
            updated[key] = int(value or 0)
        else:
            updated[key] = value
    if "enabled_sources" in updated:
        updated["enabled_portals"] = [source for source in updated["enabled_sources"] if source in {"agentmail", "linkedin", "indeed", "getonboard"}]
    PROFILE_PATH.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return updated


def get_candidate_payload() -> dict:
    markdown = CV_MARKDOWN_PATH.read_text(encoding="utf-8") if CV_MARKDOWN_PATH.exists() else ""
    profile = load_candidate_profile()
    return {
        "exists": bool(markdown or profile),
        "markdown_path": str(CV_MARKDOWN_PATH),
        "profile_path": str(CANDIDATE_PROFILE_PATH),
        "markdown": markdown,
        "candidate_profile": profile,
    }


def save_candidate_payload(payload: dict) -> dict:
    markdown = str(payload.get("markdown") or "")
    profile_payload = payload.get("candidate_profile")
    if isinstance(profile_payload, str):
        profile = json.loads(profile_payload) if profile_payload.strip() else {}
    elif isinstance(profile_payload, dict):
        profile = profile_payload
    else:
        profile = {}
    if not profile:
        profile = extract_candidate_profile(markdown, "cv.md")
    save_candidate_profile(markdown, profile)
    return get_candidate_payload()


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_analysis_db(conn)
    return conn


def get_summary(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """
        select
          sum(case when status not in ('discarded', 'duplicate', 'false_positive') then 1 else 0 end) total,
          sum(case when verdict='priorizar' and status not in ('discarded', 'duplicate', 'false_positive') then 1 else 0 end) top,
          sum(case when verdict='revisar' and status not in ('discarded', 'duplicate', 'false_positive') then 1 else 0 end) review,
          sum(case when verdict='backup' and status not in ('discarded', 'duplicate', 'false_positive') then 1 else 0 end) backup,
          sum(case when status='discarded' then 1 else 0 end) discarded,
          sum(case when status='duplicate' then 1 else 0 end) duplicates,
          sum(case when status='false_positive' then 1 else 0 end) false_positive
        from vacancies
        """
    ).fetchone()
    analysis_row = conn.execute(
        """
        select
          count(*) total,
          sum(case when status='done' then 1 else 0 end) done,
          sum(case when status='error' then 1 else 0 end) errors
        from vacancy_analyses
        """
    ).fetchone()
    by_source = conn.execute(
        """
        select source, count(*) count
        from vacancies
        where status not in ('discarded', 'duplicate', 'false_positive')
        group by source
        order by count(*) desc
        """
    ).fetchall()
    last_run = conn.execute(
        """
        select id, finished_at, imported, inserted, updated, duplicate_groups,
               duplicates_hidden, blockers_json
        from runs
        order by finished_at desc
        limit 1
        """
    ).fetchone()
    return {
        "counts": dict(rows) if rows else {},
        "analyses": dict(analysis_row) if analysis_row else {},
        "by_source": [dict(row) for row in by_source],
        "last_run": dict(last_run) if last_run else None,
        "latest_xlsx": str(LATEST_XLSX),
    }


def list_vacancies(query: dict) -> list[dict]:
    verdict = query.get("verdict", [""])[0]
    status = query.get("status", ["active"])[0]
    source = query.get("source", [""])[0]
    search = query.get("q", [""])[0].strip().lower()
    limit = min(int(query.get("limit", ["100"])[0] or 100), 500)

    where = []
    params: list[object] = []
    if verdict:
        where.append("v.verdict = ?")
        params.append(verdict)
    if source:
        where.append("v.source = ?")
        params.append(source)
    if status == "active":
        where.append("v.status not in ('discarded', 'duplicate', 'false_positive')")
    elif status:
        where.append("v.status = ?")
        params.append(status)
    if search:
        where.append("(lower(v.title) like ? or lower(v.company) like ? or lower(v.location) like ? or lower(v.description) like ?)")
        params.extend([f"%{search}%"] * 4)
    clause = "where " + " and ".join(where) if where else ""
    sql = f"""
        select v.id, v.source, v.source_detail, v.title, v.company, v.location, v.remote, v.published,
               v.salary_text, v.url, v.score, v.verdict, v.status, v.first_seen_at, v.last_seen_at,
               a.status analysis_status, a.match_score analysis_score, a.updated_at analysis_updated_at
        from vacancies
        v
        left join vacancy_analyses a on a.vacancy_id = v.id
        {clause}
        order by v.score desc, v.last_seen_at desc
        limit ?
    """
    params.append(limit)
    with connect_db() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def update_vacancy_status(vacancy_id: str, status: str) -> None:
    allowed = {"new", "review", "apply", "applied", "discarded", "false_positive", "duplicate"}
    if status not in allowed:
        raise ValueError(f"Estado invalido: {status}")
    with connect_db() as conn:
        conn.execute("update vacancies set status=? where id=?", (status, vacancy_id))
        conn.commit()


def analyze_vacancies_payload(payload: dict) -> dict:
    vacancy_ids = payload.get("ids") or payload.get("id") or []
    if isinstance(vacancy_ids, str):
        vacancy_ids = [vacancy_ids]
    vacancy_ids = [str(item) for item in vacancy_ids if str(item).strip()]
    if not vacancy_ids:
        raise ValueError("Selecciona al menos una vacante.")
    force = bool(payload.get("force"))
    offline = bool(payload.get("offline"))
    results = [analyze_vacancy(vacancy_id, force=force, offline=offline) for vacancy_id in vacancy_ids[:10]]
    return {"ok": True, "count": len(results), "analyses": results}


def get_analysis_payload(vacancy_id: str) -> dict:
    with connect_db() as conn:
        analysis = latest_analysis(conn, vacancy_id)
    return analysis or {"vacancy_id": vacancy_id, "status": "missing"}


def export_analyses_payload(query: dict) -> dict:
    raw_ids = query.get("ids", [""])[0]
    vacancy_ids = [item for item in raw_ids.split(",") if item] if raw_ids else None
    return export_analyses(vacancy_ids)


def run_radar(payload: dict) -> dict:
    limit = int(payload.get("limit_per_query") or 10)
    agentmail_days = int(payload.get("agentmail_days") or 14)
    cmd = [
        sys.executable,
        str(RUNNER),
        "--limit-per-query",
        str(limit),
        "--agentmail-days",
        str(agentmail_days),
    ]
    if payload.get("no_agentmail"):
        cmd.append("--no-agentmail")
    if payload.get("no_jobspy"):
        cmd.append("--no-jobspy")
    if payload.get("no_getonboard"):
        cmd.append("--no-getonboard")
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=600)
    return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "finished_at": datetime.now().isoformat()}


HTML = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Radar</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #1d2533;
      --muted: #647084;
      --line: #d9e0ea;
      --blue: #246bfe;
      --green: #127a5b;
      --amber: #9a5b00;
      --red: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
      letter-spacing: 0;
    }
    header {
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 22px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
      position: sticky;
      top: 0;
      z-index: 5;
    }
    h1 { font-size: 20px; margin: 0; font-weight: 720; }
    main {
      max-width: 1440px;
      margin: 0 auto;
      padding: 18px;
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 18px;
    }
    section, aside {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    aside { padding: 16px; align-self: start; position: sticky; top: 82px; }
    .toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    button, select, input, textarea {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
    }
    button {
      height: 36px;
      padding: 0 12px;
      cursor: pointer;
      font-weight: 650;
    }
    button.primary { background: var(--blue); border-color: var(--blue); color: #fff; }
    button.ghost { background: #eef3ff; border-color: #d6e2ff; color: #174ea6; }
    button.warn { background: #fff4e3; border-color: #ffd79a; color: var(--amber); }
    button:disabled { opacity: .48; cursor: not-allowed; }
    input, select { height: 36px; padding: 0 10px; }
    textarea {
      width: 100%;
      min-height: 76px;
      resize: vertical;
      padding: 9px 10px;
      line-height: 1.35;
    }
    label { display: grid; gap: 6px; margin: 12px 0; font-size: 13px; color: var(--muted); }
    label span { font-weight: 650; color: var(--ink); }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
      gap: 10px;
      padding: 16px;
      border-bottom: 1px solid var(--line);
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-height: 74px;
      background: #fbfcff;
    }
    .metric strong { display: block; font-size: 24px; line-height: 1; margin-bottom: 8px; }
    .metric span { color: var(--muted); font-size: 12px; }
    .filters {
      display: flex;
      gap: 8px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      align-items: center;
      flex-wrap: wrap;
    }
    .filters input { min-width: 240px; flex: 1; }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }
    th { color: var(--muted); background: #fbfcff; font-size: 12px; }
    td a { color: var(--blue); text-decoration: none; overflow-wrap: anywhere; }
    .title { font-weight: 700; }
    .muted { color: var(--muted); }
    .pill {
      display: inline-flex;
      align-items: center;
      height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
      background: #f8fafc;
      white-space: nowrap;
    }
    .priorizar { color: var(--green); border-color: #b6eadb; background: #ecfff8; }
    .revisar { color: var(--amber); border-color: #ffd79a; background: #fff8ed; }
    .backup { color: var(--muted); }
    .statusbar {
      padding: 10px 16px;
      color: var(--muted);
      border-bottom: 1px solid var(--line);
      min-height: 42px;
      font-size: 13px;
    }
    .profile-actions { display: flex; gap: 8px; margin-top: 12px; }
    .cv-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0; }
    .cv-actions input[type=file] { max-width: 100%; height: auto; padding: 8px; }
    .json-preview { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; min-height: 150px; font-size: 12px; }
    .selected-panel {
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      background: #fbfcff;
    }
    .analysis-box {
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      background: #fff;
      display: none;
    }
    .analysis-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }
    .analysis-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcff;
    }
    .checkcell { display: flex; gap: 8px; align-items: flex-start; }
    .checkcell input { width: 16px; height: 16px; margin-top: 3px; flex: 0 0 auto; }
    .link-button {
      height: 36px;
      display: inline-flex;
      align-items: center;
      padding: 0 12px;
      border: 1px solid #d6e2ff;
      border-radius: 6px;
      background: #eef3ff;
      color: #174ea6;
      text-decoration: none;
      font-weight: 650;
      font-size: 13px;
    }
    .runbox { margin-top: 18px; border-top: 1px solid var(--line); padding-top: 14px; }
    .portal-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(120px, 1fr));
      gap: 8px;
      margin: 10px 0 14px;
    }
    .portal-option {
      min-height: 38px;
      display: flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      color: var(--ink);
      font-size: 13px;
      font-weight: 650;
      background: #fbfcff;
    }
    .portal-option input { width: 16px; height: 16px; }
    @media (max-width: 920px) {
      main { grid-template-columns: 1fr; }
      aside { position: static; }
      .metrics { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      th:nth-child(4), td:nth-child(4), th:nth-child(5), td:nth-child(5) { display: none; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Job Radar</h1>
    <div class="toolbar">
      <button class="ghost" onclick="refreshAll()">Actualizar</button>
      <a class="link-button" href="/download/latest.xlsx">Excel</a>
      <button class="primary" onclick="runRadar()">Correr radar</button>
    </div>
  </header>
  <main>
    <aside>
      <h2 style="font-size:16px;margin:0 0 8px">Perfil</h2>
      <div id="profile"></div>
      <div class="profile-actions">
        <button class="primary" onclick="saveProfile()">Guardar perfil</button>
      </div>
      <div class="runbox">
        <h2 style="font-size:16px;margin:0 0 8px">Corrida</h2>
        <label><span>Límite por búsqueda</span><input id="limit_per_query" type="number" value="10" min="1" max="50"></label>
        <label><span>Días AgentMail</span><input id="agentmail_days" type="number" value="14" min="1" max="90"></label>
        <label><span><input id="no_getonboard" type="checkbox" style="height:auto"> Omitir GetOnBoard experimental</span></label>
      </div>
      <div class="runbox">
        <h2 style="font-size:16px;margin:0 0 8px">CV / Perfil</h2>
        <div class="cv-actions">
          <input id="cv_file" type="file" accept=".pdf,.docx,.md,.markdown,.txt">
          <button class="ghost" onclick="uploadCv()">Subir CV</button>
        </div>
        <label><span>Markdown CV</span><textarea id="cv_markdown" style="min-height:120px"></textarea></label>
        <label><span>Perfil JSON</span><textarea id="candidate_profile_json" class="json-preview"></textarea></label>
        <div class="profile-actions">
          <button class="primary" onclick="saveCandidateProfile()">Guardar CV/perfil</button>
          <button class="ghost" onclick="regenerateCandidateProfile()">Regenerar JSON</button>
        </div>
      </div>
    </aside>
    <section>
      <div class="metrics" id="metrics"></div>
      <div class="statusbar" id="status">Cargando...</div>
      <div class="selected-panel">
        <div><strong id="selectedCount">0</strong> seleccionadas</div>
        <div class="toolbar">
          <button class="ghost" onclick="selectVisibleTop()">Seleccionar Top visibles</button>
          <button class="primary" id="analyzeBtn" onclick="analyzeSelected()" disabled>Analizar match</button>
          <button class="ghost" id="exportBtn" onclick="exportSelectedAnalyses()" disabled>Export análisis</button>
          <button onclick="clearSelection()">Limpiar</button>
        </div>
      </div>
      <div class="analysis-box" id="analysisBox"></div>
      <div class="filters">
        <input id="q" placeholder="Buscar título, empresa, ubicación..." oninput="debouncedLoad()">
        <select id="verdict" onchange="loadVacancies()">
          <option value="">Todos los veredictos</option>
          <option value="priorizar">Top</option>
          <option value="revisar">Revisar</option>
          <option value="backup">Backup</option>
        </select>
        <select id="sourceFilter" onchange="loadVacancies()">
          <option value="">Todas las fuentes</option>
        </select>
        <select id="statusFilter" onchange="loadVacancies()">
          <option value="active">Activas</option>
          <option value="new">Nuevas</option>
          <option value="review">Marcadas revisar</option>
          <option value="apply">Para aplicar</option>
          <option value="applied">Aplicadas</option>
          <option value="discarded">Descartadas</option>
          <option value="duplicate">Duplicadas</option>
          <option value="false_positive">Falsos positivos</option>
          <option value="">Todos los estados</option>
        </select>
      </div>
      <div style="overflow:auto">
        <table>
          <thead>
            <tr>
              <th style="width:158px">Score</th>
              <th>Vacante</th>
              <th style="width:170px">Empresa</th>
              <th style="width:150px">Fuente</th>
              <th style="width:150px">Ubicación</th>
              <th style="width:260px">Acciones</th>
            </tr>
          </thead>
          <tbody id="vacancies"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    let profile = {};
    let timer;
    let currentRows = [];
    const selected = new Set();

    async function api(path, opts = {}) {
      const res = await fetch(path, opts);
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    }

    function lines(value) {
      return Array.isArray(value) ? value.join('\n') : (value ?? '');
    }

    function renderProfile(data) {
      profile = data;
      const fields = [
        ['profile_name', 'Nombre', 'input'],
        ['salary_target_pen', 'Salario objetivo PEN', 'number'],
        ['search_terms', 'Búsquedas', 'textarea'],
        ['locations', 'Ubicaciones', 'textarea'],
        ['jobspy_sites', 'JobSpy sites', 'textarea'],
        ['apify_mode', 'Apify mode: disabled / dry_run / enabled', 'input'],
        ['apify_hard_max_items', 'Apify hard max items', 'number'],
        ['must_review_terms', 'Términos fuertes', 'textarea'],
        ['positive_terms', 'Términos positivos', 'textarea'],
        ['negative_terms', 'Términos negativos', 'textarea'],
        ['remote_terms', 'Remoto / ubicación', 'textarea']
      ];
      const enabled = new Set(data.enabled_sources || data.enabled_portals || ['agentmail', 'linkedin', 'indeed', 'getonboard']);
      const portalHtml = `
        <div style="margin-top:12px">
          <div style="font-size:13px;font-weight:700;margin-bottom:6px">Fuentes incluidas</div>
          <div class="portal-grid">
            ${[
              ['agentmail', 'AgentMail'],
              ['linkedin', 'LinkedIn'],
              ['indeed', 'Indeed'],
              ['getonboard', 'GetOnBoard'],
              ['apify_valig', 'Apify Valig'],
              ['apify_cheap_scraper', 'Apify Cheap'],
              ['apify_curious_coder', 'Apify Curious']
            ].map(([key, label]) => `
              <label class="portal-option" title="${key.startsWith('apify_') ? 'Apify queda en dry-run/disabled hasta configurar token y cap' : ''}">
                <input type="checkbox" data-source="${key}" ${enabled.has(key) ? 'checked' : ''}>
                ${label}
              </label>
            `).join('')}
          </div>
        </div>`;
      document.getElementById('profile').innerHTML = portalHtml + fields.map(([key, label, type]) => {
        if (key === 'enabled_portals') return '';
        const value = lines(data[key]);
        if (type === 'textarea') {
          return `<label><span>${label}</span><textarea data-key="${key}">${escapeHtml(value)}</textarea></label>`;
        }
        return `<label><span>${label}</span><input data-key="${key}" type="${type}" value="${escapeHtml(value)}"></label>`;
      }).join('');
    }

    function renderMetrics(summary) {
      const c = summary.counts || {};
      const items = [
        ['Total', c.total || 0],
        ['Top', c.top || 0],
        ['Revisar', c.review || 0],
        ['Backup', c.backup || 0],
        ['Descartadas', c.discarded || 0],
        ['Duplicadas', c.duplicates || 0],
        ['Falsos +', c.false_positive || 0],
        ['Analizadas', (summary.analyses || {}).done || 0]
      ];
      document.getElementById('metrics').innerHTML = items.map(([label, value]) =>
        `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`
      ).join('');
      const sourceFilter = document.getElementById('sourceFilter');
      const selectedSource = sourceFilter.value;
      sourceFilter.innerHTML = '<option value="">Todas las fuentes</option>' + (summary.by_source || []).map(row =>
        `<option value="${escapeAttr(row.source)}">${escapeHtml(row.source)} (${row.count})</option>`
      ).join('');
      sourceFilter.value = selectedSource;
      const run = summary.last_run;
      document.getElementById('status').textContent = run
        ? `Última corrida ${run.id}: importadas ${run.imported}, nuevas ${run.inserted}, actualizadas ${run.updated}, duplicadas ocultas ${run.duplicates_hidden || 0}. Excel: ${summary.latest_xlsx}`
        : 'Sin corridas registradas.';
    }

    function renderVacancies(rows) {
      currentRows = rows;
      document.getElementById('vacancies').innerHTML = rows.map(row => `
        <tr>
          <td>
            <div class="checkcell">
              <input type="checkbox" data-select-id="${row.id}" ${selected.has(row.id) ? 'checked' : ''} onchange="toggleSelection('${row.id}', this.checked)">
              <div>
                <span class="pill ${row.verdict}">${row.score} ${row.verdict}</span>
                ${row.analysis_score !== null && row.analysis_score !== undefined ? `<div style="margin-top:6px"><span class="pill">${row.analysis_score} match</span></div>` : ''}
                ${row.analysis_status ? `<div class="muted" style="margin-top:4px">Análisis: ${escapeHtml(row.analysis_status)}</div>` : ''}
              </div>
            </div>
          </td>
          <td>
            <div class="title">${escapeHtml(row.title || '')}</div>
            <div class="muted">${escapeHtml(row.published || '')} ${escapeHtml(row.salary_text || '')}</div>
            ${row.url ? `<a href="${escapeAttr(row.url)}" target="_blank" rel="noreferrer">Abrir enlace</a>` : '<span class="muted">Sin URL</span>'}
          </td>
          <td>${escapeHtml(row.company || '')}</td>
          <td>${escapeHtml(row.source || '')}<div class="muted">${escapeHtml(row.status || '')}</div></td>
          <td>${escapeHtml(row.location || '')}</td>
          <td>
            <button onclick="setStatus('${row.id}', 'review')">Revisar</button>
            <button onclick="setStatus('${row.id}', 'apply')">Aplicar</button>
            <button class="ghost" onclick="analyzeOne('${row.id}')">Analizar</button>
            <button class="warn" onclick="setStatus('${row.id}', 'discarded')">Descartar</button>
            <button class="warn" onclick="setStatus('${row.id}', 'false_positive')">Falso +</button>
          </td>
        </tr>
      `).join('');
      syncSelectionUi();
    }

    function syncSelectionUi() {
      document.getElementById('selectedCount').textContent = selected.size;
      document.getElementById('analyzeBtn').disabled = selected.size === 0;
      document.getElementById('exportBtn').disabled = selected.size === 0;
      document.querySelectorAll('[data-select-id]').forEach(el => el.checked = selected.has(el.dataset.selectId));
    }

    function toggleSelection(id, checked) {
      if (checked) selected.add(id);
      else selected.delete(id);
      syncSelectionUi();
    }

    function clearSelection() {
      selected.clear();
      syncSelectionUi();
    }

    function selectVisibleTop() {
      currentRows
        .filter(row => row.verdict === 'priorizar' && row.status !== 'duplicate' && row.status !== 'false_positive')
        .slice(0, 10)
        .forEach(row => selected.add(row.id));
      syncSelectionUi();
    }

    function renderAnalysisResults(items) {
      const box = document.getElementById('analysisBox');
      const rows = (items || []).map(item => item.analysis ? item : {analysis: item});
      if (!rows.length) {
        box.style.display = 'none';
        box.innerHTML = '';
        return;
      }
      box.style.display = 'block';
      box.innerHTML = `<div class="analysis-grid">${rows.map(row => {
        const a = row.analysis || {};
        return `<div class="analysis-card">
          <div><strong>${a.match_score ?? row.match_score ?? 'n/d'}/100</strong> ${escapeHtml(a.probability || '')}</div>
          <div class="muted">${escapeHtml(row.model || a.method || '')}</div>
          <p>${escapeHtml(a.summary || row.error || '')}</p>
          <div><strong>Brechas</strong></div>
          <ul>${(a.critical_gaps || []).slice(0, 4).map(x => `<li>${escapeHtml(x)}</li>`).join('') || '<li>Sin brechas críticas detectadas</li>'}</ul>
          <div><strong>Cursos/certs</strong></div>
          <ul>${(a.recommended_courses || []).slice(0, 4).map(x => `<li>${escapeHtml(x)}</li>`).join('') || '<li>Sin recomendación específica</li>'}</ul>
        </div>`;
      }).join('')}</div>`;
    }

    async function loadProfile() {
      renderProfile(await api('/api/profile'));
    }

    async function saveProfile() {
      const payload = {};
      document.querySelectorAll('[data-key]').forEach(el => payload[el.dataset.key] = el.value);
      payload.enabled_sources = [...document.querySelectorAll('[data-source]:checked')].map(el => el.dataset.source);
      renderProfile(await api('/api/profile', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      }));
      document.getElementById('status').textContent = 'Perfil guardado. Corre el radar para aplicar cambios de búsqueda; el scoring se aplicará en la corrida.';
    }

    function renderCandidateProfile(data) {
      document.getElementById('cv_markdown').value = data.markdown || '';
      document.getElementById('candidate_profile_json').value = JSON.stringify(data.candidate_profile || {}, null, 2);
    }

    async function loadCandidateProfile() {
      renderCandidateProfile(await api('/api/candidate-profile'));
    }

    async function uploadCv() {
      const file = document.getElementById('cv_file').files[0];
      if (!file) {
        document.getElementById('status').textContent = 'Elige un PDF, DOCX, Markdown o TXT.';
        return;
      }
      const form = new FormData();
      form.append('cv', file);
      document.getElementById('status').textContent = 'Procesando CV...';
      const data = await api('/api/cv/upload', {method: 'POST', body: form});
      renderCandidateProfile(data);
      document.getElementById('status').textContent = 'CV convertido a Markdown y perfil generado. Corre el radar para aplicar este perfil al scoring.';
    }

    async function saveCandidateProfile() {
      const payload = {
        markdown: document.getElementById('cv_markdown').value,
        candidate_profile: document.getElementById('candidate_profile_json').value
      };
      renderCandidateProfile(await api('/api/candidate-profile', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      }));
      document.getElementById('status').textContent = 'CV/perfil guardado. Corre el radar para recalcular matches.';
    }

    async function regenerateCandidateProfile() {
      document.getElementById('candidate_profile_json').value = '';
      await saveCandidateProfile();
    }

    async function loadSummary() {
      renderMetrics(await api('/api/summary'));
    }

    async function loadVacancies() {
      const params = new URLSearchParams({
        q: document.getElementById('q').value,
        verdict: document.getElementById('verdict').value,
        source: document.getElementById('sourceFilter').value,
        status: document.getElementById('statusFilter').value,
        limit: '150'
      });
      renderVacancies(await api('/api/vacancies?' + params.toString()));
    }

    function debouncedLoad() {
      clearTimeout(timer);
      timer = setTimeout(loadVacancies, 250);
    }

    async function setStatus(id, status) {
      await api('/api/vacancy/status', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id, status})
      });
      await refreshAll();
    }

    async function analyzeOne(id) {
      selected.add(id);
      await analyzeSelected([id]);
    }

    async function analyzeSelected(ids = null) {
      const targetIds = ids || [...selected];
      if (!targetIds.length) return;
      document.getElementById('status').textContent = `Analizando ${targetIds.length} vacante(s)...`;
      const result = await api('/api/vacancy/analyze', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: targetIds})
      });
      renderAnalysisResults(result.analyses || []);
      document.getElementById('status').textContent = `Análisis terminado: ${result.count} vacante(s).`;
      await refreshAll();
    }

    async function exportSelectedAnalyses() {
      const ids = [...selected];
      if (!ids.length) return;
      const result = await api('/api/analyses/export?ids=' + encodeURIComponent(ids.join(',')));
      document.getElementById('status').textContent = `Export listo: ${result.latest_markdown}${result.xlsx ? ' | ' + result.xlsx : ''}`;
    }

    async function runRadar() {
      await saveProfile();
      document.getElementById('status').textContent = 'Corriendo radar... puede tardar unos minutos.';
      const result = await api('/api/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          limit_per_query: document.getElementById('limit_per_query').value,
          agentmail_days: document.getElementById('agentmail_days').value,
          no_getonboard: document.getElementById('no_getonboard').checked
        })
      });
      document.getElementById('status').textContent = result.stdout || result.stderr || 'Corrida terminada.';
      await refreshAll();
    }

    async function refreshAll() {
      await loadSummary();
      await loadVacancies();
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function escapeAttr(value) { return escapeHtml(value); }

    loadProfile();
    loadCandidateProfile();
    refreshAll();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("job-radar-dashboard " + fmt % args + "\n")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/profile":
            send_json(self, load_profile())
            return
        if parsed.path == "/api/candidate-profile":
            send_json(self, get_candidate_payload())
            return
        if parsed.path == "/api/summary":
            with connect_db() as conn:
                send_json(self, get_summary(conn))
            return
        if parsed.path == "/api/vacancies":
            send_json(self, list_vacancies(parse_qs(parsed.query)))
            return
        if parsed.path == "/api/analysis":
            query = parse_qs(parsed.query)
            send_json(self, get_analysis_payload(str(query.get("id", [""])[0])))
            return
        if parsed.path == "/api/analyses/export":
            send_json(self, export_analyses_payload(parse_qs(parsed.query)))
            return
        if parsed.path == "/download/latest.xlsx":
            send_file(self, LATEST_XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            return
        send_json(self, {"error": "not_found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/cv/upload":
                filename, content = read_cv_upload(self)
                process_cv_upload(filename, content)
                send_json(self, get_candidate_payload())
                return
            payload = read_json_body(self)
            if parsed.path == "/api/profile":
                send_json(self, save_profile(payload))
                return
            if parsed.path == "/api/candidate-profile":
                send_json(self, save_candidate_payload(payload))
                return
            if parsed.path == "/api/vacancy/status":
                update_vacancy_status(str(payload["id"]), str(payload["status"]))
                send_json(self, {"ok": True})
                return
            if parsed.path == "/api/vacancy/analyze":
                send_json(self, analyze_vacancies_payload(payload))
                return
            if parsed.path == "/api/run":
                send_json(self, run_radar(payload))
                return
            send_json(self, {"error": "not_found"}, 404)
        except Exception as exc:
            send_json(self, {"error": type(exc).__name__, "detail": str(exc)}, 500)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local dashboard for Job Radar.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"JOB_RADAR_DASHBOARD http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
