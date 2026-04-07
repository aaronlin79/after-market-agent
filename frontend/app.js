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

const SECTION_COPY = {
  "Must Know": "Highest-signal developments that deserve attention before the market opens.",
  "Watch at Open": "Relevant developments to keep on-screen as price discovery starts.",
  "Undercovered but Important": "Potentially meaningful stories with limited coverage that could still matter.",
  "SEC Filings Worth Checking": "Filing-driven developments that may require direct source review.",
  "Likely Noise": "Lower-confidence items that are worth noting but not leading with.",
};

const elements = {
  appBanner: document.getElementById("app-banner"),
  navLinks: document.querySelectorAll(".nav-link"),
  views: document.querySelectorAll(".view"),
  runNowButton: document.getElementById("run-now-button"),
  refreshButton: document.getElementById("refresh-button"),
  runFeedback: document.getElementById("run-feedback"),
  latestRunPill: document.getElementById("latest-run-pill"),
  heroWatchlistName: document.getElementById("hero-watchlist-name"),
  heroWatchlistSummary: document.getElementById("hero-watchlist-summary"),
  heroSymbolCount: document.getElementById("hero-symbol-count"),
  heroDigestStatus: document.getElementById("hero-digest-status"),
  heroRunStatus: document.getElementById("hero-run-status"),
  dashboardEmptyState: document.getElementById("dashboard-empty-state"),
  dashboardPanels: document.getElementById("dashboard-panels"),
  digestTitle: document.getElementById("digest-title"),
  digestMeta: document.getElementById("digest-meta"),
  digestSections: document.getElementById("digest-sections"),
  digestLoading: document.getElementById("digest-loading"),
  digestError: document.getElementById("digest-error"),
  clustersLoading: document.getElementById("clusters-loading"),
  clustersError: document.getElementById("clusters-error"),
  rankedClusters: document.getElementById("ranked-clusters"),
  watchlistsLoading: document.getElementById("watchlists-loading"),
  watchlistsError: document.getElementById("watchlists-error"),
  watchlistList: document.getElementById("watchlist-list"),
  watchlistForm: document.getElementById("watchlist-form"),
  watchlistEditForm: document.getElementById("watchlist-edit-form"),
  selectedWatchlistTitle: document.getElementById("selected-watchlist-title"),
  watchlistDetailEmpty: document.getElementById("watchlist-detail-empty"),
  watchlistDetail: document.getElementById("watchlist-detail"),
  watchlistActionFeedback: document.getElementById("watchlist-action-feedback"),
  symbolForm: document.getElementById("symbol-form"),
  symbolList: document.getElementById("symbol-list"),
  sampleSymbols: document.getElementById("sample-symbols"),
  sampleSymbolButtons: document.querySelectorAll(".sample-symbol-button"),
  runsLoading: document.getElementById("runs-loading"),
  runsError: document.getElementById("runs-error"),
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

  if (response.status === 204) {
    return null;
  }

  const rawBody = await response.text();
  let parsedBody = null;
  if (rawBody) {
    try {
      parsedBody = JSON.parse(rawBody);
    } catch (_error) {
      parsedBody = rawBody;
    }
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    if (parsedBody && typeof parsedBody === "object" && !Array.isArray(parsedBody)) {
      const payload = parsedBody;
      detail = payload.detail || JSON.stringify(payload);
    } else if (typeof parsedBody === "string" && parsedBody.trim()) {
      detail = parsedBody;
    }
    throw new Error(detail);
  }

  return parsedBody;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setActiveView(viewName) {
  elements.navLinks.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  elements.views.forEach((view) => {
    view.classList.toggle("active", view.id === `${viewName}-view`);
  });
}

function setBanner(message = "", kind = "success") {
  if (!message) {
    elements.appBanner.className = "app-banner hidden";
    elements.appBanner.textContent = "";
    return;
  }
  elements.appBanner.className = `app-banner ${kind}`;
  elements.appBanner.textContent = message;
}

function setBlockState({ loadingEl = null, errorEl = null, loading = false, error = "" }) {
  if (loadingEl) {
    loadingEl.classList.toggle("hidden", !loading);
  }
  if (errorEl) {
    errorEl.classList.toggle("hidden", !error);
    errorEl.textContent = error;
  }
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

function isMeaningfulDigest(digest) {
  return Boolean(digest && Array.isArray(digest.entries) && digest.entries.length > 0);
}

function inferSectionFromCluster(cluster) {
  if (cluster.event_type === "sec_filing") {
    return "SEC Filings Worth Checking";
  }
  if (cluster.undercovered_important) {
    return "Undercovered but Important";
  }
  if ((cluster.importance_score || 0) < 0.45 || cluster.confidence === "low") {
    return "Likely Noise";
  }
  if ((cluster.importance_score || 0) >= 0.75 && ["medium", "high"].includes(cluster.confidence)) {
    return "Must Know";
  }
  return "Watch at Open";
}

function buildFallbackDigestFromRankedClusters() {
  if (!state.rankedClusters.length) {
    return null;
  }

  const entries = state.rankedClusters.slice(0, 8).map((cluster, index) => ({
    id: `fallback-${cluster.cluster_id || index}`,
    section_name: inferSectionFromCluster(cluster),
    rank: index + 1,
    cluster_id: cluster.cluster_id || null,
    cluster_key: cluster.cluster_id || null,
    representative_title: cluster.representative_title || "Untitled cluster",
    primary_symbol: cluster.primary_symbol || "UNKNOWN",
    event_type: cluster.event_type || "other",
    confidence: cluster.confidence || "unknown",
    importance_score: cluster.importance_score || 0,
    article_count: cluster.article_count || 0,
    summary_text: cluster.summary_text || "No summary available.",
    why_it_matters: cluster.why_it_matters || "Why it matters is not available.",
    unknowns: Array.isArray(cluster.unknowns) ? cluster.unknowns : [],
    undercovered_important: Boolean(cluster.undercovered_important),
  }));

  const symbols = [];
  entries.forEach((entry) => {
    if (entry.primary_symbol !== "UNKNOWN" && !symbols.includes(entry.primary_symbol)) {
      symbols.push(entry.primary_symbol);
    }
  });

  return {
    subject_line: `Morning Brief — ${entries.length} items | ${symbols.slice(0, 3).join(", ") || "Top Signals"}`,
    generated_at: null,
    delivery_status: "live",
    entries,
    is_fallback: true,
  };
}

function selectedWatchlist() {
  return state.watchlists.find((item) => item.id === state.selectedWatchlistId) || null;
}

function renderHero() {
  const watchlist = selectedWatchlist() || state.watchlists[0] || null;
  const latestRun = state.pipelineRuns[0] || null;

  if (!watchlist) {
    elements.heroWatchlistName.textContent = "Create your first watchlist";
    elements.heroWatchlistSummary.textContent = "Add the names you want monitored before tomorrow’s open, then run the pipeline.";
    elements.heroSymbolCount.textContent = "0";
  } else {
    elements.heroWatchlistName.textContent = watchlist.name;
    elements.heroWatchlistSummary.textContent = watchlist.symbol_count
      ? `${watchlist.symbol_count} tracked symbols ready for the next digest.`
      : "This watchlist is empty. Add symbols before running the pipeline.";
    elements.heroSymbolCount.textContent = String(watchlist.symbol_count || 0);
  }

  elements.heroDigestStatus.textContent = state.latestDigest ? "Ready" : "Not generated";
  elements.heroRunStatus.textContent = latestRun ? latestRun.status : "No runs yet";
}

function renderWatchlists() {
  elements.watchlistList.innerHTML = "";

  if (!state.watchlists.length) {
    elements.watchlistList.innerHTML = '<div class="empty-state"><h3>No watchlists yet</h3><p>Create one to start building tomorrow morning’s brief.</p></div>';
    renderWatchlistDetail(null);
    renderHero();
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
  renderHero();
}

function renderWatchlistDetail(watchlist) {
  if (!watchlist) {
    elements.selectedWatchlistTitle.textContent = "Select a watchlist";
    elements.watchlistDetailEmpty.innerHTML = "Choose a watchlist to edit symbols.";
    elements.watchlistDetailEmpty.classList.remove("hidden");
    elements.watchlistDetail.classList.add("hidden");
    elements.symbolList.innerHTML = "";
    elements.watchlistActionFeedback.textContent = "";
    elements.sampleSymbols.classList.add("hidden");
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
    elements.sampleSymbols.classList.remove("hidden");
    elements.symbolList.innerHTML = '<div class="empty-state"><h3>No symbols yet</h3><p>Add symbols below so the pipeline has something to monitor before the next run.</p></div>';
    return;
  }

  elements.sampleSymbols.classList.add("hidden");
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
        elements.watchlistActionFeedback.textContent = `Removing ${symbol.symbol}...`;
        await api(`/watchlists/${watchlist.id}/symbols/${symbol.id}`, { method: "DELETE" });
        elements.watchlistActionFeedback.textContent = `${symbol.symbol} removed from ${watchlist.name}.`;
        await loadWatchlists(watchlist.id);
      } catch (error) {
        elements.watchlistActionFeedback.textContent = `Could not remove ${symbol.symbol}: ${error.message}`;
        setBanner(`Could not remove ${symbol.symbol}. ${error.message}`, "error");
      }
    });
    elements.symbolList.appendChild(item);
  });
}

