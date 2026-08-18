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
const saveProfileSettings = document.getElementById("saveProfileSettings");
const settingsUnsavedHint = document.getElementById("settingsUnsavedHint");

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
  profileName.value = profile.name || "";
  salaryMinPen.value = profile.salary_min_pen ?? 7000;
  remoteSalaryMultiplier.value = profile.remote_salary_multiplier ?? 1.1;
  targetRoles.value = listToText(profile.target_roles);
  targetLocations.value = listToText(profile.target_locations);
  targetAreas.value = listToText(profile.target_areas);
  adjacentAreas.value = listToText(profile.adjacent_areas);
  dailyReviewTime.value = timeForInput(profile.daily_review_time);
  profileTimezone.value = profile.timezone || "America/Lima";
  updateRemoteFloor();
  profileLoaded = true;
  profileDirty = false;
  settingsUnsavedHint.textContent = "Los cambios se aplican al próximo análisis.";
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
  return {
    name: profileName.value.trim(),
    salary_min_pen: Number(salaryMinPen.value),
    remote_salary_multiplier: Number(remoteSalaryMultiplier.value),
    target_locations: textToList(targetLocations.value),
    target_roles: textToList(targetRoles.value),
    target_areas: textToList(targetAreas.value),
    adjacent_areas: textToList(adjacentAreas.value),
    daily_review_time: dailyReviewTime.value,
    timezone: profileTimezone.value.trim(),
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
    profileSettingsStatus.textContent = "Configuración guardada.";
  } catch (error) {
    profileSettingsStatus.classList.add("error");
    profileSettingsStatus.textContent = error.message;
  } finally {
    saveProfileSettings.disabled = false;
  }
}

function markDirty() {
  if (!profileLoaded) return;
  profileDirty = true;
  settingsUnsavedHint.textContent = "Tienes cambios sin guardar.";
}

profileSettingsForm.addEventListener("input", (event) => {
  if (event.target === salaryMinPen || event.target === remoteSalaryMultiplier) {
    updateRemoteFloor();
  }
  markDirty();
});
profileSettingsForm.addEventListener("submit", saveSettings);
window.addEventListener("hashchange", () => {
  if (settingsRouteActive() && (!profileLoaded || !profileDirty)) loadProfileSettings();
});

if (settingsRouteActive()) loadProfileSettings();
