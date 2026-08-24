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

function structuredFitPresentation(status) {
  return structuredFitStatusPresentation[status]
    || { label: status || "Sin dato", className: "unknown" };
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
      <div class="structured-fit-heading">
        <h3>Requisitos vs perfil</h3>
        <span>rules-v5</span>
      </div>
      ${rows}
      ${structuredSkillItems(structured.skill_items)}
      ${reviewNote}
    </section>`;
}

const baseRenderAnalysisWithNoStructuredFit = renderAnalysis;
renderAnalysis = function renderAnalysisWithStructuredFit(analysis) {
  const base = baseRenderAnalysisWithNoStructuredFit(analysis);
  if (!analysis) return base;
  return `${base}${renderStructuredFit(analysis)}`;
};
