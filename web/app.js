
const $ = (id) => document.getElementById(id);

let currentJobId = null;
let currentReport = null;
let pollTimer = null;
let scenarioDetailsFromApi = {};
let allScenariosFromApi = [];


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

  if (!selected) {
    scenarioDetailsCard.classList.add("hidden");
    return;
  }

  const details = scenarioDetailsFromApi[selected] || SCENARIO_DETAILS[selected] || {
    title: selected.replaceAll("_", " ").replace(".yml", ""),
    description: "This scenario will be applied before the investigation starts.",
    impact: "Impact: depends on scenario resources",
    expected: "Expected RCA: OpsLens will infer it from collected evidence"
  };

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
  const lower = String(name || "").toLowerCase();

  if (lower.includes("payments")) return "opslens-payments";
  if (lower.includes("orders")) return "opslens-orders";
  if (lower.includes("platform")) return "opslens-platform";

  return "";
}

function renderScenarioOptionsForNamespace() {
  if (!scenarioSelect) return;

  const selectedNamespace = namespaceValue ? namespaceValue() : "";
  const previousValue = scenarioSelect.value;

  scenarioSelect.innerHTML = "";
  scenarioSelect.appendChild(option("", "No scenario"));

  const filtered = (allScenariosFromApi || []).filter((scenario) => {
    if (!scenario) return false;
    if (String(scenario).startsWith("_setup/")) return false;

    const scenarioNamespace = scenarioNamespaceFromName(scenario);

    if (!selectedNamespace) return true;
    if (!scenarioNamespace) return true;

    return scenarioNamespace === selectedNamespace;
  });

  filtered.forEach((scenario) => scenarioSelect.appendChild(option(scenario)));

  if (filtered.includes(previousValue)) {
    scenarioSelect.value = previousValue;
  }

  updateScenarioDetails();
}


async function loadScenarios() {
  scenarioSelect.innerHTML = "";
  scenarioSelect.appendChild(option("", "Loading scenarios..."));

  try {
    const scenarios = await api("/api/scenarios");
    allScenariosFromApi = scenarios.scenarios || [];
    renderScenarioOptionsForNamespace();
  } catch (error) {
    scenarioSelect.innerHTML = "";
    scenarioSelect.appendChild(option("", "Could not load scenarios"));
    console.error("Scenario loading failed:", error);
  }
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
  const node = nodeSelect.value;

  namespaceSelect.innerHTML = "";
  namespaceSelect.appendChild(option("", "Loading namespaces..."));

  try {
    const response = node
      ? await api(`/api/cluster/nodes/${encodeURIComponent(node)}/namespaces`)
      : await api("/api/cluster/namespaces");

    const namespaces = response.namespaces || [];
    namespaceSelect.innerHTML = "";

    if (!namespaces.length) {
      namespaceSelect.appendChild(option("", "No namespaces with pods on this node"));
      updateScopeInfo();
      return;
    }

    namespaces.forEach((ns) => namespaceSelect.appendChild(option(ns)));

    if (namespaces.includes("opslens-chaos")) {
      namespaceSelect.value = "opslens-chaos";
    }

    updateScopeInfo();
  } catch (error) {
    namespaceSelect.innerHTML = "";
    namespaceSelect.appendChild(option("", "Could not load namespaces"));
    updateScopeInfo();
  }
}

nodeSelect.addEventListener("change", loadNamespacesForSelectedNode);
scenarioSelect.addEventListener("change", updateScenarioDetails);
namespaceSelect.addEventListener("change", () => {
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
    apply_scenario: applyScenario.checked && Boolean(scenarioSelect.value),
    reset_namespace: resetNamespace ? resetNamespace.checked : false,
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
    reset_namespace: resetNamespace ? resetNamespace.checked : false,
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
