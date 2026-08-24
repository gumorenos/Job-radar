const applicationStageLabels = {
  TO_APPLY: "Para postular",
  APPLIED: "Postulada",
  INTERVIEW: "Entrevista",
  OFFER: "Oferta",
  CLOSED: "Cerrada",
};

const applicationPageSize = 50;
let applicationStage = "TO_APPLY";
let applicationSearchTimer = null;
let applicationListRequestId = 0;
let applicationLoadedItems = [];
let applicationTotal = 0;
const applicationsList = document.getElementById("applicationsList");
const applicationStageGrid = document.querySelector(".application-stages");
const applicationSearchToolbar = document.createElement("div");
applicationSearchToolbar.className = "application-search-toolbar";
applicationSearchToolbar.innerHTML = `
  <label class="application-search-field">
    <span>Buscar en postulaciones</span>
    <input
      id="applicationSearch"
      type="search"
      maxlength="200"
      placeholder="Puesto, empresa, ubicación o notas"
      autocomplete="off"
    >
  </label>
  <span class="application-search-meta" id="applicationSearchMeta" aria-live="polite"></span>`;
applicationStageGrid.insertAdjacentElement("afterend", applicationSearchToolbar);
const applicationSearch = document.getElementById("applicationSearch");
const applicationSearchMeta = document.getElementById("applicationSearchMeta");

async function applicationRequest(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload.detail) message = payload.detail;
    } catch (_) {
      // Keep the HTTP status when no JSON body is available.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function resetApplicationPaging() {
  applicationLoadedItems = [];
  applicationTotal = 0;
}

function setApplicationStage(stage, { reload = true } = {}) {
  applicationStage = stage;
  resetApplicationPaging();
  document.querySelectorAll("[data-application-stage]").forEach((button) => {
    button.classList.toggle("active", button.dataset.applicationStage === stage);
  });
  if (reload) loadApplications();
}

function renderApplicationSummary(summary) {
  Object.entries(summary).forEach(([key, value]) => {
    const element = document.querySelector(`[data-application-count="${key}"]`);
    if (element) element.textContent = value;
  });
}

function notesStateLabel(notes) {
  return notes ? "Con notas" : "Sin notas";
}

function applicationRows(items) {
  return items.map((item) => `
    <article class="application-row" data-application-id="${item.id}">
      <div class="application-row-main">
        <div class="application-copy">
          <button
            type="button"
            class="application-job-link"
            data-job-link="${item.job_id}"
            aria-label="Abrir ${escapeHtml(item.title)} en Radar"
          >${escapeHtml(item.title)}</button>
          <span>${escapeHtml(item.company || "Empresa no indicada")}</span>
          <small>${escapeHtml(item.location || "Ubicación no indicada")}${item.applied_at ? ` · Postulada ${formatDate(item.applied_at)}` : ""}</small>
        </div>
        <label class="application-stage-control">
          <span>Etapa</span>
          <select data-stage-select="${item.id}" aria-label="Etapa de ${escapeHtml(item.title)}">
            ${Object.entries(applicationStageLabels).map(([value, label]) => `
              <option value="${value}" ${value === item.stage ? "selected" : ""}>${label}</option>`).join("")}
          </select>
        </label>
      </div>
      <details class="application-notes-panel">
        <summary>
          Notas de seguimiento
          <span data-notes-state="${item.id}">${notesStateLabel(item.notes)}</span>
        </summary>
        <label class="application-notes-field">
          <span>Notas</span>
          <textarea
            data-notes-input="${item.id}"
            maxlength="5000"
            rows="4"
            placeholder="Ej. contacto, siguiente paso, feedback de entrevista…"
          >${escapeHtml(item.notes || "")}</textarea>
        </label>
        <div class="application-notes-actions">
          <span class="application-notes-status" data-notes-status="${item.id}" role="status"></span>
          <button type="button" class="secondary" data-save-notes="${item.id}">Guardar notas</button>
        </div>
      </details>
    </article>`).join("");
}

function bindApplicationRows() {
  document.querySelectorAll("[data-stage-select]").forEach((select) => {
    select.addEventListener("change", () => {
      updateApplicationStage(select.dataset.stageSelect, select.value, select);
    });
  });
  document.querySelectorAll("[data-save-notes]").forEach((button) => {
    button.addEventListener("click", () => saveApplicationNotes(button.dataset.saveNotes, button));
  });
  document.querySelectorAll("[data-job-link]").forEach((button) => {
    button.addEventListener("click", () => openApplicationInRadar(button.dataset.jobLink));
  });
  const loadMore = document.getElementById("applicationLoadMore");
  if (loadMore) {
    loadMore.addEventListener("click", () => loadApplicationList({ append: true }));
  }
}

function renderApplications(items, total) {
  if (!items.length) {
    const search = applicationSearch.value.trim();
    applicationsList.innerHTML = `
      <div class="empty-state panel-empty">
        <h3>${search ? "Sin resultados" : `Sin ${escapeHtml(applicationStageLabels[applicationStage].toLowerCase())}`}</h3>
        <p>${search
          ? `No hay postulaciones en esta etapa que coincidan con “${escapeHtml(search)}”.`
          : "Las oportunidades que decidas perseguir desde Radar aparecerán aquí."}</p>
      </div>`;
    return;
  }

  const remaining = Math.max(0, total - items.length);
  const loadMore = remaining
    ? `<div class="application-load-more">
        <span>Mostrando ${items.length} de ${total}</span>
        <button type="button" class="secondary" id="applicationLoadMore">
          Cargar más · ${Math.min(applicationPageSize, remaining)}
        </button>
      </div>`
    : "";

  applicationsList.innerHTML = `
    <div class="application-table">${applicationRows(items)}</div>
    ${loadMore}`;
  bindApplicationRows();
}

