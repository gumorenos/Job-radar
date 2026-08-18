const cvGrid = document.getElementById("cvGrid");
const cvStatus = document.getElementById("cvStatus");
const addCvButton = document.getElementById("addCvButton");
const cvDialog = document.getElementById("cvDialog");
const cvForm = document.getElementById("cvForm");
const closeCvDialog = document.getElementById("closeCvDialog");
const cancelCvDialog = document.getElementById("cancelCvDialog");
const saveCvButton = document.getElementById("saveCvButton");
const cvDialogTitle = document.getElementById("cvDialogTitle");
const cvParentId = document.getElementById("cvParentId");
const cvName = document.getElementById("cvName");
const cvTargetRole = document.getElementById("cvTargetRole");
const cvTargetArea = document.getElementById("cvTargetArea");
const cvContent = document.getElementById("cvContent");
const cvIsBase = document.getElementById("cvIsBase");
const cvActivate = document.getElementById("cvActivate");

let cvItems = new Map();

function cvRouteActive() {
  return window.location.hash.replace(/^#\//, "").split("/")[0] === "cvs";
}

function cvEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function cvDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-PE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

async function cvApi(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload.detail) message = payload.detail;
    } catch (_) {
      // Keep HTTP status when there is no JSON body.
    }
    throw new Error(message);
  }
  return response.json();
}

function cvApprovalLabel(item) {
  if (item.approval_status === "DRAFT") return "Borrador";
  if (item.approval_status === "REJECTED") return "Rechazado";
  return "Aprobado";
}

function cvActions(item) {
  const actions = [];
  if (item.approval_status === "DRAFT") {
    actions.push(`<button class="primary" data-cv-action="approve" data-cv-id="${item.id}">Aprobar</button>`);
    actions.push(`<button class="secondary" data-cv-action="reject" data-cv-id="${item.id}">Rechazar</button>`);
  }
  if (item.approval_status === "APPROVED" && !item.is_active) {
    actions.push(`<button class="primary" data-cv-action="activate" data-cv-id="${item.id}">Usar este CV</button>`);
  }
  actions.push(`<button class="secondary" data-cv-action="version" data-cv-id="${item.id}">Nueva versión</button>`);
  return actions.join("");
}

function renderCvItems(items) {
  cvItems = new Map(items.map((item) => [item.id, item]));
  if (!items.length) {
    cvGrid.innerHTML = `
      <div class="empty-state panel-empty cv-empty">
        <div class="empty-icon">▤</div>
        <h3>Todavía no hay CVs</h3>
        <p>Añade tu CV base. Después podrás crear versiones especializadas sin sobrescribirlo.</p>
      </div>`;
    return;
  }

  cvGrid.innerHTML = items.map((item) => {
    const tags = [
      item.is_base ? '<span class="tag">Base</span>' : "",
      item.is_active ? '<span class="tag active-tag">Activo</span>' : "",
      `<span class="tag muted-tag">${cvEscape(cvApprovalLabel(item))}</span>`,
      item.generated_by_ai ? '<span class="tag ai-tag">IA</span>' : "",
    ].filter(Boolean).join("");
    const target = [item.target_role, item.target_area].filter(Boolean).map(cvEscape).join(" · ");
    const preview = item.content_text
      ? cvEscape(item.content_text.slice(0, 180))
      : "Sin contenido de texto guardado todavía.";

    return `
      <article class="cv-card ${item.is_active ? "active-cv" : ""}">
        <div class="cv-card-tags">${tags}</div>
        <div class="cv-card-title">
          <div>
            <h3>${cvEscape(item.name)}</h3>
            <small>Versión ${item.version} · ${cvEscape(cvDate(item.created_at))}</small>
          </div>
        </div>
        <p class="cv-target">${target || "Perfil general"}</p>
        <p class="cv-preview">${preview}</p>
        ${item.generated_by_ai && item.approval_status === "DRAFT" ? `
          <p class="cv-warning">Este borrador fue generado por IA y no puede activarse hasta que lo apruebes.</p>` : ""}
        <div class="cv-card-actions">${cvActions(item)}</div>
      </article>`;
  }).join("");
}

