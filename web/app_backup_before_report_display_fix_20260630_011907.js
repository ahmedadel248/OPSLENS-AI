
const $ = (id) => document.getElementById(id);

let currentJobId = null;
let currentReport = null;
let pollTimer = null;
let scenarioDetailsFromApi = {};
let allScenariosFromApi = [];

const DEMO_CATALOG = {
  namespaces: [
    "opslens-retail",
    "opslens-platform"
  ],
  scenarios: [
    {
      id: "service-selector-mismatch",
      title: "Service selector mismatch",
      namespace: "opslens-retail",
      description: "Service selector does not match backend pod labels.",
      impact: "Impact: service has no ready backend endpoints.",
      expected: "Expected RCA: service selector mismatch."
    },
    {
      id: "readiness-probe-404",
      title: "Readiness probe 404",
      namespace: "opslens-retail",
      description: "Application is running, but the readiness probe checks a wrong path.",
      impact: "Impact: deployment has no ready replica.",
      expected: "Expected RCA: readiness probe path mismatch."
    },
    {
      id: "crashloop-startup-error",
      title: "CrashLoop startup error",
      namespace: "opslens-retail",
      description: "Application container exits during startup with a fatal error.",
      impact: "Impact: pod restarts repeatedly and the workload is unavailable.",
      expected: "Expected RCA: application startup failure."
    },
    {
      id: "missing-env-traceback",
      title: "Missing env traceback",
      namespace: "opslens-retail",
      description: "Application fails because a required environment variable is missing.",
      impact: "Impact: pod fails during startup.",
      expected: "Expected RCA: missing runtime configuration."
    },
    {
      id: "oomkilled-worker",
      title: "OOMKilled worker",
      namespace: "opslens-platform",
      description: "Worker consumes memory above its limit and gets killed by Kubernetes.",
      impact: "Impact: worker restarts and cannot complete work.",
      expected: "Expected RCA: memory limit exceeded."
    },
    {
      id: "pod-cpu-anomaly",
      title: "Pod CPU anomaly",
      namespace: "opslens-platform",
      description: "Pod consumes CPU significantly above its learned baseline.",
      impact: "Impact: performance anomaly requiring investigation.",
      expected: "Expected RCA: pod-level CPU anomaly."
    },
    {
      id: "readiness-plus-cpu-neighbor",
      title: "Readiness plus unrelated CPU neighbor",
      namespace: "opslens-platform",
      description: "Primary readiness issue exists with a separate CPU-heavy neighbor pod.",
      impact: "Impact: primary workload is not ready; neighbor CPU issue is related follow-up.",
      expected: "Expected RCA: readiness issue separated from unrelated CPU finding."
    }
  ]
};

function demoScenarioById(id) {
  return DEMO_CATALOG.scenarios.find((item) => item.id === String(id || ""));
}


const SCENARIO_DETAILS = {
  "multi_issue_k8s_chaos.yml": {
    title: "Multi-issue Kubernetes Incident",
    description: "Creates a primary service connectivity issue plus secondary workload failures for a richer RCA report.",
    impact: "Impact: frontend cannot reach backend service",
    expected: "Expected RCA: primary root cause plus additional findings"
  },
  "service_targetport_mismatch.yml": {
    title: "Service TargetPort Mismatch",
    description: "The Service routes traffic to the wrong targetPort, so traffic does not reach the application container correctly.",
    impact: "Impact: service traffic fails",
    expected: "Expected RCA: targetPort must match container port"
  },
  "scenario_targetport_mismatch.yml": {
    title: "Service TargetPort Mismatch",
    description: "The Service routes traffic to the wrong targetPort, so traffic does not reach the application container correctly.",
    impact: "Impact: service traffic fails",
    expected: "Expected RCA: targetPort must match container port"
  },
  "scenario_full_stack_incident.yml": {
    title: "Full-stack Incident",
    description: "Creates multiple Kubernetes symptoms across the selected namespace to test evidence correlation.",
    impact: "Impact: multiple resources show failure symptoms",
    expected: "Expected RCA: primary incident separated from secondary findings"
  }
};

let revealObserver = null;
let scrollRaf = null;

const views = document.querySelectorAll(".view");
const navLinks = document.querySelectorAll(".nav-link");
const drawerLinks = document.querySelectorAll(".drawer-link");
const sidebarLinks = document.querySelectorAll(".sidebar-link");

const headerMenuBtn = $("headerMenuBtn");
const drawerOverlay = $("drawerOverlay");
const appSidebar = $("appSidebar");
const supportBtn = $("supportBtn");
const sideDrawer = $("sideDrawer");

const nodeSelect = $("nodeSelect");
const clusterLoadStatus = $("clusterLoadStatus");
const namespaceSelect = $("namespaceSelect");
const scopeInfo = $("scopeInfo");
const scenarioSelect = $("scenarioSelect");
const scenarioDetailsCard = $("scenarioDetailsCard");
const scenarioTitle = $("scenarioTitle");
const scenarioDescription = $("scenarioDescription");
const scenarioImpact = $("scenarioImpact");
const scenarioExpected = $("scenarioExpected");
const applyScenario = $("applyScenario");
const resetNamespace = $("resetNamespace");
const demoMetrics = $("demoMetrics");
const waitSeconds = $("waitSeconds");
const runBtn = $("runBtn");

const pipeline = $("pipeline");
const pipelineHint = $("pipelineHint");
const timelineLog = $("timelineLog");

const emptyState = $("emptyState");
const reportSection = $("reportSection");
const reportTitle = $("reportTitle");
const storySteps = $("storySteps");
const severityBadge = $("severityBadge");
const confidenceBadge = $("confidenceBadge");
const incidentSummary = $("incidentSummary");
const rootCause = $("rootCause");
const evidenceTrail = $("evidenceTrail");
const additionalFindings = $("additionalFindings");
const fixStrategy = $("fixStrategy");
const actions = $("actions");
const commands = $("commands");
const verificationIntent = $("verificationIntent");
const verificationCommands = $("verificationCommands");

const downloadFormat = $("downloadFormat");
const downloadReportBtn = $("downloadReportBtn");
const copySummaryBtn = $("copySummaryBtn");

const toastHost = $("toastHost");
const globalStatusBar = $("globalStatusBar");
const globalStatusTitle = $("globalStatusTitle");
const globalStatusText = $("globalStatusText");
const globalStatusAction = $("globalStatusAction");
const investigationRecords = $("investigationRecords");
const clearRecordsBtn = $("clearRecordsBtn");
const refreshHistoryBtn = $("refreshHistoryBtn");

const feedbackForm = $("feedbackForm");
const feedbackStatus = $("feedbackStatus");

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json();
}

function showView(viewId) {
  localStorage.setItem("opslens_current_view", viewId);
  if (location.hash !== `#${viewId}`) {
    history.replaceState(null, "", `#${viewId}`);
  }

  views.forEach((view) => {
    const active = view.id === viewId;
    view.classList.toggle("hidden", !active);

    if (active) {
      view.classList.remove("view-enter");
      void view.offsetWidth;
      view.classList.add("view-enter");
    }
  });

  navLinks.forEach((btn) => {
    if (btn.dataset.view) {
      btn.classList.toggle("active", btn.dataset.view === viewId);
    }
  });

  sidebarLinks.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === viewId);
  });

  // clear completed status when opening report
  if (
    viewId === "reportView" &&
    globalStatusTitle &&
    globalStatusTitle.textContent.toLowerCase().includes("completed")
  ) {
    clearGlobalStatus();
  }

  closeDrawer();
  window.scrollTo({ top: 0, behavior: "smooth" });
  observeReveal();
  requestScrollMotion();
}

function toggleDrawer() {
  const isOpen = sideDrawer && sideDrawer.classList.contains("open");

  if (isOpen) {
    closeDrawer();
  } else {
    openDrawer();
  }
}

function toggleSidebar() {
  const collapsed = document.body.classList.toggle("sidebar-collapsed");
  localStorage.setItem("opslens_sidebar_collapsed", collapsed ? "1" : "0");
}

function openDrawer() {
  if (!sideDrawer || !drawerOverlay) return;
  sideDrawer.classList.add("open");
  drawerOverlay.classList.add("open");
}

function closeDrawer() {
  if (sideDrawer) sideDrawer.classList.remove("open");
  if (drawerOverlay) drawerOverlay.classList.remove("open");
}

navLinks.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.view) showView(btn.dataset.view);
  });
});

drawerLinks.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.view) showView(btn.dataset.view);
  });
});

sidebarLinks.forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.view) showView(btn.dataset.view);
  });
});

headerMenuBtn.addEventListener("click", toggleSidebar);

if (supportBtn) {
  supportBtn.addEventListener("click", () => showView("helpView"));
}
drawerOverlay.addEventListener("click", closeDrawer);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
});

function option(value, text = value) {
  const el = document.createElement("option");
  el.value = value;
  el.textContent = text;
  return el;
}

async function bootstrap() {
  setupSplash();
  setupRevealObserver();
  setupScrollMotion();
  renderPipeline([]);

  restoreInitialView();
  restoreLatestCachedReport();
  restoreLatestBackendReportIfNeeded();

  await loadNodes();
  await loadScenarioDetails();
  await loadScenarios();
  await loadNamespacesForSelectedNode();
  restoreActiveJobPolling();
}

async function loadNodes() {
  nodeSelect.innerHTML = "";
  nodeSelect.appendChild(option("", "Loading nodes..."));

  if (clusterLoadStatus) {
    clusterLoadStatus.textContent = "Loading cluster nodes...";
    clusterLoadStatus.className = "field-note";
  }

  try {
    const nodes = await api("/api/cluster/nodes");
    const list = nodes.nodes || [];

    nodeSelect.innerHTML = "";

    if (!list.length) {
      nodeSelect.appendChild(option("", "No nodes found"));
      if (clusterLoadStatus) {
        clusterLoadStatus.textContent = "No nodes found. Start Minikube and check kubectl access.";
        clusterLoadStatus.className = "field-note error";
      }
      updateScopeInfo();
      return;
    }

    list.forEach((node) => nodeSelect.appendChild(option(node)));

    if (clusterLoadStatus) {
      clusterLoadStatus.textContent = `Loaded ${list.length} node(s) from the cluster`;
      clusterLoadStatus.className = "field-note success";
    }
  } catch (error) {
    nodeSelect.innerHTML = "";
    nodeSelect.appendChild(option("", "Could not load nodes"));

    if (clusterLoadStatus) {
      clusterLoadStatus.textContent = "Could not load nodes. Check FastAPI logs and kubectl access.";
      clusterLoadStatus.className = "field-note error";
    }

    console.error("Node loading failed:", error);
  }
}

function updateScenarioDetails() {
  if (!scenarioDetailsCard) return;

  const selected = scenarioSelect.value;
  const details = demoScenarioById(selected);

  if (!selected || !details) {
    scenarioDetailsCard.classList.add("hidden");
    return;
  }

  scenarioDetailsCard.classList.remove("hidden");
  scenarioTitle.textContent = details.title;
  scenarioDescription.textContent = details.description;
  scenarioImpact.textContent = details.impact;
  scenarioExpected.textContent = details.expected;
}

async function loadScenarioDetails() {
  try {
    const result = await api("/api/db/scenarios/details");
    scenarioDetailsFromApi = result.scenarios || {};
  } catch (error) {
    console.error("Scenario details loading failed:", error);
    scenarioDetailsFromApi = {};
  }
}


function scenarioNamespaceFromName(name) {
  const scenario = demoScenarioById(name);
  return scenario ? scenario.namespace : "";
}

function renderScenarioOptionsForNamespace() {
  if (!scenarioSelect) return;

  const selectedNamespace = namespaceValue ? namespaceValue() : "";
  const previousValue = scenarioSelect.value;

  scenarioSelect.innerHTML = "";

  if (!selectedNamespace) {
    scenarioSelect.appendChild(option("", "Select namespace first"));
    updateScenarioDetails();
    return;
  }

  scenarioSelect.appendChild(option("", `Select scenario for ${selectedNamespace}`));

  const filtered = DEMO_CATALOG.scenarios.filter((scenario) => {
    return scenario.namespace === selectedNamespace;
  });

  filtered.forEach((scenario) => {
    scenarioSelect.appendChild(option(scenario.id, scenario.title));
  });

  if (filtered.some((scenario) => scenario.id === previousValue)) {
    scenarioSelect.value = previousValue;
  } else {
    scenarioSelect.value = "";
  }

  updateScenarioDetails();
}


async function loadScenarios() {
  allScenariosFromApi = DEMO_CATALOG.scenarios.map((scenario) => scenario.id);
  renderScenarioOptionsForNamespace();
}

function restoreSidebarState() {
  const saved = localStorage.getItem("opslens_sidebar_collapsed");

  if (saved === "0") {
    document.body.classList.remove("sidebar-collapsed");
  } else {
    document.body.classList.add("sidebar-collapsed");
  }
}

function restoreInitialView() {
  const fromHash = location.hash ? location.hash.replace("#", "") : "";
  const saved = localStorage.getItem("opslens_current_view");
  const viewId = fromHash || saved || "homeView";

  if ($(viewId)) {
    showView(viewId);
  } else {
    showView("homeView");
  }
}

window.addEventListener("hashchange", () => {
  const viewId = location.hash ? location.hash.replace("#", "") : "homeView";
  if ($(viewId)) showView(viewId);
});

function setupSplash() {
  const splash = $("splashScreen");
  if (!splash) return;

  setTimeout(() => splash.classList.add("splash-hidden"), 1200);
  setTimeout(() => splash.remove(), 1850);
}

function setupRevealObserver() {
  revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        entry.target.classList.toggle("revealed", entry.isIntersecting);
      });
    },
    { threshold: 0.12 }
  );

  observeReveal();
}

function observeReveal() {
  if (!revealObserver) return;

  document.querySelectorAll(".reveal").forEach((el) => {
    revealObserver.observe(el);
  });
}

function setupScrollMotion() {
  window.addEventListener("scroll", requestScrollMotion, { passive: true });
  window.addEventListener("resize", requestScrollMotion);
  requestScrollMotion();
}

function requestScrollMotion() {
  if (scrollRaf) return;

  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = null;
    applyScrollMotion();
  });
}

function applyScrollMotion() {
  const height = window.innerHeight || 1;

  document.querySelectorAll(".scroll-motion").forEach((el) => {
    const rect = el.getBoundingClientRect();
    const center = rect.top + rect.height / 2;
    const distance = (center - height / 2) / height;
    const offset = Math.max(-12, Math.min(12, distance * -22));

    el.style.setProperty("--scroll-offset", `${offset}px`);
  });
}

async function loadNamespacesForSelectedNode() {
  namespaceSelect.innerHTML = "";

  DEMO_CATALOG.namespaces.forEach((namespace) => {
    namespaceSelect.appendChild(option(namespace));
  });

  const saved = localStorage.getItem("opslens_selected_namespace");

  if (saved && DEMO_CATALOG.namespaces.includes(saved)) {
    namespaceSelect.value = saved;
  } else {
    namespaceSelect.value = DEMO_CATALOG.namespaces[0];
  }

  if (applyScenario) {
    applyScenario.checked = false;
    applyScenario.disabled = true;
  }

  if (resetNamespace) {
    resetNamespace.checked = false;
    resetNamespace.disabled = true;
  }

  updateScopeInfo();
  renderScenarioOptionsForNamespace();
}

nodeSelect.addEventListener("change", loadNamespacesForSelectedNode);
scenarioSelect.addEventListener("change", updateScenarioDetails);
namespaceSelect.addEventListener("change", () => {
  localStorage.setItem("opslens_selected_namespace", namespaceSelect.value || "");
  updateScopeInfo();
  renderScenarioOptionsForNamespace();
});

function namespaceValue() {
  return namespaceSelect.value;
}

function updateScopeInfo() {
  if (!scopeInfo) return;

  const node = nodeSelect.value || "unknown node";
  const namespace = namespaceSelect.value || "";

  if (!namespace) {
    scopeInfo.textContent = `Select a namespace running on node ${node}`;
    return;
  }

  scopeInfo.textContent = `Namespace ${namespace} has Pods scheduled on node ${node}`;
}

function renderPipeline(stages) {
  pipeline.innerHTML = "";

  const fallback = [
    ["scope", "Investigation Scope", "pending"],
    ["scenario", "Scenario Preparation", "pending"],
    ["collectors", "Collectors", "pending"],
    ["config_agent", "Config Agent", "pending"],
    ["logs_agent", "Logs Agent", "pending"],
    ["metrics_agent", "Metrics Agent", "pending"],
    ["supervisor", "Supervisor Agent", "pending"],
    ["llm", "Reasoning Layer", "pending"],
    ["safety", "Safety Layer", "pending"],
    ["report", "Report", "pending"],
  ].map(([key, label, status]) => ({ key, label, status }));

  const finalStages = stages && stages.length ? stages : fallback;

  const runningIndex = finalStages.findIndex((stage) => stage.status === "running");

  finalStages.forEach((stage, index) => {
    const status = stage.status || "pending";
    const card = document.createElement("div");
    const isReceiving = runningIndex >= 0 && index === runningIndex + 1 && status === "pending";
    card.className = `stage ${status}${isReceiving ? " receiving" : ""}`;
    card.style.setProperty("--i", index);

    card.innerHTML = `
      <div class="stage-top">
        <div class="stage-status"><span></span></div>
        <div class="stage-line"></div>
      </div>
      <h4>${escapeHtml(stage.label || stage.key || "Stage")}</h4>
      <p>${escapeHtml(status)}</p>
    `;

    pipeline.appendChild(card);
  });

  updateTimeline(finalStages);
}

function updateTimeline(stages) {
  const active = stages.filter((stage) => stage.status && stage.status !== "pending");

  if (!active.length) {
    timelineLog.innerHTML = `<p class="muted">No activity yet.</p>`;
    return;
  }

  timelineLog.innerHTML = active.map((stage) => `
    <div class="timeline-item ${escapeHtml(stage.status)}">
      <span></span>
      <p>${escapeHtml(stage.label || stage.key || "Stage")} <strong>${escapeHtml(stage.status)}</strong></p>
    </div>
  `).join("");
}

