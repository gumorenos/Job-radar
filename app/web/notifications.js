(() => {
  const button = document.querySelector('.topbar-actions button[aria-label="Notificaciones"]');
  if (!button) return;

  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = "/app/notifications.css";
  document.head.appendChild(stylesheet);

  button.id = "notificationButton";
  button.classList.add("notification-button");
  button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-expanded", "false");
  button.innerHTML = '<span aria-hidden="true">○</span><span class="notification-badge" hidden>0</span>';

  const drawer = document.createElement("aside");
  drawer.id = "notificationDrawer";
  drawer.className = "notification-drawer";
  drawer.setAttribute("aria-label", "Centro de notificaciones");
  drawer.setAttribute("aria-hidden", "true");
  drawer.innerHTML = `
    <div class="notification-drawer-header">
      <div><p class="eyebrow">Actividad</p><h2>Notificaciones</h2></div>
      <button class="icon-button" id="notificationClose" type="button" aria-label="Cerrar notificaciones">×</button>
    </div>
    <div class="notification-drawer-toolbar">
      <span id="notificationUnreadLabel">Cargando…</span>
      <button class="secondary compact" id="notificationReadAll" type="button">Marcar todas como leídas</button>
    </div>
    <div class="notification-list" id="notificationList" aria-live="polite"></div>`;
  document.body.appendChild(drawer);

  const badge = button.querySelector(".notification-badge");
  const closeButton = document.getElementById("notificationClose");
  const readAllButton = document.getElementById("notificationReadAll");
  const unreadLabel = document.getElementById("notificationUnreadLabel");
  const list = document.getElementById("notificationList");
  let open = false;

  function notificationEscape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[char]);
  }

  function relativeDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("es-PE", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function classificationLabel(value) {
    if (value === "HIGH_PRIORITY") return "Alta prioridad";
    if (value === "DISCARD") return "Descartada";
    return "Revisar";
  }

  function classificationClass(value) {
    if (value === "HIGH_PRIORITY") return "high";
    if (value === "DISCARD") return "discarded";
    return "review";
  }

  async function notificationApi(path, options = {}) {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    const response = await fetch(path, { ...options, headers });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function updateBadge(unread) {
    const count = Number(unread || 0);
    badge.textContent = count > 99 ? "99+" : String(count);
    badge.hidden = count === 0;
    button.setAttribute(
      "aria-label",
      count === 0 ? "Notificaciones" : `Notificaciones, ${count} sin leer`,
    );
    unreadLabel.textContent = count === 0
      ? "Todo al día"
      : `${count} ${count === 1 ? "sin leer" : "sin leer"}`;
    readAllButton.disabled = count === 0;
  }

  async function loadSummary() {
    try {
      const summary = await notificationApi("/api/v1/notifications/inbox/summary");
      updateBadge(summary.unread);
    } catch (_) {
      // Notification availability should never block the rest of the workspace.
    }
  }

  function renderInbox(items) {
    if (!items.length) {
      list.innerHTML = `
        <div class="notification-empty">
          <strong>No hay notificaciones todavía</strong>
          <p>Las oportunidades priorizadas o enviadas a Revisar aparecerán aquí.</p>
        </div>`;
      return;
    }

    list.innerHTML = items.map((item) => {
      const unread = !item.read_at;
      return `
        <button class="notification-item ${unread ? "unread" : ""}"
                type="button"
                data-notification-id="${item.id}"
                data-job-id="${item.job_id}"
                data-classification="${notificationEscape(item.classification || "REVIEW")}">
          <div class="notification-item-top">
            <span class="classification-pill ${classificationClass(item.classification)}">
              ${classificationLabel(item.classification)}
            </span>
            <time>${notificationEscape(relativeDate(item.sent_at || item.created_at))}</time>
          </div>
          <strong>${notificationEscape(item.title)}</strong>
          <span>${notificationEscape(item.company || "Empresa no indicada")}</span>
          ${item.recommendation ? `<small>${notificationEscape(item.recommendation)}</small>` : ""}
        </button>`;
    }).join("");
  }

  async function loadInbox() {
    list.innerHTML = '<div class="notification-loading">Cargando notificaciones…</div>';
    try {
      const inbox = await notificationApi("/api/v1/notifications/inbox?limit=40");
      updateBadge(inbox.unread);
      renderInbox(inbox.items);
    } catch (error) {
      list.innerHTML = `
        <div class="notification-empty error-state">
          <strong>No se pudieron cargar las notificaciones</strong>
          <p>${notificationEscape(error.message)}</p>
        </div>`;
    }
  }

  function setOpen(next) {
    open = next;
    drawer.classList.toggle("open", open);
    drawer.setAttribute("aria-hidden", String(!open));
    button.setAttribute("aria-expanded", String(open));
    if (open) loadInbox();
  }

  async function markRead(notificationId) {
    await notificationApi(`/api/v1/notifications/${notificationId}/read`, { method: "POST" });
  }

  async function openJobFromNotification(itemButton) {
    const notificationId = itemButton.dataset.notificationId;
    const jobId = itemButton.dataset.jobId;
    const classification = itemButton.dataset.classification || "REVIEW";
    try {
      await markRead(notificationId);
    } catch (_) {
      // Opening the opportunity is still useful if marking read fails transiently.
    }

    setOpen(false);
    window.location.hash = "#/radar";
    const filter = classification === "HIGH_PRIORITY"
      ? "high"
      : classification === "DISCARD" ? "discarded" : "review";
    window.setTimeout(() => {
      if (typeof setRadarFilter === "function") setRadarFilter(filter);
      if (typeof loadJobDetail === "function") loadJobDetail(jobId);
      loadSummary();
    }, 0);
  }

  button.addEventListener("click", () => setOpen(!open));
  closeButton.addEventListener("click", () => setOpen(false));
  list.addEventListener("click", (event) => {
    const item = event.target.closest("[data-notification-id]");
    if (item) openJobFromNotification(item);
  });
  readAllButton.addEventListener("click", async () => {
    readAllButton.disabled = true;
    try {
      await notificationApi("/api/v1/notifications/inbox/read-all", { method: "POST" });
      await loadInbox();
    } catch (_) {
      readAllButton.disabled = false;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && open) setOpen(false);
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadSummary();
  });
  window.setInterval(() => {
    if (!document.hidden) loadSummary();
  }, 60_000);

  loadSummary();
})();