function renderDigest() {
  const digest = isMeaningfulDigest(state.latestDigest) ? state.latestDigest : buildFallbackDigestFromRankedClusters();
  elements.digestSections.innerHTML = "";

  if (!digest) {
    elements.dashboardEmptyState.classList.remove("hidden");
    elements.dashboardPanels.classList.add("hidden");
    elements.digestTitle.textContent = "No digest available yet";
    elements.digestMeta.textContent = "Run the morning pipeline once your watchlist is ready.";
    return;
  }

  elements.dashboardEmptyState.classList.add("hidden");
  elements.dashboardPanels.classList.remove("hidden");
  elements.digestTitle.textContent = digest.subject_line;
  elements.digestMeta.textContent = digest.is_fallback
    ? "Showing live ranked clusters because the latest stored digest has no surfaced entries yet."
    : `Generated ${formatDateTime(digest.generated_at)} • delivery ${digest.delivery_status}`;

  const grouped = new Map();
  digest.entries.forEach((entry) => {
    const section = entry.section_name || "Watch at Open";
    if (!grouped.has(section)) {
      grouped.set(section, []);
    }
    grouped.get(section).push(entry);
  });

  const populatedSections = SECTION_ORDER.filter((sectionName) => (grouped.get(sectionName) || []).length > 0);
  if (!populatedSections.length) {
    elements.digestSections.innerHTML = '<div class="empty-state"><h3>No surfaced stories</h3><p>The digest exists but does not yet contain ranked items for this watchlist.</p></div>';
    return;
  }

  populatedSections.forEach((sectionName) => {
    const entries = grouped.get(sectionName) || [];
    const section = document.createElement("section");
    section.className = "section-block";
    section.innerHTML = `
      <div class="panel-header">
        <div>
          <h3>${escapeHtml(sectionName)}</h3>
          <p class="section-copy">${escapeHtml(SECTION_COPY[sectionName] || "")}</p>
        </div>
        <span class="badge subtle">${entries.length} item${entries.length === 1 ? "" : "s"}</span>
      </div>
    `;

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

      if (Array.isArray(entry.unknowns) && entry.unknowns.length) {
        const unknowns = document.createElement("div");
        unknowns.className = "unknowns-box";
        unknowns.innerHTML = `
          <div class="card-label">Still unclear</div>
          <ul class="unknowns-list">${entry.unknowns.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul>
        `;
        node.appendChild(unknowns);
      }

      section.appendChild(node);
    });

    elements.digestSections.appendChild(section);
  });
}

