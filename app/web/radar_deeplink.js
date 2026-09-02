function radarDeepLinkJobId() {
  const match = window.location.hash.match(
    /^#\/radar\/([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/i,
  );
  return match ? match[1] : null;
}

let lastRadarDeepLink = null;

async function openRadarDeepLink() {
  const jobId = radarDeepLinkJobId();
  if (!jobId || currentRoute() !== "radar") return;
  const currentKey = `${window.location.hash}:${jobId}`;
  if (currentKey === lastRadarDeepLink && detailPanel.classList.contains("open")) return;
  lastRadarDeepLink = currentKey;
  await loadJobDetail(jobId);
}

window.addEventListener("hashchange", () => {
  window.setTimeout(openRadarDeepLink, 0);
});

openRadarDeepLink();