function setPipelineHint(job) {
  const status = job.status || "unknown";

  if (status === "running") {
    pipelineHint.textContent = "Agents are collecting evidence and correlating findings.";
  } else if (status === "completed") {
    pipelineHint.textContent = "Investigation completed. Report is ready.";
  } else if (status === "failed") {
    pipelineHint.textContent = "Investigation failed. Check the error details.";
  } else {
    pipelineHint.textContent = "Waiting for an investigation.";
  }
}

async function runInvestigation() {
  const payload = {
    node_name: nodeSelect.value,
    namespace: namespaceValue(),
    scenario_name: scenarioSelect.value || null,
    apply_scenario: false,
    reset_namespace: false,
    demo_seed_metrics: demoMetrics ? demoMetrics.checked : false,
    wait_seconds: Number(waitSeconds.value || 45),
  };

  if (!payload.node_name || !payload.namespace) {
    alert("Please select node and namespace.");
    return;
  }

  runBtn.disabled = true;
  runBtn.textContent = "Analysis running...";
  showView("pipelineView");

  try {
    const job = await api("/api/investigations", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    currentJobId = job.job_id;
    localStorage.setItem("opslens_active_job_id", currentJobId);
    setGlobalStatus("Investigation running", "OpsLens is analyzing the selected scope.", "View Pipeline", () => showView("pipelineView"));
    setPipelineHint(job);
    renderPipeline(job.stages);

    const runningStage = (job.stages || []).find((stage) => stage.status === "running");
    if (job.status === "running") {
      setGlobalStatus(
        "Investigation running",
        runningStage ? `Current stage: ${runningStage.label}` : "OpsLens is analyzing the selected scope.",
        "View Pipeline",
        () => showView("pipelineView")
      );
    }

    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollJob, 1200);
  } catch (error) {
    alert(`Failed to start investigation:\n${error.message}`);
    runBtn.disabled = false;
    runBtn.textContent = "Launch Analysis";
  }
}

async function pollJob() {
  if (!currentJobId) return;

  try {
    const job = await api(`/api/investigations/${currentJobId}`);

    setPipelineHint(job);
    renderPipeline(job.stages);

    if (job.status === "completed") {
      clearInterval(pollTimer);
      pollTimer = null;

      runBtn.disabled = false;
      runBtn.textContent = "Launch Analysis";

      currentReport = job.report || {};
      currentReport.job_id = job.job_id || currentJobId || currentReport.job_id || "";
      currentReport.__opslens_job_id = currentReport.job_id;
      currentReport.created_at = currentReport.created_at || job.created_at || new Date().toISOString();
      localStorage.removeItem("opslens_active_job_id");

      renderReport(currentReport);
      await loadBackendInvestigationHistory();
      setGlobalStatus("Investigation completed", "The RCA report is ready.", "View Report", () => {
        clearGlobalStatus();
        showView("reportView");
      });

      const activeView = localStorage.getItem("opslens_current_view") || "homeView";

      if (activeView === "pipelineView") {
        showView("reportView");
      } else {
        showToast("Investigation completed", "The RCA report is ready.", "View report", () => showView("reportView"));
      }
    }

    if (job.status === "failed") {
      clearInterval(pollTimer);
      pollTimer = null;

      localStorage.removeItem("opslens_active_job_id");

      runBtn.disabled = false;
      runBtn.textContent = "Launch Analysis";

      alert(`Investigation failed:\n${job.error || "Unknown error"}`);
    }
  } catch (error) {
    clearInterval(pollTimer);
    pollTimer = null;

    runBtn.disabled = false;
    runBtn.textContent = "Launch Analysis";

    alert(`Polling failed:\n${error.message}`);
  }
}

function renderReport(report) {
  emptyState.classList.add("hidden");
  reportSection.classList.remove("hidden");

  reportTitle.textContent = report.title || "OpsLens Incident Report";
  severityBadge.textContent = report.severity || "unknown";
  confidenceBadge.textContent = report.confidence || "unknown";
  incidentSummary.textContent = report.incident_summary || "";
  rootCause.textContent = report.root_cause_story || "";

  renderIncidentStory(report);
  renderEvidence(report.agent_reasoning || []);
  renderAdditional(report.additional_findings || []);
  renderIncidentGrouping(report);
  renderFix(report.recommended_fix || {});
  renderVerification(report.verification || {});
}

function renderIncidentStory(report) {
  if (!storySteps) return;

  const fix = report.recommended_fix || {};
  const verification = report.verification || {};
  const evidence = report.agent_reasoning || [];

  const firstEvidence = evidence.length
    ? evidence[0].finding || evidence[0].meaning || "Evidence collected by OpsLens agents"
    : "Evidence collected by OpsLens agents";

  const steps = [
    {
      label: "Problem",
      text: report.incident_summary || "OpsLens detected an incident in the selected Kubernetes scope"
    },
    {
      label: "Evidence",
      text: firstEvidence
    },
    {
      label: "Root cause",
      text: report.root_cause_story || "Root cause was identified from correlated findings"
    },
    {
      label: "Recommended fix",
      text: fix.strategy || "Review the recommended action plan and safe commands"
    },
    {
      label: "Verification",
      text: verification.intent || "Run verification commands and confirm the service is healthy"
    }
  ];

  storySteps.innerHTML = steps.map((step, index) => `
    <div class="story-step" style="--i:${index}">
      <div class="story-index">${index + 1}</div>
      <div>
        <strong>${escapeHtml(step.label)}</strong>
        <p>${escapeHtml(step.text)}</p>
      </div>
    </div>
  `).join("");
}

function renderEvidence(rows) {
  if (!rows.length) {
    evidenceTrail.innerHTML = `<p class="muted">No evidence rows available.</p>`;
    return;
  }

  evidenceTrail.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Agent</th>
          <th>Finding</th>
          <th>Meaning</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.agent || "")}</td>
            <td>${escapeHtml(row.finding || "")}</td>
            <td>${escapeHtml(row.meaning || "")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderAdditional(rows) {
  if (!rows.length) {
    additionalFindings.innerHTML = `<p class="muted">No additional findings detected.</p>`;
    return;
  }

  additionalFindings.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Resource</th>
          <th>Finding</th>
          <th>Impact</th>
          <th>Priority</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.resource || "")}</td>
            <td>${escapeHtml(row.finding || "")}</td>
            <td>${escapeHtml(row.impact || "")}</td>
            <td>${escapeHtml(row.priority || "")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderFix(fix) {
  fixStrategy.textContent = fix.strategy || "";

  const fixActions = fix.actions || [];
  actions.innerHTML = fixActions.map((action, index) => `
    <div class="action">
      <strong>Priority ${index + 1}: ${escapeHtml(action.action_type || "action")}</strong>
      <p>${escapeHtml(action.reason || "")}</p>
      <small>Risk: ${escapeHtml(action.risk || "unknown")}</small>
    </div>
  `).join("");

  renderCommands(commands, fix.commands || []);
}

function renderVerification(verification) {
  verificationIntent.textContent = verification.intent || "";
  renderCommands(verificationCommands, verification.commands || []);
}

function renderCommands(container, list) {
  if (!list.length) {
    container.innerHTML = `<p class="muted">No commands available.</p>`;
    return;
  }

  container.innerHTML = list.map((command, index) => `
    <div class="command">
      <div class="command-header">
        <strong>Command ${index + 1}</strong>
        <button class="copy-btn" data-command="${encodeURIComponent(command)}" type="button">Copy</button>
      </div>
      <pre>${escapeHtml(command)}</pre>
    </div>
  `).join("");

  container.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const command = decodeURIComponent(btn.dataset.command || "");
      await navigator.clipboard.writeText(command);
      btn.textContent = "Copied";
      setTimeout(() => (btn.textContent = "Copy"), 1200);
    });
  });
}

feedbackForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const ratingValue = $("feedbackRating").value;

  const payload = {
    name: $("feedbackName").value.trim() || "Anonymous",
    email: $("feedbackEmail").value.trim() || null,
    feedback_type: $("feedbackType").value,
    rating: ratingValue ? Number(ratingValue) : null,
    message: $("feedbackMessage").value.trim(),
  };

  if (!payload.message) {
    feedbackStatus.textContent = "Please write a feedback message.";
    feedbackStatus.className = "form-status error";
    return;
  }

  try {
    const result = await api("/api/feedback", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    feedbackStatus.textContent = `Feedback saved. ID: ${result.feedback_id}`;
    feedbackStatus.className = "form-status success";
    feedbackForm.reset();
  } catch (error) {
    feedbackStatus.textContent = `Could not save feedback: ${error.message}`;
    feedbackStatus.className = "form-status error";
  }
});

function setGlobalStatus(title, text, actionLabel = "View Pipeline", action = null) {
  if (!globalStatusBar) return;

  const targetView = actionLabel.toLowerCase().includes("report") ? "reportView" : "pipelineView";

  localStorage.setItem("opslens_global_status", JSON.stringify({
    title,
    text,
    actionLabel,
    targetView
  }));

  globalStatusBar.classList.remove("hidden");
  globalStatusTitle.textContent = title;
  globalStatusText.textContent = text;

  globalStatusAction.textContent = actionLabel;
  globalStatusAction.onclick = action || (() => showView(targetView));
}

function clearGlobalStatus() {
  localStorage.removeItem("opslens_global_status");

  if (!globalStatusBar) return;
  globalStatusBar.classList.add("hidden");
}



function restoreGlobalStatus() {
  if (!globalStatusBar) return;

  let saved = null;

  try {
    saved = JSON.parse(localStorage.getItem("opslens_global_status") || "null");
  } catch {
    saved = null;
  }

  if (!saved || !saved.title) return;

  globalStatusBar.classList.remove("hidden");
  globalStatusTitle.textContent = saved.title;
  globalStatusText.textContent = saved.text || "";
  globalStatusAction.textContent = saved.actionLabel || "View Pipeline";
  globalStatusAction.onclick = () => showView(saved.targetView || "pipelineView");
}




async function saveCurrentReportToDatabase() {
  return null;
}

function showToast(title, message, actionLabel = null, action = null) {
  if (!toastHost) return;

  const toast = document.createElement("div");
  toast.className = "toast";

  toast.innerHTML = `
    <div>
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(message)}</p>
    </div>
    ${actionLabel ? `<button type="button">${escapeHtml(actionLabel)}</button>` : ""}
  `;

  if (actionLabel && action) {
    toast.querySelector("button").addEventListener("click", () => {
      action();
      toast.remove();
    });
  }

  toastHost.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-hide");
    setTimeout(() => toast.remove(), 350);
  }, 7000);
}

function getInvestigationRecords() {
  try {
    return JSON.parse(localStorage.getItem("opslens_investigation_records") || "[]");
  } catch {
    return [];
  }
}

function saveInvestigationRecord(job, report) {
  const records = getInvestigationRecords();

  const affected = report.affected_resources || {};
  const fix = report.recommended_fix || {};

  const service =
    affected.service ||
    affected.service_name ||
    affected.workload ||
    affected.deployment ||
    affected.pod ||
    "unknown-service";

  const record = {
    job_id: job.job_id || currentJobId || "",
    created_at: new Date().toISOString(),
    title: report.title || "OpsLens Investigation",
    severity: report.severity || "unknown",
    confidence: report.confidence || "unknown",
    service,
    namespace: affected.namespace || "",
    node: affected.node || "",
    fix_strategy: fix.strategy || "",
  };

  const next = [record, ...records.filter((item) => item.job_id !== record.job_id)].slice(0, 30);
  localStorage.setItem("opslens_investigation_records", JSON.stringify(next));
}

function renderInvestigationRecords() {
  if (!investigationRecords) return;

  const records = getInvestigationRecords();

  if (!records.length) {
    if (currentReport && currentReport.title) {
      investigationRecords.innerHTML = `<p class="muted">Saving current report into history...</p>`;
          return;
    }

    investigationRecords.innerHTML = `<p class="muted">No recorded investigations yet.</p>`;
    return;
  }

  investigationRecords.innerHTML = records.map((record) => {
    const date = new Date(record.created_at);
    const stamp = Number.isNaN(date.getTime())
      ? record.created_at
      : date.toLocaleString();

    return `
      <div class="record-card">
        <div>
          <strong>${escapeHtml(record.service)}</strong>
          <p>${escapeHtml(record.title)}</p>
        </div>
        <div>
          <small>Namespace</small>
          <span>${escapeHtml(record.namespace || "unknown")}</span>
        </div>
        <div>
          <small>Severity</small>
          <span>${escapeHtml(record.severity)}</span>
        </div>
        <div>
          <small>Created</small>
          <span>${escapeHtml(stamp)}</span>
        </div>
      </div>
    `;
  }).join("");
}

if (clearRecordsBtn) {
  clearRecordsBtn.addEventListener("click", () => {
    localStorage.removeItem("opslens_investigation_records");
    renderInvestigationRecords();
  });
}

async function restoreActiveJobPolling() {
  const activeJobId = localStorage.getItem("opslens_active_job_id");

  if (!activeJobId || currentJobId) return;

  try {
    await api(`/api/investigations/${encodeURIComponent(activeJobId)}`);
  } catch (error) {
    // Backend jobs are in-memory. After uvicorn restarts, old job IDs no longer exist.
    // Do not keep polling a dead job forever.
    localStorage.removeItem("opslens_active_job_id");
    localStorage.removeItem("opslens_global_status");
    currentJobId = null;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    clearGlobalStatus();
    return;
  }

  currentJobId = activeJobId;

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollJob, 1400);

  showToast("Investigation still running", "OpsLens will notify you when the report is ready.");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

runBtn.addEventListener("click", runInvestigation);

bootstrap();

// =========================================================
// OpsLens WEB FINAL controller
// Backend-only history, no local report cache, resilient polling,
// toast-only notifications, and safe downloads.
// =========================================================