function renderRankedClusters() {
  elements.rankedClusters.innerHTML = "";

  if (!state.rankedClusters.length) {
    elements.rankedClusters.innerHTML = '<div class="empty-state"><h3>No ranked clusters yet</h3><p>Run the pipeline to populate the top signals list.</p></div>';
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
      ${Array.isArray(cluster.unknowns) && cluster.unknowns.length ? `<div class="cluster-meta small">Still unclear: ${escapeHtml(cluster.unknowns.join(" • "))}</div>` : ""}
      <div class="cluster-meta small">Article count: ${cluster.article_count || 0}</div>
    `;
    elements.rankedClusters.appendChild(card);
  });
}

function renderRuns() {
  elements.runList.innerHTML = "";
  elements.runSummary.innerHTML = "";

  if (!state.pipelineRuns.length) {
    elements.runList.innerHTML = '<div class="empty-state"><h3>No recent runs</h3><p>Pipeline history will appear here after the first run.</p></div>';
    elements.runSummary.innerHTML = '<div class="empty-state"><h3>Status summary</h3><p>The latest successful and failed runs will appear here once the pipeline has executed.</p></div>';
    elements.latestRunPill.textContent = "No runs yet";
    renderHero();
    return;
  }

  const latestRun = state.pipelineRuns[0];
  elements.latestRunPill.textContent = `${latestRun.run_type} • ${latestRun.status}`;

  state.pipelineRuns.slice(0, 8).forEach((run) => {
    const card = document.createElement("article");
    card.className = "run-card";
    const metrics = formatRunMetrics(run.metrics_json);
    card.innerHTML = `
      <div class="topbar">
        <div>
          <h4>${escapeHtml(run.run_type)}</h4>
          <p>${escapeHtml(run.status)} • ${formatDateTime(run.started_at)}</p>
        </div>
        <span class="badge subtle">${run.duration_ms ?? "?"} ms</span>
      </div>
      ${metrics ? `<div class="run-metrics small">${escapeHtml(metrics)}</div>` : ""}
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

  renderHero();
}

function formatRunMetrics(metrics) {
  if (!metrics || typeof metrics !== "object") {
    return "";
  }
  const orderedKeys = [
    "fetched_count",
    "inserted_count",
    "cluster_count",
    "summaries_generated",
    "ranked_count",
    "digest_id",
    "emailed",
  ];
  const formatted = orderedKeys
    .filter((key) => key in metrics)
    .map((key) => `${key.replaceAll("_", " ")}: ${metrics[key]}`);
  return formatted.join(" • ");
}

async function loadLatestDigest() {
  setBlockState({ loadingEl: elements.digestLoading, errorEl: elements.digestError, loading: true, error: "" });
  try {
    const digests = await api("/digests");
    if (!digests.length) {
      state.latestDigest = null;
      renderDigest();
      return;
    }
    state.latestDigest = await api(`/digests/${digests[0].id}`);
    renderDigest();
  } catch (error) {
    state.latestDigest = null;
    renderDigest();
    setBlockState({
      loadingEl: elements.digestLoading,
      errorEl: elements.digestError,
      loading: false,
      error: `Could not load the latest digest. ${error.message}`,
    });
    return;
  }
  setBlockState({ loadingEl: elements.digestLoading, errorEl: elements.digestError, loading: false, error: "" });
}

async function loadRankedClusters() {
  setBlockState({ loadingEl: elements.clustersLoading, errorEl: elements.clustersError, loading: true, error: "" });
  try {
    state.rankedClusters = await api("/clusters/ranked");
    renderRankedClusters();
    if (!isMeaningfulDigest(state.latestDigest)) {
      renderDigest();
    }
    setBlockState({ loadingEl: elements.clustersLoading, errorEl: elements.clustersError, loading: false, error: "" });
  } catch (error) {
    state.rankedClusters = [];
    renderRankedClusters();
    if (!isMeaningfulDigest(state.latestDigest)) {
      renderDigest();
    }
    setBlockState({
      loadingEl: elements.clustersLoading,
      errorEl: elements.clustersError,
      loading: false,
      error: `Could not load ranked clusters. ${error.message}`,
    });
  }
}

async function loadPipelineRuns() {
  setBlockState({ loadingEl: elements.runsLoading, errorEl: elements.runsError, loading: true, error: "" });
  try {
    state.pipelineRuns = await api("/admin/pipeline-runs");
    renderRuns();
    setBlockState({ loadingEl: elements.runsLoading, errorEl: elements.runsError, loading: false, error: "" });
  } catch (error) {
    state.pipelineRuns = [];
    renderRuns();
    setBlockState({
      loadingEl: elements.runsLoading,
      errorEl: elements.runsError,
      loading: false,
      error: `Could not load pipeline history. ${error.message}`,
    });
  }
}

async function loadWatchlists(preferredWatchlistId = null) {
  setBlockState({ loadingEl: elements.watchlistsLoading, errorEl: elements.watchlistsError, loading: true, error: "" });
  try {
    const watchlists = await api("/watchlists");
    state.watchlists = watchlists;

    const nextSelectedId = preferredWatchlistId
      || state.selectedWatchlistId
      || (watchlists[0] ? watchlists[0].id : null);

    if (!nextSelectedId) {
      state.selectedWatchlistId = null;
      renderWatchlists();
      setBlockState({ loadingEl: elements.watchlistsLoading, errorEl: elements.watchlistsError, loading: false, error: "" });
      return;
    }

    await loadWatchlistDetail(nextSelectedId, watchlists);
    setBlockState({ loadingEl: elements.watchlistsLoading, errorEl: elements.watchlistsError, loading: false, error: "" });
  } catch (error) {
    state.watchlists = [];
    state.selectedWatchlistId = null;
    renderWatchlists();
    setBlockState({
      loadingEl: elements.watchlistsLoading,
      errorEl: elements.watchlistsError,
      loading: false,
      error: `Could not load watchlists. ${error.message}`,
    });
  }
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
    setBanner("Create a watchlist and add symbols before running the pipeline.", "error");
    setActiveView("watchlists");
    return;
  }

  if (!(targetWatchlist.symbols?.length || targetWatchlist.symbol_count > 0)) {
    setBanner("Add at least one symbol before running the pipeline.", "error");
    setActiveView("watchlists");
    return;
  }

  elements.runNowButton.disabled = true;
  elements.refreshButton.disabled = true;
  elements.runNowButton.textContent = "Running...";
  elements.runFeedback.textContent = `Running the morning pipeline for ${targetWatchlist.name}...`;
  setBanner("", "success");

  try {
    const result = await api("/jobs/morning-run", {
      method: "POST",
      body: JSON.stringify({ watchlist_id: targetWatchlist.id }),
    });
    elements.runFeedback.textContent =
      `Complete: ${result.fetched_count} fetched, ${result.inserted_count} inserted, ${result.cluster_count} clusters, ${result.summaries_generated} summaries, ${result.ranked_count} ranked, digest ${result.digest_id ?? "not generated"}, emailed ${result.emailed}.`;
    setBanner("Morning run finished successfully. The dashboard has been refreshed.", "success");
    await refreshDashboard();
  } catch (error) {
    elements.runFeedback.textContent = `Run failed. ${error.message}`;
    setBanner(`Morning run failed. ${error.message} Check Runs & Status for details.`, "error");
    setActiveView("runs");
    await loadPipelineRuns();
  } finally {
    elements.runNowButton.disabled = false;
    elements.refreshButton.disabled = false;
    elements.runNowButton.textContent = "Run now";
  }
}

