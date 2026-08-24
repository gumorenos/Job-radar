const radarPageSize = 50;
let radarPageItems = [];
let radarPageTotal = 0;
let radarPageContext = "";
let radarPageRequestId = 0;

function radarPagingContext() {
  return `${radarFilter}\u0000${opportunitySearch.value.trim()}`;
}

function resetRadarPaging() {
  radarPageItems = [];
  radarPageTotal = 0;
  radarPageContext = radarPagingContext();
}

function cancelRadarPaging() {
  radarPageRequestId += 1;
  radarPageItems = [];
  radarPageTotal = 0;
  radarPageContext = "";
}

function bindRadarLoadMore() {
  const button = document.getElementById("radarLoadMore");
  if (button) {
    button.addEventListener("click", () => loadRadarJobs({ append: true }));
  }
}

function renderRadarPage() {
  renderJobs(radarPageItems);
  const remaining = Math.max(0, radarPageTotal - radarPageItems.length);
  if (!remaining) return;

  opportunityList.insertAdjacentHTML("beforeend", `
    <div class="radar-load-more">
      <span>Mostrando ${radarPageItems.length} de ${radarPageTotal}</span>
      <button type="button" class="secondary" id="radarLoadMore">
        Cargar más · ${Math.min(radarPageSize, remaining)}
      </button>
    </div>`);
  bindRadarLoadMore();
}

async function loadPaginatedRadarJobs({ append = false } = {}) {
  const context = radarPagingContext();
  if (!append || context !== radarPageContext) resetRadarPaging();

  const requestId = ++radarPageRequestId;
  const offset = append ? radarPageItems.length : 0;
  if (!append) {
    opportunityList.innerHTML = `<div class="list-loading">Cargando oportunidades…</div>`;
  } else {
    const button = document.getElementById("radarLoadMore");
    if (button) {
      button.disabled = true;
      button.textContent = "Cargando…";
    }
  }

  const params = new URLSearchParams({
    view: radarFilter,
    limit: String(radarPageSize),
    offset: String(offset),
  });
  const search = opportunitySearch.value.trim();
  if (search) params.set("q", search);

  try {
    const result = await api(`/api/v1/radar/jobs?${params}`);
    if (requestId !== radarPageRequestId || context !== radarPagingContext()) return;
    radarPageItems = append ? [...radarPageItems, ...result.items] : result.items;
    radarPageTotal = result.total;
    renderRadarPage();
  } catch (error) {
    if (requestId !== radarPageRequestId) return;
    opportunityList.innerHTML = `
      <div class="empty-state error-state">
        <h2>No se pudo cargar Radar</h2>
        <p>${escapeHtml(error.message)}</p>
      </div>`;
  }
}

loadRadarJobs = async function loadRadarJobsWithPaging(options = {}) {
  await loadPaginatedRadarJobs(options);
};

opportunitySearch.addEventListener("input", () => {
  radarPageRequestId += 1;
  radarPageContext = "";
});

if (currentRoute() === "radar" && radarFilter !== "duplicates") {
  loadRadarJobs();
}
