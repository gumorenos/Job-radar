const settingsStylesheet = document.createElement("link");
settingsStylesheet.rel = "stylesheet";
settingsStylesheet.href = "/app/settings.css";
document.head.appendChild(settingsStylesheet);

const profileSettingsForm = document.getElementById("profileSettingsForm");
const profileSettingsStatus = document.getElementById("profileSettingsStatus");
const profileName = document.getElementById("profileName");
const salaryMinPen = document.getElementById("salaryMinPen");
const remoteSalaryMultiplier = document.getElementById("remoteSalaryMultiplier");
const remoteSalaryFloor = document.getElementById("remoteSalaryFloor");
const targetRoles = document.getElementById("targetRoles");
const targetLocations = document.getElementById("targetLocations");
const targetAreas = document.getElementById("targetAreas");
const adjacentAreas = document.getElementById("adjacentAreas");
const dailyReviewTime = document.getElementById("dailyReviewTime");
const profileTimezone = document.getElementById("profileTimezone");
const hardRuleSeniority = document.getElementById("hardRuleSeniority");
const hardRuleOnsiteOutsideLima = document.getElementById("hardRuleOnsiteOutsideLima");
const hardRuleSalaryFloor = document.getElementById("hardRuleSalaryFloor");
const saveProfileSettings = document.getElementById("saveProfileSettings");
const settingsUnsavedHint = document.getElementById("settingsUnsavedHint");
const settingsSaveBar = profileSettingsForm.querySelector(".settings-save-bar");

const reanalyzeProfileJobs = document.createElement("button");
reanalyzeProfileJobs.type = "button";
reanalyzeProfileJobs.id = "reanalyzeProfileJobs";
reanalyzeProfileJobs.className = "secondary";
reanalyzeProfileJobs.textContent = "Reanalizar oportunidades";
reanalyzeProfileJobs.disabled = true;
const settingsSaveActions = document.createElement("div");
settingsSaveActions.className = "settings-save-actions";
settingsSaveBar.insertBefore(settingsSaveActions, saveProfileSettings);
settingsSaveActions.append(reanalyzeProfileJobs, saveProfileSettings);

const fitFactsCard = document.createElement("section");
fitFactsCard.className = "settings-card fit-facts-card";
fitFactsCard.innerHTML = `
  <div class="settings-card-heading">
    <h3>Hechos de compatibilidad</h3>
    <p>Datos explícitos del perfil usados para explicar experiencia, carrera y skills. Un término por línea.</p>
  </div>
  <div class="settings-columns">
    <label class="settings-field">
      <span>Años de experiencia</span>
      <input id="experienceYears" name="experience_years" type="number" min="0" max="80" step="0.5">
    </label>
    <label class="settings-field">
      <span>Carreras / grados</span>
      <textarea id="profileDegrees" name="degrees" rows="5" placeholder="Ej. Administración"></textarea>
    </label>
  </div>
  <div class="settings-columns">
    <label class="settings-field">
      <span>Skills con evidencia directa</span>
      <textarea id="profileSkills" name="skills" rows="7" placeholder="Ej. People Analytics"></textarea>
    </label>
    <label class="settings-field">
      <span>Skills transferibles / fáciles de cerrar</span>
      <textarea id="transferableSkills" name="transferable_skills" rows="7" placeholder="Ej. Power BI"></textarea>
    </label>
  </div>
  <p class="settings-derived">Una brecha de experiencia o carrera puede llevar a Revisar, pero no activa un descarte duro por sí sola.</p>`;

const opportunityCard = targetRoles.closest(".settings-card");
profileSettingsForm.insertBefore(fitFactsCard, opportunityCard);
const experienceYears = document.getElementById("experienceYears");
const profileDegrees = document.getElementById("profileDegrees");
const profileSkills = document.getElementById("profileSkills");
const transferableSkills = document.getElementById("transferableSkills");

const ingestionCard = document.createElement("section");
ingestionCard.className = "settings-card ingestion-health-card";
ingestionCard.innerHTML = `
  <div class="settings-card-heading">
    <h3>Fuentes e ingesta</h3>
    <p>Estado interno de las entradas que están llegando a Job Radar. No expone payloads ni secretos.</p>
  </div>
  <div class="ingestion-health" id="ingestionHealth" aria-live="polite">
    <p class="ingestion-health-empty">Cargando fuentes…</p>
  </div>`;
profileSettingsForm.insertBefore(ingestionCard, settingsSaveBar);
const ingestionHealth = document.getElementById("ingestionHealth");

