const state = {
  watchlists: [],
  selectedWatchlistId: null,
  latestDigest: null,
  rankedClusters: [],
  pipelineRuns: [],
};

const SECTION_ORDER = [
  "Must Know",
  "Watch at Open",
  "Undercovered but Important",
  "SEC Filings Worth Checking",
  "Likely Noise",
];

const elements = {
  navLinks: document.querySelectorAll(".nav-link"),
  views: document.querySelectorAll(".view"),
  runNowButton: document.getElementById("run-now-button"),
  runFeedback: document.getElementById("run-feedback"),
  latestRunPill: document.getElementById("latest-run-pill"),
  dashboardEmptyState: document.getElementById("dashboard-empty-state"),
  dashboardPanels: document.getElementById("dashboard-panels"),
  digestTitle: document.getElementById("digest-title"),
  digestMeta: document.getElementById("digest-meta"),
  digestSections: document.getElementById("digest-sections"),
  rankedClusters: document.getElementById("ranked-clusters"),
  watchlistList: document.getElementById("watchlist-list"),
  watchlistForm: document.getElementById("watchlist-form"),
  watchlistEditForm: document.getElementById("watchlist-edit-form"),
  selectedWatchlistTitle: document.getElementById("selected-watchlist-title"),
  watchlistDetailEmpty: document.getElementById("watchlist-detail-empty"),
  watchlistDetail: document.getElementById("watchlist-detail"),
  symbolForm: document.getElementById("symbol-form"),
  symbolList: document.getElementById("symbol-list"),
  runList: document.getElementById("run-list"),
  runSummary: document.getElementById("run-summary"),
  digestEntryTemplate: document.getElementById("digest-entry-template"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch (_error) {
      detail = await response.text();
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function setActiveView(viewName) {
  elements.navLinks.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  elements.views.forEach((view) => {
    view.classList.toggle("active", view.id === `${viewName}-view`);
  });
}

function formatDateTime(value) {
  if (!value) {
    return "Unavailable";
  }
  return new Date(value).toLocaleString();
}

function formatScore(value) {
  return typeof value === "number" ? value.toFixed(2) : "0.00";
}

function selectedWatchlist() {
  return state.watchlists.find((item) => item.id === state.selectedWatchlistId) || null;
}

function renderWatchlists() {
  elements.watchlistList.innerHTML = "";

  if (!state.watchlists.length) {
    elements.watchlistList.innerHTML = '<div class="muted">No watchlists yet. Create one to get started.</div>';
    renderWatchlistDetail(null);
    return;
  }

  state.watchlists.forEach((watchlist) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "watchlist-card";
    if (watchlist.id === state.selectedWatchlistId) {
      button.classList.add("active");
    }
    button.innerHTML = `
      <div class="topbar">
        <div>
          <h4>${escapeHtml(watchlist.name)}</h4>
          <p class="muted">${escapeHtml(watchlist.description || "No description yet.")}</p>
        </div>
        <span class="badge subtle">${watchlist.symbol_count} symbols</span>
      </div>
    `;
    button.addEventListener("click", async () => {
      await loadWatchlistDetail(watchlist.id);
    });
    elements.watchlistList.appendChild(button);
  });

  renderWatchlistDetail(selectedWatchlist());
}

function renderWatchlistDetail(watchlist) {
  if (!watchlist) {
    elements.selectedWatchlistTitle.textContent = "Select a watchlist";
    elements.watchlistDetailEmpty.classList.remove("hidden");
    elements.watchlistDetail.classList.add("hidden");
    elements.symbolList.innerHTML = "";
    elements.watchlistEditForm.reset();
    return;
  }

  elements.selectedWatchlistTitle.textContent = watchlist.name;
  elements.watchlistDetailEmpty.classList.add("hidden");
  elements.watchlistDetail.classList.remove("hidden");
  elements.watchlistEditForm.elements.name.value = watchlist.name;
  elements.watchlistEditForm.elements.description.value = watchlist.description || "";

  elements.symbolList.innerHTML = "";
  if (!watchlist.symbols?.length) {
    elements.symbolList.innerHTML = '<div class="muted">No symbols yet. Add one below.</div>';
    return;
  }

  const sortedSymbols = [...watchlist.symbols].sort((left, right) => left.symbol.localeCompare(right.symbol));
  sortedSymbols.forEach((symbol) => {
    const item = document.createElement("div");
    item.className = "symbol-chip";
    item.innerHTML = `
      <div>
        <strong>${escapeHtml(symbol.symbol)}</strong>
        <div class="muted small">${escapeHtml(symbol.company_name)}${symbol.sector ? ` • ${escapeHtml(symbol.sector)}` : ""}</div>
      </div>
      <div class="topbar">
        <span class="badge subtle">Weight ${Number(symbol.priority_weight).toFixed(1)}</span>
        <button class="symbol-remove" type="button">Remove</button>
      </div>
    `;
    item.querySelector("button").addEventListener("click", async () => {
      try {
        await api(`/watchlists/${watchlist.id}/symbols/${symbol.id}`, { method: "DELETE" });
        await loadWatchlists(watchlist.id);
      } catch (error) {
        window.alert(error.message);
      }
    });
    elements.symbolList.appendChild(item);
  });
}

function renderDigest() {
  const digest = state.latestDigest;
  elements.digestSections.innerHTML = "";

  if (!digest) {
    elements.dashboardEmptyState.classList.remove("hidden");
    elements.dashboardPanels.classList.add("hidden");
    elements.digestTitle.textContent = "No digest available";
    elements.digestMeta.textContent = "";
    return;
  }

  elements.dashboardEmptyState.classList.add("hidden");
  elements.dashboardPanels.classList.remove("hidden");
  elements.digestTitle.textContent = digest.subject_line;
  elements.digestMeta.textContent = `Generated ${formatDateTime(digest.generated_at)} • ${digest.delivery_status}`;

  const grouped = new Map();
  digest.entries.forEach((entry) => {
    const section = entry.section_name || "Watch at Open";
    if (!grouped.has(section)) {
      grouped.set(section, []);
    }
    grouped.get(section).push(entry);
  });

  SECTION_ORDER.forEach((sectionName) => {
    const entries = grouped.get(sectionName) || [];
    if (!entries.length) {
      return;
    }

    const section = document.createElement("section");
    section.className = "section-block";
    section.innerHTML = `<h3>${escapeHtml(sectionName)}</h3>`;

    entries.forEach((entry) => {
      const node = elements.digestEntryTemplate.content.firstElementChild.cloneNode(true);
      node.querySelector(".symbol").textContent = entry.primary_symbol || "UNKNOWN";
      node.querySelector(".event-type").textContent = entry.event_type || "other";
      node.querySelector(".confidence").textContent = entry.confidence || "unknown";
      node.querySelector(".headline").textContent = entry.representative_title || "Untitled cluster";
      node.querySelector(".summary").textContent = entry.summary_text || "No summary available.";
      node.querySelector(".why").textContent = entry.why_it_matters || "Why it matters is not available.";
      node.querySelector(".article-count").textContent = `${entry.article_count || 0} source article${entry.article_count === 1 ? "" : "s"}`;
      node.querySelector(".score-value").textContent = formatScore(entry.importance_score);
      const undercovered = node.querySelector(".undercovered");
      if (entry.undercovered_important) {
        undercovered.classList.remove("hidden");
      }
      section.appendChild(node);
    });

    elements.digestSections.appendChild(section);
  });
}

function renderRankedClusters() {
  elements.rankedClusters.innerHTML = "";

  if (!state.rankedClusters.length) {
    elements.rankedClusters.innerHTML = '<div class="muted">No ranked clusters yet.</div>';
    return;
  }

  state.rankedClusters.slice(0, 8).forEach((cluster) => {
    const card = document.createElement("article");
    card.className = "cluster-row";
    card.innerHTML = `
      <div class="digest-header">
        <div>
          <div class="symbol-row">
            <span class="symbol">${escapeHtml(cluster.primary_symbol || "UNKNOWN")}</span>
            <span class="badge subtle">${escapeHtml(cluster.event_type || "other")}</span>
            <span class="badge confidence">${escapeHtml(cluster.confidence || "unknown")}</span>
            ${cluster.undercovered_important ? '<span class="badge warning">Undercovered but important</span>' : ""}
          </div>
          <h4>${escapeHtml(cluster.representative_title || "Untitled cluster")}</h4>
        </div>
        <div class="score-block compact">
          <div class="score-label">Importance</div>
          <div class="score-value">${formatScore(cluster.importance_score)}</div>
        </div>
      </div>
      <p>${escapeHtml(cluster.summary_text || "No summary available.")}</p>
      <div class="why-box">
        <div class="card-label">Why it matters</div>
        <p>${escapeHtml(cluster.why_it_matters || "Why it matters is not available.")}</p>
      </div>
      <div class="cluster-meta small">Article count: ${cluster.article_count || 0}</div>
    `;
    elements.rankedClusters.appendChild(card);
  });
}

function renderRuns() {
  elements.runList.innerHTML = "";
  elements.runSummary.innerHTML = "";

  if (!state.pipelineRuns.length) {
    elements.runList.innerHTML = '<div class="muted">No pipeline runs yet.</div>';
    elements.runSummary.innerHTML = '<div class="muted">Run the pipeline to see operational status.</div>';
    elements.latestRunPill.textContent = "No runs yet";
    return;
  }

  const latestRun = state.pipelineRuns[0];
  elements.latestRunPill.textContent = `${latestRun.run_type} • ${latestRun.status}`;

  state.pipelineRuns.slice(0, 8).forEach((run) => {
    const card = document.createElement("article");
    card.className = "run-card";
    const metrics = run.metrics_json ? `<div class="run-metrics small">${escapeHtml(JSON.stringify(run.metrics_json))}</div>` : "";
    card.innerHTML = `
      <div class="topbar">
        <div>
          <h4>${escapeHtml(run.run_type)}</h4>
          <p>${escapeHtml(run.status)} • ${formatDateTime(run.started_at)}</p>
        </div>
        <span class="badge subtle">${run.duration_ms ?? "?"} ms</span>
      </div>
      ${metrics}
    `;
    elements.runList.appendChild(card);
  });

  const lastSuccess = state.pipelineRuns.find((run) => run.status === "success" || run.status === "partial_success");
  const lastFailure = state.pipelineRuns.find((run) => run.status === "failed");
  const summaryCards = [
    {
      title: "Last successful run",
      value: lastSuccess ? `${lastSuccess.run_type} • ${formatDateTime(lastSuccess.completed_at || lastSuccess.started_at)}` : "None yet",
    },
    {
      title: "Last failed run",
      value: lastFailure ? `${lastFailure.run_type} • ${formatDateTime(lastFailure.completed_at || lastFailure.started_at)}` : "None recently",
    },
    {
      title: "Recent run count",
      value: `${state.pipelineRuns.length} tracked runs`,
    },
  ];

  summaryCards.forEach((item) => {
    const card = document.createElement("article");
    card.className = "summary-card";
    card.innerHTML = `<h4>${escapeHtml(item.title)}</h4><p>${escapeHtml(item.value)}</p>`;
    elements.runSummary.appendChild(card);
  });
}

async function loadLatestDigest() {
  const digests = await api("/digests");
  if (!digests.length) {
    state.latestDigest = null;
    renderDigest();
    return;
  }
  state.latestDigest = await api(`/digests/${digests[0].id}`);
  renderDigest();
}

async function loadRankedClusters() {
  state.rankedClusters = await api("/clusters/ranked");
  renderRankedClusters();
}

async function loadPipelineRuns() {
  state.pipelineRuns = await api("/admin/pipeline-runs");
  renderRuns();
}

async function loadWatchlists(preferredWatchlistId = null) {
  const watchlists = await api("/watchlists");
  state.watchlists = watchlists;

  const nextSelectedId = preferredWatchlistId
    || state.selectedWatchlistId
    || (watchlists[0] ? watchlists[0].id : null);

  if (!nextSelectedId) {
    state.selectedWatchlistId = null;
    renderWatchlists();
    return;
  }

  await loadWatchlistDetail(nextSelectedId, watchlists);
}

async function loadWatchlistDetail(watchlistId, listResponse = null) {
  const detail = await api(`/watchlists/${watchlistId}`);
  state.selectedWatchlistId = detail.id;

  const summaries = listResponse || state.watchlists;
  state.watchlists = summaries.map((watchlist) => {
    if (watchlist.id !== detail.id) {
      return watchlist;
    }
    return {
      ...watchlist,
      ...detail,
      symbol_count: detail.symbols.length,
    };
  });

  if (!state.watchlists.some((watchlist) => watchlist.id === detail.id)) {
    state.watchlists = [...state.watchlists, { ...detail, symbol_count: detail.symbols.length }];
  }

  renderWatchlists();
}

async function handleRunNow() {
  const targetWatchlist = selectedWatchlist() || state.watchlists[0] || null;
  if (!targetWatchlist) {
    window.alert("Create a watchlist before running the pipeline.");
    setActiveView("watchlists");
    return;
  }

  elements.runNowButton.disabled = true;
  elements.runFeedback.textContent = "Running the full morning pipeline...";

  try {
    const result = await api("/jobs/morning-run", {
      method: "POST",
      body: JSON.stringify({ watchlist_id: targetWatchlist.id }),
    });
    elements.runFeedback.textContent = `Run complete. ${result.fetched_count} fetched, ${result.cluster_count} clusters, digest ${result.digest_id ?? "not generated"}.`;
    await refreshDashboard();
  } catch (error) {
    elements.runFeedback.textContent = `Run failed: ${error.message}`;
  } finally {
    elements.runNowButton.disabled = false;
  }
}

async function refreshDashboard() {
  await Promise.all([
    loadLatestDigest(),
    loadRankedClusters(),
    loadPipelineRuns(),
    loadWatchlists(),
  ]);
}

function attachEventListeners() {
  elements.navLinks.forEach((button) => {
    button.addEventListener("click", () => setActiveView(button.dataset.view));
  });

  document.querySelectorAll("[data-jump]").forEach((button) => {
    button.addEventListener("click", () => setActiveView(button.dataset.jump));
  });

  elements.runNowButton.addEventListener("click", handleRunNow);

  elements.watchlistForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(elements.watchlistForm);
    try {
      const created = await api("/watchlists", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          description: form.get("description") || null,
        }),
      });
      elements.watchlistForm.reset();
      await loadWatchlists(created.id);
    } catch (error) {
      window.alert(error.message);
    }
  });

  elements.watchlistEditForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const watchlist = selectedWatchlist();
    if (!watchlist) {
      return;
    }
    const form = new FormData(elements.watchlistEditForm);
    try {
      await api(`/watchlists/${watchlist.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: form.get("name"),
          description: form.get("description") || null,
        }),
      });
      await loadWatchlists(watchlist.id);
    } catch (error) {
      window.alert(error.message);
    }
  });

  elements.symbolForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const watchlist = selectedWatchlist();
    if (!watchlist) {
      return;
    }
    const form = new FormData(elements.symbolForm);
    try {
      await api(`/watchlists/${watchlist.id}/symbols`, {
        method: "POST",
        body: JSON.stringify({
          symbol: form.get("symbol"),
          company_name: form.get("company_name"),
          sector: form.get("sector") || null,
          priority_weight: Number(form.get("priority_weight") || "1"),
        }),
      });
      elements.symbolForm.reset();
      elements.symbolForm.elements.priority_weight.value = "1.0";
      await loadWatchlists(watchlist.id);
    } catch (error) {
      window.alert(error.message);
    }
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function init() {
  attachEventListeners();
  try {
    await refreshDashboard();
  } catch (error) {
    elements.runFeedback.textContent = `Initial load failed: ${error.message}`;
  }
}

init();
