const settingsForm = document.getElementById("settingsForm");
const apiBaseInput = document.getElementById("apiBase");
const extensionApiKeyInput = document.getElementById("extensionApiKey");
const cfAccessClientIdInput = document.getElementById("cfAccessClientId");
const cfAccessClientSecretInput = document.getElementById("cfAccessClientSecret");
const settingsStatus = document.getElementById("settingsStatus");

function normalizeApiBase(rawValue) {
  const value = String(rawValue || "").trim();
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("El origen debe usar HTTP o HTTPS.");
  }
  const localHost = url.hostname === "127.0.0.1" || url.hostname === "localhost";
  if (url.protocol === "http:" && !localHost) {
    throw new Error("Un servidor remoto debe usar HTTPS para proteger las credenciales.");
  }
  if (url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("Configura solo el origen, por ejemplo https://jobradar.example.com.");
  }
  return url.origin;
}

function isLocalApiBase(apiBase) {
  const url = new URL(apiBase);
  return url.hostname === "127.0.0.1" || url.hostname === "localhost";
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
  const saved = await chrome.storage.local.get([
    "apiBase",
    "extensionApiKey",
    "cfAccessClientId",
    "cfAccessClientSecret",
  ]);
  apiBaseInput.value = saved.apiBase || "http://127.0.0.1:8010";
  extensionApiKeyInput.value = saved.extensionApiKey || "";
  cfAccessClientIdInput.value = saved.cfAccessClientId || "";
  cfAccessClientSecretInput.value = saved.cfAccessClientSecret || "";
}

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  settingsStatus.classList.remove("error");
  settingsStatus.textContent = "Guardando…";
  try {
    const apiBase = normalizeApiBase(apiBaseInput.value);
    const extensionApiKey = extensionApiKeyInput.value.trim();
    const cfAccessClientId = cfAccessClientIdInput.value.trim();
    const cfAccessClientSecret = cfAccessClientSecretInput.value.trim();
    if (!extensionApiKey) throw new Error("La clave de extensión es obligatoria.");
    const hasCloudflareId = Boolean(cfAccessClientId);
    const hasCloudflareSecret = Boolean(cfAccessClientSecret);
    if (hasCloudflareId !== hasCloudflareSecret) {
      throw new Error("Completa ambos valores del Service Token de Cloudflare Access.");
    }
    if (!isLocalApiBase(apiBase) && (!hasCloudflareId || !hasCloudflareSecret)) {
      throw new Error("Una conexión remota requiere el Service Token de Cloudflare Access.");
    }
    await requestOriginPermission(apiBase);
    await chrome.storage.local.set({
      apiBase,
      extensionApiKey,
      cfAccessClientId,
      cfAccessClientSecret,
    });
    await chrome.storage.local.remove("apiKey");
    apiBaseInput.value = apiBase;
    settingsStatus.textContent = "Conexión guardada.";
  } catch (error) {
    settingsStatus.classList.add("error");
    settingsStatus.textContent = error.message;
  }
});

loadSettings();
