const connectionWarning = document.getElementById("connectionWarning");
const captureState = document.getElementById("captureState");
const captureForm = document.getElementById("captureForm");
const jobTitle = document.getElementById("jobTitle");
const jobCompany = document.getElementById("jobCompany");
const jobLocation = document.getElementById("jobLocation");
const jobWorkMode = document.getElementById("jobWorkMode");
const jobSalary = document.getElementById("jobSalary");
const jobDescription = document.getElementById("jobDescription");
const extractorNote = document.getElementById("extractorNote");
const sourceLabel = document.getElementById("sourceLabel");
const sourceUrl = document.getElementById("sourceUrl");
const sendCapture = document.getElementById("sendCapture");
const recapture = document.getElementById("recapture");
const openSettings = document.getElementById("openSettings");
const resultPanel = document.getElementById("resultPanel");
const resultStatus = document.getElementById("resultStatus");
const resultCard = document.getElementById("resultCard");
const classificationBadge = document.getElementById("classificationBadge");
const resultTitle = document.getElementById("resultTitle");
const resultCompany = document.getElementById("resultCompany");
const openRadar = document.getElementById("openRadar");
const refreshResult = document.getElementById("refreshResult");

let connection = null;
let captured = null;
let currentResult = null;

function capturePage() {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const textFromHtml = (value) => {
    const node = document.createElement("div");
    node.innerHTML = String(value || "");
    return clean(node.textContent);
  };
  const firstText = (selectors) => {
    for (const selector of selectors) {
      const node = document.querySelector(selector);
      const value = clean(node?.textContent);
      if (value) return value;
    }
    return null;
  };
  const meta = (selector) => clean(document.querySelector(selector)?.content) || null;
  const flatten = (value) => {
    if (Array.isArray(value)) return value.flatMap(flatten);
    if (!value || typeof value !== "object") return [];
    const graph = Array.isArray(value["@graph"]) ? value["@graph"].flatMap(flatten) : [];
    return [value, ...graph];
  };
  const typeIncludes = (node, expected) => {
    const type = node?.["@type"];
    return Array.isArray(type) ? type.includes(expected) : type === expected;
  };
  const locationText = (value) => {
    const locations = Array.isArray(value) ? value : value ? [value] : [];
    const parts = [];
    for (const location of locations) {
      if (typeof location === "string") {
        parts.push(clean(location));
        continue;
      }
      const address = location?.address || location;
      if (!address || typeof address !== "object") continue;
      const item = [
        address.addressLocality,
        address.addressRegion,
        address.addressCountry?.name || address.addressCountry,
      ].map(clean).filter(Boolean).join(", ");
      if (item) parts.push(item);
    }
    return [...new Set(parts)].join(" · ") || null;
  };
  const salaryText = (value) => {
    if (!value || typeof value !== "object") return null;
    const currency = clean(value.currency);
    const unit = clean(value.value?.unitText || value.unitText);
    const nested = value.value?.value;
    const min = value.value?.minValue ?? (typeof nested === "number" ? nested : null);
    const max = value.value?.maxValue ?? null;
    const amount = min !== null && max !== null
      ? `${min}–${max}`
      : min !== null
        ? String(min)
        : clean(nested);
    return clean([currency, amount, unit].filter(Boolean).join(" ")) || null;
  };
  const sourceForHost = (hostname) => {
    const host = hostname.toLowerCase();
    if (host.includes("linkedin.com")) return "linkedin";
    if (host.includes("indeed.")) return "indeed";
    if (host.includes("myworkdayjobs.com") || host.includes("workday.com")) return "workday";
    if (host.includes("computrabajo.")) return "computrabajo";
    if (host.includes("glassdoor.")) return "glassdoor";
    if (host.includes("bumeran.")) return "bumeran";
    return host.replace(/^www\./, "").slice(0, 80);
  };
  const externalIdForUrl = (url, source) => {
    if (source === "linkedin") return url.match(/\/jobs\/view\/(\d+)/)?.[1] || null;
    if (source === "indeed") return new URL(url).searchParams.get("jk");
    return null;
  };

  let structured = null;
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const parsed = JSON.parse(script.textContent || "null");
      structured = flatten(parsed).find((item) => typeIncludes(item, "JobPosting")) || structured;
    } catch (_) {
      // Invalid JSON-LD on a page must not block the user-triggered DOM fallback.
    }
  }

  const hostname = location.hostname;
  const source = sourceForHost(hostname);
  const jsonLdDescription = structured?.description ? textFromHtml(structured.description) : null;
  const fallbackDescription = firstText([
    "[data-job-description]",
    ".jobs-description-content__text",
    ".show-more-less-html__markup",
    "[class*='jobDescription']",
    "[class*='job-description']",
    "article",
  ]) || meta('meta[name="description"]');
  const description = (jsonLdDescription || fallbackDescription || "").slice(0, 20000) || null;
  const structuredWorkMode = clean(structured?.jobLocationType).toUpperCase();

  return {
    pageUrl: location.href,
    pageTitle: document.title,
    source,
    externalId: externalIdForUrl(location.href, source),
    extractor: structured ? "json_ld_job_posting" : "reviewed_dom_fallback",
    title: clean(structured?.title) || firstText(["h1", "[data-job-title]"]) || meta('meta[property="og:title"]'),
    company: clean(structured?.hiringOrganization?.name) || firstText([
      "[data-company-name]",
      ".job-details-jobs-unified-top-card__company-name",
      ".topcard__org-name-link",
      "[class*='company-name']",
    ]),
    location: locationText(structured?.jobLocation) || firstText([
      "[data-job-location]",
      ".topcard__flavor--bullet",
      "[class*='job-location']",
    ]),
    workMode: structuredWorkMode === "TELECOMMUTE" ? "REMOTE" : null,
    salaryText: salaryText(structured?.baseSalary),
    description,
  };
}

