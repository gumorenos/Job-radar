const applicationStageLabels = {
  TO_APPLY: "Para postular",
  APPLIED: "Postulada",
  INTERVIEW: "Entrevista",
  OFFER: "Oferta",
  CLOSED: "Cerrada",
};

const applicationEventLabels = {
  CREATED: "Añadida a postulaciones",
  STAGE_CHANGED: "Etapa actualizada",
  PLAN_UPDATED: "Siguiente paso actualizado",
  FOLLOW_UP_COMPLETED: "Seguimiento registrado",
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
      placeholder="Puesto, empresa, ubicación, notas o siguiente paso"
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

function applicationDueState(value) {
  if (!value) return { label: "Sin fecha", className: "" };
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { label: "Fecha inválida", className: "" };
  const today = new Date();
  const overdue = date.getTime() < today.getTime();
  const label = new Intl.DateTimeFormat("es-PE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
  return {
    label: overdue ? `Vencido · ${label}` : `Vence ${label}`,
    className: overdue ? "overdue" : "",
  };
}

function toLocalDateTimeInput(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - (date.getTimezoneOffset() * 60000));
  return local.toISOString().slice(0, 16);
}

function fromLocalDateTimeInput(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function applicationPlanMarkup(item) {
  if (!item.next_action && !item.next_action_due_at && !item.last_follow_up_at) return "";
  const due = applicationDueState(item.next_action_due_at);
  return `
    <div class="application-plan ${due.className}">
      <div>
        <span>Siguiente paso</span>
        <strong>${escapeHtml(item.next_action || "Sin acción definida")}</strong>
      </div>
      <small>${escapeHtml(due.label)}${item.last_follow_up_at ? ` · Último seguimiento ${formatDate(item.last_follow_up_at)}` : ""}</small>
    </div>`;
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
      ${applicationPlanMarkup(item)}
      <details class="application-followup-panel" data-plan-panel="${item.id}">
        <summary>
          Siguiente paso y seguimiento
          <span>${item.stage === "APPLIED" && item.follow_up_due_at ? applicationDueState(item.follow_up_due_at).label : "Planificar"}</span>
        </summary>
        <div class="application-plan-fields">
          <label>
            <span>Siguiente acción</span>
            <input data-next-action="${item.id}" maxlength="500" value="${escapeHtml(item.next_action || "")}" placeholder="Ej. escribir al recruiter">
          </label>
          <label>
            <span>Fecha objetivo</span>
            <input data-next-action-due="${item.id}" type="datetime-local" value="${escapeHtml(toLocalDateTimeInput(item.next_action_due_at))}">
          </label>
        </div>
        <div class="application-plan-actions">
          <span class="application-plan-status" data-plan-status="${item.id}" role="status"></span>
          ${item.stage === "APPLIED" ? `<button type="button" class="secondary" data-follow-up-complete="${item.id}">Seguimiento hecho</button>` : ""}
          <button type="button" class="secondary" data-load-timeline="${item.id}">Ver historial</button>
          <button type="button" class="primary" data-save-plan="${item.id}">Guardar siguiente paso</button>
        </div>
        <div class="application-timeline" data-timeline="${item.id}"></div>
      </details>
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
  document.querySelectorAll("[data-save-plan]").forEach((button) => {
    button.addEventListener("click", () => saveApplicationPlan(button.dataset.savePlan, button));
  });
  document.querySelectorAll("[data-follow-up-complete]").forEach((button) => {
    button.addEventListener("click", () => markApplicationFollowUp(button.dataset.followUpComplete, button));
  });
  document.querySelectorAll("[data-load-timeline]").forEach((button) => {
    button.addEventListener("click", () => loadApplicationTimeline(button.dataset.loadTimeline, button));
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

async function saveApplicationPlan(applicationId, button) {
  const action = document.querySelector(`[data-next-action="${applicationId}"]`);
  const due = document.querySelector(`[data-next-action-due="${applicationId}"]`);
  const status = document.querySelector(`[data-plan-status="${applicationId}"]`);
  const row = applicationLoadedItems.find((item) => item.id === applicationId);
  if (!action || !due || !status || !row) return;

  const dueAt = fromLocalDateTimeInput(due.value);
  const payload = {
    next_action: action.value.trim() || null,
    next_action_due_at: dueAt,
  };
  if (row.stage === "APPLIED") payload.follow_up_due_at = dueAt;

  button.disabled = true;
  status.classList.remove("error");
  status.textContent = "Guardando…";
  try {
    await applicationRequest(`/api/v1/applications/${applicationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    resetApplicationPaging();
    await loadApplicationList();
  } catch (error) {
    button.disabled = false;
    status.classList.add("error");
    status.textContent = `No se pudo guardar: ${error.message}`;
  }
}

async function markApplicationFollowUp(applicationId, button) {
  const status = document.querySelector(`[data-plan-status="${applicationId}"]`);
  button.disabled = true;
  if (status) {
    status.classList.remove("error");
    status.textContent = "Registrando…";
  }
  try {
    await applicationRequest(`/api/v1/applications/${applicationId}/follow-up-complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ next_follow_up_days: 7 }),
    });
    resetApplicationPaging();
    await loadApplicationList();
  } catch (error) {
    button.disabled = false;
    if (status) {
      status.classList.add("error");
      status.textContent = `No se pudo registrar: ${error.message}`;
    }
  }
}

async function loadApplicationTimeline(applicationId, button) {
  const target = document.querySelector(`[data-timeline="${applicationId}"]`);
  if (!target) return;
  button.disabled = true;
  target.innerHTML = `<span class="application-timeline-loading">Cargando historial…</span>`;
  try {
    const result = await applicationRequest(`/api/v1/applications/${applicationId}/timeline`);
    target.innerHTML = result.items.length
      ? `<ol>${result.items.map((event) => `
          <li>
            <strong>${escapeHtml(applicationEventLabels[event.event_type] || event.event_type)}</strong>
            <span>${escapeHtml(event.note || "")}</span>
            <small>${formatDate(event.occurred_at)}${event.from_stage || event.to_stage
              ? ` · ${escapeHtml(event.from_stage ? applicationStageLabels[event.from_stage] || event.from_stage : "Inicio")} → ${escapeHtml(event.to_stage ? applicationStageLabels[event.to_stage] || event.to_stage : "—")}`
              : ""}</small>
          </li>`).join("")}</ol>`
      : `<span class="application-timeline-loading">Sin eventos todavía.</span>`;
    button.textContent = "Historial actualizado";
  } catch (error) {
    target.innerHTML = `<span class="application-timeline-error">${escapeHtml(error.message)}</span>`;
    button.disabled = false;
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

function cockpitMarkup(application) {
  if (!application) {
    return `
      <section class="opportunity-cockpit">
        <div>
          <span class="cockpit-eyebrow">Tu proceso</span>
          <strong>No está en Postulaciones</strong>
        </div>
        <p>Si decides perseguir esta oportunidad, añádela para gestionar siguiente paso, fechas e historial.</p>
      </section>`;
  }
  const due = applicationDueState(application.next_action_due_at);
  return `
    <section class="opportunity-cockpit ${due.className}" data-application-cockpit="${application.id}">
      <div class="cockpit-heading">
        <div>
          <span class="cockpit-eyebrow">Tu proceso · ${escapeHtml(applicationStageLabels[application.stage])}</span>
          <strong>${escapeHtml(application.next_action || "Sin siguiente paso")}</strong>
        </div>
        <small>${escapeHtml(due.label)}</small>
      </div>
      ${application.last_follow_up_at ? `<p>Último seguimiento ${formatDate(application.last_follow_up_at)}.</p>` : ""}
      <div class="cockpit-actions">
        <button type="button" class="secondary" data-cockpit-manage="${application.stage}">Gestionar postulación</button>
        ${application.stage === "APPLIED" ? `<button type="button" class="primary" data-cockpit-follow-up="${application.id}">Seguimiento hecho</button>` : ""}
      </div>
    </section>`;
}

async function syncRadarApplicationAction() {
  const actions = detailPanel.querySelector(".detail-actions");
  const header = detailPanel.querySelector(".detail-header");
  if (!actions || !header) return;
  const jobId = detailPanel.dataset.jobId || detailPanel.querySelector("#feedbackForm")?.dataset.jobId;
  if (!jobId) return;
  const alreadySynchronized = detailPanel.dataset.applicationSyncJobId === jobId
    && actions.querySelector("[data-application-action]")
    && detailPanel.querySelector(".opportunity-cockpit");
  if (alreadySynchronized) return;
  detailPanel.dataset.applicationSyncJobId = jobId;

  let existing = null;
  try {
    existing = await applicationRequest(`/api/v1/applications/by-job/${jobId}`);
  } catch (error) {
    detailPanel.dataset.applicationSyncJobId = "";
    if (error.status !== 404) return;
  }

  detailPanel.querySelector(".opportunity-cockpit")?.remove();
  header.insertAdjacentHTML("afterend", cockpitMarkup(existing));

  const existingAction = actions.querySelector("[data-application-action]");
  if (existingAction) existingAction.remove();
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
      detailPanel.dataset.applicationSyncJobId = "";
      await syncRadarApplicationAction();
    } catch (error) {
      button.disabled = false;
      button.textContent = "No se pudo añadir";
      button.title = error.message;
    }
  });
  actions.appendChild(button);

  const manage = detailPanel.querySelector("[data-cockpit-manage]");
  if (manage) {
    manage.addEventListener("click", () => {
      setApplicationStage(manage.dataset.cockpitManage, { reload: false });
      window.location.hash = "#/applications";
    });
  }
  const followUp = detailPanel.querySelector("[data-cockpit-follow-up]");
  if (followUp) {
    followUp.addEventListener("click", async () => {
      followUp.disabled = true;
      followUp.textContent = "Registrando…";
      try {
        existing = await applicationRequest(
          `/api/v1/applications/${followUp.dataset.cockpitFollowUp}/follow-up-complete`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ next_follow_up_days: 7 }),
          },
        );
        detailPanel.dataset.applicationSyncJobId = "";
        await syncRadarApplicationAction();
      } catch (error) {
        followUp.disabled = false;
        followUp.textContent = "No se pudo registrar";
        followUp.title = error.message;
      }
    });
  }
}

const baseLoadJobDetail = loadJobDetail;
loadJobDetail = async function loadJobDetailWithApplicationContext(jobId) {
  detailPanel.dataset.jobId = jobId;
  detailPanel.dataset.applicationSyncJobId = "";
  return baseLoadJobDetail(jobId);
};

document.querySelectorAll("[data-application-stage]").forEach((button) => {
  button.addEventListener("click", () => setApplicationStage(button.dataset.applicationStage));
});

applicationSearch.addEventListener("input", () => {
  clearTimeout(applicationSearchTimer);
  applicationListRequestId += 1;
  resetApplicationPaging();
  applicationSearchTimer = setTimeout(loadApplicationList, 250);
});
applicationSearch.addEventListener("search", () => {
  clearTimeout(applicationSearchTimer);
  applicationListRequestId += 1;
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