async function refreshDashboard() {
  await Promise.all([
    loadLatestDigest(),
    loadRankedClusters(),
    loadPipelineRuns(),
    loadWatchlists(state.selectedWatchlistId),
  ]);
}

async function handleWatchlistCreate(event) {
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
    elements.watchlistActionFeedback.textContent = `Created ${created.name}.`;
    setBanner(`Created watchlist ${created.name}.`, "success");
    await loadWatchlists(created.id);
  } catch (error) {
    setBanner(`Could not create watchlist. ${error.message}`, "error");
  }
}

async function handleWatchlistUpdate(event) {
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
    elements.watchlistActionFeedback.textContent = `Saved changes to ${form.get("name")}.`;
    setBanner("Watchlist updated.", "success");
    await loadWatchlists(watchlist.id);
  } catch (error) {
    elements.watchlistActionFeedback.textContent = `Could not update watchlist. ${error.message}`;
    setBanner(`Could not update watchlist. ${error.message}`, "error");
  }
}

async function addSymbol(payload) {
  const watchlist = selectedWatchlist();
  if (!watchlist) {
    setBanner("Select a watchlist before adding symbols.", "error");
    return;
  }
  try {
    await api(`/watchlists/${watchlist.id}/symbols`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.watchlistActionFeedback.textContent = `${payload.symbol} added to ${watchlist.name}.`;
    setBanner(`Added ${payload.symbol} to ${watchlist.name}.`, "success");
    await loadWatchlists(watchlist.id);
  } catch (error) {
    const duplicate = error.message.toLowerCase().includes("already") || error.message.includes("409");
    const message = duplicate
      ? `${payload.symbol} is already on this watchlist.`
      : `Could not add ${payload.symbol}. ${error.message}`;
    elements.watchlistActionFeedback.textContent = message;
    setBanner(message, "error");
  }
}

async function handleSymbolSubmit(event) {
  event.preventDefault();
  const form = new FormData(elements.symbolForm);
  await addSymbol({
    symbol: form.get("symbol"),
    company_name: form.get("company_name"),
    sector: form.get("sector") || null,
    priority_weight: Number(form.get("priority_weight") || "1"),
  });
  elements.symbolForm.reset();
  elements.symbolForm.elements.priority_weight.value = "1.0";
}

function attachEventListeners() {
  elements.navLinks.forEach((button) => {
    button.addEventListener("click", () => setActiveView(button.dataset.view));
  });

  document.querySelectorAll("[data-jump]").forEach((button) => {
    button.addEventListener("click", () => setActiveView(button.dataset.jump));
  });

  elements.runNowButton.addEventListener("click", handleRunNow);
  elements.refreshButton.addEventListener("click", async () => {
    elements.runFeedback.textContent = "Refreshing dashboard data...";
    await refreshDashboard();
    elements.runFeedback.textContent = "Dashboard refreshed.";
  });
  elements.watchlistForm.addEventListener("submit", handleWatchlistCreate);
  elements.watchlistEditForm.addEventListener("submit", handleWatchlistUpdate);
  elements.symbolForm.addEventListener("submit", handleSymbolSubmit);

  elements.sampleSymbolButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      await addSymbol({
        symbol: button.dataset.symbol,
        company_name: button.dataset.companyName,
        sector: null,
        priority_weight: 1.0,
      });
    });
  });
}

async function init() {
  attachEventListeners();
  setBanner("", "success");
  try {
    await refreshDashboard();
    elements.runFeedback.textContent = "Ready. Configure the watchlist or run the pipeline.";
  } catch (error) {
    elements.runFeedback.textContent = `Initial load failed. ${error.message}`;
    setBanner(`Could not connect cleanly to the backend. ${error.message}`, "error");
  }
}

init();
