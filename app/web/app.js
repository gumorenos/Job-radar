const routes = {
  radar: { eyebrow: "Radar", title: "Oportunidades" },
  applications: { eyebrow: "CRM", title: "Postulaciones" },
  cvs: { eyebrow: "Perfil profesional", title: "CVs" },
  settings: { eyebrow: "Administración", title: "Configuración" },
};

const filterLabels = {
  high: "Alta prioridad",
  review: "Revisar",
  discarded: "Descartadas",
  duplicates: "Posibles duplicados",
};

const feedbackReasonLabels = {
  SALARY: "Salario",
  SENIORITY: "Seniority",
  SKILLS: "Skills",
  LOCATION: "Ubicación",
  INDUSTRY: "Industria",
  DEGREE: "Grado / carrera",
  TITLE: "Título del puesto",
  OTHER: "Otro",
};

const sidebar = document.querySelector(".sidebar");
const detailPanel = document.getElementById("detailPanel");
const opportunityList = document.getElementById("opportunityList");
const opportunitySearch = document.getElementById("opportunitySearch");
let radarFilter = "high";
let searchTimer;
let initialRadarLoad = true;

function currentRoute() {
  const route = window.location.hash.replace(/^#\//, "").split("/")[0];
  return routes[route] ? route : "radar";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-PE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload.detail) message = payload.detail;
    } catch (_) {
      // Preserve the HTTP status when the response body is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function renderRoute() {
  const route = currentRoute();
  const meta = routes[route];

  document.querySelectorAll("[data-view]").forEach((view) => {
    view.classList.toggle("active", view.dataset.view === route);
  });
  document.querySelectorAll("[data-route]").forEach((link) => {
    const active = link.dataset.route === route;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });

  document.getElementById("eyebrow").textContent = meta.eyebrow;
  document.getElementById("pageTitle").textContent = meta.title;
  sidebar.classList.remove("open");
  document.title = `${meta.title} · Job Radar`;

  if (route === "radar") loadRadar();
}

function setRadarFilter(filter, { reload = true } = {}) {
  radarFilter = filter;
  document.querySelectorAll("[data-radar-filter]").forEach((control) => {
    control.classList.toggle("active", control.dataset.radarFilter === filter);
  });
  if (reload) loadRadarJobs();
}

function classificationPresentation(item) {
  if (item.classification === "HIGH_PRIORITY") {
    return { label: "Alta prioridad", className: "high" };
  }
  if (item.classification === "DISCARD") {
    return { label: "Descartada", className: "discarded" };
  }
  if (item.classification === "REVIEW") {
    return { label: "Revisar", className: "review" };
  }
  return { label: "Sin análisis", className: "pending" };
}

function renderSummary(summary) {
  Object.entries(summary).forEach(([key, value]) => {
    const element = document.querySelector(`[data-summary-value="${key}"]`);
    if (element) element.textContent = value;
  });
}

