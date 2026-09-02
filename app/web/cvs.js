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
const cvFile = document.getElementById("cvFile");
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

function fileMediaType(file) {
  if (file.type) return file.type;
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".docx")) {
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  }
  if (lower.endsWith(".txt")) return "text/plain";
  return "application/octet-stream";
}

async function uploadCvFile(cvId, file) {
  if (file.size > 10 * 1024 * 1024) {
    throw new Error("El archivo supera el límite de 10 MB.");
  }
  return cvApi(`/api/v1/cvs/${cvId}/file?filename=${encodeURIComponent(file.name)}`, {
    method: "PUT",
    headers: { "Content-Type": fileMediaType(file) },
    body: file,
  });
}

function cvApprovalLabel(item) {
  if (item.approval_status === "DRAFT") return "Borrador";
  if (item.approval_status === "REJECTED") return "Rechazado";
  return "Aprobado";
}

function cvActions(item) {
  const actions = [];
  if (item.parent_cv_id) {
    actions.push(`<button class="secondary" data-cv-action="compare" data-cv-id="${item.id}">Comparar cambios</button>`);
  }
  if (item.approval_status === "DRAFT") {
    actions.push(`<button class="primary" data-cv-action="approve" data-cv-id="${item.id}">Aprobar</button>`);
    actions.push(`<button class="secondary" data-cv-action="reject" data-cv-id="${item.id}">Rechazar</button>`);
  }
  if (item.approval_status === "APPROVED" && !item.is_active) {
    actions.push(`<button class="primary" data-cv-action="activate" data-cv-id="${item.id}">Usar este CV</button>`);
  }
  if (item.has_file) {
    actions.push(`<a class="secondary cv-file-link" href="/api/v1/cvs/${item.id}/file">Descargar archivo</a>`);
  } else {
    actions.push(`<button class="secondary" data-cv-action="attach" data-cv-id="${item.id}">Adjuntar archivo</button>`);
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
      item.tailored_for_job_id ? '<span class="tag tailored-tag">Para vacante</span>' : "",
    ].filter(Boolean).join("");
    const target = [item.target_role, item.target_area].filter(Boolean).map(cvEscape).join(" · ");
    const preview = item.content_text
      ? cvEscape(item.content_text.slice(0, 180))
      : "Sin contenido de texto guardado todavía.";
    const fileMeta = item.has_file
      ? `<p class="cv-file-meta">Archivo: ${cvEscape(item.original_filename || "documento")}</p>`
      : '<p class="cv-file-meta muted">Sin archivo binario adjunto.</p>';

    return `
      <article class="cv-card ${item.is_active ? "active-cv" : ""}" data-cv-card-id="${item.id}">
        <div class="cv-card-tags">${tags}</div>
        <div class="cv-card-title">
          <div>
            <h3>${cvEscape(item.name)}</h3>
            <small>Versión ${item.version} · ${cvEscape(cvDate(item.created_at))}</small>
          </div>
        </div>
        <p class="cv-target">${target || "Perfil general"}</p>
        <p class="cv-preview">${preview}</p>
        ${fileMeta}
        ${item.generated_by_ai && item.approval_status === "DRAFT" ? `
          <p class="cv-warning">Este borrador fue generado por IA. Revisa sus cambios y evidencia antes de aprobarlo; no puede activarse automáticamente.</p>` : ""}
        <div class="cv-comparison-slot" data-cv-comparison-slot="${item.id}"></div>
        <div class="cv-card-actions">${cvActions(item)}</div>
      </article>`;
  }).join("");
}

function cvChangeMarkup(change) {
  const label = {
    ADDED: "Añadido",
    REMOVED: "Eliminado",
    REPLACED: "Reescrito",
  }[change.kind] || change.kind;
  const original = change.original
    ? `<div><span>Antes</span><p>${cvEscape(change.original)}</p></div>`
    : "";
  const proposed = change.proposed
    ? `<div><span>Ahora</span><p>${cvEscape(change.proposed)}</p></div>`
    : "";
  const warning = change.needs_human_verification
    ? '<strong class="cv-claim-warning">Revisar evidencia antes de aprobar</strong>'
    : "";
  return `
    <li class="cv-change ${change.kind.toLowerCase()}">
      <div class="cv-change-heading"><strong>${cvEscape(label)}</strong>${warning}</div>
      ${original}${proposed}
    </li>`;
}

function cvRequirementMarkup(jobContext) {
  if (!jobContext) return "";
  const skills = Array.isArray(jobContext.required_skills) ? jobContext.required_skills : [];
  return `
    <div class="cv-job-signals">
      <strong>${cvEscape(jobContext.title)}${jobContext.company ? ` · ${cvEscape(jobContext.company)}` : ""}</strong>
      <p>Skills requeridos detectados en la vacante; se muestran como señales, no como un score.</p>
      ${skills.length ? `<div class="cv-skill-signals">${skills.map((item) => `
        <span class="${item.present ? "present" : "missing"}">${item.present ? "✓" : "!"} ${cvEscape(item.skill)}</span>`).join("")}</div>` : '<small>La vacante no tiene skills estructurados.</small>'}
    </div>`;
}

