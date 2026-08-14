const routes = {
  radar: { eyebrow: "Radar", title: "Oportunidades" },
  applications: { eyebrow: "CRM", title: "Postulaciones" },
  cvs: { eyebrow: "Perfil profesional", title: "CVs" },
  settings: { eyebrow: "Administración", title: "Configuración" },
};

const sidebar = document.querySelector(".sidebar");
const detailPanel = document.getElementById("detailPanel");

function currentRoute() {
  const route = window.location.hash.replace(/^#\//, "").split("/")[0];
  return routes[route] ? route : "radar";
}

function renderRoute() {
  const route = currentRoute();
  const meta = routes[route];

  document.querySelectorAll("[data-view]").forEach((view) => {
    view.classList.toggle("active", view.dataset.view === route);
  });
  document.querySelectorAll("[data-route]").forEach((link) => {
    const active = link.dataset.route === route;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });

  document.getElementById("eyebrow").textContent = meta.eyebrow;
  document.getElementById("pageTitle").textContent = meta.title;
  sidebar.classList.remove("open");
  document.title = `${meta.title} · Job Radar`;
}

function setRadarFilter(filter) {
  document.querySelectorAll("[data-radar-filter]").forEach((control) => {
    control.classList.toggle("active", control.dataset.radarFilter === filter);
  });
}

document.querySelectorAll("[data-radar-filter]").forEach((control) => {
  control.addEventListener("click", () => setRadarFilter(control.dataset.radarFilter));
});

document.getElementById("mobileNav").addEventListener("click", () => {
  sidebar.classList.toggle("open");
});

document.getElementById("detailClose").addEventListener("click", () => {
  detailPanel.classList.remove("open");
});

window.addEventListener("hashchange", renderRoute);

if (!window.location.hash) {
  window.location.hash = "#/radar";
} else {
  renderRoute();
}
