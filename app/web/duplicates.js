const duplicateCandidates = new Map();
const duplicatePageSize = 50;
const baseLoadRadarJobs = loadRadarJobs;
let duplicatePageItems = [];
let duplicatePageTotal = 0;
let duplicatePageContext = "";
let duplicatePageRequestId = 0;

function duplicatePercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${Math.round(number * 100)}%`;
}

function duplicateMeta(job) {
  return [
    job.location,
    job.work_mode !== "UNKNOWN" ? job.work_mode : null,
    job.salary_text,
  ].filter(Boolean).map(escapeHtml).join(" · ");
}

function renderDuplicateCandidates(items) {
  duplicateCandidates.clear();
  items.forEach((item) => duplicateCandidates.set(item.id, item));

  if (!items.length) {
    const search = opportunitySearch.value.trim();
    opportunityList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">≋</div>
        <h2>${search ? "Sin duplicados que coincidan" : "Sin posibles duplicados"}</h2>
        <p>${search
          ? `No hay pares pendientes que coincidan con “${escapeHtml(search)}”.`
          : "No hay pares dudosos pendientes de decisión humana."}</p>
      </div>`;
    return;
  }

  opportunityList.innerHTML = items.map((item) => `
    <button class="duplicate-row" data-duplicate-id="${item.id}">
      <div class="duplicate-copy">
        <strong>${escapeHtml(item.job_a.title)} ↔ ${escapeHtml(item.job_b.title)}</strong>
        <span>${escapeHtml(item.job_a.company || item.job_b.company || "Empresa no indicada")}</span>
        <small>${escapeHtml(item.job_a.location || "Ubicación A no indicada")} · ${escapeHtml(item.job_b.location || "Ubicación B no indicada")}</small>
      </div>
      <span class="duplicate-confidence">${duplicatePercent(item.confidence)} similitud</span>
    </button>`).join("");

  document.querySelectorAll("[data-duplicate-id]").forEach((row) => {
    row.addEventListener("click", () => {
      const candidate = duplicateCandidates.get(row.dataset.duplicateId);
      if (candidate) renderDuplicateDetail(candidate);
    });
  });
}

function duplicateJobCard(job, label) {
  return `
    <article class="duplicate-job-card">
      <p class="eyebrow">${escapeHtml(label)}</p>
      <h3>${escapeHtml(job.title)}</h3>
      <p class="duplicate-company">${escapeHtml(job.company || "Empresa no indicada")}</p>
      <p class="duplicate-meta">${duplicateMeta(job) || "Información parcial"}</p>
      <p class="duplicate-description">${escapeHtml(job.description || "Sin descripción completa.")}</p>
    </article>`;
}

function duplicateReasonText(candidate) {
  const title = duplicatePercent(candidate.reasons?.title_similarity);
  const company = duplicatePercent(candidate.reasons?.company_similarity);
  const location = duplicatePercent(candidate.reasons?.location_similarity);
  return `Título ${title} · Empresa ${company} · Ubicación ${location}`;
}

function renderDuplicateDetail(candidate) {
  detailPanel.classList.add("open");
  detailPanel.innerHTML = `
    <button class="detail-close" id="detailClose" aria-label="Cerrar detalle">×</button>
    <div class="detail-header">
      <p class="eyebrow">Posible duplicado</p>
      <h2>${duplicatePercent(candidate.confidence)} de similitud</h2>
      <p class="detail-meta">Compara ambos registros antes de decidir. Unir consolida las fuentes; mantener separadas conserva ambos jobs.</p>
    </div>
    <section class="detail-section duplicate-compare">
      ${duplicateJobCard(candidate.job_a, "Registro A")}
      ${duplicateJobCard(candidate.job_b, "Registro B")}
      <p class="duplicate-reasons">${escapeHtml(duplicateReasonText(candidate))}</p>
    </section>
    <section class="detail-section">
      <h3>Decisión</h3>
      <p class="detail-muted">Si eliges Unir, Job Radar conservará como principal el registro más antiguo y mantendrá el historial de análisis como auditoría.</p>
      <div class="duplicate-actions">
        <button type="button" class="primary" data-duplicate-decision="MERGE">Unir</button>
        <button type="button" class="secondary" data-duplicate-decision="KEEP_SEPARATE">Mantener separadas</button>
      </div>
      <div class="duplicate-status" id="duplicateStatus" role="status" aria-live="polite"></div>
    </section>`;

  document.getElementById("detailClose").addEventListener("click", closeDetail);
  detailPanel.querySelectorAll("[data-duplicate-decision]").forEach((button) => {
    button.addEventListener("click", () => {
      resolveDuplicateCandidate(candidate.id, button.dataset.duplicateDecision);
    });
  });
}