function renderJobs(items) {
  if (!items.length) {
    opportunityList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">◎</div>
        <h2>Sin oportunidades en ${escapeHtml(filterLabels[radarFilter])}</h2>
        <p>${radarFilter === "duplicates"
          ? "Cuando Job Radar detecte coincidencias dudosas, aparecerán aquí para que decidas si deben unirse."
          : "Prueba otra clasificación o cambia la búsqueda."}</p>
      </div>`;
    return;
  }

  opportunityList.innerHTML = items.map((item) => {
    const classification = classificationPresentation(item);
    const meta = [item.location, item.work_mode !== "UNKNOWN" ? item.work_mode : null, item.salary_text]
      .filter(Boolean)
      .map(escapeHtml)
      .join(" · ");
    const score = item.score === null || item.score === undefined
      ? ""
      : `<span class="score-badge">${item.score}% match</span>`;
    const human = item.classification_source === "human"
      ? `<span class="human-badge">Corregida</span>`
      : "";

    return `
      <button class="opportunity-row" data-job-id="${item.id}">
        <div class="opportunity-body">
          <div class="opportunity-heading">
            <span class="classification-pill ${classification.className}">${classification.label}</span>
            ${human}
            ${score}
          </div>
          <strong>${escapeHtml(item.title)}</strong>
          <span class="opportunity-company">${escapeHtml(item.company || "Empresa no indicada")}</span>
          <small>${meta || "Información parcial"}</small>
        </div>
        <div class="opportunity-side">
          <span>${escapeHtml(item.posting_source || "Fuente desconocida")}</span>
          <small>${formatDate(item.last_seen_at)}</small>
          <b aria-hidden="true">›</b>
        </div>
      </button>`;
  }).join("");

  document.querySelectorAll("[data-job-id]").forEach((row) => {
    row.addEventListener("click", () => loadJobDetail(row.dataset.jobId));
  });
}

function renderObjectList(value, emptyText) {
  const items = Array.isArray(value) ? value : [];
  if (!items.length) return `<p class="detail-muted">${escapeHtml(emptyText)}</p>`;
  return `<ul class="detail-list">${items.slice(0, 6).map((item) => {
    if (typeof item === "string") return `<li>${escapeHtml(item)}</li>`;
    return `<li>${escapeHtml(JSON.stringify(item))}</li>`;
  }).join("")}</ul>`;
}

function renderAnalysis(analysis) {
  if (!analysis) {
    return `
      <section class="detail-section pending-analysis">
        <h3>Análisis</h3>
        <p>Esta oportunidad todavía no tiene un análisis de compatibilidad. Mientras tanto permanece en Revisar.</p>
      </section>`;
  }

  const classification = classificationPresentation({ classification: analysis.classification });
  return `
    <section class="analysis-summary">
      <div>
        <span class="classification-pill ${classification.className}">${classification.label}</span>
        <strong>${analysis.score ?? "—"}<small>${analysis.score === null ? "" : "%"}</small></strong>
        <span>${escapeHtml(analysis.confidence ? `Confianza ${analysis.confidence.toLowerCase()}` : "")}</span>
      </div>
      <p>${escapeHtml(analysis.explanation || analysis.recommendation || "Análisis disponible sin explicación resumida.")}</p>
    </section>
    <section class="detail-section">
      <h3>Por qué encaja</h3>
      ${renderObjectList(analysis.strengths, "Sin fortalezas estructuradas todavía.")}
    </section>
    <section class="detail-section">
      <h3>Brechas</h3>
      ${renderObjectList(analysis.gaps, "Sin brechas registradas.")}
    </section>
    ${analysis.career_move_assessment ? `
      <section class="detail-section"><h3>Movimiento de carrera</h3><p>${escapeHtml(analysis.career_move_assessment)}</p></section>` : ""}
    ${analysis.salary_assessment ? `
      <section class="detail-section"><h3>Salario</h3><p>${escapeHtml(analysis.salary_assessment)}</p></section>` : ""}`;
}

function renderFeedback(detail) {
  if (!detail.latest_analysis || !detail.latest_analysis.classification) {
    return `
      <section class="detail-section feedback-section">
        <h3>Tu decisión</h3>
        <p class="detail-muted">Podrás corregir la clasificación cuando exista un análisis del sistema.</p>
      </section>`;
  }

  const feedback = detail.latest_feedback;
  const currentClassification = feedback?.human_classification || detail.effective_classification || "REVIEW";
  const currentReason = feedback?.reason_code || "OTHER";
  const currentComment = feedback?.comment || "";
  const currentPresentation = classificationPresentation({ classification: currentClassification });
  const existing = feedback ? `
    <div class="feedback-current">
      <div>
        <span class="classification-pill ${currentPresentation.className}">${currentPresentation.label}</span>
        <strong>Decisión humana vigente</strong>
      </div>
      <p>${escapeHtml(feedbackReasonLabels[feedback.reason_code] || feedback.reason_code)}${feedback.comment ? ` · ${escapeHtml(feedback.comment)}` : ""}</p>
      <small>Guardada ${formatDate(feedback.created_at)}. El análisis original del sistema se conserva.</small>
    </div>` : `
    <p class="detail-muted feedback-intro">Si no estás de acuerdo con Job Radar, registra tu decisión. No se borra el análisis original.</p>`;

  const classificationOptions = [
    ["HIGH_PRIORITY", "Alta prioridad"],
    ["REVIEW", "Revisar"],
    ["DISCARD", "Descartar"],
  ].map(([value, label]) => `
    <label class="feedback-choice-option">
      <input type="radio" name="human_classification" value="${value}" ${currentClassification === value ? "checked" : ""}>
      <span>${label}</span>
    </label>`).join("");

  const reasonOptions = Object.entries(feedbackReasonLabels).map(([value, label]) => `
    <option value="${value}" ${currentReason === value ? "selected" : ""}>${label}</option>`).join("");

  return `
    <section class="detail-section feedback-section">
      <h3>Tu decisión</h3>
      ${existing}
      <form id="feedbackForm" class="feedback-form" data-job-id="${detail.id}">
        <fieldset>
          <legend>Clasificación correcta</legend>
          <div class="feedback-choices">${classificationOptions}</div>
        </fieldset>
        <label>
          <span>Motivo</span>
          <select name="reason_code" required>${reasonOptions}</select>
        </label>
        <label>
          <span>Nota opcional</span>
          <textarea name="comment" maxlength="2000" rows="3" placeholder="Qué interpretó mal Job Radar">${escapeHtml(currentComment)}</textarea>
        </label>
        <div class="feedback-actions">
          <button type="submit" class="primary">Guardar corrección</button>
          <span id="feedbackStatus" role="status" aria-live="polite"></span>
        </div>
      </form>
    </section>`;
}

function renderDetail(detail) {
  const latestPosting = detail.postings[0];
  const sourceLink = latestPosting?.url
    ? `<a class="primary detail-link" href="${escapeHtml(latestPosting.url)}" target="_blank" rel="noreferrer">Abrir oferta</a>`
    : "";
  const meta = [
    detail.location,
    detail.work_mode !== "UNKNOWN" ? detail.work_mode : null,
    detail.employment_type,
    latestPosting?.salary_text,
  ].filter(Boolean).map(escapeHtml).join(" · ");

  detailPanel.innerHTML = `
    <button class="detail-close" id="detailClose" aria-label="Cerrar detalle">×</button>
    <div class="detail-header">
      <p class="eyebrow">Oportunidad</p>
      <h2>${escapeHtml(detail.title)}</h2>
      <p class="detail-company">${escapeHtml(detail.company || "Empresa no indicada")}</p>
      <p class="detail-meta">${meta || "Información parcial"}</p>
      <div class="detail-actions">${sourceLink}</div>
    </div>
    ${renderAnalysis(detail.latest_analysis)}
    ${renderFeedback(detail)}
    <section class="detail-section">
      <h3>Descripción</h3>
      <p class="description-text">${escapeHtml(detail.description || "La fuente todavía no proporcionó una descripción completa.")}</p>
    </section>
    <section class="detail-section">
      <h3>Fuentes</h3>
      <div class="source-list">
        ${detail.postings.length ? detail.postings.map((posting) => `
          <div>
            <strong>${escapeHtml(posting.source || "Fuente")}</strong>
            <span>Vista ${formatDate(posting.last_seen_at)}</span>
            ${posting.url ? `<a href="${escapeHtml(posting.url)}" target="_blank" rel="noreferrer">Abrir</a>` : ""}
          </div>`).join("") : "<p>Sin publicaciones asociadas.</p>"}
      </div>
    </section>`;

  document.getElementById("detailClose").addEventListener("click", closeDetail);
  const feedbackForm = document.getElementById("feedbackForm");
  if (feedbackForm) feedbackForm.addEventListener("submit", submitFeedback);
  detailPanel.classList.add("open");
}

function closeDetail() {
  detailPanel.classList.remove("open");
  detailPanel.innerHTML = `
    <button class="detail-close" id="detailClose" aria-label="Cerrar detalle">×</button>
    <div class="detail-empty">
      <span>Selecciona una oportunidad</span>
      <p>El análisis, las brechas y las fuentes aparecerán aquí sin sacarte de Radar.</p>
    </div>`;
  document.getElementById("detailClose").addEventListener("click", closeDetail);
}

async function submitFeedback(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const jobId = form.dataset.jobId;
  const formData = new FormData(form);
  const status = document.getElementById("feedbackStatus");
  const submit = form.querySelector("button[type='submit']");
  const payload = {
    human_classification: formData.get("human_classification"),
    reason_code: formData.get("reason_code"),
    comment: String(formData.get("comment") || "").trim() || null,
  };

  submit.disabled = true;
  status.textContent = "Guardando…";
  status.classList.remove("error");
  try {
    await api(`/api/v1/radar/jobs/${jobId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    status.textContent = "Guardado";
    await Promise.all([loadRadarSummary(), loadRadarJobs()]);
    await loadJobDetail(jobId);
  } catch (error) {
    status.textContent = error.message;
    status.classList.add("error");
    submit.disabled = false;
  }
}

async function loadRadarSummary() {
  const summary = await api("/api/v1/radar/summary");
  renderSummary(summary);
  if (initialRadarLoad && summary.high === 0 && summary.review > 0) {
    setRadarFilter("review", { reload: false });
  }
  initialRadarLoad = false;
}

async function loadRadarJobs() {
  opportunityList.innerHTML = `<div class="list-loading">Cargando oportunidades…</div>`;
  const params = new URLSearchParams({ view: radarFilter, limit: "100" });
  const search = opportunitySearch.value.trim();
  if (search) params.set("q", search);
  try {
    const result = await api(`/api/v1/radar/jobs?${params}`);
    renderJobs(result.items);
  } catch (error) {
    opportunityList.innerHTML = `
      <div class="empty-state error-state">
        <h2>No se pudo cargar Radar</h2>
        <p>${escapeHtml(error.message)}</p>
      </div>`;
  }
}

async function loadJobDetail(jobId) {
  detailPanel.classList.add("open");
  detailPanel.innerHTML = `<div class="detail-loading">Cargando detalle…</div>`;
  try {
    renderDetail(await api(`/api/v1/radar/jobs/${jobId}`));
  } catch (error) {
    detailPanel.innerHTML = `<div class="detail-empty"><span>No se pudo abrir</span><p>${escapeHtml(error.message)}</p></div>`;
  }
}

async function loadRadar() {
  try {
    await loadRadarSummary();
    await loadRadarJobs();
  } catch (error) {
    opportunityList.innerHTML = `<div class="empty-state error-state"><h2>Radar no disponible</h2><p>${escapeHtml(error.message)}</p></div>`;
  }
}

document.querySelectorAll("[data-radar-filter]").forEach((control) => {
  control.addEventListener("click", () => setRadarFilter(control.dataset.radarFilter));
});

document.getElementById("mobileNav").addEventListener("click", () => {
  sidebar.classList.toggle("open");
});

document.getElementById("detailClose").addEventListener("click", closeDetail);

document.getElementById("focusSearch").addEventListener("click", () => {
  window.location.hash = "#/radar";
  opportunitySearch.focus();
});

opportunitySearch.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadRadarJobs, 250);
});

window.addEventListener("hashchange", renderRoute);

if (!window.location.hash) {
  window.location.hash = "#/radar";
} else {
  renderRoute();
}