async function loadCvs() {
  if (!cvRouteActive()) return;
  cvStatus.textContent = "";
  cvGrid.innerHTML = '<div class="list-loading">Cargando CVs…</div>';
  try {
    const result = await cvApi("/api/v1/cvs");
    renderCvItems(result.items);
  } catch (error) {
    cvGrid.innerHTML = `
      <div class="empty-state error-state panel-empty">
        <h3>No se pudieron cargar los CVs</h3>
        <p>${cvEscape(error.message)}</p>
      </div>`;
  }
}

function resetCvForm() {
  cvForm.reset();
  cvParentId.value = "";
  cvDialogTitle.textContent = "Añadir CV";
  saveCvButton.textContent = "Guardar CV";
}

function openNewCvDialog(parent = null) {
  resetCvForm();
  if (parent) {
    cvDialogTitle.textContent = `Nueva versión de ${parent.name}`;
    saveCvButton.textContent = "Crear versión";
    cvParentId.value = parent.id;
    cvName.value = parent.name;
    cvTargetRole.value = parent.target_role || "";
    cvTargetArea.value = parent.target_area || "";
    cvContent.value = parent.content_text || "";
    cvIsBase.checked = parent.is_base;
  }
  cvDialog.showModal();
  cvName.focus();
}

function closeDialog() {
  cvDialog.close();
  resetCvForm();
}

async function saveCv(event) {
  event.preventDefault();
  const formData = new FormData(cvForm);
  const payload = {
    name: String(formData.get("name") || "").trim(),
    parent_cv_id: String(formData.get("parent_cv_id") || "").trim() || null,
    target_role: String(formData.get("target_role") || "").trim() || null,
    target_area: String(formData.get("target_area") || "").trim() || null,
    content_text: String(formData.get("content_text") || "").trim() || null,
    is_base: formData.get("is_base") === "on",
    activate: formData.get("activate") === "on",
    generated_by_ai: false,
  };

  saveCvButton.disabled = true;
  cvStatus.textContent = "Guardando CV…";
  cvStatus.classList.remove("error");
  try {
    await cvApi("/api/v1/cvs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    closeDialog();
    cvStatus.textContent = payload.parent_cv_id ? "Nueva versión guardada." : "CV guardado.";
    await loadCvs();
  } catch (error) {
    cvStatus.textContent = error.message;
    cvStatus.classList.add("error");
  } finally {
    saveCvButton.disabled = false;
  }
}

async function applyCvAction(action, item) {
  cvStatus.textContent = "Actualizando CV…";
  cvStatus.classList.remove("error");
  try {
    if (action === "version") {
      openNewCvDialog(item);
      cvStatus.textContent = "";
      return;
    }
    if (action === "activate") {
      await cvApi(`/api/v1/cvs/${item.id}/activate`, { method: "POST" });
      cvStatus.textContent = `${item.name} ahora es el CV activo.`;
    } else {
      const decision = action === "approve" ? "APPROVED" : "REJECTED";
      await cvApi(`/api/v1/cvs/${item.id}/approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: decision }),
      });
      cvStatus.textContent = decision === "APPROVED" ? "CV aprobado." : "CV rechazado.";
    }
    await loadCvs();
  } catch (error) {
    cvStatus.textContent = error.message;
    cvStatus.classList.add("error");
  }
}

cvGrid.addEventListener("click", (event) => {
  const button = event.target.closest("[data-cv-action]");
  if (!button) return;
  const item = cvItems.get(button.dataset.cvId);
  if (!item) return;
  applyCvAction(button.dataset.cvAction, item);
});

addCvButton.addEventListener("click", () => openNewCvDialog());
closeCvDialog.addEventListener("click", closeDialog);
cancelCvDialog.addEventListener("click", closeDialog);
cvForm.addEventListener("submit", saveCv);

cvDialog.addEventListener("click", (event) => {
  if (event.target === cvDialog) closeDialog();
});

window.addEventListener("hashchange", loadCvs);
if (cvRouteActive()) loadCvs();