function cvComparisonMarkup(comparison) {
  const summary = comparison.summary;
  const changes = Array.isArray(comparison.changes) ? comparison.changes : [];
  return `
    <section class="cv-comparison-panel">
      <div class="cv-comparison-heading">
        <div><strong>Comparación con versión padre</strong><small>${cvEscape(comparison.parent_name)} → ${cvEscape(comparison.current_name)}</small></div>
        <span>${summary.current_word_count} palabras</span>
      </div>
      <div class="cv-comparison-stats">
        <span>+${summary.added_segments} añadidos</span>
        <span>~${summary.replaced_segments} reescritos</span>
        <span>−${summary.removed_segments} eliminados</span>
        <span>${summary.quantified_statement_count} frases cuantificadas</span>
      </div>
      ${cvRequirementMarkup(comparison.job_context)}
      ${changes.length ? `<ol class="cv-change-list">${changes.slice(0, 16).map(cvChangeMarkup).join("")}</ol>` : '<p class="cv-comparison-empty">No hay cambios de texto detectables frente al padre.</p>'}
      ${changes.length > 16 ? `<small class="cv-comparison-more">Se muestran 16 de ${changes.length} cambios.</small>` : ""}
      ${comparison.generated_by_ai ? '<p class="cv-comparison-safety">Las afirmaciones nuevas de un borrador IA se marcan para revisión humana. Job Radar no afirma automáticamente que estén sustentadas.</p>' : ""}
    </section>`;
}

async function showCvComparison(item, button) {
  const slot = document.querySelector(`[data-cv-comparison-slot="${item.id}"]`);
  if (!slot) return;
  if (slot.dataset.loaded === "true") {
    slot.innerHTML = "";
    slot.dataset.loaded = "false";
    button.textContent = "Comparar cambios";
    return;
  }

  button.disabled = true;
  button.textContent = "Comparando…";
  try {
    const comparison = await cvApi(`/api/v1/cvs/${item.id}/comparison`);
    slot.innerHTML = cvComparisonMarkup(comparison);
    slot.dataset.loaded = "true";
    button.textContent = "Ocultar comparación";
  } catch (error) {
    cvStatus.textContent = `No se pudo comparar: ${error.message}`;
    cvStatus.classList.add("error");
    button.textContent = "Comparar cambios";
  } finally {
    button.disabled = false;
  }
}

async function loadCvs(options = {}) {
  if (!cvRouteActive()) return;
  if (!options.preserveStatus) cvStatus.textContent = "";
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
  const file = cvFile.files[0] || null;
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
    const created = await cvApi("/api/v1/cvs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    let fileError = null;
    if (file) {
      cvStatus.textContent = "Guardando archivo del CV…";
      try {
        await uploadCvFile(created.id, file);
      } catch (error) {
        fileError = error;
      }
    }
    closeDialog();
    if (fileError) {
      cvStatus.textContent = `La versión se guardó, pero el archivo no: ${fileError.message}. Puedes adjuntarlo desde la tarjeta.`;
      cvStatus.classList.add("error");
    } else {
      cvStatus.textContent = payload.parent_cv_id ? "Nueva versión guardada." : "CV guardado.";
    }
    await loadCvs({ preserveStatus: true });
  } catch (error) {
    cvStatus.textContent = error.message;
    cvStatus.classList.add("error");
  } finally {
    saveCvButton.disabled = false;
  }
}

async function chooseAndAttachFile(item) {
  const picker = document.createElement("input");
  picker.type = "file";
  picker.accept = ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";
  picker.addEventListener("change", async () => {
    const file = picker.files[0];
    if (!file) return;
    cvStatus.textContent = `Adjuntando ${file.name}…`;
    cvStatus.classList.remove("error");
    try {
      await uploadCvFile(item.id, file);
      cvStatus.textContent = "Archivo guardado. Esta versión ya no puede sobrescribirse.";
      await loadCvs({ preserveStatus: true });
    } catch (error) {
      cvStatus.textContent = error.message;
      cvStatus.classList.add("error");
    }
  }, { once: true });
  picker.click();
}

async function applyCvAction(action, item, button) {
  cvStatus.textContent = "Actualizando CV…";
  cvStatus.classList.remove("error");
  try {
    if (action === "compare") {
      cvStatus.textContent = "";
      await showCvComparison(item, button);
      return;
    }
    if (action === "version") {
      openNewCvDialog(item);
      cvStatus.textContent = "";
      return;
    }
    if (action === "attach") {
      cvStatus.textContent = "";
      chooseAndAttachFile(item);
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
    await loadCvs({ preserveStatus: true });
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
  applyCvAction(button.dataset.cvAction, item, button);
});

addCvButton.addEventListener("click", () => openNewCvDialog());
closeCvDialog.addEventListener("click", closeDialog);
cancelCvDialog.addEventListener("click", closeDialog);
cvForm.addEventListener("submit", saveCv);

cvDialog.addEventListener("click", (event) => {
  if (event.target === cvDialog) closeDialog();
});

window.addEventListener("hashchange", () => loadCvs());
if (cvRouteActive()) loadCvs();
