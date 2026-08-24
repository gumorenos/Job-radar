const feedbackInsightsStylesheet = document.createElement("link");
feedbackInsightsStylesheet.rel = "stylesheet";
feedbackInsightsStylesheet.href = "/app/feedback_insights.css";
document.head.appendChild(feedbackInsightsStylesheet);

const feedbackReasonPresentation = {
  SALARY: "Salario",
  SENIORITY: "Seniority",
  SKILLS: "Skills",
  LOCATION: "Ubicación",
  INDUSTRY: "Industria",
  DEGREE: "Grado / carrera",
  TITLE: "Título del puesto",
  OTHER: "Otro",
};

const feedbackClassificationPresentation = {
  HIGH_PRIORITY: "Alta prioridad",
  REVIEW: "Revisar",
  DISCARD: "Descartar",
};

const feedbackInsightsForm = document.getElementById("profileSettingsForm");
const feedbackInsightsSaveBar = feedbackInsightsForm?.querySelector(".settings-save-bar");
const feedbackInsightsCard = document.createElement("section");
feedbackInsightsCard.className = "settings-card feedback-insights-card";
feedbackInsightsCard.innerHTML = `
  <div class="settings-card-heading">
    <h3>Correcciones del Radar</h3>
    <p>Patrones agregados de tus decisiones. Se observan; no cambian reglas automáticamente.</p>
  </div>
  <div class="feedback-insights" id="feedbackInsights" aria-live="polite">
    <p class="feedback-insights-empty">Cargando correcciones…</p>
  </div>`;

if (feedbackInsightsForm && feedbackInsightsSaveBar) {
  feedbackInsightsForm.insertBefore(feedbackInsightsCard, feedbackInsightsSaveBar);
}

const feedbackInsights = document.getElementById("feedbackInsights");

function feedbackSettingsRouteActive() {
  return window.location.hash.replace(/^#\//, "").split("/")[0] === "settings";
}

function feedbackInsightsEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function feedbackReasonLabel(reason) {
  return feedbackReasonPresentation[reason] || reason || "Otro";
}

function feedbackClassificationLabel(classification) {
  return feedbackClassificationPresentation[classification] || classification || "Sin dato";
}

function renderFeedbackInsights(payload) {
  if (!feedbackInsights) return;
  if (!payload.jobs_with_feedback) {
    feedbackInsights.innerHTML = `
      <div class="feedback-insights-empty">
        <strong>Aún no hay correcciones</strong>
        <p>Cuando ajustes clasificaciones en Radar, aquí aparecerán patrones agregados.</p>
      </div>`;
    return;
  }

  const reasons = Array.isArray(payload.by_reason) ? payload.by_reason.slice(0, 5) : [];
  const transitions = Array.isArray(payload.transitions) ? payload.transitions.slice(0, 5) : [];
  const reasonRows = reasons.length
    ? reasons.map((item) => `
        <div class="feedback-insight-row">
          <span>${feedbackInsightsEscape(feedbackReasonLabel(item.reason))}</span>
          <strong>${Number(item.count || 0)}</strong>
          <small>${Number(item.overrides || 0)} cambian la clasificación</small>
        </div>`).join("")
    : '<p class="feedback-insights-empty">Sin motivos agregados todavía.</p>';
  const transitionRows = transitions.length
    ? transitions.map((item) => `
        <div class="feedback-transition-row">
          <span>${feedbackInsightsEscape(feedbackClassificationLabel(item.system_classification))}</span>
          <b aria-hidden="true">→</b>
          <span>${feedbackInsightsEscape(feedbackClassificationLabel(item.human_classification))}</span>
          <strong>${Number(item.count || 0)}</strong>
        </div>`).join("")
    : '<p class="feedback-insights-empty">Sin transiciones agregadas todavía.</p>';

  feedbackInsights.innerHTML = `
    <div class="feedback-insight-metrics">
      <div><strong>${Number(payload.total_events || 0)}</strong><span>eventos guardados</span></div>
      <div><strong>${Number(payload.jobs_with_feedback || 0)}</strong><span>vacantes corregidas</span></div>
      <div><strong>${Number(payload.current_overrides || 0)}</strong><span>decisiones distintas</span></div>
      <div><strong>${Number(payload.current_agreements || 0)}</strong><span>coincidencias actuales</span></div>
    </div>
    <div class="feedback-insight-columns">
      <div>
        <h4>Motivos actuales</h4>
        <div class="feedback-insight-list">${reasonRows}</div>
      </div>
      <div>
        <h4>Cambios de clasificación</h4>
        <div class="feedback-insight-list">${transitionRows}</div>
      </div>
    </div>
    <p class="feedback-insights-note">Los conteos actuales usan la corrección más reciente de cada vacante; el historial completo sigue siendo append-only.</p>`;
}

async function loadFeedbackInsights() {
  if (!feedbackSettingsRouteActive() || !feedbackInsights) return;
  feedbackInsights.innerHTML = '<p class="feedback-insights-empty">Cargando correcciones…</p>';
  try {
    const response = await fetch("/api/v1/feedback/insights", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    renderFeedbackInsights(await response.json());
  } catch (error) {
    feedbackInsights.innerHTML = `<p class="feedback-insights-empty error">No se pudieron cargar las correcciones: ${feedbackInsightsEscape(error.message)}</p>`;
  }
}

window.addEventListener("hashchange", () => {
  if (feedbackSettingsRouteActive()) loadFeedbackInsights();
});

if (feedbackSettingsRouteActive()) loadFeedbackInsights();