function showToast(title, message, actionLabel = null, action = null, type = "info") {
  if (!toastHost) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type} clickable-toast`;

  toast.innerHTML = `
    <div>
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(message || "")}</p>
    </div>
    ${actionLabel ? `<button type="button">${escapeHtml(actionLabel)}</button>` : ""}
  `;

  let closed = false;

  function closeToast() {
    if (closed) return;
    closed = true;
    toast.classList.add("toast-hide");
    setTimeout(() => toast.remove(), 350);
  }

  if (actionLabel && action) {
    const button = toast.querySelector("button");
    if (button) {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        action();
        closeToast();
      });
    }
  }

  toast.addEventListener("click", closeToast);
  toastHost.appendChild(toast);

  setTimeout(closeToast, 7000);
}

function normalizeReport(value) {
  if (!value) return null;

  if (typeof value === "string") {
    try {
      return normalizeReport(JSON.parse(value));
    } catch {
      return null;
    }
  }

  if (typeof value !== "object") return null;

  if (value.report && typeof value.report === "object") return value.report;
  if (typeof value.report === "string") return normalizeReport(value.report);

  return value;
}

function reportAffected(report) {
  return (report && report.affected_resources && typeof report.affected_resources === "object")
    ? report.affected_resources
    : {};
}

function reportServiceName(report) {
  const affected = reportAffected(report);
  return (
    affected.service ||
    affected.service_name ||
    affected.workload ||
    affected.deployment ||
    affected.pod ||
    "unknown-service"
  );
}

function reportCreatedStamp(record) {
  const raw = record.created_at || record.finished_at || record.modified_at || "";
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleString();
}

function stableHistoryFingerprint(record) {
  const parts = [
    record.title || "",
    record.namespace || "",
    record.service || "",
    record.node || "",
    record.severity || "",
    record.summary || "",
    record.root_cause || "",
    record.fix_strategy || "",
  ];

  return parts.map((part) => String(part).trim().toLowerCase()).join("||");
}

function clearFrontendHistoryCache() {
  try {
    [
      "opslens_cached_reports",
      "opslens_cached_reports_v2",
      "opslens_investigation_records"
    ].forEach((key) => localStorage.removeItem(key));
  } catch {}
}

function getCachedReports() {
  return [];
}

function cacheReportLocally() {
  return;
}

function restoreLatestCachedReport() {
  return;
}

async function saveCurrentReportToDatabase() {
  return null;
}

function getInvestigationRecords() {
  return [];
}

function saveInvestigationRecord() {
  return;
}

function renderInvestigationRecords() {
  return loadBackendInvestigationHistory();
}

function buildReportSummaryText(report) {
  if (!report) return "";

  const fix = report.recommended_fix || {};
  const verification = report.verification || {};
  const affected = reportAffected(report);

  return [
    `Title: ${report.title || "OpsLens Incident Report"}`,
    `Severity: ${report.severity || "unknown"}`,
    `Confidence: ${report.confidence || "unknown"}`,
    `Namespace: ${affected.namespace || "unknown"}`,
    `Node: ${affected.node || affected.node_name || "unknown"}`,
    `Service: ${affected.service || affected.service_name || "unknown"}`,
    "",
    `Summary: ${report.incident_summary || ""}`,
    "",
    `Root Cause: ${report.root_cause_story || ""}`,
    "",
    `Recommended Fix: ${fix.strategy || ""}`,
    "",
    `Verification: ${verification.intent || ""}`,
  ].join("\n");
}

function setRunButtonRunning(isRunning) {
  if (!runBtn) return;
  runBtn.disabled = Boolean(isRunning);
  runBtn.textContent = isRunning ? "Analysis running..." : "Launch Analysis";
}

function finishActiveJob() {
  localStorage.removeItem("opslens_active_job_id");
  localStorage.removeItem("opslens_active_job_started_at");
  localStorage.removeItem("opslens_active_pipeline_stage");
  currentJobId = null;
  setRunButtonRunning(false);
}

async function runInvestigation() {
  const payload = {
    node_name: nodeSelect ? nodeSelect.value : "",
    namespace: namespaceValue ? namespaceValue() : "",
    scenario_name: scenarioSelect ? (scenarioSelect.value || null) : null,
    apply_scenario: Boolean(applyScenario && applyScenario.checked && scenarioSelect && scenarioSelect.value),
    reset_namespace: false,
    demo_seed_metrics: demoMetrics ? demoMetrics.checked : false,
    wait_seconds: waitSeconds ? Number(waitSeconds.value || 45) : 45,
  };

  if (!payload.node_name || !payload.namespace) {
    showToast(
      "Missing investigation scope",
      "Please choose both a node and a namespace before launching the investigation.",
      null,
      null,
      "warning"
    );
    return;
  }

  setRunButtonRunning(true);
  showView("pipelineView");
  setGlobalStatus("Investigation running", "OpsLens is analyzing the selected scope.", "View Pipeline", () => showView("pipelineView"));

  try {
    const job = await api("/api/investigations", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    currentJobId = job.job_id;
    localStorage.setItem("opslens_active_job_id", currentJobId);

    setPipelineHint(job);
    renderPipeline(job.stages);

    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollJob, 1200);

    showToast("Investigation started", "OpsLens is collecting evidence from the selected scope.", null, null, "info");
  } catch (error) {
    finishActiveJob();
    clearGlobalStatus();
    showToast("Could not start investigation", error.message || String(error), null, null, "error");
  }
}

async function handleCompletedJob(job, notify = true) {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  currentReport = normalizeReport(job.report) || {};
  currentReport.job_id = job.job_id || currentJobId || currentReport.job_id || "";
  currentReport.__opslens_job_id = currentReport.__opslens_job_id || currentReport.job_id;
  currentReport.created_at = currentReport.created_at || job.created_at || new Date().toISOString();
  currentReport.finished_at = currentReport.finished_at || job.finished_at || new Date().toISOString();

  renderReport(currentReport);
  await loadBackendInvestigationHistory();

  finishActiveJob();
  clearGlobalStatus();

  if (notify) {
    showToast("Investigation completed", "The RCA report is ready in the Reports section.", null, null, "success");
  }
}

async function pollJob() {
  if (!currentJobId) return;

  try {
    const job = await api(`/api/investigations/${encodeURIComponent(currentJobId)}`);

    setPipelineHint(job);
    renderPipeline(job.stages);

    if (job.status === "completed") {
      await handleCompletedJob(job, true);
      return;
    }

    if (job.status === "failed") {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }

      finishActiveJob();
      clearGlobalStatus();
      showToast("Investigation failed", job.error || "Unknown error", null, null, "error");
      return;
    }

    setRunButtonRunning(true);
  } catch (error) {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }

    finishActiveJob();
    clearGlobalStatus();
    showToast("Investigation disconnected", "Could not reconnect to the running job. Please check the API server.", null, null, "error");
  }
}

async function restoreActiveJobPolling() {
  const activeJobId = localStorage.getItem("opslens_active_job_id");

  if (!activeJobId || currentJobId) return;

  currentJobId = activeJobId;
  setRunButtonRunning(true);

  try {
    const job = await api(`/api/investigations/${encodeURIComponent(activeJobId)}`);

    setPipelineHint(job);
    renderPipeline(job.stages);

    if (job.status === "completed") {
      await handleCompletedJob(job, false);
      showToast("Investigation completed", "The RCA report is ready in the Reports section.", null, null, "success");
      return;
    }

    if (job.status === "failed") {
      finishActiveJob();
      clearGlobalStatus();
      showToast("Investigation failed", job.error || "The restored job failed.", null, null, "error");
      return;
    }

    setGlobalStatus("Investigation running", "OpsLens restored the active investigation after refresh.", "View Pipeline", () => showView("pipelineView"));

    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollJob, 1200);

    showToast("Investigation resumed", "OpsLens reconnected to the running job after refresh.", null, null, "info");
  } catch (error) {
    finishActiveJob();
    clearGlobalStatus();
    showToast("Investigation not found", "The previous job is no longer available on the API server.", null, null, "warning");
  }
}

async function restoreLatestBackendReportIfNeeded() {
  const currentView = localStorage.getItem("opslens_current_view") || "";

  if (currentView !== "reportView") return;
  if (currentReport) return;

  try {
    const history = await api("/api/db/history?limit=1");
    const latest = (history.records || [])[0];

    if (!latest || !latest.record_id) return;

    const report = await api(`/api/db/history/${encodeURIComponent(latest.record_id)}`);
    currentReport = normalizeReport(report) || report;
    renderReport(currentReport);
  } catch (error) {
    console.warn("Could not restore latest backend report:", error);
  }
}

async function loadBackendInvestigationHistory() {
  if (!investigationRecords) return;

  investigationRecords.innerHTML = `<p class="muted">Loading investigation history...</p>`;

  try {
    const result = await api("/api/db/history?limit=50");
    const records = Array.isArray(result.records) ? result.records : [];
    renderBackendInvestigationRecords(records);
  } catch (error) {
    investigationRecords.innerHTML = `
      <div class="history-error">
        <strong>Could not load backend history</strong>
        <p>${escapeHtml(error.message || error)}</p>
      </div>
    `;
  }
}

function uniqueHistoryRecords(records) {
  const seen = new Set();
  const unique = [];

  for (const record of records || []) {
    const fingerprint = stableHistoryFingerprint(record);
    const key = fingerprint && fingerprint !== "|||||||" ? fingerprint : String(record.record_id || "");

    if (seen.has(key)) continue;

    seen.add(key);
    unique.push(record);
  }

  return unique;
}

function renderBackendInvestigationRecords(records) {
  if (!investigationRecords) return;

  const unique = uniqueHistoryRecords(records);

  if (!unique.length) {
    investigationRecords.innerHTML = `
      <div class="empty-history">
        <strong>No reports yet</strong>
        <p>Run an investigation first. Completed reports will appear here automatically.</p>
      </div>
    `;
    return;
  }

  investigationRecords.innerHTML = unique.map((record) => {
    const stamp = reportCreatedStamp(record);

    return `
      <div class="record-card backend-record" data-record-id="${escapeHtml(record.record_id || "")}">
        <div>
          <strong>${escapeHtml(record.service || "unknown-service")}</strong>
          <p>${escapeHtml(record.title || "OpsLens Investigation")}</p>
        </div>
        <div>
          <small>Namespace</small>
          <span>${escapeHtml(record.namespace || "unknown")}</span>
        </div>
        <div>
          <small>Severity</small>
          <span>${escapeHtml(record.severity || "unknown")}</span>
        </div>
        <div>
          <small>Created</small>
          <span>${escapeHtml(stamp)}</span>
        </div>
        <div class="record-actions">
          <button type="button" class="open-record-btn" data-record-id="${escapeHtml(record.record_id || "")}">Open</button>
          <button type="button" class="download-record-btn" data-record-id="${escapeHtml(record.record_id || "")}">PDF</button>
        </div>
      </div>
    `;
  }).join("");

  investigationRecords.querySelectorAll(".open-record-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const recordId = btn.dataset.recordId;

      if (!recordId) {
        showToast("No record selected", "Please choose an investigation record first.", null, null, "warning");
        return;
      }

      try {
        const report = await api(`/api/db/history/${encodeURIComponent(recordId)}`);
        currentReport = normalizeReport(report) || report;
        currentJobId = null;
        renderReport(currentReport);
        showView("reportView");
      } catch (error) {
        showToast("Could not open report", error.message || String(error), null, null, "error");
      }
    });
  });

  investigationRecords.querySelectorAll(".download-record-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const recordId = btn.dataset.recordId;

      if (!recordId) {
        showToast("No record selected", "Please choose an investigation record first.", null, null, "warning");
        return;
      }

      window.location.href = `/api/db/history/${encodeURIComponent(recordId)}/report/pdf/download`;
    });
  });
}

function renderIncidentGrouping(report) {
  const existing = document.getElementById("incidentGroupingCard");
  if (existing) existing.remove();

  if (!reportSection || !report) return;

  const groups = Array.isArray(report.incident_groups) ? report.incident_groups : [];
  const separate = Array.isArray(report.separate_findings) ? report.separate_findings : [];
  const unclassified = Array.isArray(report.unclassified_findings) ? report.unclassified_findings : [];

  if (!groups.length && !separate.length && !unclassified.length) return;

  const card = document.createElement("section");
  card.id = "incidentGroupingCard";
  card.className = "report-card incident-grouping-card reveal";

  function signalTitle(signal) {
    if (!signal) return "Signal";
    if (typeof signal === "string") return signal;
    return signal.summary || signal.finding || signal.anomaly_type || signal.type || signal.name || "Signal";
  }

  function signalText(signal) {
    if (!signal) return "";
    if (typeof signal === "string") return signal;
    return signal.message || signal.meaning || signal.resource || signal.pod_name || signal.deployment_name || "";
  }

  function renderSignalList(signals) {
    if (!Array.isArray(signals) || !signals.length) {
      return `<p class="muted">No related signals.</p>`;
    }

    return `
      <ul class="incident-signal-list">
        ${signals.map((signal) => `
          <li>
            <strong>${escapeHtml(signalTitle(signal))}</strong>
            <span>${escapeHtml(signalText(signal))}</span>
          </li>
        `).join("")}
      </ul>
    `;
  }

  const groupHtml = groups.map((group, index) => {
    const root = group.root || group.primary || group.primary_signal || group;
    const related = group.related_signals || group.supporting_signals || group.related || [];

    return `
      <div class="incident-group-item">
        <div class="incident-group-header">
          <strong>Incident Group ${index + 1}</strong>
          <span>${escapeHtml(group.relationship || group.reason || "correlated evidence")}</span>
        </div>
        <p><b>Root:</b> ${escapeHtml(signalTitle(root))}</p>
        ${renderSignalList(related)}
      </div>
    `;
  }).join("");

  card.innerHTML = `
    <div class="section-title">
      <span>Incident Grouping</span>
      <small>Primary incident separated from unrelated findings</small>
    </div>

    ${groupHtml || ""}

    ${separate.length ? `
      <h4>Separate Findings</h4>
      ${renderSignalList(separate)}
    ` : ""}

    ${unclassified.length ? `
      <h4>Unclassified Findings</h4>
      ${renderSignalList(unclassified)}
    ` : ""}

    ${report.incident_grouping_policy ? `
      <p class="muted">${escapeHtml(report.incident_grouping_policy)}</p>
    ` : ""}
  `;

  const after = additionalFindings ? additionalFindings.closest(".report-card") : null;

  if (after && after.parentNode) {
    after.parentNode.insertBefore(card, after.nextSibling);
  } else {
    reportSection.appendChild(card);
  }

  observeReveal();
}

async function postExport(report, format) {
  const response = await fetch(`/api/export/report/${encodeURIComponent(format)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "*/*",
    },
    body: JSON.stringify(report),
  });

  if (!response.ok) {
    let detail = await response.text();
    try {
      const json = JSON.parse(detail);
      detail = json.detail || detail;
    } catch {}
    throw new Error(detail || `Export failed with status ${response.status}`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || `opslens-report.${format === "markdown" ? "md" : format}`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");

  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();

  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 900);
}

function selectedDownloadFormat() {
  const raw = String(downloadFormat?.value || "pdf").toLowerCase().trim();

  if (raw === "xlsx" || raw === "excel") return "xlsx";
  if (raw === "csv") return "csv";
  if (raw === "json") return "json";
  if (raw === "md" || raw === "markdown") return "markdown";

  return "pdf";
}

if (copySummaryBtn) {
  copySummaryBtn.addEventListener("click", async () => {
    if (!currentReport) {
      showToast("No report selected", "Please open an investigation report first.", null, null, "warning");
      return;
    }

    await navigator.clipboard.writeText(buildReportSummaryText(currentReport));
    showToast("Summary copied", "The report summary is now in your clipboard.", null, null, "success");
  });
}

if (downloadReportBtn) {
  downloadReportBtn.addEventListener("click", async () => {
    if (!currentReport) {
      showToast("No report selected", "Please open an investigation report before downloading.", null, null, "warning");
      return;
    }

    try {
      await postExport(currentReport, selectedDownloadFormat());
      showToast("Download started", "Your report export is being downloaded.", null, null, "success");
    } catch (error) {
      console.error("Download failed:", error);
      showToast("Download failed", error.message || String(error), null, null, "error");
    }
  });
}

if (refreshHistoryBtn) {
  refreshHistoryBtn.addEventListener("click", loadBackendInvestigationHistory);
}

if (clearRecordsBtn) {
  clearRecordsBtn.style.display = "none";
}

window.opslensCacheReportFinal = function () {
  return;
};

window.opslensSaveReportFinal = async function () {
  return null;
};

window.opslensRestoreLatestReportFinal = function () {
  return;
};

window.addEventListener("load", () => {
  clearFrontendHistoryCache();
  document.querySelectorAll(".opslens-export-report-picker").forEach((node) => node.remove());
  loadBackendInvestigationHistory();
});

// =========================================================
// OpsLens safe UI report/pipeline override v1
// =========================================================
// OpsLens safe UI report/pipeline override v1
// Scope:
// - Does NOT change API calls.
// - Does NOT change polling.
// - Does NOT touch CSS animations.
// - Reuses existing stage/report DOM and classes.
// - Makes report simpler: metadata, problem, root cause, fix commands, verification, summary.
// =========================================================

function opsUiText(value) {
  if (value === null || value === undefined) return "";

  if (typeof value === "string") {
    return value.replace(/\s+/g, " ").trim();
  }

  if (Array.isArray(value)) {
    return value.map(opsUiText).filter(Boolean).join(" ");
  }

  if (typeof value === "object") {
    const preferred = [
      "summary",
      "meaning",
      "message",
      "reason",
      "strategy",
      "intent",
      "finding",
      "command",
      "anomaly_type",
      "event_type"
    ];

    for (const key of preferred) {
      if (value[key]) return opsUiText(value[key]);
    }

    return Object.values(value).map(opsUiText).filter(Boolean).join(" ");
  }

  return String(value).trim();
}

function opsUiAllText(report) {
  return opsUiText(report || {});
}

