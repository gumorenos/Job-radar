const settingsForm = document.getElementById("settingsForm");
const apiBaseInput = document.getElementById("apiBase");
const apiKeyInput = document.getElementById("apiKey");
const settingsStatus = document.getElementById("settingsStatus");

function normalizeApiBase(rawValue) {
  const value = String(rawValue || "").trim();
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("El origen debe usar HTTP o HTTPS.");
  }
  const localHost = url.hostname === "127.0.0.1" || url.hostname === "localhost";
  if (url.protocol === "http:" && !localHost) {
    throw new Error("Un servidor remoto debe usar HTTPS para proteger la API key.");
  }
  if (url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("Configura solo el origen, por ejemplo http://127.0.0.1:8010.");
  }
  return url.origin;
}

function originPermissionPattern(apiBase) {
  const url = new URL(apiBase);
  return `${url.protocol}//${url.hostname}/*`;
}

async function requestOriginPermission(apiBase) {
  const originPattern = originPermissionPattern(apiBase);
  const granted = await chrome.permissions.request({ origins: [originPattern] });
  if (!granted) throw new Error("Chrome no concedió permiso para conectarse a ese origen.");
}

async function loadSettings() {
  const saved = await chrome.storage.local.get(["apiBase", "apiKey"]);
  apiBaseInput.value = saved.apiBase || "http://127.0.0.1:8010";
  apiKeyInput.value = saved.apiKey || "";
}

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  settingsStatus.classList.remove("error");
  settingsStatus.textContent = "Guardando…";
  try {
    const apiBase = normalizeApiBase(apiBaseInput.value);
    const apiKey = apiKeyInput.value.trim();
    if (!apiKey) throw new Error("La API key es obligatoria.");
    await requestOriginPermission(apiBase);
    await chrome.storage.local.set({ apiBase, apiKey });
    apiBaseInput.value = apiBase;
    settingsStatus.textContent = "Conexión guardada.";
  } catch (error) {
    settingsStatus.classList.add("error");
    settingsStatus.textContent = error.message;
  }
});

loadSettings();
