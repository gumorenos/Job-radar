const structuredFitStylesheet = document.createElement("link");
structuredFitStylesheet.rel = "stylesheet";
structuredFitStylesheet.href = "/app/structured_fit.css";
document.head.appendChild(structuredFitStylesheet);

const structuredFitStatusPresentation = {
  MEETS: { label: "Cumple", className: "meets" },
  PARTIALLY: { label: "Parcial", className: "partial" },
  TRANSFERABLE: { label: "Transferible", className: "transferable" },
  DOES_NOT_MEET: { label: "No cumple", className: "missing" },
  POSSIBLE_EXCLUSION: { label: "Posible exclusión", className: "exclusion" },
  UNKNOWN: { label: "Sin dato", className: "unknown" },
};

const businessRuleLabels = {
  SENIORITY_TITLE: "Seniority del título",
  ONSITE_LOCATION: "Ubicación y modalidad",
  PUBLISHED_SALARY: "Salario publicado",
  AGRICULTURE_INDUSTRY: "Industria",
  DEGREE_MISMATCH: "Carrera / grado",
  EXPERIENCE_GAP: "Experiencia",
};

function structuredFitPresentation(status) {
  return structuredFitStatusPresentation[status]
    || { label: status || "Sin dato", className: "unknown" };
}

function businessRulePresentation(severity) {
  if (severity === "HARD") return { label: "Descarte duro", className: "hard" };
  if (severity === "WARNING") return { label: "Advertencia", className: "warning" };
  return { label: "Cumple", className: "info" };
}

function structuredFitRow(label, assessment) {
  if (!assessment || typeof assessment !== "object") return "";
  const presentation = structuredFitPresentation(assessment.status);
  return `
    <div class="structured-fit-row">
      <div class="structured-fit-row-heading">
        <strong>${escapeHtml(label)}</strong>
        <span class="fit-status ${presentation.className}">${escapeHtml(presentation.label)}</span>
      </div>
      <p>${escapeHtml(assessment.message || "Sin explicación estructurada.")}</p>
    </div>`;
}

function structuredSkillItems(items) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <div class="structured-skill-list">
      ${items.map((item) => {
        const presentation = structuredFitPresentation(item?.status);
        return `
          <div class="structured-skill-item">
            <span>${escapeHtml(item?.skill || "Skill")}</span>
            <span class="fit-status ${presentation.className}">${escapeHtml(presentation.label)}</span>
          </div>`;
      }).join("")}
    </div>`;
}

function renderBusinessRules(analysis) {
  const results = analysis?.rule_results?.results;
  if (!Array.isArray(results) || !results.length) return "";

  const active = results.filter((item) => item?.severity === "HARD" || item?.severity === "WARNING");
  const passed = results.filter((item) => item?.severity === "INFO" && item?.passed !== false).length;
  const rows = active.map((item) => {
    const presentation = businessRulePresentation(item.severity);
    const label = businessRuleLabels[item.code] || item.code || "Regla";
    return `
      <div class="business-rule-row">
        <div>
          <strong>${escapeHtml(label)}</strong>
          <span class="rule-status ${presentation.className}">${escapeHtml(presentation.label)}</span>
        </div>
        <p>${escapeHtml(item.message || "Regla activada sin explicación adicional.")}</p>
      </div>`;
  }).join("");

  const quietState = active.length
    ? ""
    : '<p class="business-rules-clear">Sin descartes duros ni advertencias activas.</p>';
  return `
    <section class="detail-section business-rules-section">
      <div class="decision-section-heading">
        <h3>Reglas de negocio</h3>
        <span>${passed}/${results.length} sin alerta</span>
      </div>
      ${quietState}
      ${rows}
    </section>`;
}

function renderStructuredFit(analysis) {
  const structured = analysis?.skill_analysis?.structured_fit;
  if (!structured || typeof structured !== "object") return "";

  const rows = [
    structuredFitRow("Experiencia", structured.experience),
    structuredFitRow("Carrera / grado", structured.degree),
    structuredFitRow("Skills", structured.skills),
  ].filter(Boolean).join("");

  if (!rows) return "";
  const reviewNote = structured.requires_review
    ? '<p class="structured-fit-note">Hay una o más brechas que justifican Revisar; no son un descarte duro por sí solas.</p>'
    : "";

  return `
    <section class="detail-section structured-fit-section">
      <div class="decision-section-heading">
        <h3>Requisitos vs perfil</h3>
        <span>${escapeHtml(analysis.analyzer_version || analysis.rule_results?.analyzer_version || "rules")}</span>
      </div>
      ${rows}
      ${structuredSkillItems(structured.skill_items)}
      ${reviewNote}
    </section>`;
}

function renderRecommendedCv(analysis) {
  const cv = analysis?.skill_analysis?.recommended_cv;
  if (!cv || typeof cv !== "object" || !cv.name) return "";
  const version = cv.version === null || cv.version === undefined ? "" : ` · v${cv.version}`;
  return `
    <section class="detail-section recommended-cv-section">
      <div class="decision-section-heading">
        <h3>CV recomendado</h3>
        <span>Para esta oportunidad</span>
      </div>
      <div class="recommended-cv-card">
        <strong>${escapeHtml(cv.name)}${escapeHtml(version)}</strong>
        <p>Esta recomendación pertenece al análisis guardado. No activa ni modifica un CV automáticamente.</p>
      </div>
    </section>`;
}

const baseRenderAnalysisWithNoStructuredFit = renderAnalysis;
renderAnalysis = function renderAnalysisWithStructuredFit(analysis) {
  const base = baseRenderAnalysisWithNoStructuredFit(analysis);
  if (!analysis) return base;
  return `${base}${renderBusinessRules(analysis)}${renderStructuredFit(analysis)}${renderRecommendedCv(analysis)}`;
};