function opsUiAffected(report) {
  const affected = { ...((report && report.affected_resources) || {}) };
  const all = opsUiAllText(report);

  if (!affected.pod && !affected.pod_name) {
    const podMatch =
      all.match(/Pod\/([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i) ||
      all.match(/pod\s+'([^']+)'/i) ||
      all.match(/pod\s+([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i);

    if (podMatch) affected.pod = podMatch[1];
  }

  if (!affected.deployment && !affected.deployment_name) {
    const deploymentMatch =
      all.match(/deployment\s+'([^']+)'/i) ||
      all.match(/deployment\/([a-z0-9][a-z0-9.-]+)/i) ||
      all.match(/Deployment\s+([a-z0-9][a-z0-9.-]+)/i);

    if (deploymentMatch) affected.deployment = deploymentMatch[1];
  }

  return affected;
}

function opsUiSetCardTitle(element, title) {
  if (!element) return;
  const card = element.closest(".report-card");
  if (!card) return;
  const h3 = card.querySelector("h3");
  if (h3) h3.textContent = title;
}

function opsUiSetStoryTitle(kicker, title) {
  const panel = document.getElementById("incidentStoryPanel");
  if (!panel) return;

  const kickerEl = panel.querySelector(".kicker");
  const titleEl = panel.querySelector(".story-head h3");

  if (kickerEl) kickerEl.textContent = kicker;
  if (titleEl) titleEl.textContent = title;
}

function opsUiProblem(report) {
  const all = opsUiAllText(report).toLowerCase();
  const affected = opsUiAffected(report);
  const pod = affected.pod || affected.pod_name || "The affected pod";
  const deployment = affected.deployment || affected.deployment_name || "the deployment";

  if (all.includes("readiness") && all.includes("not ready")) {
    return `${pod} is failing readiness checks, so Kubernetes keeps it NotReady and ${deployment} has no available ready replica.`;
  }

  return (
    opsUiText(report.incident_summary) ||
    opsUiText(report.summary) ||
    opsUiText(report.title) ||
    opsUiText(report.incident_title) ||
    "OpsLens detected an active Kubernetes workload issue."
  );
}

function opsUiRootCause(report) {
  const allRaw = opsUiAllText(report);
  const all = allRaw.toLowerCase();

  if (all.includes("readiness") && (all.includes("404") || all.includes("not-found"))) {
    const pathMatch = allRaw.match(/(\/healthz[-a-zA-Z0-9_/]*)/);
    if (pathMatch) {
      return `The readiness probe is targeting '${pathMatch[1]}', but the application returns HTTP 404 for that endpoint, so the pod never becomes Ready.`;
    }

    return "The readiness probe is returning HTTP 404, so Kubernetes marks the pod as NotReady and the deployment remains unavailable.";
  }

  return (
    opsUiText(report.root_cause_story) ||
    opsUiText(report.root_cause_hypothesis) ||
    "OpsLens selected the root cause from the strongest correlated Kubernetes, log, configuration, and metrics signals."
  );
}

function opsUiSummary(report) {
  const affected = opsUiAffected(report);

  const namespace = affected.namespace || "the selected namespace";
  const node = affected.node || affected.node_name || "the selected node";
  const deployment =
    affected.deployment ||
    affected.deployment_name ||
    affected.service ||
    affected.service_name ||
    affected.pod ||
    affected.pod_name ||
    "the affected workload";

  return `OpsLens investigated ${deployment} in namespace ${namespace} on node ${node}. ${opsUiProblem(report)} ${opsUiRootCause(report)}`;
}

function opsUiDedupe(items) {
  const seen = new Set();
  const result = [];

  for (const item of items || []) {
    const text = opsUiText(item);
    if (!text) continue;

    const key = text.toLowerCase();
    if (seen.has(key)) continue;

    seen.add(key);
    result.push(text);
  }

  return result;
}

function opsUiExtractKubectl(value) {
  const text = opsUiText(value);
  const match = text.match(/(kubectl\s+.+)$/);
  if (match) return match[1].trim();
  if (text.startsWith("kubectl ")) return text;
  return "";
}

function opsUiCollectCommands(value) {
  const commands = [];

  if (!value) return commands;

  if (Array.isArray(value)) {
    value.forEach((item) => commands.push(...opsUiCollectCommands(item)));
    return commands;
  }

  if (typeof value === "object") {
    if (value.command) {
      const cmd = opsUiExtractKubectl(value.command);
      if (cmd) commands.push(cmd);
    }

    ["commands", "safe_commands", "verification_commands"].forEach((key) => {
      if (Array.isArray(value[key])) {
        value[key].forEach((item) => commands.push(...opsUiCollectCommands(item)));
      }
    });

    Object.values(value).forEach((item) => {
      if (typeof item === "string") {
        const cmd = opsUiExtractKubectl(item);
        if (cmd) commands.push(cmd);
      }
    });

    return commands;
  }

  const cmd = opsUiExtractKubectl(value);
  if (cmd) commands.push(cmd);

  return commands;
}

function opsUiFixCommands(report) {
  const affected = opsUiAffected(report);
  const ns = affected.namespace || "default";
  const deployment = affected.deployment || affected.deployment_name;
  const service = affected.service || affected.service_name;
  const all = opsUiAllText(report).toLowerCase();

  const commands = [];

  if (deployment && all.includes("readiness")) {
    commands.push("# Inspect the current readinessProbe configuration");
    commands.push(`kubectl describe deployment ${deployment} -n ${ns}`);
    commands.push("");
    commands.push("# Edit the readinessProbe path/port to match a real application health endpoint");
    commands.push(`kubectl edit deployment ${deployment} -n ${ns}`);
    commands.push("");
    commands.push("# Watch the rollout after applying the fix");
    commands.push(`kubectl rollout status deployment/${deployment} -n ${ns}`);
  } else if (deployment) {
    commands.push(`kubectl describe deployment ${deployment} -n ${ns}`);
    commands.push(`kubectl rollout status deployment/${deployment} -n ${ns}`);
  }

  if (service) {
    commands.push(`kubectl get endpoints ${service} -n ${ns}`);
  }

  opsUiCollectCommands(report.recommended_fix).forEach((cmd) => {
    if (!commands.includes(cmd)) commands.push(cmd);
  });

  return opsUiDedupe(commands).slice(0, 10);
}

function opsUiVerificationCommands(report) {
  const affected = opsUiAffected(report);
  const ns = affected.namespace || "default";
  const pod = affected.pod || affected.pod_name;
  const deployment = affected.deployment || affected.deployment_name;
  const service = affected.service || affected.service_name;

  const commands = [];

  if (deployment) {
    commands.push(`kubectl rollout status deployment/${deployment} -n ${ns}`);
  }

  commands.push(`kubectl get pods -n ${ns}`);

  if (pod) {
    commands.push(`kubectl describe pod ${pod} -n ${ns}`);
  }

  if (service) {
    commands.push(`kubectl get endpoints ${service} -n ${ns}`);
  }

  commands.push(`kubectl get events -n ${ns} --sort-by=.lastTimestamp`);

  opsUiCollectCommands(report.verification).forEach((cmd) => {
    if (!commands.includes(cmd)) commands.push(cmd);
  });

  return opsUiDedupe(commands).slice(0, 8);
}

function opsUiRenderMetadata(report) {
  const affected = opsUiAffected(report);

  const rows = [
    ["Namespace", affected.namespace || ""],
    ["Node", affected.node || affected.node_name || ""],
    ["Service", affected.service || affected.service_name || ""],
    ["Deployment", affected.deployment || affected.deployment_name || ""],
    ["Pod", affected.pod || affected.pod_name || ""],
    ["Severity", report.severity || ""],
    ["Confidence", report.confidence || ""],
    ["Detected Time", report.generated_at || report.created_at || ""],
  ];

  return `
    <table>
      <tbody>
        ${rows.map(([key, value]) => `
          <tr>
            <th>${escapeHtml(key)}</th>
            <td>${escapeHtml(value || "-")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function opsUiRenderCodeList(container, lines) {
  if (!container) return;

  const cleanLines = lines && lines.length ? lines : ["No command available."];

  container.innerHTML = `
    <div class="command">
      <pre>${escapeHtml(cleanLines.join("\n"))}</pre>
    </div>
  `;
}

function opsUiRenderStory(report) {
  if (!storySteps) return;

  const steps = [
    ["1", "Scope", "OpsLens selected the node, namespace, and workload context."],
    ["2", "Problem", opsUiProblem(report)],
    ["3", "Root Cause", opsUiRootCause(report)],
    ["4", "Fix", "Use the recommended command block, then verify rollout and endpoints."],
  ];

  storySteps.innerHTML = steps.map(([num, title, text]) => `
    <div class="story-step">
      <span>${escapeHtml(num)}</span>
      <div>
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(text)}</p>
      </div>
    </div>
  `).join("");
}

function renderPipeline(stages) {
  pipeline.innerHTML = "";

  const source = Array.isArray(stages) && stages.length ? stages : [];
  const textOf = (stage) => `${stage.key || ""} ${stage.label || ""}`.toLowerCase();

  function hasStatus(words) {
    let status = "pending";

    source.forEach((stage) => {
      const text = textOf(stage);
      const matched = words.some((word) => text.includes(word));

      if (!matched) return;

      if (stage.status === "failed") status = "failed";
      else if (stage.status === "running" && status !== "failed") status = "running";
      else if (stage.status === "done" && !["failed", "running"].includes(status)) status = "done";
      else if (stage.status === "completed" && !["failed", "running"].includes(status)) status = "done";
    });

    return status;
  }

  const highLevel = [
    {
      key: "start",
      label: "Start",
      status: source.length ? "done" : "pending",
    },
    {
      key: "scope",
      label: "Scope Setup",
      status: hasStatus(["scope", "scenario", "preparation"]),
    },
    {
      key: "collect",
      label: "Data Collection",
      status: hasStatus(["collect", "collector", "kubernetes", "logs", "metrics"]),
    },
    {
      key: "detect",
      label: "Detection Layer",
      status: hasStatus(["detect", "detector", "signal", "config", "resource"]),
    },
    {
      key: "agents",
      label: "Agent Analysis",
      status: hasStatus(["agent", "events", "logs", "config", "metrics"]),
    },
    {
      key: "supervisor",
      label: "Supervisor",
      status: hasStatus(["supervisor", "correlation"]),
    },
    {
      key: "ai",
      label: "AI Reasoning",
      status: hasStatus(["llm", "reasoning", "gemini", "ai"]),
    },
    {
      key: "report",
      label: "Report",
      status: hasStatus(["report", "safety", "export"]),
    },
  ];

  if (source.length) {
    const anyRunning = source.some((stage) => stage.status === "running");
    const anyFailed = source.some((stage) => stage.status === "failed");
    const allDone = source.every((stage) => ["done", "completed"].includes(stage.status));

    if (allDone && !anyFailed) {
      highLevel.forEach((stage) => stage.status = "done");
    }

    if (anyFailed) {
      const failedIndex = Math.max(0, highLevel.findIndex((stage) => stage.status === "failed"));
      highLevel[failedIndex >= 0 ? failedIndex : highLevel.length - 1].status = "failed";
    }

    if (anyRunning && !highLevel.some((stage) => stage.status === "running")) {
      const firstPending = highLevel.findIndex((stage) => stage.status === "pending");
      if (firstPending >= 0) highLevel[firstPending].status = "running";
    }
  }

  const runningIndex = highLevel.findIndex((stage) => stage.status === "running");

  highLevel.forEach((stage, index) => {
    const status = stage.status || "pending";
    const card = document.createElement("div");
    const isReceiving = runningIndex >= 0 && index === runningIndex + 1 && status === "pending";
    card.className = `stage ${status}${isReceiving ? " receiving" : ""}`;
    card.style.setProperty("--i", index);

    card.innerHTML = `
      <div class="stage-top">
        <div class="stage-status"><span></span></div>
        <div class="stage-line"></div>
      </div>
      <h4>${escapeHtml(stage.label)}</h4>
      <p>${escapeHtml(status)}</p>
    `;

    pipeline.appendChild(card);
  });

  updateTimeline(highLevel);
}

function renderReport(report) {
  emptyState.classList.add("hidden");
  reportSection.classList.remove("hidden");

  opsUiSetStoryTitle("Summary", "From scope to fix");
  opsUiSetCardTitle(incidentSummary, "Problem");
  opsUiSetCardTitle(rootCause, "Root Cause");
  opsUiSetCardTitle(evidenceTrail, "Metadata / Scope");
  opsUiSetCardTitle(additionalFindings, "Agent / Model Status");
  opsUiSetCardTitle(fixStrategy, "Recommended Fix");
  opsUiSetCardTitle(commands, "Recommended Fix Commands");
  opsUiSetCardTitle(verificationIntent, "Verification");

  const affected = opsUiAffected(report);
  const workload =
    affected.deployment ||
    affected.deployment_name ||
    affected.service ||
    affected.service_name ||
    affected.pod ||
    affected.pod_name ||
    "OpsLens Incident Report";

  reportTitle.textContent = report.title || `[${String(report.severity || "unknown").toUpperCase()}] ${workload}`;
  severityBadge.textContent = report.severity || "unknown";
  confidenceBadge.textContent = report.confidence || "unknown";

  incidentSummary.textContent = opsUiProblem(report);
  rootCause.textContent = opsUiRootCause(report);

  opsUiRenderStory(report);

  if (evidenceTrail) {
    evidenceTrail.innerHTML = opsUiRenderMetadata(report);
  }

  const agentRows = [];

  const contributions = report.agent_contributions || {};
  Object.entries(contributions).forEach(([name, value]) => {
    const status = value && value.status ? value.status : "completed";
    const finding = value && value.finding ? value.finding : (
      Array.isArray(value.findings) && value.findings.length
        ? value.findings.map((item) => item.summary || item.anomaly_type || "").filter(Boolean).join("; ")
        : "No active signal detected."
    );

    agentRows.push([name, status, finding]);
  });

  if (additionalFindings) {
    if (agentRows.length) {
      additionalFindings.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Status</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            ${agentRows.map(([agent, status, result]) => `
              <tr>
                <td>${escapeHtml(agent)}</td>
                <td>${escapeHtml(status)}</td>
                <td>${escapeHtml(result || "-")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    } else {
      additionalFindings.innerHTML = `<p class="muted">No agent status details available.</p>`;
    }
  }

  fixStrategy.textContent = "Review the recommended commands before applying changes.";
  actions.innerHTML = "";
  opsUiRenderCodeList(commands, opsUiFixCommands(report));

  verificationIntent.textContent = "Run these checks after applying the fix to confirm recovery.";
  opsUiRenderCodeList(verificationCommands, opsUiVerificationCommands(report));

  observeReveal();
  requestScrollMotion();
}

// =========================================================
// OpsLens UI pipeline/copy polish v2
// =========================================================
// OpsLens UI pipeline/copy polish v2
// Keeps existing animations/classes.
// Improves pipeline layout and restores copy buttons for command blocks.
// =========================================================

function opsUiEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function opsUiCopyText(text) {
  const value = String(text || "").trim();

  if (!value) {
    if (typeof showToast === "function") {
      showToast("Nothing to copy", "No command text is available.");
    }
    return;
  }

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }

    if (typeof showToast === "function") {
      showToast("Copied", "Commands copied to clipboard.");
    }
  } catch (error) {
    console.error("Copy failed:", error);
    alert("Copy failed. Please copy the commands manually.");
  }
}

function opsUiCopyCode(button) {
  const block = button && button.closest(".command");
  const pre = block && block.querySelector("pre");

  if (!pre) return;
  opsUiCopyText(pre.textContent || "");
}

function opsUiRenderCodeList(container, lines) {
  if (!container) return;

  const cleanLines = Array.isArray(lines) && lines.length
    ? lines
    : ["No command available."];

  const text = cleanLines.join("\n");

  container.innerHTML = `
    <div class="command command-copyable">
      <div class="command-header">
        <strong>Command block</strong>
        <button class="copy-btn" type="button" onclick="opsUiCopyCode(this)">Copy</button>
      </div>
      <pre>${opsUiEscape(text)}</pre>
    </div>
  `;
}

function renderPipeline(stages) {
  pipeline.innerHTML = "";
  pipeline.classList.add("pipeline-balanced");

  const source = Array.isArray(stages) && stages.length ? stages : [];

  const textOf = (stage) => `${stage.key || ""} ${stage.label || ""}`.toLowerCase();

  function hasStatus(words) {
    let status = "pending";

    source.forEach((stage) => {
      const text = textOf(stage);
      const matched = words.some((word) => text.includes(word));

      if (!matched) return;

      if (stage.status === "failed") status = "failed";
      else if (stage.status === "running" && status !== "failed") status = "running";
      else if (["done", "completed"].includes(stage.status) && !["failed", "running"].includes(status)) {
        status = "done";
      }
    });

    return status;
  }

  const highLevel = [
    {
      key: "scope",
      label: "Target Scope",
      status: source.length ? hasStatus(["scope", "scenario", "preparation"]) : "pending",
      note: "Node, namespace, scenario"
    },
    {
      key: "collect",
      label: "Collect Evidence",
      status: source.length ? hasStatus(["collect", "collector", "kubernetes", "events", "logs", "metrics"]) : "pending",
      note: "Events, logs, metrics"
    },
    {
      key: "agents",
      label: "Run Agents",
      status: source.length ? hasStatus(["agent", "detect", "detector", "config", "resource", "lstm"]) : "pending",
      note: "K8s, logs, config, metrics"
    },
    {
      key: "correlate",
      label: "Correlate Findings",
      status: source.length ? hasStatus(["supervisor", "correlation", "root"]) : "pending",
      note: "Primary vs related signals"
    },
    {
      key: "ai",
      label: "AI Reasoning",
      status: source.length ? hasStatus(["llm", "reasoning", "gemini", "ai"]) : "pending",
      note: "Explain problem and cause"
    },
    {
      key: "report",
      label: "Report",
      status: source.length ? hasStatus(["report", "safety", "export"]) : "pending",
      note: "Fix and verification"
    },
  ];

  if (source.length) {
    const anyRunning = source.some((stage) => stage.status === "running");
    const anyFailed = source.some((stage) => stage.status === "failed");
    const allDone = source.every((stage) => ["done", "completed"].includes(stage.status));

    if (allDone && !anyFailed) {
      highLevel.forEach((stage) => {
        stage.status = "done";
      });
    }

    if (anyFailed) {
      const failedIndex = highLevel.findIndex((stage) => stage.status === "failed");
      highLevel[failedIndex >= 0 ? failedIndex : highLevel.length - 1].status = "failed";
    }

    if (anyRunning && !highLevel.some((stage) => stage.status === "running")) {
      const firstPending = highLevel.findIndex((stage) => stage.status === "pending");
      if (firstPending >= 0) highLevel[firstPending].status = "running";
    }
  }

  const runningIndex = highLevel.findIndex((stage) => stage.status === "running");

  highLevel.forEach((stage, index) => {
    const status = stage.status || "pending";
    const card = document.createElement("div");
    const isReceiving = runningIndex >= 0 && index === runningIndex + 1 && status === "pending";

    card.className = `stage ${status}${isReceiving ? " receiving" : ""}`;
    card.style.setProperty("--i", index);

    card.innerHTML = `
      <div class="stage-top">
        <div class="stage-status"><span></span></div>
        <div class="stage-line"></div>
      </div>
      <h4>${opsUiEscape(stage.label)}</h4>
      <p>${opsUiEscape(stage.note || status)}</p>
    `;

    pipeline.appendChild(card);
  });

  if (typeof updateTimeline === "function") {
    updateTimeline(highLevel);
  }
}

// =========================================================
// OpsLens Clear App History button override v1
// =========================================================
// OpsLens Clear App History button override v1
// Converts Refresh History into Clear History.
// Clears frontend/local app history only.
// Does NOT delete backend DB reports or exported files.
// =========================================================

(function () {
  const CLEAR_FLAG = "opslens_app_history_cleared";

  const HISTORY_KEYS = [
    "opslens_cached_reports",
    "opslens_cached_reports_v2",
    "opslens_investigation_records"
  ];

  function opsClearLocalHistoryOnly() {
    try {
      HISTORY_KEYS.forEach((key) => localStorage.removeItem(key));
      localStorage.setItem(CLEAR_FLAG, "1");
    } catch (_) {}

    if (investigationRecords) {
      investigationRecords.innerHTML = `
        <div class="empty-history">
          <strong>No app history</strong>
          <p>Frontend history was cleared. New completed investigations will appear here again.</p>
        </div>
      `;
    }

    if (typeof showToast === "function") {
      showToast("History cleared", "Frontend app history was cleared. Database reports were not deleted.");
    }
  }

  function opsRenderEmptyHistoryIfCleared() {
    if (localStorage.getItem(CLEAR_FLAG) !== "1") return false;

    if (investigationRecords) {
      investigationRecords.innerHTML = `
        <div class="empty-history">
          <strong>No app history</strong>
          <p>Frontend history was cleared. Run a new investigation to show new records here.</p>
        </div>
      `;
    }

    return true;
  }

  // When a new investigation starts, allow history to show new results again.
  if (runBtn) {
    runBtn.addEventListener("click", () => {
      try {
        localStorage.removeItem(CLEAR_FLAG);
      } catch (_) {}
    }, true);
  }

  const originalLoadBackendHistory =
    typeof loadBackendInvestigationHistory === "function"
      ? loadBackendInvestigationHistory
      : null;

  if (originalLoadBackendHistory) {
    loadBackendInvestigationHistory = async function () {
      if (opsRenderEmptyHistoryIfCleared()) return;
      return originalLoadBackendHistory();
    };
  }

  renderInvestigationRecords = function () {
    if (opsRenderEmptyHistoryIfCleared()) return;
    if (originalLoadBackendHistory) return originalLoadBackendHistory();

    if (investigationRecords) {
      investigationRecords.innerHTML = `<p class="muted">No recorded investigations yet.</p>`;
    }
  };

  // Replace Refresh History button with a clean clone to remove older refresh listeners safely.
  const oldRefresh = document.getElementById("refreshHistoryBtn");

  if (oldRefresh && oldRefresh.parentNode) {
    const clearButton = oldRefresh.cloneNode(true);
    clearButton.textContent = "Clear History";
    clearButton.title = "Clear frontend app history";
    clearButton.setAttribute("aria-label", "Clear frontend app history");

    oldRefresh.parentNode.replaceChild(clearButton, oldRefresh);

    clearButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      opsClearLocalHistoryOnly();
    });
  }

  // Keep old Clear button hidden if it exists, because Refresh button is now the clear action.
  const oldClear = document.getElementById("clearRecordsBtn");
  if (oldClear) {
    oldClear.style.display = "none";
  }
})();

// =========================================================
// OpsLens report agent/model status fallback v3
// =========================================================
// OpsLens report agent/model status fallback v3
// Shows additional_findings in the Agent / Model Status card when agent_contributions is empty.
// Keeps previous renderReport behavior and only patches the missing display.
// =========================================================

(function () {
  const previousRenderReport = typeof renderReport === "function" ? renderReport : null;

  function renderAdditionalFindingsFallback(report) {
    if (!additionalFindings) return;

    const findings = Array.isArray(report.additional_findings)
      ? report.additional_findings
      : [];

    if (!findings.length) return;

    additionalFindings.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Resource</th>
            <th>Finding</th>
            <th>Impact</th>
            <th>Priority</th>
          </tr>
        </thead>
        <tbody>
          ${findings.map((item) => {
            const resource = item && typeof item === "object" ? item.resource || "scope" : "scope";
            const finding = item && typeof item === "object" ? item.finding || item.summary || opsUiText(item) : opsUiText(item);
            const impact = item && typeof item === "object" ? item.impact || "Related operational signal." : "Related operational signal.";
            const priority = item && typeof item === "object" ? item.priority || item.severity || "Follow-up" : "Follow-up";

            return `
              <tr>
                <td>${opsUiEscape(resource)}</td>
                <td>${opsUiEscape(finding)}</td>
                <td>${opsUiEscape(impact)}</td>
                <td>${opsUiEscape(priority)}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    `;
  }

  renderReport = function (report) {
    if (previousRenderReport) {
      previousRenderReport(report);
    }

    // Always refresh command blocks using the copy-enabled renderer.
    if (typeof opsUiRenderCodeList === "function") {
      if (commands && typeof opsUiFixCommands === "function") {
        opsUiRenderCodeList(commands, opsUiFixCommands(report));
      }

      if (verificationCommands && typeof opsUiVerificationCommands === "function") {
        opsUiRenderCodeList(verificationCommands, opsUiVerificationCommands(report));
      }
    }

    const contributions = report.agent_contributions || {};
    const hasContributions = Object.keys(contributions).length > 0;

    if (!hasContributions) {
      renderAdditionalFindingsFallback(report);
    }
  };
})();

// =========================================================
// OpsLens final UI behavior polish v4
// =========================================================
// OpsLens final UI behavior polish v4
// 1) Clear History hides old backend records using cutoff timestamp.
// 2) Notify when report completes while user is not on Reports.
// 3) Auto-collapse sidebar/drawer after selecting a section.
// =========================================================

(function () {
  const HISTORY_CUTOFF_KEY = "opslens_history_clear_after_ms";

  function opsHistoryCutoffMs() {
    const raw = Number(localStorage.getItem(HISTORY_CUTOFF_KEY) || "0");
    return Number.isFinite(raw) ? raw : 0;
  }

  function opsRecordTimeMs(record) {
    const raw =
      record.finished_at ||
      record.modified_at ||
      record.created_at ||
      record.generated_at ||
      "";

    const date = new Date(raw);
    const ms = date.getTime();

    return Number.isNaN(ms) ? Date.now() : ms;
  }

  function opsFilterHistoryAfterCutoff(records) {
    const cutoff = opsHistoryCutoffMs();

    if (!cutoff) return records || [];

    return (records || []).filter((record) => {
      return opsRecordTimeMs(record) > cutoff;
    });
  }

  function opsRenderEmptyHistoryCleared() {
    if (!investigationRecords) return;

    investigationRecords.innerHTML = `
      <div class="empty-history">
        <strong>No app history</strong>
        <p>History was cleared for this browser. New completed investigations will appear here.</p>
      </div>
    `;
  }

  function opsClearHistoryForAppOnly() {
    const now = Date.now();

    try {
      localStorage.setItem(HISTORY_CUTOFF_KEY, String(now));

      [
        "opslens_cached_reports",
        "opslens_cached_reports_v2",
        "opslens_investigation_records",
        "opslens_active_pipeline_stage"
      ].forEach((key) => localStorage.removeItem(key));
    } catch (_) {}

    opsRenderEmptyHistoryCleared();

    if (typeof showToast === "function") {
      showToast(
        "History cleared",
        "Old history is hidden in this browser. New investigations will appear after they finish.",
        null,
        null,
        "success"
      );
    }
  }

  if (typeof renderBackendInvestigationRecords === "function") {
    const originalRenderBackendInvestigationRecords = renderBackendInvestigationRecords;

    renderBackendInvestigationRecords = function (records) {
      const filtered = opsFilterHistoryAfterCutoff(records || []);

      if (!filtered.length && opsHistoryCutoffMs()) {
        opsRenderEmptyHistoryCleared();
        return;
      }

      return originalRenderBackendInvestigationRecords(filtered);
    };
  }

  if (refreshHistoryBtn && refreshHistoryBtn.parentNode) {
    const clearButton = refreshHistoryBtn.cloneNode(true);
    clearButton.textContent = "Clear History";
    clearButton.title = "Clear frontend history";
    clearButton.setAttribute("aria-label", "Clear frontend history");

    refreshHistoryBtn.parentNode.replaceChild(clearButton, refreshHistoryBtn);

    clearButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      opsClearHistoryForAppOnly();
    });
  }

  if (clearRecordsBtn) {
    clearRecordsBtn.style.display = "none";
  }

  function opsCollapseNavigationAfterChoice() {
    try {
      if (typeof closeDrawer === "function") closeDrawer();

      document.body.classList.add("sidebar-collapsed");
      localStorage.setItem("opslens_sidebar_collapsed", "1");
    } catch (_) {}
  }

  document.querySelectorAll(".sidebar-link, .drawer-link").forEach((button) => {
    button.addEventListener("click", () => {
      setTimeout(opsCollapseNavigationAfterChoice, 30);
    }, true);
  });

  if (typeof handleCompletedJob === "function") {
    const originalHandleCompletedJob = handleCompletedJob;

    handleCompletedJob = async function (job, notify = true) {
      const activeViewBefore = localStorage.getItem("opslens_current_view") || "homeView";

      await originalHandleCompletedJob(job, false);

      if (!notify) return;

      if (activeViewBefore !== "reportView") {
        if (typeof setGlobalStatus === "function") {
          setGlobalStatus(
            "Report ready",
            "The investigation is complete. The RCA report is ready in Reports.",
            "Open Report",
            () => {
              if (typeof clearGlobalStatus === "function") clearGlobalStatus();
              showView("reportView");
            }
          );
        }

        if (typeof showToast === "function") {
          showToast(
            "Report ready",
            "The investigation finished successfully.",
            "Open Report",
            () => showView("reportView"),
            "success"
          );
        }
      }
    };
  }
})();

// =========================================================
// OpsLens final report/history alignment v5
// =========================================================
// OpsLens final report/history alignment v5
// - Shows only latest 5 backend reports.
// - Keeps Clear History cutoff behavior.
// - Aligns site report structure with PDF report.
// - Replaces unclear severity wording with Impact Level.
// =========================================================

(function () {
  const HISTORY_LIMIT = 5;
  const HISTORY_CUTOFF_KEY = "opslens_history_clear_after_ms";

  function finalText(value) {
    if (value === null || value === undefined) return "";

    if (typeof value === "string") {
      return value.replace(/\s+/g, " ").trim();
    }

    if (Array.isArray(value)) {
      return value.map(finalText).filter(Boolean).join(" ");
    }

    if (typeof value === "object") {
      const preferred = ["summary", "meaning", "message", "reason", "strategy", "intent", "finding", "command"];
      for (const key of preferred) {
        if (value[key]) return finalText(value[key]);
      }
      return Object.values(value).map(finalText).filter(Boolean).join(" ");
    }

    return String(value).trim();
  }

  function finalEscape(value) {
    if (typeof escapeHtml === "function") return escapeHtml(value || "");
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function finalAllText(report) {
    return finalText(report || {});
  }

  function finalAffected(report) {
    const affected = { ...((report && report.affected_resources) || {}) };
    const all = finalAllText(report);

    if (!affected.pod && !affected.pod_name) {
      const podMatch =
        all.match(/Pod\/([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i) ||
        all.match(/pod\s+'([^']+)'/i) ||
        all.match(/pod\s+([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i);

      if (podMatch) affected.pod = podMatch[1];
    }

    return affected;
  }

  function finalImpactLabel(report) {
    const severity = String((report && report.severity) || "unknown").toLowerCase();

    if (severity === "critical") return "Critical - workload unavailable";
    if (severity === "high") return "High - service degraded";
    if (severity === "medium") return "Medium - operational risk";
    if (severity === "low") return "Low - informational";
    return severity || "unknown";
  }

  function finalProblem(report) {
    const all = finalAllText(report).toLowerCase();
    const affected = finalAffected(report);

    const pod = affected.pod || affected.pod_name || "The affected pod";
    const deployment = affected.deployment || affected.deployment_name || "the deployment";

    if (all.includes("readiness") && all.includes("not ready")) {
      return `${pod} is failing readiness checks. Kubernetes keeps the pod NotReady, so ${deployment} has no available ready replica.`;
    }

    return (
      finalText(report.incident_summary) ||
      finalText(report.summary) ||
      "OpsLens detected an active Kubernetes workload issue."
    );
  }

  function finalRootCause(report) {
    const allRaw = finalAllText(report);
    const all = allRaw.toLowerCase();

    if (all.includes("readiness") && (all.includes("404") || all.includes("not-found"))) {
      const pathMatch = allRaw.match(/(\/healthz[-a-zA-Z0-9_/]*)/);
      if (pathMatch) {
        return `The readiness probe is configured to call '${pathMatch[1]}', but the application returns HTTP 404 for that endpoint. Because the health check fails, Kubernetes never marks the pod as Ready.`;
      }

      return "The readiness probe returns HTTP 404. Because the health check fails, Kubernetes keeps the pod NotReady and the deployment remains unavailable.";
    }

    return (
      finalText(report.root_cause_story) ||
      finalText(report.root_cause_hypothesis) ||
      "OpsLens selected the most likely root cause from the correlated Kubernetes, log, configuration, and metrics signals."
    );
  }

  function finalMetadataHtml(report) {
    const affected = finalAffected(report);

    const rows = [
      ["Namespace", affected.namespace || ""],
      ["Node", affected.node || affected.node_name || ""],
      ["Service", affected.service || affected.service_name || ""],
      ["Deployment", affected.deployment || affected.deployment_name || ""],
      ["Pod", affected.pod || affected.pod_name || ""],
      ["Impact Level", finalImpactLabel(report)],
      ["Confidence", report.confidence || ""],
      ["Detected Time", report.generated_at || report.created_at || report.finished_at || ""],
    ];

    return `
      <table>
        <tbody>
          ${rows.map(([key, value]) => `
            <tr>
              <th>${finalEscape(key)}</th>
              <td>${finalEscape(value || "-")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function finalCommandLines(report, mode) {
    const affected = finalAffected(report);
    const ns = affected.namespace || "default";
    const pod = affected.pod || affected.pod_name;
    const deployment = affected.deployment || affected.deployment_name;
    const service = affected.service || affected.service_name;

    const lines = [];

    if (mode === "fix") {
      if (deployment) {
        lines.push("# Inspect the current readinessProbe configuration");
        lines.push(`kubectl describe deployment ${deployment} -n ${ns}`);
        lines.push("");
        lines.push("# Edit the readinessProbe path/port to match the real application health endpoint");
        lines.push(`kubectl edit deployment ${deployment} -n ${ns}`);
        lines.push("");
        lines.push("# Watch the rollout after applying the fix");
        lines.push(`kubectl rollout status deployment/${deployment} -n ${ns}`);
      }

      if (service) lines.push(`kubectl get endpoints ${service} -n ${ns}`);
      return lines;
    }

    if (deployment) lines.push(`kubectl rollout status deployment/${deployment} -n ${ns}`);
    lines.push(`kubectl get pods -n ${ns}`);
    if (pod) lines.push(`kubectl describe pod ${pod} -n ${ns}`);
    if (service) lines.push(`kubectl get endpoints ${service} -n ${ns}`);
    lines.push(`kubectl get events -n ${ns} --sort-by=.lastTimestamp`);

    return [...new Set(lines)].slice(0, 8);
  }

  function finalRenderCode(container, lines) {
    if (!container) return;

    const text = (lines && lines.length ? lines : ["No command available."]).join("\n");

    container.innerHTML = `
      <div class="command command-copyable">
        <div class="command-header">
          <strong>Command block</strong>
          <button class="copy-btn" type="button">Copy</button>
        </div>
        <pre>${finalEscape(text)}</pre>
      </div>
    `;

    const btn = container.querySelector(".copy-btn");
    if (btn) {
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(text);
          if (typeof showToast === "function") showToast("Copied", "Commands copied to clipboard.");
        } catch (_) {
          alert("Copy failed. Please copy the commands manually.");
        }
      });
    }
  }

  function finalRelatedRows(report) {
    const rows = [];
    const findings = Array.isArray(report.additional_findings) ? report.additional_findings : [];

    findings.forEach((item) => {
      const text = finalText(item).toLowerCase();

      if (text.includes("deploymentnot found in collected evidence")) return;
      if (text.includes("not found in collected evidence status")) return;

      if (item && typeof item === "object") {
        rows.push([
          item.resource || item.pod_name || item.deployment_name || "scope",
          item.finding || item.summary || item.anomaly_type || "",
          item.impact || item.meaning || "Related operational signal.",
          item.priority || item.severity || "Follow-up",
        ]);
      } else if (finalText(item)) {
        rows.push(["scope", finalText(item), "Related operational signal.", "Follow-up"]);
      }
    });

    return rows.slice(0, 6);
  }

  function finalRelatedHtml(report) {
    const rows = finalRelatedRows(report);

    if (!rows.length) {
      return `<p class="muted">No separate related findings. The visible signals belong to the primary incident chain.</p>`;
    }

    return `
      <table>
        <thead>
          <tr>
            <th>Resource / Agent</th>
            <th>Finding</th>
            <th>Impact / Status</th>
            <th>Priority</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(([resource, finding, impact, priority]) => `
            <tr>
              <td>${finalEscape(resource)}</td>
              <td>${finalEscape(finding)}</td>
              <td>${finalEscape(impact)}</td>
              <td>${finalEscape(priority)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function finalSummary(report) {
    const affected = finalAffected(report);
    const workload =
      affected.deployment ||
      affected.deployment_name ||
      affected.service ||
      affected.service_name ||
      affected.pod ||
      affected.pod_name ||
      "the affected workload";

    const ns = affected.namespace || "the selected namespace";
    const node = affected.node || affected.node_name || "the selected node";
    const relatedCount = finalRelatedRows(report).length;

    let text = `OpsLens investigated ${workload} in namespace ${ns} on node ${node}. The primary problem is that ${finalProblem(report)} The root cause is that ${finalRootCause(report)}`;

    if (relatedCount) {
      text += ` OpsLens also found ${relatedCount} separate follow-up signal(s), listed separately so they are not confused with the primary root cause.`;
    }

    return text;
  }

  function finalSetCardTitle(element, title) {
    if (!element) return;
    const card = element.closest(".report-card");
    if (!card) return;
    const h3 = card.querySelector("h3");
    if (h3) h3.textContent = title;
  }

  renderReport = function (report) {
    currentReport = report;

    if (emptyState) emptyState.classList.add("hidden");
    if (reportSection) reportSection.classList.remove("hidden");

    const affected = finalAffected(report);
    const workload =
      affected.deployment ||
      affected.deployment_name ||
      affected.service ||
      affected.service_name ||
      affected.pod ||
      affected.pod_name ||
      "OpsLens Incident";

    if (reportTitle) reportTitle.textContent = `Incident Report: ${workload}`;
    if (severityBadge) severityBadge.textContent = `Impact: ${finalImpactLabel(report)}`;
    if (confidenceBadge) confidenceBadge.textContent = `Confidence: ${report.confidence || "unknown"}`;

    finalSetCardTitle(incidentSummary, "Primary Problem");
    finalSetCardTitle(rootCause, "Root Cause");
    finalSetCardTitle(evidenceTrail, "Metadata / Scope");
    finalSetCardTitle(additionalFindings, "Related Findings / Agent Status");
    finalSetCardTitle(fixStrategy, "Recommended Fix");
    finalSetCardTitle(commands, "Recommended Fix Commands");
    finalSetCardTitle(verificationIntent, "Verification");
    finalSetCardTitle(verificationCommands, "Verification Commands");

    if (incidentSummary) incidentSummary.textContent = finalProblem(report);
    if (rootCause) rootCause.textContent = finalRootCause(report);
    if (evidenceTrail) evidenceTrail.innerHTML = finalMetadataHtml(report);
    if (additionalFindings) additionalFindings.innerHTML = finalRelatedHtml(report);

    if (fixStrategy) {
      fixStrategy.textContent = "Apply the recommended command block after reviewing the deployment configuration and expected health endpoint.";
    }

    if (actions) actions.innerHTML = "";
    finalRenderCode(commands, finalCommandLines(report, "fix"));

    if (verificationIntent) {
      verificationIntent.textContent = "Run these commands after applying the fix to confirm the rollout, pod readiness, endpoints, and recent events.";
    }

    finalRenderCode(verificationCommands, finalCommandLines(report, "verify"));

    if (storySteps) {
      storySteps.innerHTML = `
        <div class="story-step"><span>1</span><div><strong>Scope</strong><p>${finalEscape(workload)} was investigated inside ${finalEscape(affected.namespace || "-")}.</p></div></div>
        <div class="story-step"><span>2</span><div><strong>Problem</strong><p>${finalEscape(finalProblem(report))}</p></div></div>
        <div class="story-step"><span>3</span><div><strong>Cause</strong><p>${finalEscape(finalRootCause(report))}</p></div></div>
        <div class="story-step"><span>4</span><div><strong>Action</strong><p>Use the fix commands, then verify rollout and endpoints.</p></div></div>
      `;
    }

    if (typeof observeReveal === "function") observeReveal();
    if (typeof requestScrollMotion === "function") requestScrollMotion();
  };

  function recordTimeMs(record) {
    const raw = record.finished_at || record.modified_at || record.created_at || record.generated_at || "";
    const ms = new Date(raw).getTime();
    return Number.isNaN(ms) ? Date.now() : ms;
  }

  function historyCutoffMs() {
    const raw = Number(localStorage.getItem(HISTORY_CUTOFF_KEY) || "0");
    return Number.isFinite(raw) ? raw : 0;
  }

  function filterRecords(records) {
    const cutoff = historyCutoffMs();

    let filtered = Array.isArray(records) ? records : [];

    if (cutoff) {
      filtered = filtered.filter((record) => recordTimeMs(record) > cutoff);
    }

    return filtered.slice(0, HISTORY_LIMIT);
  }

  const oldRenderBackendInvestigationRecords =
    typeof renderBackendInvestigationRecords === "function"
      ? renderBackendInvestigationRecords
      : null;

  renderBackendInvestigationRecords = function (records) {
    const filtered = filterRecords(records);

    if (!filtered.length) {
      if (investigationRecords) {
        investigationRecords.innerHTML = `
          <div class="empty-history">
            <strong>No reports yet</strong>
            <p>Run an investigation first. The latest ${HISTORY_LIMIT} reports will appear here.</p>
          </div>
        `;
      }
      return;
    }

    if (oldRenderBackendInvestigationRecords) {
      return oldRenderBackendInvestigationRecords(filtered);
    }
  };

  loadBackendInvestigationHistory = async function () {
    if (!investigationRecords) return;

    investigationRecords.innerHTML = `<p class="muted">Loading investigation history.</p>`;

    try {
      const result = await api(`/api/db/history?limit=${HISTORY_LIMIT}`);
      renderBackendInvestigationRecords(result.records || []);
    } catch (error) {
      investigationRecords.innerHTML = `
        <div class="history-error">
          <strong>Could not load backend history</strong>
          <p>${finalEscape(error.message || error)}</p>
        </div>
      `;
    }
  };
})();

// =========================================================
// OpsLens persistent hidden history ids v6
// =========================================================
// OpsLens persistent hidden history ids v6
// Clear History hides current backend records by record_id.
// It persists across refresh but does NOT delete DB/files.
// Shows only latest 5 visible records.
// =========================================================

(function () {
  const HIDDEN_IDS_KEY = "opslens_hidden_history_record_ids";
  const HISTORY_LIMIT = 5;

  function histGetHiddenIds() {
    try {
      return new Set(JSON.parse(localStorage.getItem(HIDDEN_IDS_KEY) || "[]"));
    } catch (_) {
      return new Set();
    }
  }

  function histSaveHiddenIds(ids) {
    try {
      localStorage.setItem(HIDDEN_IDS_KEY, JSON.stringify(Array.from(ids)));
    } catch (_) {}
  }

  function histRecordId(record) {
    if (!record) return "";

    return String(
      record.record_id ||
      record.id ||
      record.job_id ||
      record.investigation_id ||
      record.run_id ||
      record.json_report_path ||
      `${record.title || ""}|${record.created_at || ""}|${record.generated_at || ""}`
    );
  }

  function histFilter(records) {
    const hidden = histGetHiddenIds();

    return (records || [])
      .filter((record) => {
        const id = histRecordId(record);
        return id && !hidden.has(id);
      })
      .slice(0, HISTORY_LIMIT);
  }

  function histRenderEmpty() {
    if (!investigationRecords) return;

    investigationRecords.innerHTML = `
      <div class="empty-history">
        <strong>No reports shown</strong>
        <p>History was cleared in this browser. New completed investigations will appear here.</p>
      </div>
    `;
  }

  async function histClearVisibleHistory() {
    const hidden = histGetHiddenIds();

    try {
      const result = await api("/api/db/history?limit=100");
      (result.records || []).forEach((record) => {
        const id = histRecordId(record);
        if (id) hidden.add(id);
      });
    } catch (_) {
      document.querySelectorAll("[data-record-id]").forEach((el) => {
        const id = el.getAttribute("data-record-id");
        if (id) hidden.add(id);
      });
    }

    [
      "opslens_cached_reports",
      "opslens_cached_reports_v2",
      "opslens_investigation_records"
    ].forEach((key) => {
      try { localStorage.removeItem(key); } catch (_) {}
    });

    histSaveHiddenIds(hidden);
    histRenderEmpty();

    if (typeof showToast === "function") {
      showToast("History cleared", "Old reports are hidden in this browser. Database files were not deleted.");
    }
  }

  const originalRenderBackend =
    typeof renderBackendInvestigationRecords === "function"
      ? renderBackendInvestigationRecords
      : null;

  renderBackendInvestigationRecords = function (records) {
    const visible = histFilter(records || []);

    if (!visible.length) {
      histRenderEmpty();
      return;
    }

    if (originalRenderBackend) {
      return originalRenderBackend(visible);
    }

    if (investigationRecords) {
      investigationRecords.innerHTML = visible.map((record) => `
        <div class="record-card" data-record-id="${histRecordId(record)}">
          <strong>${record.title || record.service || "Report"}</strong>
          <p>${record.namespace || ""}</p>
        </div>
      `).join("");
    }
  };

  loadBackendInvestigationHistory = async function () {
    if (!investigationRecords) return;

    investigationRecords.innerHTML = `<p class="muted">Loading investigation history.</p>`;

    try {
      const result = await api("/api/db/history?limit=100");
      renderBackendInvestigationRecords(result.records || []);
    } catch (error) {
      investigationRecords.innerHTML = `
        <div class="history-error">
          <strong>Could not load history</strong>
          <p>${String(error.message || error)}</p>
        </div>
      `;
    }
  };

  const refresh = document.getElementById("refreshHistoryBtn");

  if (refresh && refresh.parentNode) {
    const clearButton = refresh.cloneNode(true);
    clearButton.textContent = "Clear History";
    clearButton.title = "Clear visible app history";
    clearButton.setAttribute("aria-label", "Clear visible app history");

    refresh.parentNode.replaceChild(clearButton, refresh);

    clearButton.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      await histClearVisibleHistory();
    });
  }

  if (clearRecordsBtn) {
    clearRecordsBtn.style.display = "none";
  }
})();

// =========================================================
// OpsLens clear history also clears current report view v7
// =========================================================
// OpsLens clear history also clears current report view v7
// Clear History now:
// - hides current backend history records,
// - clears currentReport,
// - resets the Reports page,
// - prevents latest report auto-restore after browser refresh.
// =========================================================

(function () {
  const HIDDEN_IDS_KEY = "opslens_hidden_history_record_ids";
  const REPORT_VIEW_CLEARED_KEY = "opslens_report_view_cleared";

  function clearViewGetHiddenIds() {
    try {
      return new Set(JSON.parse(localStorage.getItem(HIDDEN_IDS_KEY) || "[]"));
    } catch (_) {
      return new Set();
    }
  }

  function clearViewSaveHiddenIds(ids) {
    try {
      localStorage.setItem(HIDDEN_IDS_KEY, JSON.stringify(Array.from(ids)));
    } catch (_) {}
  }

  function clearViewReportId(report) {
    if (!report) return "";

    return String(
      report.record_id ||
      report.job_id ||
      report.__opslens_job_id ||
      report.investigation_id ||
      report.run_id ||
      report.json_report_path ||
      `${report.title || ""}|${report.created_at || ""}|${report.generated_at || ""}|${report.finished_at || ""}`
    );
  }

  function clearViewRecordId(record) {
    if (!record) return "";

    return String(
      record.record_id ||
      record.id ||
      record.job_id ||
      record.investigation_id ||
      record.run_id ||
      record.json_report_path ||
      `${record.title || ""}|${record.created_at || ""}|${record.generated_at || ""}|${record.finished_at || ""}`
    );
  }

  function clearViewIsHiddenReport(report) {
    const id = clearViewReportId(report);
    if (!id) return false;
    return clearViewGetHiddenIds().has(id);
  }

  function clearCurrentReportView() {
    currentReport = null;
    currentJobId = null;

    try {
      localStorage.setItem(REPORT_VIEW_CLEARED_KEY, "1");
      localStorage.removeItem("opslens_cached_reports");
      localStorage.removeItem("opslens_cached_reports_v2");
      localStorage.removeItem("opslens_investigation_records");
      localStorage.removeItem("opslens_active_job_id");
      localStorage.removeItem("opslens_active_pipeline_stage");
    } catch (_) {}

    if (reportTitle) reportTitle.textContent = "No report yet";
    if (severityBadge) severityBadge.textContent = "Impact: -";
    if (confidenceBadge) confidenceBadge.textContent = "Confidence: -";

    if (incidentSummary) incidentSummary.textContent = "";
    if (rootCause) rootCause.textContent = "";
    if (evidenceTrail) evidenceTrail.innerHTML = "";
    if (additionalFindings) additionalFindings.innerHTML = "";
    if (fixStrategy) fixStrategy.textContent = "";
    if (actions) actions.innerHTML = "";
    if (commands) commands.innerHTML = "";
    if (verificationIntent) verificationIntent.textContent = "";
    if (verificationCommands) verificationCommands.innerHTML = "";
    if (storySteps) storySteps.innerHTML = "";

    if (reportSection) reportSection.classList.add("hidden");

    if (emptyState) {
      emptyState.classList.remove("hidden");
      const heading = emptyState.querySelector("h2, h3, strong");
      const paragraph = emptyState.querySelector("p");

      if (heading) heading.textContent = "No report yet";
      if (paragraph) paragraph.textContent = "Run or open a new investigation report to display it here.";
    }

    if (downloadReportBtn) downloadReportBtn.disabled = true;
    if (copySummaryBtn) copySummaryBtn.disabled = true;
  }

  async function clearHistoryAndCurrentReport() {
    const hidden = clearViewGetHiddenIds();

    try {
      const result = await api("/api/db/history?limit=100");
      (result.records || []).forEach((record) => {
        const id = clearViewRecordId(record);
        if (id) hidden.add(id);
      });
    } catch (_) {}

    if (currentReport) {
      const currentId = clearViewReportId(currentReport);
      if (currentId) hidden.add(currentId);
    }

    document.querySelectorAll("[data-record-id]").forEach((el) => {
      const id = el.getAttribute("data-record-id");
      if (id) hidden.add(id);
    });

    clearViewSaveHiddenIds(hidden);
    clearCurrentReportView();

    if (investigationRecords) {
      investigationRecords.innerHTML = `
        <div class="empty-history">
          <strong>No reports shown</strong>
          <p>History and the current report view were cleared in this browser. New completed investigations will appear here.</p>
        </div>
      `;
    }

    if (typeof showToast === "function") {
      showToast("Cleared", "History and current report view were cleared.");
    }
  }

  // Make existing Clear History button also clear the currently displayed report.
  document.addEventListener("click", function (event) {
    const button = event.target.closest("button");
    if (!button) return;

    const text = (button.textContent || "").trim().toLowerCase();
    const id = button.id || "";

    if (id === "refreshHistoryBtn" || text === "clear history") {
      event.preventDefault();
      event.stopPropagation();
      clearHistoryAndCurrentReport();
    }
  }, true);

  // Prevent hidden/cleared report from re-rendering.
  if (typeof renderReport === "function") {
    const previousRenderReportForClearView = renderReport;

    renderReport = function (report) {
      if (localStorage.getItem(REPORT_VIEW_CLEARED_KEY) === "1" && clearViewIsHiddenReport(report)) {
        clearCurrentReportView();
        return;
      }

      try {
        localStorage.removeItem(REPORT_VIEW_CLEARED_KEY);
      } catch (_) {}

      if (downloadReportBtn) downloadReportBtn.disabled = false;
      if (copySummaryBtn) copySummaryBtn.disabled = false;

      return previousRenderReportForClearView(report);
    };
  }

  // Prevent latest cached/backend auto-restore after clear.
  restoreLatestCachedReport = function () {
    if (localStorage.getItem(REPORT_VIEW_CLEARED_KEY) === "1") {
      clearCurrentReportView();
      return;
    }
    return null;
  };

  restoreLatestBackendReportIfNeeded = async function () {
    const currentView = localStorage.getItem("opslens_current_view") || "";

    if (currentView !== "reportView") return;
    if (currentReport) return;

    if (localStorage.getItem(REPORT_VIEW_CLEARED_KEY) === "1") {
      clearCurrentReportView();
      return;
    }

    try {
      const history = await api("/api/db/history?limit=1");
      const latest = (history.records || [])[0];

      if (!latest || !latest.record_id) return;

      const hidden = clearViewGetHiddenIds();
      if (hidden.has(String(latest.record_id))) {
        clearCurrentReportView();
        return;
      }

      const report = await api(`/api/db/history/${encodeURIComponent(latest.record_id)}`);

      if (clearViewIsHiddenReport(report)) {
        clearCurrentReportView();
        return;
      }

      currentReport = report;
      renderReport(report);
    } catch (error) {
      console.warn("Could not restore latest backend report:", error);
    }
  };

  // When a new investigation starts, allow new report rendering again.
  if (runBtn) {
    runBtn.addEventListener("click", () => {
      try {
        localStorage.removeItem(REPORT_VIEW_CLEARED_KEY);
      } catch (_) {}
    }, true);
  }
})();

// =========================================================
// OpsLens Enterprise Report View v13
// =========================================================
// OpsLens Enterprise Report View v13
// Aligns site report with enterprise PDF sections.
// =========================================================

(function () {
  function entText(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value.replace(/\s+/g, " ").trim();
    if (Array.isArray(value)) return value.map(entText).filter(Boolean).join(" ");
    if (typeof value === "object") {
      const preferred = ["summary", "meaning", "message", "reason", "strategy", "intent", "finding", "command"];
      for (const key of preferred) {
        if (value[key]) return entText(value[key]);
      }
      return Object.values(value).map(entText).filter(Boolean).join(" ");
    }
    return String(value).trim();
  }

  function entEsc(value) {
    if (typeof escapeHtml === "function") return escapeHtml(value || "");
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function entAffected(report) {
    const affected = { ...((report && report.affected_resources) || {}) };
    const all = entText(report);

    if (!affected.pod && !affected.pod_name) {
      const podMatch =
        all.match(/Pod\/([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i) ||
        all.match(/pod\s+'([^']+)'/i) ||
        all.match(/pod\s+([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i);
      if (podMatch) affected.pod = podMatch[1];
    }

    return affected;
  }

  function entImpact(report) {
    const severity = String((report && report.severity) || "unknown").toLowerCase();
    if (severity === "critical") return "Critical - workload unavailable";
    if (severity === "warning") return "Warning - degraded or anomalous";
    if (severity === "info") return "Info - informational";
    return severity;
  }

  function entProblem(report) {
    return entText(report.incident_summary) || "Analysis Inconclusive.";
  }

  function entRoot(report) {
    return entText(report.root_cause_story || report.root_cause_hypothesis) || "Analysis Inconclusive.";
  }

  function entWorkload(report) {
    const a = entAffected(report);
    return a.service || a.deployment || a.deployment_name || a.pod || a.pod_name || "Kubernetes Workload";
  }

  function entSummary(report) {
    const a = entAffected(report);
    const ns = a.namespace || "the selected namespace";
    const workload = entWorkload(report);
    return [
      `Failure: ${entProblem(report)}`,
      `Root Cause: ${entRoot(report)}`,
      `Operational Impact: The impact is scoped to ${workload} in namespace ${ns}, with impact level: ${entImpact(report)}.`
    ];
  }

  function entRelatedRows(report) {
    const findings = Array.isArray(report.additional_findings) ? report.additional_findings : [];
    const rows = [];

    findings.forEach((item) => {
      const text = entText(item).toLowerCase();
      if (text.includes("agentexecutionerror") || text.includes("deploymentnot found in collected evidence")) return;

      if (item && typeof item === "object") {
        const resource = item.resource || item.pod_name || item.deployment_name || "scope";
        const finding = item.finding || item.summary || item.anomaly_type || "";
        const impact = item.impact || item.meaning || "Related operational signal.";
        const priority = item.priority || item.severity || "Follow-up";
        if (finding) rows.push([resource, finding, `${impact} / ${priority}`]);
      } else if (entText(item)) {
        rows.push(["scope", entText(item), "Related operational signal / Follow-up"]);
      }
    });

    return rows.slice(0, 8);
  }

  function entCommandLines(lines, limit) {
    const clean = [];
    const seen = new Set();

    (lines || []).forEach((line) => {
      const item = String(line || "").trim();
      if (!item.startsWith("kubectl ")) return;
      const key = item.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      clean.push(item);
    });

    return clean.slice(0, limit);
  }

  function entFix(report) {
    if (typeof opsUiFixCommands === "function") {
      return entCommandLines(opsUiFixCommands(report), 3);
    }
    return [];
  }

  function entVerify(report) {
    if (typeof opsUiVerificationCommands === "function") {
      return entCommandLines(opsUiVerificationCommands(report), 2);
    }
    return [];
  }

  function entDiagnosticRows(report) {
    const a = entAffected(report);
    const rows = [];

    if (a.service || a.service_name) rows.push(["Service", a.service || a.service_name, "In investigation scope"]);
    if (a.deployment || a.deployment_name) rows.push(["Deployment", a.deployment || a.deployment_name, "Affected workload"]);
    if (a.pod || a.pod_name) rows.push(["Pod", a.pod || a.pod_name, "Affected pod"]);

    const agents = Array.isArray(report.agent_run_status) ? report.agent_run_status : [];
    agents.slice(0, 8).forEach((item) => {
      rows.push([
        `Agent: ${item.agent || "agent"}`,
        `${item.status || "completed"} (${item.event_count || 0} signal(s))`,
        item.finding || "No active signal detected."
      ]);
    });

    return rows;
  }

  function entTable(headers, rows) {
    return `
      <table>
        <thead>
          <tr>${headers.map((h) => `<th>${entEsc(h)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>${row.map((cell) => `<td>${entEsc(cell || "-")}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    `;
  }

  function entRenderCode(container, lines) {
    if (!container) return;

    const text = (lines && lines.length ? lines : ["# Analysis Inconclusive"]).join("\n");

    container.innerHTML = `
      <div class="command command-copyable">
        <div class="command-header">
          <strong>Command block</strong>
          <button class="copy-btn" type="button">Copy</button>
        </div>
        <pre>${entEsc(text)}</pre>
      </div>
    `;

    const btn = container.querySelector(".copy-btn");
    if (btn) {
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(text);
          if (typeof showToast === "function") showToast("Copied", "Commands copied to clipboard.");
        } catch (_) {
          alert("Copy failed. Please copy manually.");
        }
      });
    }
  }

  function entSetCardTitle(element, title) {
    if (!element) return;
    const card = element.closest(".report-card");
    if (!card) return;
    const h3 = card.querySelector("h3");
    if (h3) h3.textContent = title;
  }

  renderReport = function (report) {
    currentReport = report;

    if (emptyState) emptyState.classList.add("hidden");
    if (reportSection) reportSection.classList.remove("hidden");

    const a = entAffected(report);
    const workload = entWorkload(report);

    if (reportTitle) reportTitle.textContent = `Incident Report: ${workload}`;
    if (severityBadge) severityBadge.textContent = `Impact: ${entImpact(report)}`;
    if (confidenceBadge) confidenceBadge.textContent = `Confidence: ${report.confidence || "unknown"}`;

    entSetCardTitle(incidentSummary, "What happened");
    entSetCardTitle(rootCause, "Why it happened");
    entSetCardTitle(evidenceTrail, "Header / Scope");
    entSetCardTitle(additionalFindings, "Related findings / technical evidence");
    entSetCardTitle(fixStrategy, "Recommended next actions");
    entSetCardTitle(commands, "Recommended commands");
    entSetCardTitle(verificationIntent, "Validation checks");
    entSetCardTitle(verificationCommands, "Validation commands");

    if (incidentSummary) {
      incidentSummary.innerHTML = `
        <ul>
          ${entSummary(report).map((item) => `<li>${entEsc(item)}</li>`).join("")}
        </ul>
      `;
    }

    if (rootCause) {
      rootCause.innerHTML = `
        <p><strong>Root Cause:</strong> ${entEsc(entRoot(report))}</p>
        <p><strong>Why it is the blocker:</strong> ${entEsc(entProblem(report))}</p>
      `;
    }

    if (evidenceTrail) {
      evidenceTrail.innerHTML = entTable(
        ["Field", "Value"],
        [
          ["Namespace", a.namespace || ""],
          ["Node", a.node || a.node_name || ""],
          ["Service", a.service || a.service_name || ""],
          ["Deployment", a.deployment || a.deployment_name || ""],
          ["Pod", a.pod || a.pod_name || ""],
          ["Impact", entImpact(report)],
          ["Confidence", report.confidence || ""],
          ["Time", report.generated_at || report.created_at || report.finished_at || ""],
        ]
      );
    }

    const related = entRelatedRows(report);
    const diagnostic = entDiagnosticRows(report);

    if (additionalFindings) {
      additionalFindings.innerHTML = `
        <h4>Related Findings</h4>
        ${
          related.length
            ? entTable(["Resource", "Finding", "Impact / Priority"], related)
            : `<p class="muted">No separate unrelated findings were identified.</p>`
        }
        <h4>Technical evidence</h4>
        ${entTable(["Type", "Resource / Agent", "Status"], diagnostic.length ? diagnostic : [["Scope", "No diagnostic details", "Analysis Inconclusive"]])}
      `;
    }

    if (fixStrategy) {
      fixStrategy.textContent = "Review these recommended next actions before applying changes.";
    }

    if (actions) actions.innerHTML = "";
    entRenderCode(commands, entFix(report));

    if (verificationIntent) {
      verificationIntent.textContent = "Run these checks after remediation to validate recovery.";
    }

    entRenderCode(verificationCommands, entVerify(report));

    if (storySteps) {
      storySteps.innerHTML = `
        <div class="story-step"><span>1</span><div><strong>Why it happened</strong><p>${entEsc(entProblem(report))}</p></div></div>
        <div class="story-step"><span>2</span><div><strong>Root Cause</strong><p>${entEsc(entRoot(report))}</p></div></div>
        <div class="story-step"><span>3</span><div><strong>Remediate</strong><p>Review the recommended actions.</p></div></div>
        <div class="story-step"><span>4</span><div><strong>Verify</strong><p>Validate rollout, pod status, endpoints, or anomaly recovery.</p></div></div>
      `;
    }

    if (typeof observeReveal === "function") observeReveal();
    if (typeof requestScrollMotion === "function") requestScrollMotion();
  };
})();

// =========================================================
// OpsLens CrashLoop UI command alignment v15
// =========================================================
// OpsLens CrashLoop UI command alignment v15
// Ensures site remediation/verification matches PDF logic for CrashLoop/app traceback.
// =========================================================

(function () {
  function v15Text(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value.replace(/\s+/g, " ").trim();
    if (Array.isArray(value)) return value.map(v15Text).filter(Boolean).join(" ");
    if (typeof value === "object") return Object.values(value).map(v15Text).filter(Boolean).join(" ");
    return String(value).trim();
  }

  function v15Affected(report) {
    const affected = { ...((report && report.affected_resources) || {}) };
    const all = v15Text(report);

    if (!affected.pod && !affected.pod_name) {
      const m =
        all.match(/Pod\/([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i) ||
        all.match(/pod\s+'([^']+)'/i) ||
        all.match(/pod\s+([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i);

      if (m) affected.pod = m[1];
    }

    return affected;
  }

  function v15IncidentType(report) {
    const text = v15Text({
      title: report.title,
      incident_summary: report.incident_summary,
      root_cause_story: report.root_cause_story,
      root_cause_facts: report.root_cause_facts,
      agent_reasoning: report.agent_reasoning,
      affected_resources: report.affected_resources,
    }).toLowerCase();

    if (text.includes("selector") && (text.includes("endpoint") || text.includes("service"))) return "service_selector";
    if (text.includes("traceback") || text.includes("fatal") || text.includes("crashloopbackoff")) return "crashloop";
    if (text.includes("oomkilled") || text.includes("outofmemory")) return "oom";
    if (text.includes("podlstmresourceanomaly") || text.includes("higher than predicted")) return "pod_cpu_anomaly";
    if (text.includes("readiness") && (text.includes("404") || text.includes("not-found"))) return "readiness_404";
    return "generic";
  }

  function v15Problem(report) {
    const a = v15Affected(report);
    const pod = a.pod || a.pod_name || "the affected pod";
    const deployment = a.deployment || a.deployment_name || "the deployment";
    const type = v15IncidentType(report);

    if (type === "crashloop") {
      return `${pod} is stuck in CrashLoopBackOff because the application container fails during startup. As a result, ${deployment} cannot reach a stable Ready state.`;
    }

    return v15Text(report.incident_summary) || "Analysis Inconclusive.";
  }

  function v15Commands(report, mode) {
    const a = v15Affected(report);
    const ns = a.namespace || "default";
    const pod = a.pod || a.pod_name;
    const deployment = a.deployment || a.deployment_name;
    const service = a.service || a.service_name;
    const type = v15IncidentType(report);

    if (mode === "fix") {
      if (type === "crashloop") {
        return [
          pod ? `kubectl describe pod ${pod} -n ${ns}` : "",
          pod ? `kubectl logs ${pod} -n ${ns} --previous` : "",
          deployment ? `kubectl describe deployment ${deployment} -n ${ns}` : "",
        ].filter(Boolean).slice(0, 3);
      }

      if (type === "service_selector") {
        return [
          service ? `kubectl get svc ${service} -n ${ns} -o yaml` : "",
          service ? `kubectl get endpoints ${service} -n ${ns}` : "",
          `kubectl get pods -n ${ns} --show-labels`,
        ].filter(Boolean).slice(0, 3);
      }

      if (type === "pod_cpu_anomaly") {
        return [
          pod ? `kubectl top pod ${pod} -n ${ns}` : "",
          pod ? `kubectl describe pod ${pod} -n ${ns}` : "",
          pod ? `kubectl logs ${pod} -n ${ns} --tail=120` : "",
        ].filter(Boolean).slice(0, 3);
      }
    }

    if (mode === "verify") {
      if (type === "crashloop") {
        return [
          `kubectl get pods -n ${ns}`,
          pod ? `kubectl logs ${pod} -n ${ns} --tail=80` : "",
        ].filter(Boolean).slice(0, 2);
      }

      if (type === "service_selector") {
        return [
          service ? `kubectl get endpoints ${service} -n ${ns}` : "",
          `kubectl get pods -n ${ns} --show-labels`,
        ].filter(Boolean).slice(0, 2);
      }

      if (type === "pod_cpu_anomaly") {
        return [
          pod ? `kubectl top pod ${pod} -n ${ns}` : "",
          pod ? `kubectl logs ${pod} -n ${ns} --tail=80` : "",
        ].filter(Boolean).slice(0, 2);
      }
    }

    if (mode === "fix") {
      return [
        deployment ? `kubectl describe deployment ${deployment} -n ${ns}` : "",
        deployment ? `kubectl rollout status deployment/${deployment} -n ${ns}` : "",
      ].filter(Boolean);
    }

    return [
      `kubectl get pods -n ${ns}`,
      deployment ? `kubectl rollout status deployment/${deployment} -n ${ns}` : "",
    ].filter(Boolean).slice(0, 2);
  }

  function v15RenderCode(container, lines) {
    if (!container) return;

    const text = (lines && lines.length ? lines : ["# Analysis Inconclusive"]).join("\n");

    container.innerHTML = `
      <div class="command command-copyable">
        <div class="command-header">
          <strong>Command block</strong>
          <button class="copy-btn" type="button">Copy</button>
        </div>
        <pre>${escapeHtml(text)}</pre>
      </div>
    `;

    const btn = container.querySelector(".copy-btn");
    if (btn) {
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(text);
          if (typeof showToast === "function") showToast("Copied", "Commands copied to clipboard.");
        } catch (_) {
          alert("Copy failed. Please copy manually.");
        }
      });
    }
  }

  const oldRenderReportV15 = typeof renderReport === "function" ? renderReport : null;

  renderReport = function (report) {
    if (oldRenderReportV15) oldRenderReportV15(report);

    if (incidentSummary && v15IncidentType(report) === "crashloop") {
      const items = [
        `Failure: ${v15Problem(report)}`,
        `Root Cause: ${v15Text(report.root_cause_story) || "Analysis Inconclusive."}`,
        `Operational Impact: Impact is scoped to ${v15Affected(report).deployment || v15Affected(report).deployment_name || "the workload"}.`,
      ];

      incidentSummary.innerHTML = `<ul>${items.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>`;
    }

    v15RenderCode(commands, v15Commands(report, "fix"));
    v15RenderCode(verificationCommands, v15Commands(report, "verify"));
  };
})();

// =========================================================
// OpsLens Final Generic UI Command Alignment v16
// =========================================================
// OpsLens Final Generic UI Command Alignment v16
// Purpose:
// - Neutralizes any scenario-specific UI command patch.
// - Keeps site commands aligned with the same generic incident categories used by backend guard.
// - Does not change API calls or animations.
// =========================================================

(function () {
  function f16Text(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value.replace(/\s+/g, " ").trim();
    if (Array.isArray(value)) return value.map(f16Text).filter(Boolean).join(" ");
    if (typeof value === "object") {
      return Object.values(value).map(f16Text).filter(Boolean).join(" ");
    }
    return String(value).trim();
  }

  function f16Affected(report) {
    const affected = { ...((report && report.affected_resources) || {}) };
    const all = f16Text(report);

    if (!affected.pod && !affected.pod_name) {
      const m =
        all.match(/Pod\/([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i) ||
        all.match(/pod\s+'([^']+)'/i) ||
        all.match(/pod\s+([a-z0-9][a-z0-9.-]*-[a-z0-9]+)/i);

      if (m) affected.pod = m[1];
    }

    return affected;
  }

  function f16PrimaryText(report) {
    return f16Text({
      title: report.title,
      incident_summary: report.incident_summary,
      root_cause_story: report.root_cause_story,
      root_cause_hypothesis: report.root_cause_hypothesis,
      primary_incident_group: report.primary_incident_group,
      root_cause_facts: report.root_cause_facts,
      agent_reasoning: report.agent_reasoning,
      evidence_trail: report.evidence_trail,
      affected_resources: report.affected_resources
    }).toLowerCase();
  }

  function f16IncidentType(report) {
    const text = f16PrimaryText(report);

    if ((text.includes("selector") && (text.includes("endpoint") || text.includes("service"))) ||
        text.includes("empty endpoints") ||
        text.includes("service has no endpoints")) {
      return "service_selector";
    }

    if (text.includes("targetport") || text.includes("target port")) return "service_targetport";
    if (text.includes("imagepullbackoff") || text.includes("errimagepull") || text.includes("failed to pull image")) return "image_pull";
    if (text.includes("missing env") || text.includes("environment variable") || text.includes("keyerror")) return "missing_env";
    if (text.includes("oomkilled") || text.includes("outofmemory") || text.includes("out of memory")) return "oom";
    if (text.includes("podlstmresourceanomaly") || text.includes("higher than predicted") || text.includes("higher than expected")) return "pod_cpu_anomaly";
    if (text.includes("traceback") || text.includes("fatal") || text.includes("crashloopbackoff")) return "crashloop";
    if (text.includes("readiness") && (text.includes("404") || text.includes("not-found"))) return "readiness_404";
    if (text.includes("readiness")) return "readiness";

    return "generic";
  }

  function f16ExtractCommands(value) {
    const raw = f16Text(value);
    const parts = raw
      .replace(/`/g, "")
      .replace(/\s+and\s+(?=kubectl\s)/gi, "\n")
      .replace(/(?<!^)\s+(?=kubectl\s)/g, "\n")
      .split(/\n+/);

    const out = [];
    const seen = new Set();

    for (let line of parts) {
      line = line.trim();
      if (!line.includes("kubectl ")) continue;
      line = line.slice(line.toLowerCase().indexOf("kubectl "));
      line = line.replace(/\s+/g, " ").replace(/[,'"`;]+$/g, "").trim();
      if (!line.startsWith("kubectl ")) continue;
      const key = line.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(line);
    }

    return out;
  }

  function f16CommandsMatch(commands, type) {
    if (!commands || !commands.length) return false;
    const joined = commands.join("\n").toLowerCase();

    if (joined.includes("delete ")) return false;

    if (type === "service_selector") {
      return joined.includes("get svc") ||
             joined.includes("describe svc") ||
             joined.includes("get endpoints") ||
             joined.includes("show-labels") ||
             joined.includes("edit svc");
    }

    if (type === "crashloop" || type === "missing_env") {
      if (joined.includes("readinessprobe") || joined.includes("/healthz")) return false;
      const hasPodOrLogs = joined.includes("describe pod") || joined.includes("logs") || joined.includes("--previous");
      const hasContext = joined.includes("describe deployment") || joined.includes("edit deployment") || joined.includes("rollout status");
      return hasPodOrLogs && hasContext;
    }

    if (type === "oom") {
      if (joined.includes("readinessprobe") || joined.includes("/healthz")) return false;
      return joined.includes("--previous") ||
             joined.includes("top pod") ||
             joined.includes("describe pod") ||
             joined.includes("describe deployment") ||
             joined.includes("edit deployment");
    }

    if (type === "pod_cpu_anomaly") {
      if (joined.includes("oom") || joined.includes("--previous") || joined.includes("readinessprobe")) return false;
      return joined.includes("top pod") ||
             joined.includes("logs") ||
             joined.includes("describe pod") ||
             joined.includes("describe deployment");
    }

    if (type === "image_pull") {
      if (joined.includes("readinessprobe") || joined.includes("/healthz")) return false;
      return joined.includes("describe pod") ||
             joined.includes("get events") ||
             joined.includes("describe deployment") ||
             joined.includes("edit deployment");
    }

    if (type === "readiness_404" || type === "readiness") {
      return joined.includes("readiness") ||
             joined.includes("describe deployment") ||
             joined.includes("edit deployment") ||
             joined.includes("rollout status") ||
             joined.includes("get endpoints");
    }

    return true;
  }

  function f16FallbackCommands(report, mode) {
    const a = f16Affected(report);
    const ns = a.namespace || "default";
    const pod = a.pod || a.pod_name;
    const deployment = a.deployment || a.deployment_name;
    const service = a.service || a.service_name;
    const type = f16IncidentType(report);

    if (mode === "fix") {
      if (type === "service_selector") {
        return [
          service ? `kubectl get svc ${service} -n ${ns} -o yaml` : "",
          service ? `kubectl get endpoints ${service} -n ${ns}` : "",
          `kubectl get pods -n ${ns} --show-labels`
        ].filter(Boolean).slice(0, 3);
      }

      if (type === "crashloop" || type === "missing_env") {
        return [
          pod ? `kubectl describe pod ${pod} -n ${ns}` : "",
          pod ? `kubectl logs ${pod} -n ${ns} --previous` : "",
          deployment ? `kubectl describe deployment ${deployment} -n ${ns}` : ""
        ].filter(Boolean).slice(0, 3);
      }

      if (type === "oom") {
        return [
          pod ? `kubectl describe pod ${pod} -n ${ns}` : "",
          pod ? `kubectl logs ${pod} -n ${ns} --previous` : "",
          pod ? `kubectl top pod ${pod} -n ${ns}` : ""
        ].filter(Boolean).slice(0, 3);
      }

      if (type === "pod_cpu_anomaly") {
        return [
          pod ? `kubectl top pod ${pod} -n ${ns}` : "",
          pod ? `kubectl describe pod ${pod} -n ${ns}` : "",
          pod ? `kubectl logs ${pod} -n ${ns} --tail=120` : ""
        ].filter(Boolean).slice(0, 3);
      }

      if (type === "image_pull") {
        return [
          pod ? `kubectl describe pod ${pod} -n ${ns}` : "",
          `kubectl get events -n ${ns} --sort-by=.lastTimestamp`,
          deployment ? `kubectl describe deployment ${deployment} -n ${ns}` : ""
        ].filter(Boolean).slice(0, 3);
      }

      if (type === "readiness_404" || type === "readiness") {
        return [
          deployment ? `kubectl describe deployment ${deployment} -n ${ns}` : "",
          deployment ? `kubectl edit deployment ${deployment} -n ${ns}` : "",
          deployment ? `kubectl rollout status deployment/${deployment} -n ${ns}` : ""
        ].filter(Boolean).slice(0, 3);
      }

      return [
        deployment ? `kubectl describe deployment ${deployment} -n ${ns}` : "",
        pod ? `kubectl describe pod ${pod} -n ${ns}` : ""
      ].filter(Boolean).slice(0, 3);
    }

    if (mode === "verify") {
      if (type === "service_selector") {
        return [
          service ? `kubectl get endpoints ${service} -n ${ns}` : "",
          `kubectl get pods -n ${ns} --show-labels`
        ].filter(Boolean).slice(0, 2);
      }

      if (type === "pod_cpu_anomaly") {
        return [
          pod ? `kubectl top pod ${pod} -n ${ns}` : "",
          pod ? `kubectl logs ${pod} -n ${ns} --tail=80` : ""
        ].filter(Boolean).slice(0, 2);
      }

      if (type === "crashloop" || type === "missing_env") {
        return [
          `kubectl get pods -n ${ns}`,
          pod ? `kubectl logs ${pod} -n ${ns} --tail=80` : ""
        ].filter(Boolean).slice(0, 2);
      }

      return [
        deployment ? `kubectl rollout status deployment/${deployment} -n ${ns}` : "",
        `kubectl get pods -n ${ns}`
      ].filter(Boolean).slice(0, 2);
    }

    return [];
  }

  function f16FinalCommands(report, mode) {
    const type = f16IncidentType(report);
    const source = mode === "fix" ? report.recommended_fix : report.verification;
    const llm = f16ExtractCommands(source);

    if (mode === "fix" && f16CommandsMatch(llm, type)) {
      return llm.slice(0, 3);
    }

    if (mode === "verify" && llm.length) {
      return llm.filter((cmd) => !cmd.toLowerCase().includes("delete ")).slice(0, 2);
    }

    return f16FallbackCommands(report, mode);
  }

  function f16RenderCode(container, lines) {
    if (!container) return;

    const text = (lines && lines.length ? lines : ["# Analysis Inconclusive"]).join("\n");

    container.innerHTML = `
      <div class="command command-copyable">
        <div class="command-header">
          <strong>Command block</strong>
          <button class="copy-btn" type="button">Copy</button>
        </div>
        <pre>${escapeHtml(text)}</pre>
      </div>
    `;

    const btn = container.querySelector(".copy-btn");
    if (btn) {
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(text);
          if (typeof showToast === "function") showToast("Copied", "Commands copied to clipboard.");
        } catch (_) {
          alert("Copy failed. Please copy manually.");
        }
      });
    }
  }

  const previousRenderReportF16 = typeof renderReport === "function" ? renderReport : null;

  renderReport = function (report) {
    if (previousRenderReportF16) previousRenderReportF16(report);

    f16RenderCode(commands, f16FinalCommands(report, "fix"));
    f16RenderCode(verificationCommands, f16FinalCommands(report, "verify"));
  };
})();

// =========================================================
// OpsLens Friendly Technical Evidence Labels v19
// =========================================================
// OpsLens Friendly Technical Evidence Labels v19
// Display-only change.
// Renames raw internal agent keys in the report UI.
// =========================================================

(function () {
  const LABELS = {
    "agent: resource_metrics": "Node Resource Check",
    "agent: pod_lstm_metrics": "Pod Anomaly Check",
    "agent: kubernetes_events": "Kubernetes Events Check",
    "agent: logs": "Application Logs Check",
    "agent: ansible_config": "Workload Configuration Check",
    "resource_metrics": "Node Resource Check",
    "pod_lstm_metrics": "Pod Anomaly Check",
    "kubernetes_events": "Kubernetes Events Check",
    "logs": "Application Logs Check",
    "ansible_config": "Workload Configuration Check"
  };

  function friendlyEvidenceText(value) {
    const raw = String(value || "").trim();
    const key = raw.toLowerCase();

    if (LABELS[key]) return LABELS[key];

    if (key === "no active signal detected.") {
      return "No issue detected by this check.";
    }

    if (key.startsWith("agent:")) {
      return raw.replace(/^agent:/i, "Check:").trim();
    }

    return raw;
  }

  function applyFriendlyEvidenceLabels() {
    const root = additionalFindings || reportSection || document;

    if (!root) return;

    root.querySelectorAll("td, th, p, span").forEach((el) => {
      const text = (el.textContent || "").trim();
      const next = friendlyEvidenceText(text);

      if (next !== text) {
        el.textContent = next;
      }
    });

    root.querySelectorAll("th").forEach((th) => {
      const text = (th.textContent || "").trim().toLowerCase();

      if (text === "resource / agent") {
        th.textContent = "Source";
      }

      if (text === "status") {
        th.textContent = "Result";
      }

      if (text === "type") {
        th.textContent = "Evidence";
      }
    });
  }

  const previousRenderReportEvidenceLabels =
    typeof renderReport === "function" ? renderReport : null;

  renderReport = function (report) {
    if (previousRenderReportEvidenceLabels) {
      previousRenderReportEvidenceLabels(report);
    }

    applyFriendlyEvidenceLabels();
  };

  document.addEventListener("DOMContentLoaded", applyFriendlyEvidenceLabels);
})();

// =========================================================
// OpsLens Namespace Scenario Filter v1
// =========================================================
// OpsLens Namespace Scenario Filter v1
// Filters available demo scenarios based on selected namespace.
// Display-only/control-only patch; does not change animations or pipeline.
// =========================================================

(function () {
  let scenarioCatalogV1 = [];

  function nsScenarioText(value) {
    return String(value || "").trim();
  }

  function nsScenarioSelectedNamespace() {
    const candidates = [
      document.getElementById("namespaceSelect"),
      document.getElementById("namespace"),
      document.querySelector("[name='namespace']"),
      document.querySelector("select[data-role='namespace']")
    ].filter(Boolean);

    for (const el of candidates) {
      const value = nsScenarioText(el.value);
      if (value) return value;
    }

    return "";
  }

  function nsScenarioSelectElement() {
    return (
      document.getElementById("scenarioSelect") ||
      document.getElementById("scenario") ||
      document.querySelector("[name='scenario']") ||
      document.querySelector("select[data-role='scenario']")
    );
  }

  function nsScenarioMatches(item, namespace) {
    const namespaces = item.namespaces || [item.namespace].filter(Boolean);
    return namespaces.includes(namespace);
  }

  function nsScenarioRenderOptions(namespace) {
    const select = nsScenarioSelectElement();
    if (!select || !scenarioCatalogV1.length) return;

    const visible = namespace
      ? scenarioCatalogV1.filter((item) => nsScenarioMatches(item, namespace))
      : scenarioCatalogV1;

    const previous = select.value;

    select.innerHTML = "";

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = namespace
      ? `Select scenario for ${namespace}`
      : "Select namespace first";
    select.appendChild(placeholder);

    visible.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id || item.name || item.filename || item.path;
      option.textContent = item.title || item.name || item.filename;
      option.dataset.namespace = item.namespace || "";
      option.dataset.path = item.path || "";
      select.appendChild(option);
    });

    const stillExists = Array.from(select.options).some((opt) => opt.value === previous);
    select.value = stillExists ? previous : "";
  }

  function nsScenarioMarkCards(namespace) {
    document.querySelectorAll("[data-scenario], [data-scenario-id], .scenario-card").forEach((card) => {
      const scenarioId =
        card.getAttribute("data-scenario") ||
        card.getAttribute("data-scenario-id") ||
        "";

      const item = scenarioCatalogV1.find((x) =>
        x.id === scenarioId ||
        x.name === scenarioId ||
        x.filename === scenarioId ||
        x.path === scenarioId
      );

      if (!item || !namespace) {
        card.style.display = "";
        return;
      }

      card.style.display = nsScenarioMatches(item, namespace) ? "" : "none";
    });
  }

  function nsScenarioApplyFilter() {
    const namespace = nsScenarioSelectedNamespace();
    nsScenarioRenderOptions(namespace);
    nsScenarioMarkCards(namespace);

    try {
      localStorage.setItem("opslens_selected_namespace", namespace || "");
    } catch (_) {}
  }

  async function nsScenarioLoadCatalog() {
    try {
      const response = await fetch("/api/scenarios/catalog");
      if (!response.ok) return;

      const payload = await response.json();
      scenarioCatalogV1 = payload.scenarios || [];

      nsScenarioApplyFilter();
    } catch (error) {
      console.warn("Could not load scenario catalog:", error);
    }
  }

  document.addEventListener("change", function (event) {
    const target = event.target;
    if (!target) return;

    const id = target.id || "";
    const name = target.name || "";

    if (
      id.toLowerCase().includes("namespace") ||
      name.toLowerCase().includes("namespace") ||
      target.getAttribute("data-role") === "namespace"
    ) {
      nsScenarioApplyFilter();
    }
  });

  const previousLoadScenariosV1 =
    typeof loadScenarios === "function" ? loadScenarios : null;

  if (previousLoadScenariosV1) {
    loadScenarios = async function () {
      const result = await previousLoadScenariosV1.apply(this, arguments);
      await nsScenarioLoadCatalog();
      return result;
    };
  }

  document.addEventListener("DOMContentLoaded", nsScenarioLoadCatalog);

  window.opslensReloadScenarioCatalog = nsScenarioLoadCatalog;
})();

// =========================================================
// OpsLens Preloaded Scenario UI Mode v1
// =========================================================
// OpsLens Preloaded Scenario UI Mode v1
// All scenarios are already applied. Selecting a scenario only focuses investigation.
// =========================================================

(function () {
  function disableScenarioApplyControls() {
    if (typeof applyScenario !== "undefined" && applyScenario) {
      applyScenario.checked = false;
      applyScenario.disabled = true;

      const label = applyScenario.closest("label");
      if (label) {
        label.title = "Scenarios are preloaded. Selection is used as investigation focus only.";
      }
    }

    if (typeof resetNamespace !== "undefined" && resetNamespace) {
      resetNamespace.checked = false;
      resetNamespace.disabled = true;

      const label = resetNamespace.closest("label");
      if (label) {
        label.title = "Namespace reset is disabled in preloaded demo mode.";
      }
    }
  }

  const previousRunInvestigationPreloaded =
    typeof runInvestigation === "function" ? runInvestigation : null;

  if (previousRunInvestigationPreloaded) {
    runInvestigation = async function () {
      disableScenarioApplyControls();
      return previousRunInvestigationPreloaded.apply(this, arguments);
    };
  }

  document.addEventListener("DOMContentLoaded", disableScenarioApplyControls);
})();

// =========================================================
// OpsLens final namespace scenario filter v2
// =========================================================
// OpsLens final namespace scenario filter v2
// Source of truth: /api/scenarios/catalog from scenarios_index.json
// =========================================================

(function () {
  let catalog = [];

  function getNamespaceSelect() {
    return (
      document.getElementById("namespaceSelect") ||
      document.getElementById("namespace") ||
      document.querySelector("[name='namespace']") ||
      document.querySelector("select[data-role='namespace']")
    );
  }

  function getScenarioSelect() {
    return (
      document.getElementById("scenarioSelect") ||
      document.getElementById("scenario") ||
      document.querySelector("[name='scenario']") ||
      document.querySelector("select[data-role='scenario']")
    );
  }

  function selectedNamespace() {
    const ns = getNamespaceSelect();
    return ns ? String(ns.value || "").trim() : "";
  }

  function renderScenarioOptions() {
    const select = getScenarioSelect();
    const ns = selectedNamespace();

    if (!select || !catalog.length) return;

    const previous = select.value;

    const filtered = catalog.filter((item) => item.namespace === ns);

    select.innerHTML = "";

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = ns
      ? `Select scenario for ${ns}`
      : "Select namespace first";

    select.appendChild(placeholder);

    filtered.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.title || item.id;
      option.dataset.namespace = item.namespace;
      option.dataset.manifest = item.manifest || item.filename || "";
      option.dataset.path = item.path || "";
      select.appendChild(option);
    });

    const stillExists = Array.from(select.options).some((opt) => opt.value === previous);
    select.value = stillExists ? previous : "";

    try {
      localStorage.setItem("opslens_selected_namespace", ns || "");
    } catch (_) {}
  }

  async function loadIndexedScenarioCatalog() {
    try {
      const response = await fetch("/api/scenarios/catalog");
      if (!response.ok) return;

      const payload = await response.json();
      catalog = payload.scenarios || [];

      renderScenarioOptions();
    } catch (error) {
      console.warn("Could not load indexed scenario catalog:", error);
    }
  }

  document.addEventListener("change", function (event) {
    const target = event.target;
    if (!target) return;

    const id = String(target.id || "").toLowerCase();
    const name = String(target.name || "").toLowerCase();

    if (id.includes("namespace") || name.includes("namespace") || target.getAttribute("data-role") === "namespace") {
      renderScenarioOptions();
    }
  });

  if (typeof loadScenarios === "function") {
    const previousLoadScenarios = loadScenarios;

    loadScenarios = async function () {
      const result = await previousLoadScenarios.apply(this, arguments);
      await loadIndexedScenarioCatalog();
      return result;
    };
  }

  document.addEventListener("DOMContentLoaded", loadIndexedScenarioCatalog);

  window.opslensReloadScenarioCatalog = loadIndexedScenarioCatalog;
})();

// =========================================================
// OpsLens final namespace dropdown override v3
// =========================================================
// OpsLens final namespace dropdown override v3
// Forces demo UI to show only namespaces from scenarios_index.json.
// Then filters scenarios by selected namespace.
// =========================================================

(function () {
  let catalogPayloadV3 = null;
  let renderingV3 = false;

  function nsSelectV3() {
    return (
      document.getElementById("namespaceSelect") ||
      document.getElementById("namespace") ||
      document.querySelector("[name='namespace']") ||
      document.querySelector("select[data-role='namespace']")
    );
  }

  function scenarioSelectV3() {
    return (
      document.getElementById("scenarioSelect") ||
      document.getElementById("scenario") ||
      document.querySelector("[name='scenario']") ||
      document.querySelector("select[data-role='scenario']")
    );
  }

  function namespaceNamesV3() {
    if (!catalogPayloadV3) return [];

    const direct = catalogPayloadV3.namespaces || [];

    if (Array.isArray(direct) && direct.length) {
      return direct.filter(Boolean);
    }

    const fromScenarios = new Set();

    (catalogPayloadV3.scenarios || []).forEach((item) => {
      if (item.namespace) fromScenarios.add(item.namespace);
    });

    return Array.from(fromScenarios).sort();
  }

  function namespaceDetailsV3() {
    const details = catalogPayloadV3 && Array.isArray(catalogPayloadV3.namespace_details)
      ? catalogPayloadV3.namespace_details
      : [];

    const map = {};

    details.forEach((item) => {
      if (item && item.name) {
        map[item.name] = item;
      }
    });

    return map;
  }

  function optionsMatchDemoNamespacesV3(select, namespaces) {
    const values = Array.from(select.options)
      .map((option) => option.value)
      .filter(Boolean)
      .sort()
      .join("|");

    const expected = namespaces.slice().sort().join("|");

    return values === expected;
  }

  function renderNamespacesV3(force = false) {
    if (!catalogPayloadV3 || renderingV3) return;

    const select = nsSelectV3();
    if (!select) return;

    const namespaces = namespaceNamesV3();
    if (!namespaces.length) return;

    if (!force && optionsMatchDemoNamespacesV3(select, namespaces)) {
      return;
    }

    const current = String(select.value || "");
    const saved = localStorage.getItem("opslens_selected_namespace") || "";
    const nextValue = namespaces.includes(current)
      ? current
      : namespaces.includes(saved)
        ? saved
        : "";

    const details = namespaceDetailsV3();

    renderingV3 = true;

    select.innerHTML = "";

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select demo namespace";
    select.appendChild(placeholder);

    namespaces.forEach((namespace) => {
      const option = document.createElement("option");
      option.value = namespace;
      option.textContent = details[namespace]?.title
        ? `${namespace}`
        : namespace;

      if (details[namespace]?.description) {
        option.title = details[namespace].description;
      }

      select.appendChild(option);
    });

    select.value = nextValue;

    renderingV3 = false;

    renderScenariosV3(true);
  }

  function renderScenariosV3(force = false) {
    if (!catalogPayloadV3 || renderingV3) return;

    const scenarioSelect = scenarioSelectV3();
    if (!scenarioSelect) return;

    const nsSelect = nsSelectV3();
    const namespace = nsSelect ? String(nsSelect.value || "") : "";

    const scenarios = (catalogPayloadV3.scenarios || [])
      .filter((item) => item.namespace === namespace);

    const current = String(scenarioSelect.value || "");

    renderingV3 = true;

    scenarioSelect.innerHTML = "";

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = namespace
      ? `Select scenario for ${namespace}`
      : "Select namespace first";
    scenarioSelect.appendChild(placeholder);

    scenarios.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.title || item.id;
      option.dataset.namespace = item.namespace || "";
      option.dataset.manifest = item.manifest || item.filename || "";
      option.dataset.path = item.path || "";
      scenarioSelect.appendChild(option);
    });

    const stillExists = Array.from(scenarioSelect.options)
      .some((option) => option.value === current);

    scenarioSelect.value = stillExists ? current : "";

    renderingV3 = false;
  }

  async function loadCatalogV3() {
    try {
      const response = await fetch("/api/scenarios/catalog", {
        cache: "no-store",
      });

      if (!response.ok) return;

      catalogPayloadV3 = await response.json();

      renderNamespacesV3(true);
      renderScenariosV3(true);
    } catch (error) {
      console.warn("Could not load OpsLens scenario catalog:", error);
    }
  }

  function disableApplyResetV3() {
    const checks = document.querySelectorAll("input[type='checkbox']");

    checks.forEach((checkbox) => {
      const label = checkbox.closest("label");
      const text = label ? (label.textContent || "").toLowerCase() : "";

      if (
        text.includes("apply selected scenario") ||
        text.includes("reset selected namespace")
      ) {
        checkbox.checked = false;
        checkbox.disabled = true;
        if (label) {
          label.style.opacity = "0.55";
          label.title = "Scenarios are preloaded. Selection is used as investigation focus only.";
        }
      }
    });
  }

  document.addEventListener("change", function (event) {
    const target = event.target;
    if (!target || renderingV3) return;

    const ns = nsSelectV3();

    if (target === ns) {
      localStorage.setItem("opslens_selected_namespace", String(target.value || ""));
      renderScenariosV3(true);
    }
  }, true);

  document.addEventListener("DOMContentLoaded", function () {
    loadCatalogV3();
    disableApplyResetV3();
  });

  const observerV3 = new MutationObserver(function () {
    if (!catalogPayloadV3 || renderingV3) return;

    const select = nsSelectV3();
    const namespaces = namespaceNamesV3();

    if (select && namespaces.length && !optionsMatchDemoNamespacesV3(select, namespaces)) {
      renderNamespacesV3(true);
    }

    disableApplyResetV3();
  });

  try {
    observerV3.observe(document.body, {
      childList: true,
      subtree: true,
    });
  } catch (_) {}

  setInterval(function () {
    if (!catalogPayloadV3 || renderingV3) return;
    renderNamespacesV3(false);
    disableApplyResetV3();
  }, 1200);

  window.opslensReloadScenarioCatalog = loadCatalogV3;
})();