async function resolveDuplicateCandidate(candidateId, decision) {
  const status = document.getElementById("duplicateStatus");
  const buttons = detailPanel.querySelectorAll("[data-duplicate-decision]");
  buttons.forEach((button) => { button.disabled = true; });
  if (status) {
    status.classList.remove("error");
    status.textContent = decision === "MERGE" ? "Uniendo registros…" : "Guardando decisión…";
  }

  try {
    await api(`/api/v1/radar/duplicates/${candidateId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    await Promise.all([loadRadarSummary(), loadDuplicateCandidates()]);
    closeDetail();
  } catch (error) {
    if (status) {
      status.classList.add("error");
      status.textContent = error.message;
    }
    buttons.forEach((button) => { button.disabled = false; });
  }
}

function duplicatePagingContext() {
  return opportunitySearch.value.trim();
}

function resetDuplicatePaging() {
  duplicatePageItems = [];
  duplicatePageTotal = 0;
  duplicatePageContext = duplicatePagingContext();
}

function cancelDuplicatePaging() {
  duplicatePageRequestId += 1;
  duplicatePageItems = [];
  duplicatePageTotal = 0;
  duplicatePageContext = "";
}

function bindDuplicateLoadMore() {
  const button = document.getElementById("duplicateLoadMore");
  if (button) {
    button.addEventListener("click", () => loadDuplicateCandidates({ append: true }));
  }
}

function renderDuplicatePage() {
  renderDuplicateCandidates(duplicatePageItems);
  const remaining = Math.max(0, duplicatePageTotal - duplicatePageItems.length);
  if (!remaining) return;

  opportunityList.insertAdjacentHTML("beforeend", `
    <div class="radar-load-more">
      <span>Mostrando ${duplicatePageItems.length} de ${duplicatePageTotal}</span>
      <button type="button" class="secondary" id="duplicateLoadMore">
        Cargar más · ${Math.min(duplicatePageSize, remaining)}
      </button>
    </div>`);
  bindDuplicateLoadMore();
}

async function loadDuplicateCandidates({ append = false } = {}) {
  const context = duplicatePagingContext();
  if (!append || context !== duplicatePageContext) resetDuplicatePaging();

  const requestId = ++duplicatePageRequestId;
  const offset = append ? duplicatePageItems.length : 0;
  if (!append) {
    opportunityList.innerHTML = `<div class="list-loading">Buscando posibles duplicados…</div>`;
  } else {
    const button = document.getElementById("duplicateLoadMore");
    if (button) {
      button.disabled = true;
      button.textContent = "Cargando…";
    }
  }

  const params = new URLSearchParams({
    status: "PENDING",
    limit: String(duplicatePageSize),
    offset: String(offset),
  });
  const search = opportunitySearch.value.trim();
  if (search) params.set("q", search);

  try {
    const result = await api(`/api/v1/radar/duplicates?${params}`);
    if (requestId !== duplicatePageRequestId || context !== duplicatePagingContext()) return;
    duplicatePageItems = append ? [...duplicatePageItems, ...result.items] : result.items;
    duplicatePageTotal = result.total;
    renderDuplicatePage();
  } catch (error) {
    if (requestId !== duplicatePageRequestId) return;
    opportunityList.innerHTML = `
      <div class="empty-state error-state">
        <h2>No se pudieron cargar los duplicados</h2>
        <p>${escapeHtml(error.message)}</p>
      </div>`;
  }
}

loadRadarJobs = async function loadRadarJobsWithDuplicates(options = {}) {
  if (radarFilter === "duplicates") {
    cancelRadarPaging();
    await loadDuplicateCandidates(options);
    return;
  }
  cancelDuplicatePaging();
  await baseLoadRadarJobs(options);
};

opportunitySearch.addEventListener("input", () => {
  duplicatePageRequestId += 1;
  duplicatePageContext = "";
});