function classificationPresentation(value) {
  if (value === "HIGH_PRIORITY") return { label: "Alta prioridad", className: "high" };
  if (value === "DISCARD") return { label: "Descartada", className: "discarded" };
  if (value === "REVIEW") return { label: "Revisar", className: "review" };
  return { label: "Procesando", className: "pending" };
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function loadConnection() {
  const saved = await chrome.storage.local.get(["apiBase", "apiKey"]);
  if (!saved.apiBase || !saved.apiKey) {
    connection = null;
    connectionWarning.classList.remove("hidden");
    return false;
  }
  const granted = await chrome.permissions.contains({ origins: [`${saved.apiBase}/*`] });
  if (!granted) {
    connection = null;
    connectionWarning.classList.remove("hidden");
    return false;
  }
  connection = { apiBase: saved.apiBase, apiKey: saved.apiKey };
  connectionWarning.classList.add("hidden");
  return true;
}

async function activeHttpTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !/^https?:\/\//i.test(tab.url || "")) {
    throw new Error("Abre una vacante en una página HTTP/HTTPS y vuelve a pulsar la extensión.");
  }
  return tab;
}

function showCapture(data) {
  captured = data;
  jobTitle.value = data.title || "";
  jobCompany.value = data.company || "";
  jobLocation.value = data.location || "";
  jobWorkMode.value = data.workMode || "";
  jobSalary.value = data.salaryText || "";
  jobDescription.value = data.description || "";
  extractorNote.textContent = data.extractor === "json_ld_job_posting"
    ? "Datos estructurados JobPosting detectados; revisa igualmente antes de enviar."
    : "No se encontró JobPosting estructurado; se usó un fallback DOM y requiere revisión.";
  sourceLabel.textContent = `Fuente: ${data.source || "desconocida"}`;
  sourceUrl.href = data.pageUrl;
  captureState.classList.add("hidden");
  captureForm.classList.remove("hidden");
}

async function captureActivePage() {
  captureForm.classList.add("hidden");
  captureState.classList.remove("hidden");
  captureState.textContent = "Leyendo únicamente la pestaña activa…";
  resultPanel.classList.add("hidden");
  try {
    const tab = await activeHttpTab();
    const [injection] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: capturePage,
    });
    const data = injection?.result;
    if (!data || !data.pageUrl) throw new Error("No se pudo leer esta página.");
    showCapture(data);
    const saved = await chrome.storage.local.get("lastIngestion");
    if (saved.lastIngestion?.pageUrl === data.pageUrl && saved.lastIngestion?.ingestionId) {
      await checkResult(saved.lastIngestion.ingestionId, { poll: false });
    }
  } catch (error) {
    captureState.textContent = error.message;
  }
}