async function loadApplicationSummary() {
  renderApplicationSummary(await applicationRequest("/api/v1/applications/summary"));
}

async function loadApplicationList({ append = false } = {}) {
  const requestId = ++applicationListRequestId;
  const offset = append ? applicationLoadedItems.length : 0;
  if (!append) {
    resetApplicationPaging();
    applicationsList.innerHTML = `<div class="applications-loading">Cargando postulaciones…</div>`;
  } else {
    const button = document.getElementById("applicationLoadMore");
    if (button) {
      button.disabled = true;
      button.textContent = "Cargando…";
    }
  }

  const params = new URLSearchParams({
    stage: applicationStage,
    limit: String(applicationPageSize),
    offset: String(offset),
  });
  const search = applicationSearch.value.trim();
  if (search) params.set("q", search);

  try {
    const result = await applicationRequest(`/api/v1/applications?${params}`);
    if (requestId !== applicationListRequestId) return;

    applicationLoadedItems = append
      ? [...applicationLoadedItems, ...result.items]
      : result.items;
    applicationTotal = result.total;
    applicationSearchMeta.textContent = search
      ? `${result.total} ${result.total === 1 ? "resultado" : "resultados"}`
      : (applicationLoadedItems.length < result.total
        ? `${applicationLoadedItems.length} de ${result.total}`
        : "");
    renderApplications(applicationLoadedItems, applicationTotal);
  } catch (error) {
    if (requestId !== applicationListRequestId) return;
    applicationSearchMeta.textContent = "";
    applicationsList.innerHTML = `
      <div class="empty-state panel-empty error-state">
        <h3>No se pudieron cargar las postulaciones</h3>
        <p>${escapeHtml(error.message)}</p>
      </div>`;
  }
}

async function loadApplications() {
  if (currentRoute() !== "applications") return;
  await Promise.all([loadApplicationSummary(), loadApplicationList()]);
}

async function updateApplicationStage(applicationId, stage, select) {
  select.disabled = true;
  try {
    await applicationRequest(`/api/v1/applications/${applicationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage }),
    });
    resetApplicationPaging();
    await Promise.all([loadApplicationSummary(), loadApplicationList()]);
  } catch (error) {
    select.disabled = false;
    window.alert(`No se pudo actualizar la etapa: ${error.message}`);
  }
}

async function saveApplicationNotes(applicationId, button) {
  const input = document.querySelector(`[data-notes-input="${applicationId}"]`);
  const status = document.querySelector(`[data-notes-status="${applicationId}"]`);
  const state = document.querySelector(`[data-notes-state="${applicationId}"]`);
  if (!input || !status || !state) return;

  button.disabled = true;
  status.classList.remove("error");
  status.textContent = "Guardando…";
  try {
    const updated = await applicationRequest(`/api/v1/applications/${applicationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: input.value }),
    });
    input.value = updated.notes || "";
    state.textContent = notesStateLabel(updated.notes);
    status.textContent = "Notas guardadas.";
  } catch (error) {
    status.classList.add("error");
    status.textContent = `No se pudo guardar: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

function openApplicationInRadar(jobId) {
  if (!jobId) return;
  window.location.hash = "#/radar";
  window.setTimeout(() => loadJobDetail(jobId), 0);
}

async function syncRadarApplicationAction() {
  const form = detailPanel.querySelector("#feedbackForm");
  const actions = detailPanel.querySelector(".detail-actions");
  if (!form || !actions || actions.querySelector("[data-application-action]")) return;

  const jobId = form.dataset.jobId;
  if (!jobId) return;

  let existing = null;
  try {
    existing = await applicationRequest(`/api/v1/applications/by-job/${jobId}`);
  } catch (error) {
    if (error.status !== 404) return;
  }

  const button = document.createElement("button");
  button.type = "button";
  button.dataset.applicationAction = jobId;
  button.className = existing ? "secondary" : "primary";
  button.textContent = existing
    ? `En Postulaciones · ${applicationStageLabels[existing.stage]}`
    : "Añadir a postulaciones";

  button.addEventListener("click", async () => {
    if (existing) {
      setApplicationStage(existing.stage, { reload: false });
      window.location.hash = "#/applications";
      return;
    }

    button.disabled = true;
    button.textContent = "Añadiendo…";
    try {
      const result = await applicationRequest(`/api/v1/applications/jobs/${jobId}`, {
        method: "POST",
      });
      existing = result.application;
      button.disabled = false;
      button.className = "secondary";
      button.textContent = `En Postulaciones · ${applicationStageLabels[existing.stage]}`;
    } catch (error) {
      button.disabled = false;
      button.textContent = "No se pudo añadir";
      button.title = error.message;
    }
  });

  actions.appendChild(button);
}

document.querySelectorAll("[data-application-stage]").forEach((button) => {
  button.addEventListener("click", () => setApplicationStage(button.dataset.applicationStage));
});

applicationSearch.addEventListener("input", () => {
  clearTimeout(applicationSearchTimer);
  resetApplicationPaging();
  applicationSearchTimer = setTimeout(loadApplicationList, 250);
});
applicationSearch.addEventListener("search", () => {
  clearTimeout(applicationSearchTimer);
  resetApplicationPaging();
  loadApplicationList();
});

const applicationDetailObserver = new MutationObserver(() => {
  syncRadarApplicationAction();
});
applicationDetailObserver.observe(detailPanel, { childList: true, subtree: true });

window.addEventListener("hashchange", () => {
  if (currentRoute() === "applications") loadApplications();
});

if (currentRoute() === "applications") loadApplications();