let profileLoaded = false;
let profileDirty = false;

function settingsRouteActive() {
  return window.location.hash.replace(/^#\//, "").split("/")[0] === "settings";
}

function settingsEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

async function profileApi(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload.detail) {
        message = typeof payload.detail === "string"
          ? payload.detail
          : "Revisa los campos de configuración.";
      }
    } catch (_) {
      // Keep the HTTP error when there is no JSON response.
    }
    throw new Error(message);
  }
  return response.json();
}

function listToText(items) {
  return Array.isArray(items) ? items.join("\n") : "";
}

function textToList(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function timeForInput(value) {
  return String(value || "21:00").slice(0, 5);
}

function updateRemoteFloor() {
  const local = Number(salaryMinPen.value);
  const multiplier = Number(remoteSalaryMultiplier.value);
  if (!Number.isFinite(local) || !Number.isFinite(multiplier)) {
    remoteSalaryFloor.textContent = "—";
    return;
  }
  const amount = Math.round(local * multiplier);
  remoteSalaryFloor.textContent = new Intl.NumberFormat("es-PE", {
    style: "currency",
    currency: "PEN",
    maximumFractionDigits: 0,
  }).format(amount);
}

function renderProfile(profile) {
  const hardRules = profile.hard_rules || {};
  profileName.value = profile.name || "";
  salaryMinPen.value = profile.salary_min_pen ?? 7000;
  remoteSalaryMultiplier.value = profile.remote_salary_multiplier ?? 1.1;
  experienceYears.value = profile.experience_years ?? "";
  profileDegrees.value = listToText(profile.degrees);
  profileSkills.value = listToText(profile.skills);
  transferableSkills.value = listToText(profile.transferable_skills);
  targetRoles.value = listToText(profile.target_roles);
  targetLocations.value = listToText(profile.target_locations);
  targetAreas.value = listToText(profile.target_areas);
  adjacentAreas.value = listToText(profile.adjacent_areas);
  dailyReviewTime.value = timeForInput(profile.daily_review_time);
  profileTimezone.value = profile.timezone || "America/Lima";
  hardRuleSeniority.checked = hardRules.discard_disallowed_titles !== false;
  hardRuleOnsiteOutsideLima.checked = hardRules.discard_onsite_outside_lima !== false;
  hardRuleSalaryFloor.checked = hardRules.discard_published_salary_below_floor !== false;
  updateRemoteFloor();
  profileLoaded = true;
  profileDirty = false;
  reanalyzeProfileJobs.disabled = false;
  settingsUnsavedHint.textContent = "Los cambios se aplican al próximo análisis.";
}

function formatIngestionTime(value) {
  if (!value) return "Sin actividad";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Sin actividad";
  return new Intl.DateTimeFormat("es-PE", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(parsed);
}

function renderIngestionHealth(overview) {
  const sources = Array.isArray(overview.sources) ? overview.sources : [];
  if (!sources.length) {
    ingestionHealth.innerHTML = '<p class="ingestion-health-empty">Aún no hay ingestas registradas.</p>';
    return;
  }

  const sourceRows = sources.map((source) => {
    const warning = Number(source.failed || 0) > 0 || Number(source.partial || 0) > 0;
    return `
      <div class="ingestion-source-row">
        <div>
          <strong>${settingsEscape(source.ingestion_source)}</strong>
          <span>Última entrada: ${settingsEscape(formatIngestionTime(source.last_received_at))}</span>
        </div>
        <div class="ingestion-source-metrics">
          <span><b>${Number(source.total || 0)}</b> total</span>
          <span><b>${Number(source.completed || 0)}</b> completas</span>
          <span class="${warning ? "warning" : ""}"><b>${Number(source.failed || 0)}</b> fallidas</span>
        </div>
      </div>`;
  }).join("");

  ingestionHealth.innerHTML = `
    ${sourceRows}
    <div class="ingestion-task-summary">
      Cola: ${Number(overview.pending_tasks || 0)} pendientes ·
      ${Number(overview.running_tasks || 0)} ejecutando ·
      ${Number(overview.failed_tasks || 0)} fallidas
    </div>`;
}

async function loadIngestionHealth() {
  if (!settingsRouteActive()) return;
  try {
    const overview = await profileApi("/api/v1/ingestions/summary");
    renderIngestionHealth(overview);
  } catch (error) {
    ingestionHealth.innerHTML = `<p class="ingestion-health-empty error">No se pudo cargar el estado de fuentes: ${settingsEscape(error.message)}</p>`;
  }
}

async function loadProfileSettings() {
  if (!settingsRouteActive()) return;
  profileSettingsStatus.classList.remove("error");
  profileSettingsStatus.textContent = "Cargando configuración…";
  try {
    const profile = await profileApi("/api/v1/profile");
    renderProfile(profile);
    profileSettingsStatus.textContent = "";
  } catch (error) {
    profileSettingsStatus.classList.add("error");
    profileSettingsStatus.innerHTML = `No se pudo cargar la configuración: ${settingsEscape(error.message)}`;
  }
}

function payloadFromForm() {
  const rawExperience = experienceYears.value.trim();
  return {
    name: profileName.value.trim(),
    salary_min_pen: Number(salaryMinPen.value),
    remote_salary_multiplier: Number(remoteSalaryMultiplier.value),
    experience_years: rawExperience === "" ? null : Number(rawExperience),
    degrees: textToList(profileDegrees.value),
    skills: textToList(profileSkills.value),
    transferable_skills: textToList(transferableSkills.value),
    target_locations: textToList(targetLocations.value),
    target_roles: textToList(targetRoles.value),
    target_areas: textToList(targetAreas.value),
    adjacent_areas: textToList(adjacentAreas.value),
    daily_review_time: dailyReviewTime.value,
    timezone: profileTimezone.value.trim(),
    hard_rules: {
      discard_disallowed_titles: hardRuleSeniority.checked,
      discard_onsite_outside_lima: hardRuleOnsiteOutsideLima.checked,
      discard_published_salary_below_floor: hardRuleSalaryFloor.checked,
    },
  };
}

async function saveSettings(event) {
  event.preventDefault();
  if (!profileSettingsForm.reportValidity()) return;

  saveProfileSettings.disabled = true;
  profileSettingsStatus.classList.remove("error");
  profileSettingsStatus.textContent = "Guardando configuración…";
  try {
    const profile = await profileApi("/api/v1/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payloadFromForm()),
    });
    renderProfile(profile);
    profileSettingsStatus.textContent = "Configuración guardada. Puedes reanalizar las oportunidades existentes cuando quieras.";
  } catch (error) {
    profileSettingsStatus.classList.add("error");
    profileSettingsStatus.textContent = error.message;
  } finally {
    saveProfileSettings.disabled = false;
  }
}

async function reanalyzeExistingJobs() {
  if (!profileLoaded || profileDirty) {
    profileSettingsStatus.classList.add("error");
    profileSettingsStatus.textContent = "Guarda primero los cambios del perfil antes de reanalizar.";
    return;
  }

  reanalyzeProfileJobs.disabled = true;
  profileSettingsStatus.classList.remove("error");
  profileSettingsStatus.textContent = "Programando reanálisis…";
  try {
    const result = await profileApi("/api/v1/profile/reanalyze", { method: "POST" });
    if (!Number(result.jobs_considered || 0)) {
      profileSettingsStatus.textContent = "No hay oportunidades activas para reanalizar.";
    } else {
      profileSettingsStatus.textContent = (
        `Reanálisis programado para ${Number(result.jobs_considered)} oportunidades: `
        + `${Number(result.enqueued)} nuevas tareas y `
        + `${Number(result.reused_pending)} ya estaban pendientes.`
      );
    }
    await loadIngestionHealth();
  } catch (error) {
    profileSettingsStatus.classList.add("error");
    profileSettingsStatus.textContent = error.message;
  } finally {
    reanalyzeProfileJobs.disabled = profileDirty || !profileLoaded;
  }
}

function markDirty() {
  if (!profileLoaded) return;
  profileDirty = true;
  reanalyzeProfileJobs.disabled = true;
  settingsUnsavedHint.textContent = "Tienes cambios sin guardar. Guarda antes de reanalizar.";
}

profileSettingsForm.addEventListener("input", (event) => {
  if (event.target === salaryMinPen || event.target === remoteSalaryMultiplier) {
    updateRemoteFloor();
  }
  markDirty();
});
profileSettingsForm.addEventListener("submit", saveSettings);
reanalyzeProfileJobs.addEventListener("click", reanalyzeExistingJobs);
window.addEventListener("hashchange", () => {
  if (settingsRouteActive()) {
    if (!profileLoaded || !profileDirty) loadProfileSettings();
    loadIngestionHealth();
  }
});

if (settingsRouteActive()) {
  loadProfileSettings();
  loadIngestionHealth();
}