async function apiRequest(path, options = {}) {
  if (!connection) throw new Error("Configura primero la conexión con Job Radar.");
  const headers = {
    Accept: "application/json",
    Authorization: `Bearer ${connection.apiKey}`,
    ...(options.headers || {}),
  };
  const response = await fetch(`${connection.apiBase}${path}`, { ...options, headers });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch (_) {
      // Preserve HTTP status when the API does not return JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

async function payloadIdempotencyKey(payload) {
  const encoded = new TextEncoder().encode(JSON.stringify(payload));
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  const hex = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `chrome-extension:${hex.slice(0, 48)}`;
}

function reviewedPayload() {
  const title = jobTitle.value.trim();
  if (!title) throw new Error("Confirma el título del puesto antes de enviar.");
  return {
    ingestion_source: "chrome_extension",
    posting_source: captured.source || null,
    external_id: captured.externalId || null,
    captured_at: new Date().toISOString(),
    job: {
      title,
      company: jobCompany.value.trim() || null,
      location: jobLocation.value.trim() || null,
      work_mode: jobWorkMode.value || null,
      salary_text: jobSalary.value.trim() || null,
      description: jobDescription.value.trim() || null,
      url: captured.pageUrl,
    },
    metadata: {
      extension_version: chrome.runtime.getManifest().version,
      extractor: captured.extractor,
      page_host: new URL(captured.pageUrl).hostname,
      human_reviewed_before_submit: true,
    },
    raw: {
      page_title: captured.pageTitle,
      extractor: captured.extractor,
    },
  };
}

function renderResult(data) {
  currentResult = data;
  resultPanel.classList.remove("hidden");
  const presentation = classificationPresentation(data.classification);
  classificationBadge.textContent = presentation.label;
  classificationBadge.className = `classification-badge ${presentation.className}`;
  resultTitle.textContent = data.title || jobTitle.value || "Vacante capturada";
  resultCompany.textContent = data.company || jobCompany.value || "Empresa no indicada";
  resultCard.classList.toggle("hidden", !data.job_id);

  if (data.ingestion_status === "FAILED" || data.analysis_status === "FAILED") {
    resultStatus.textContent = `El procesamiento falló${data.error_code ? `: ${data.error_code}` : "."}`;
    resultStatus.classList.add("error");
    refreshResult.classList.add("hidden");
    return;
  }
  resultStatus.classList.remove("error");
  if (data.analysis_status === "READY") {
    resultStatus.textContent = `Análisis listo · ${data.analyzer_version || "motor actual"}`;
    refreshResult.classList.add("hidden");
  } else if (data.job_id) {
    resultStatus.textContent = "Vacante normalizada. El matching todavía está procesándose.";
    refreshResult.classList.remove("hidden");
  } else {
    resultStatus.textContent = "Vacante recibida. Esperando normalización.";
    refreshResult.classList.remove("hidden");
  }
}

async function checkResult(ingestionId, { poll = true } = {}) {
  resultPanel.classList.remove("hidden");
  resultStatus.classList.remove("error");
  resultStatus.textContent = "Consultando Job Radar…";
  const attempts = poll ? 10 : 1;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const data = await apiRequest(`/api/v1/ingestions/jobs/${ingestionId}/result`);
      renderResult(data);
      if (data.analysis_status === "READY" || data.analysis_status === "FAILED") return;
    } catch (error) {
      resultStatus.classList.add("error");
      resultStatus.textContent = `No se pudo consultar: ${error.message}`;
      return;
    }
    if (attempt < attempts - 1) await delay(1000);
  }
}

captureForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!captured) return;
  sendCapture.disabled = true;
  resultPanel.classList.remove("hidden");
  resultCard.classList.add("hidden");
  refreshResult.classList.add("hidden");
  resultStatus.classList.remove("error");
  resultStatus.textContent = "Enviando a Job Radar…";
  try {
    const payload = reviewedPayload();
    const idempotencyKey = await payloadIdempotencyKey(payload);
    const accepted = await apiRequest("/api/v1/ingestions/jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify(payload),
    });
    await chrome.storage.local.set({
      lastIngestion: {
        pageUrl: captured.pageUrl,
        ingestionId: accepted.ingestion_id,
        savedAt: new Date().toISOString(),
      },
    });
    await checkResult(accepted.ingestion_id);
  } catch (error) {
    resultStatus.classList.add("error");
    resultStatus.textContent = `No se pudo enviar: ${error.message}`;
  } finally {
    sendCapture.disabled = false;
  }
});

refreshResult.addEventListener("click", async () => {
  const saved = await chrome.storage.local.get("lastIngestion");
  if (saved.lastIngestion?.ingestionId) {
    await checkResult(saved.lastIngestion.ingestionId, { poll: false });
  }
});

openRadar.addEventListener("click", () => {
  if (!connection || !currentResult?.job_id) return;
  chrome.tabs.create({ url: `${connection.apiBase}/app/#/radar/${currentResult.job_id}` });
});

recapture.addEventListener("click", captureActivePage);
openSettings.addEventListener("click", () => chrome.runtime.openOptionsPage());

(async function initialize() {
  await loadConnection();
  await captureActivePage();
})();
