
const $ = (id) => document.getElementById(id);

let currentJobId = null;
let currentReport = null;
let pollTimer = null;
let scenarioDetailsFromApi = {};


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

async function loadScenarios() {
  scenarioSelect.innerHTML = "";
  scenarioSelect.appendChild(option("", "Loading scenarios..."));

  try {
    const scenarios = await api("/api/scenarios");
    const list = scenarios.scenarios || [];

    scenarioSelect.innerHTML = "";
    scenarioSelect.appendChild(option("", "No scenario"));

    list.forEach((scenario) => scenarioSelect.appendChild(option(scenario)));

    if (list.includes("multi_issue_k8s_chaos.yml")) {
      scenarioSelect.value = "multi_issue_k8s_chaos.yml";
    }

    updateScenarioDetails();
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
namespaceSelect.addEventListener("change", updateScopeInfo);

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
    reset_namespace: false,
    demo_seed_metrics: false,
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
      localStorage.removeItem("opslens_active_job_id");

      renderReport(currentReport);
      saveCurrentReportToDatabase(currentReport);
      saveInvestigationRecord(job, currentReport);
      renderInvestigationRecords();
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
  cacheReportLocally(report);
  saveCurrentReportToDatabase(report);

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

downloadReportBtn.addEventListener("click", () => {
  const format = downloadFormat.value || "pdf";

  if (currentJobId) {
    window.location.href = `/api/investigations/${currentJobId}/report/${format}/download`;
    return;
  }

  window.location.href = `/api/reports/latest/${format}/download`;
});

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




async function saveCurrentReportToDatabase(report) {
  if (!report || !report.title) return null;

  try {
    const saved = await api("/api/db/reports/save", {
      method: "POST",
      body: JSON.stringify(report),
    });

    await loadBackendInvestigationHistory();
    return saved;
  } catch (error) {
    console.warn("Could not save report to database:", error);
    showToast("Report not saved", "The report is visible, but database save failed.");
    return null;
  }
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
      saveCurrentReportToDatabase(currentReport);
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

function restoreActiveJobPolling() {
  const activeJobId = localStorage.getItem("opslens_active_job_id");

  if (!activeJobId || currentJobId) return;

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
// Backend investigation history
// =========================================================

async function loadBackendInvestigationHistory() {
  if (!investigationRecords) return;

  investigationRecords.innerHTML = `<p class="muted">Loading investigation history...</p>`;

  try {
    const result = await api("/api/db/history");
    await await renderBackendInvestigationRecords(result.records || []);
  } catch (error) {
    investigationRecords.innerHTML = `
      <div class="history-error">
        <strong>Could not load backend history</strong>
        <p>${escapeHtml(error.message)}</p>
      </div>
    `;
  }
}

async function renderBackendInvestigationRecords(records) {
  if (!investigationRecords) return;

  if (!records.length) {
    investigationRecords.innerHTML = `<p class="muted">No recorded investigations yet.</p>`;
    return;
  }

  investigationRecords.innerHTML = records.map((record) => {
    const date = new Date(record.modified_at || record.created_at);
    const stamp = Number.isNaN(date.getTime())
      ? (record.created_at || "")
      : date.toLocaleString();

    return `
      <div class="record-card backend-record" data-record-id="${escapeHtml(record.record_id)}">
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
          <button type="button" class="open-record-btn" data-record-id="${escapeHtml(record.record_id)}">Open</button>
          <button type="button" class="download-record-btn" data-record-id="${escapeHtml(record.record_id)}">PDF</button>
        </div>
      </div>
    `;
  }).join("");

  investigationRecords.querySelectorAll(".open-record-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const recordId = btn.dataset.recordId;
      const report = await api(`/api/db/history/${encodeURIComponent(recordId)}`);
      currentReport = report;
      currentJobId = null;
      renderReport(report);
      showView("reportView");
    });
  });

  investigationRecords.querySelectorAll(".download-record-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const recordId = btn.dataset.recordId;
      window.location.href = `/api/db/history/${encodeURIComponent(recordId)}/report/pdf/download`;
    });
  });
}

// Override old localStorage renderer
function renderInvestigationRecords() {
  loadBackendInvestigationHistory();
}

// Keep local save no-op because backend history is based on saved report files
function saveInvestigationRecord(job, report) {
  return;
}

if (refreshHistoryBtn) {
  refreshHistoryBtn.addEventListener("click", loadBackendInvestigationHistory);
}

if (clearRecordsBtn) {
  clearRecordsBtn.style.display = "none";
}


function buildReportSummaryText(report) {
  if (!report) return "";

  const fix = report.recommended_fix || {};
  const verification = report.verification || {};
  const affected = report.affected_resources || {};

  return [
    `Title: ${report.title || "OpsLens Incident Report"}`,
    `Severity: ${report.severity || "unknown"}`,
    `Confidence: ${report.confidence || "unknown"}`,
    `Namespace: ${affected.namespace || "unknown"}`,
    `Node: ${affected.node || "unknown"}`,
    `Service: ${affected.service || affected.service_name || "unknown"}`,
    "",
    `Summary: ${report.incident_summary || ""}`,
    "",
    `Root Cause: ${report.root_cause_story || ""}`,
    "",
    `Recommended Fix: ${fix.strategy || ""}`,
    "",
    `Verification: ${verification.intent || ""}`,
  ].join("\\n");
}

if (copySummaryBtn) {
  copySummaryBtn.addEventListener("click", async () => {
    if (!currentReport) {
      showToast("No report available", "Run or open an investigation report first.");
      return;
    }

    await navigator.clipboard.writeText(buildReportSummaryText(currentReport));
    showToast("Summary copied", "The report summary is now in your clipboard.");
  });
}


// =========================================================
// Local cache for last 10 reports
// =========================================================

function getCachedReports() {
  try {
    return JSON.parse(localStorage.getItem("opslens_cached_reports") || "[]");
  } catch {
    return [];
  }
}

function cacheReportLocally(report) {
  if (!report || !report.title) return;

  const affected = report.affected_resources || {};
  const service =
    affected.service ||
    affected.service_name ||
    affected.workload ||
    affected.deployment ||
    affected.pod ||
    "unknown-service";

  const cacheId = `${service}_${Date.now()}`;

  const cached = {
    cache_id: cacheId,
    cached_at: new Date().toISOString(),
    title: report.title || "OpsLens Incident Report",
    service,
    namespace: affected.namespace || "",
    node: affected.node || "",
    severity: report.severity || "unknown",
    confidence: report.confidence || "unknown",
    report,
  };

  const current = getCachedReports();

  const next = [
    cached,
    ...current.filter((item) => item.title !== cached.title || item.service !== cached.service),
  ].slice(0, 10);

  localStorage.setItem("opslens_cached_reports", JSON.stringify(next));
}

function restoreLatestCachedReport() {
  const currentView = localStorage.getItem("opslens_current_view") || "";

  if (currentView !== "reportView") return;
  if (currentReport) return;

  const cached = getCachedReports();

  if (!cached.length) return;

  currentReport = cached[0].report;
  renderReport(currentReport);
  saveCurrentReportToDatabase(currentReport);
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
    currentReport = report;
    renderReport(report);
  } catch (error) {
    console.warn("Could not restore latest backend report:", error);
  }
}


// =========================================================
// Final DB history + local cache last 5 override
// =========================================================

function getCachedReports() {
  try {
    return JSON.parse(localStorage.getItem("opslens_cached_reports_v2") || "[]");
  } catch {
    return [];
  }
}

function cacheReportLocally(report) {
  if (!report || !report.title) return;

  const affected = report.affected_resources || {};
  const service =
    affected.service ||
    affected.service_name ||
    affected.workload ||
    affected.deployment ||
    affected.pod ||
    "unknown-service";

  const cached = {
    cache_id: `${service}_${Date.now()}`,
    cached_at: new Date().toISOString(),
    title: report.title || "OpsLens Incident Report",
    service,
    namespace: affected.namespace || "",
    node: affected.node || "",
    severity: report.severity || "unknown",
    confidence: report.confidence || "unknown",
    report,
  };

  const current = getCachedReports();
  const next = [cached, ...current].slice(0, 5);

  localStorage.setItem("opslens_cached_reports_v2", JSON.stringify(next));
}

async function saveCurrentReportToDatabase(report) {
  if (!report || !report.title) return null;

  try {
    const saved = await api("/api/db/reports/save", {
      method: "POST",
      body: JSON.stringify(report),
    });

    loadBackendInvestigationHistory();
    return saved;
  } catch (error) {
    console.warn("Could not save report to database:", error);
    return null;
  }
}

async function loadBackendInvestigationHistory() {
  if (!investigationRecords) return;

  investigationRecords.innerHTML = `<p class="muted">Loading investigation history...</p>`;

  try {
    const result = await api("/api/db/history");
    const records = result.records || [];

    if (!records.length) {
      const cached = getCachedReports();

      if (cached.length) {
        renderCachedReportsAsHistory(cached);
        return;
      }

      investigationRecords.innerHTML = `
        <div class="empty-history">
          <strong>No reports yet</strong>
          <p>Run an investigation first. Completed reports will appear here automatically.</p>
        </div>
      `;
      return;
    }

    renderBackendInvestigationRecords(records);
  } catch (error) {
    const cached = getCachedReports();

    if (cached.length) {
      renderCachedReportsAsHistory(cached);
      return;
    }

    investigationRecords.innerHTML = `
      <div class="empty-history">
        <strong>No reports yet</strong>
        <p>Could not load database history. Run an investigation first, then refresh history.</p>
      </div>
    `;
  }
}

function renderCachedReportsAsHistory(cached) {
  investigationRecords.innerHTML = cached.map((item) => {
    const date = new Date(item.cached_at);
    const stamp = Number.isNaN(date.getTime()) ? item.cached_at : date.toLocaleString();

    return `
      <div class="record-card cached-record">
        <div>
          <strong>${escapeHtml(item.service || "unknown-service")}</strong>
          <p>${escapeHtml(item.title || "Cached report")}</p>
        </div>
        <div>
          <small>Namespace</small>
          <span>${escapeHtml(item.namespace || "unknown")}</span>
        </div>
        <div>
          <small>Severity</small>
          <span>${escapeHtml(item.severity || "unknown")}</span>
        </div>
        <div>
          <small>Cached</small>
          <span>${escapeHtml(stamp)}</span>
        </div>
        <div class="record-actions">
          <button type="button" class="open-cached-btn" data-cache-id="${escapeHtml(item.cache_id)}">Open</button>
        </div>
      </div>
    `;
  }).join("");

  investigationRecords.querySelectorAll(".open-cached-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cacheId = btn.dataset.cacheId;
      const item = getCachedReports().find((entry) => entry.cache_id === cacheId);

      if (!item) return;

      currentReport = item.report;
      renderReport(currentReport);
      showView("reportView");
    });
  });
}

function renderBackendInvestigationRecords(records) {
  if (!investigationRecords) return;

  investigationRecords.innerHTML = records.map((record) => {
    const date = new Date(record.modified_at || record.created_at);
    const stamp = Number.isNaN(date.getTime()) ? (record.created_at || "") : date.toLocaleString();

    return `
      <div class="record-card backend-record" data-record-id="${escapeHtml(record.record_id)}">
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
          <button type="button" class="open-record-btn" data-record-id="${escapeHtml(record.record_id)}">Open</button>
          <button type="button" class="download-record-btn" data-record-id="${escapeHtml(record.record_id)}">PDF</button>
        </div>
      </div>
    `;
  }).join("");

  investigationRecords.querySelectorAll(".open-record-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const recordId = btn.dataset.recordId;
      const report = await api(`/api/db/history/${encodeURIComponent(recordId)}`);
      currentReport = report;
      renderReport(report);
      showView("reportView");
    });
  });

  investigationRecords.querySelectorAll(".download-record-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const recordId = btn.dataset.recordId;
      window.location.href = `/api/db/history/${encodeURIComponent(recordId)}/report/pdf/download`;
    });
  });
}

function restoreLatestCachedReport() {
  const currentView = localStorage.getItem("opslens_current_view") || "";

  if (currentView !== "reportView") return;
  if (currentReport) return;

  const cached = getCachedReports();

  if (!cached.length) return;

  currentReport = cached[0].report;
  renderReport(currentReport);
}


// =========================================================
// Final product report persistence guard
// Ensures reports are cached locally and saved to SQLite.
// =========================================================

(function () {
  const CACHE_KEY = "opslens_cached_reports_v2";
  let savingReportToDb = false;

  function readCachedReportsFinal() {
    try {
      return JSON.parse(localStorage.getItem(CACHE_KEY) || "[]");
    } catch {
      return [];
    }
  }

  function writeCachedReportsFinal(items) {
    localStorage.setItem(CACHE_KEY, JSON.stringify(items.slice(0, 5)));
  }

  window.opslensCacheReportFinal = function (report) {
    if (!report || !report.title) return;

    const affected = report.affected_resources || {};
    const service =
      affected.service ||
      affected.service_name ||
      affected.workload ||
      affected.deployment ||
      affected.pod ||
      "unknown-service";

    const item = {
      cache_id: `${service}_${Date.now()}`,
      cached_at: new Date().toISOString(),
      title: report.title || "OpsLens Incident Report",
      service,
      namespace: affected.namespace || "",
      node: affected.node || "",
      severity: report.severity || "unknown",
      confidence: report.confidence || "unknown",
      report,
    };

    const current = readCachedReportsFinal()
      .filter((entry) => JSON.stringify(entry.report) !== JSON.stringify(report));

    writeCachedReportsFinal([item, ...current]);
  };

  window.opslensSaveReportFinal = async function (report) {
    if (!report || !report.title || savingReportToDb) return null;

    savingReportToDb = true;

    try {
      const saved = await api("/api/db/reports/save", {
        method: "POST",
        body: JSON.stringify(report),
      });

      return saved;
    } catch (error) {
      console.warn("SQLite report save failed:", error);
      return null;
    } finally {
      savingReportToDb = false;
    }
  };

  if (typeof renderReport === "function" && !window.__opslensRenderReportWrappedFinal) {
    window.__opslensRenderReportWrappedFinal = true;

    const originalRenderReport = renderReport;

    renderReport = function (report) {
      originalRenderReport(report);

      if (report && report.title) {
        window.opslensCacheReportFinal(report);
        window.opslensSaveReportFinal(report).then(() => {
          if (typeof loadBackendInvestigationHistory === "function") {
            loadBackendInvestigationHistory();
          }
        });
      }
    };
  }

  window.opslensRestoreLatestReportFinal = function () {
    const view = localStorage.getItem("opslens_current_view") || location.hash.replace("#", "");

    if (view !== "reportView") return;
    if (typeof currentReport !== "undefined" && currentReport) return;

    const cached = readCachedReportsFinal();

    if (!cached.length) return;

    currentReport = cached[0].report;

    if (typeof renderReport === "function") {
      renderReport(currentReport);
    }
  };

  window.addEventListener("load", () => {
    setTimeout(() => {
      window.opslensRestoreLatestReportFinal();

      if (typeof loadBackendInvestigationHistory === "function") {
        loadBackendInvestigationHistory();
      }
    }, 350);
  });
})();


// =========================================================
// Final feedback success toast
// Replaces ugly inline success text with a clean floating toast.
// =========================================================

(function () {
  function ensureFeedbackToast() {
    let toast = document.querySelector(".opslens-feedback-toast");

    if (toast) return toast;

    toast = document.createElement("div");
    toast.className = "opslens-feedback-toast";
    toast.innerHTML = `
      <div class="toast-check">?</div>
      <div>
        <strong>Feedback sent</strong>
        <span>Thanks. Your note was saved successfully.</span>
      </div>
    `;

    document.body.appendChild(toast);
    return toast;
  }

  window.showOpsLensFeedbackToast = function () {
    const toast = ensureFeedbackToast();

    toast.classList.add("show");

    clearTimeout(window.__opslensFeedbackToastTimer);
    window.__opslensFeedbackToastTimer = setTimeout(() => {
      toast.classList.remove("show");
    }, 2600);
  };

  function cleanFeedbackInlineMessages() {
    const feedbackView = document.querySelector("#feedbackView");

    if (!feedbackView) return;

    const candidates = feedbackView.querySelectorAll("p, div, span, small");

    candidates.forEach((node) => {
      const text = (node.textContent || "").trim().toLowerCase();

      if (
        text.startsWith("feedback saved") ||
        text.includes("feedback saved. id") ||
        text.includes("could not save feedback")
      ) {
        node.textContent = "";
        node.style.display = "none";
      }
    });
  }

  const observer = new MutationObserver(() => {
    const feedbackView = document.querySelector("#feedbackView");

    if (!feedbackView) return;

    const text = (feedbackView.textContent || "").toLowerCase();

    if (text.includes("feedback saved")) {
      cleanFeedbackInlineMessages();
      window.showOpsLensFeedbackToast();
    }
  });

  window.addEventListener("load", () => {
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  });
})();


// =========================================================
// Final persistent investigation progress + live stage sync
// Keeps the investigation bar visible after refresh and
// updates current stage during polling.
// =========================================================

(function () {
  const ACTIVE_JOB_KEY = "opslens_active_job_id";
  const STATUS_KEY = "opslens_global_status";
  const STARTED_KEY = "opslens_active_job_started_at";
  const STAGE_KEY = "opslens_active_pipeline_stage";

  const STAGES = [
    { id: "scope", label: "Scope" },
    { id: "collect", label: "Collect" },
    { id: "detect", label: "Detect" },
    { id: "reason", label: "Reason" },
    { id: "report", label: "Report" },
  ];

  let progressPollTimer = null;
  let lastStage = localStorage.getItem(STAGE_KEY) || "scope";

  function getActiveJobId() {
    return localStorage.getItem(ACTIVE_JOB_KEY);
  }

  function setActiveJob(jobId) {
    if (!jobId) return;

    localStorage.setItem(ACTIVE_JOB_KEY, jobId);
    localStorage.setItem(STARTED_KEY, String(Date.now()));
    localStorage.setItem(STAGE_KEY, "scope");

    lastStage = "scope";
    showPersistentProgress("scope", "Investigation started");
    startPersistentProgressPolling();
  }

  function clearActiveJob() {
    localStorage.removeItem(ACTIVE_JOB_KEY);
    localStorage.removeItem(STARTED_KEY);
    localStorage.removeItem(STAGE_KEY);
  }

  function stageIndex(stageId) {
    const index = STAGES.findIndex((stage) => stage.id === stageId);
    return index < 0 ? 0 : index;
  }

  function inferStageFromPayload(payload) {
    const explicit =
      payload?.current_stage ||
      payload?.stage ||
      payload?.pipeline_stage ||
      payload?.status_stage ||
      payload?.progress_stage;

    if (explicit) {
      const value = String(explicit).toLowerCase();

      if (value.includes("scope") || value.includes("queued") || value.includes("apply")) return "scope";
      if (value.includes("collect") || value.includes("kubernetes") || value.includes("logs") || value.includes("metrics")) return "collect";
      if (value.includes("detect") || value.includes("agent") || value.includes("anomaly") || value.includes("signal")) return "detect";
      if (value.includes("reason") || value.includes("supervisor") || value.includes("gemini") || value.includes("rca")) return "reason";
      if (value.includes("report") || value.includes("complete") || value.includes("done")) return "report";
    }

    const status = String(payload?.status || payload?.state || "").toLowerCase();

    if (status.includes("complete") || status.includes("success") || status.includes("done")) {
      return "report";
    }

    if (status.includes("fail") || status.includes("error")) {
      return "report";
    }

    const message = String(payload?.message || payload?.detail || payload?.status_message || "").toLowerCase();

    if (message.includes("collect") || message.includes("collector")) return "collect";
    if (message.includes("detect") || message.includes("agent") || message.includes("anomaly")) return "detect";
    if (message.includes("reason") || message.includes("supervisor") || message.includes("rca") || message.includes("gemini")) return "reason";
    if (message.includes("report") || message.includes("complete")) return "report";

    // Fallback smooth progress when backend does not expose stage.
    const startedAt = Number(localStorage.getItem(STARTED_KEY) || Date.now());
    const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));

    if (elapsedSeconds < 5) return "scope";
    if (elapsedSeconds < 18) return "collect";
    if (elapsedSeconds < 32) return "detect";
    if (elapsedSeconds < 48) return "reason";
    return "report";
  }

  function getStageLabel(stageId) {
    return STAGES.find((stage) => stage.id === stageId)?.label || "Running";
  }

  function ensureProgressBar() {
    let bar = document.querySelector(".opslens-live-progress");

    if (bar) return bar;

    bar = document.createElement("div");
    bar.className = "opslens-live-progress";
    bar.innerHTML = `
      <div class="live-progress-top">
        <div>
          <strong class="live-progress-title">Investigation running</strong>
          <span class="live-progress-subtitle">OpsLens is collecting evidence from the selected scope.</span>
        </div>
        <div class="live-progress-stage">Scope</div>
      </div>
      <div class="live-progress-track">
        <div class="live-progress-fill"></div>
      </div>
      <div class="live-progress-steps">
        ${STAGES.map((stage) => `<span data-live-stage="${stage.id}">${stage.label}</span>`).join("")}
      </div>
    `;

    document.body.appendChild(bar);
    return bar;
  }

  function showPersistentProgress(stageId, message) {
    const bar = ensureProgressBar();
    const index = stageIndex(stageId);
    const percent = ((index + 1) / STAGES.length) * 100;

    bar.classList.add("show");
    bar.querySelector(".live-progress-stage").textContent = getStageLabel(stageId);
    bar.querySelector(".live-progress-fill").style.width = `${percent}%`;

    if (message) {
      bar.querySelector(".live-progress-subtitle").textContent = message;
    }

    bar.querySelectorAll("[data-live-stage]").forEach((node) => {
      const nodeStage = node.dataset.liveStage;
      const nodeIndex = stageIndex(nodeStage);

      node.classList.toggle("done", nodeIndex < index);
      node.classList.toggle("active", nodeStage === stageId);
    });

    syncPipelineStage(stageId);
  }

  function completePersistentProgress(message) {
    showPersistentProgress("report", message || "Investigation completed");

    setTimeout(() => {
      const bar = document.querySelector(".opslens-live-progress");
      if (bar) bar.classList.remove("show");
    }, 3200);

    clearActiveJob();

    if (progressPollTimer) {
      clearInterval(progressPollTimer);
      progressPollTimer = null;
    }
  }

  function syncPipelineStage(stageId) {
    lastStage = stageId;
    localStorage.setItem(STAGE_KEY, stageId);

    const index = stageIndex(stageId);
    const label = getStageLabel(stageId);

    // Update common "current stage" labels.
    const labelSelectors = [
      "#currentStage",
      "#pipelineCurrentStage",
      ".current-stage",
      ".current-stage-value",
      ".pipeline-current-stage",
      "[data-current-stage]"
    ];

    labelSelectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => {
        if (node) node.textContent = label;
      });
    });

    // Update stage cards/steps by data attributes if present.
    document.querySelectorAll("[data-stage], [data-pipeline-stage]").forEach((node) => {
      const nodeStage = (node.dataset.stage || node.dataset.pipelineStage || "").toLowerCase();
      const nodeIndex = stageIndex(nodeStage);

      node.classList.toggle("is-active", nodeStage === stageId);
      node.classList.toggle("active", nodeStage === stageId);
      node.classList.toggle("is-done", nodeIndex >= 0 && nodeIndex < index);
      node.classList.toggle("done", nodeIndex >= 0 && nodeIndex < index);
    });

    // Fallback: update visible pipeline cards by text.
    const stageWords = {
      scope: ["scope"],
      collect: ["collect"],
      detect: ["detect"],
      reason: ["reason", "rca", "supervisor"],
      report: ["report"],
    };

    document.querySelectorAll(".pipeline-step, .pipeline-card, .stage-card, .step-card").forEach((node) => {
      const text = (node.textContent || "").toLowerCase();
      let matchedStage = null;

      Object.entries(stageWords).forEach(([stage, words]) => {
        if (words.some((word) => text.includes(word))) {
          matchedStage = stage;
        }
      });

      if (!matchedStage) return;

      const matchedIndex = stageIndex(matchedStage);

      node.classList.toggle("is-active", matchedStage === stageId);
      node.classList.toggle("active", matchedStage === stageId);
      node.classList.toggle("is-done", matchedIndex < index);
      node.classList.toggle("done", matchedIndex < index);
    });
  }

  async function pollActiveJobOnce() {
    const jobId = getActiveJobId();

    if (!jobId) return;

    try {
      const response = await fetch(`/api/investigations/${encodeURIComponent(jobId)}`, {
        headers: { "Accept": "application/json" },
      });

      if (!response.ok) {
        showPersistentProgress(lastStage || "scope", "Investigation status is reconnecting...");
        return;
      }

      const payload = await response.json();
      const stage = inferStageFromPayload(payload);
      const status = String(payload?.status || payload?.state || "").toLowerCase();

      showPersistentProgress(stage, payload?.message || payload?.status_message || "Investigation is running");

      if (
        status.includes("complete") ||
        status.includes("success") ||
        status.includes("done") ||
        payload?.report ||
        payload?.result
      ) {
        completePersistentProgress("Investigation completed");
      }

      if (status.includes("fail") || status.includes("error")) {
        completePersistentProgress("Investigation finished with an error");
      }
    } catch (error) {
      showPersistentProgress(lastStage || "scope", "Investigation status is reconnecting...");
    }
  }

  function startPersistentProgressPolling() {
    if (progressPollTimer) return;

    pollActiveJobOnce();

    progressPollTimer = setInterval(() => {
      pollActiveJobOnce();
    }, 2500);
  }

  // Capture investigation creation and persist job_id.
  if (!window.__opslensFetchProgressWrapped) {
    window.__opslensFetchProgressWrapped = true;

    const originalFetch = window.fetch.bind(window);

    window.fetch = async function (...args) {
      const response = await originalFetch(...args);

      try {
        const url = String(args[0] || "");
        const method = String(args[1]?.method || "GET").toUpperCase();

        if (url.includes("/api/investigations") && method === "POST") {
          response.clone().json().then((payload) => {
            const jobId = payload?.job_id || payload?.id || payload?.record_id;

            if (jobId) {
              setActiveJob(jobId);
            }
          }).catch(() => {});
        }

        if (url.includes("/api/investigations/") && method === "GET") {
          response.clone().json().then((payload) => {
            const stage = inferStageFromPayload(payload);
            showPersistentProgress(stage, payload?.message || payload?.status_message || "Investigation is running");
          }).catch(() => {});
        }
      } catch {}

      return response;
    };
  }

  window.addEventListener("load", () => {
    const jobId = getActiveJobId();
    const stage = localStorage.getItem(STAGE_KEY) || "scope";

    if (jobId) {
      showPersistentProgress(stage, "Restoring active investigation...");
      startPersistentProgressPolling();
    }
  });
})();


// =========================================================
// Product disclaimer + hide investigation bar during splash
// =========================================================

(function () {
  function markUiReadyAfterSplash() {
    document.body.classList.remove("opslens-ui-ready");

    const markReady = () => {
      document.body.classList.add("opslens-ui-ready");
    };

    // Wait for the splash/logo intro to finish before allowing progress bar visibility.
    setTimeout(markReady, 1500);
  }

  function injectProgressDisclaimer() {
    const bar = document.querySelector(".opslens-live-progress");

    if (!bar) return;

    if (bar.querySelector(".live-progress-disclaimer")) return;

    const note = document.createElement("div");
    note.className = "live-progress-disclaimer";
    note.textContent = "OpsLens can make mistakes. Verify evidence and safe commands before applying changes.";

    bar.appendChild(note);
  }

  window.addEventListener("load", () => {
    markUiReadyAfterSplash();

    setInterval(() => {
      injectProgressDisclaimer();
    }, 600);
  });
})();


// =========================================================
// Final report download fallback + completion notification
// =========================================================

(function () {
  function getActiveReportForExport() {
    if (typeof currentReport !== "undefined" && currentReport) {
      return currentReport;
    }

    try {
      const cached = JSON.parse(localStorage.getItem("opslens_cached_reports_v2") || "[]");
      if (cached.length && cached[0].report) return cached[0].report;
    } catch {}

    return null;
  }

  function safeText(value) {
    if (value === null || value === undefined) return "";
    if (Array.isArray(value)) return value.map(safeText).join("\n");
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  }

  function listToMarkdown(value) {
    if (!value) return "- Not found in collected evidence";

    if (Array.isArray(value)) {
      if (!value.length) return "- Not found in collected evidence";

      return value.map((item) => {
        if (typeof item === "object" && item !== null) {
          if (item.command) return `- ${item.title ? `**${item.title}:** ` : ""}\`${item.command}\``;
          return `- ${safeText(item)}`;
        }
        return `- ${safeText(item)}`;
      }).join("\n");
    }

    if (typeof value === "object") {
      return Object.entries(value).map(([key, val]) => `- **${key}:** ${safeText(val)}`).join("\n");
    }

    return `- ${safeText(value)}`;
  }

  function reportToMarkdown(report) {
    const affected = report.affected_resources || {};
    const fix = report.recommended_fix || {};

    return `# ${report.title || "OpsLens Incident Report"}

## Status

| Field | Value |
|---|---|
| Severity | ${report.severity || "not found"} |
| Confidence | ${report.confidence || "not found"} |
| Namespace | ${affected.namespace || "not found in collected evidence"} |
| Node | ${affected.node || affected.node_name || "not found in collected evidence"} |
| Service | ${affected.service || "not found in collected evidence"} |
| Deployment | ${affected.deployment || "not found in collected evidence"} |

## Incident Summary

${report.incident_summary || report.summary || "No active incident was detected in the selected scope."}

## Evidence Trail

${listToMarkdown(report.evidence_trail || report.evidence)}

## Additional Findings

${listToMarkdown(report.additional_findings || report.additional_issues)}

## Root Cause Story

${report.root_cause_story || report.root_cause || "No root cause was identified because no active failure evidence was found."}

## Recommended Fix

${fix.strategy || report.recommendation || "No remediation required. Continue monitoring."}

## Safe Commands

${listToMarkdown(fix.safe_commands || report.safe_commands)}

## Verification Plan

${fix.verification_plan || report.verification_plan || "Verify the selected namespace state."}

## Verification Commands

${listToMarkdown(fix.verification_commands || report.verification_commands)}

---

OpsLens can make mistakes. Verify evidence and safe commands before applying changes.
`;
  }

  function downloadBlob(filename, content, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");

    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();

    setTimeout(() => {
      URL.revokeObjectURL(url);
      a.remove();
    }, 500);
  }

  function makeExportName(report, ext) {
    const affected = report?.affected_resources || {};
    const service =
      affected.service ||
      affected.deployment ||
      affected.namespace ||
      "opslens-report";

    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "_");
    const clean = String(service).replace(/[^a-zA-Z0-9_-]+/g, "-");

    return `${clean}_${stamp}.${ext}`;
  }

  function getSelectedExportFormat() {
    const select =
      document.querySelector("#exportFormat") ||
      document.querySelector("[name='exportFormat']") ||
      document.querySelector(".export-card select") ||
      document.querySelector("#reportView select");

    return String(select?.value || "markdown").toLowerCase();
  }

  function isDownloadButton(target) {
    const button = target.closest("button, a");

    if (!button) return false;

    const text = (button.textContent || "").trim().toLowerCase();
    const id = String(button.id || "").toLowerCase();
    const cls = String(button.className || "").toLowerCase();

    return (
      text === "download" ||
      text.includes("download") ||
      id.includes("download") ||
      cls.includes("download")
    );
  }

  async function handleReportDownload(event) {
    if (!isDownloadButton(event.target)) return;

    const reportView = document.querySelector("#reportView");
    if (!reportView || !reportView.contains(event.target)) return;

    const report = getActiveReportForExport();
    if (!report) return;

    const format = getSelectedExportFormat();

    // Markdown and JSON should never depend on backend file paths.
    if (format.includes("markdown") || format === "md") {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      downloadBlob(
        makeExportName(report, "md"),
        reportToMarkdown(report),
        "text/markdown;charset=utf-8"
      );

      return;
    }

    if (format.includes("json")) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      downloadBlob(
        makeExportName(report, "json"),
        JSON.stringify(report, null, 2),
        "application/json;charset=utf-8"
      );

      return;
    }

    // PDF/Excel can still use backend route if available.
  }

  document.addEventListener("click", handleReportDownload, true);


  function ensureReportReadyToast() {
    let toast = document.querySelector(".opslens-report-ready-toast");

    if (toast) return toast;

    toast = document.createElement("div");
    toast.className = "opslens-report-ready-toast";
    toast.innerHTML = `
      <div class="report-ready-check">?</div>
      <div>
        <strong>Report ready</strong>
        <span>Investigation completed. Open the Reports page to review it.</span>
      </div>
      <button type="button" class="report-ready-open">Open</button>
    `;

    toast.querySelector(".report-ready-open").addEventListener("click", () => {
      location.hash = "#reportView";
      toast.classList.remove("show");
    });

    document.body.appendChild(toast);
    return toast;
  }

  window.showOpsLensReportReadyToast = function () {
    const toast = ensureReportReadyToast();

    toast.classList.add("show");

    clearTimeout(window.__opslensReportReadyToastTimer);
    window.__opslensReportReadyToastTimer = setTimeout(() => {
      toast.classList.remove("show");
    }, 5000);
  };

  function hideAllProgressBarsAfterComplete() {
    const bars = document.querySelectorAll(
      ".opslens-live-progress, .global-status, .global-status-bar, .investigation-status, .investigation-status-bar, .status-bar, #globalStatus, #investigationStatus"
    );

    bars.forEach((bar) => {
      bar.classList.remove("show", "active", "running", "visible");
      bar.classList.add("completed");
      bar.style.opacity = "0";
      bar.style.pointerEvents = "none";
    });

    localStorage.removeItem("opslens_active_job_id");
    localStorage.removeItem("opslens_active_job_started_at");
    localStorage.removeItem("opslens_active_pipeline_stage");
    localStorage.removeItem("opslens_global_status");
  }

  function completeProgressWithNotification() {
    const bar = document.querySelector(".opslens-live-progress");

    if (bar) {
      const stage = bar.querySelector(".live-progress-stage");
      const subtitle = bar.querySelector(".live-progress-subtitle");
      const fill = bar.querySelector(".live-progress-fill");

      if (stage) stage.textContent = "Completed";
      if (subtitle) subtitle.textContent = "Investigation completed. Report is ready.";
      if (fill) fill.style.width = "100%";
    }

    window.showOpsLensReportReadyToast();

    setTimeout(hideAllProgressBarsAfterComplete, 1800);
  }

  function payloadCompleted(payload) {
    const status = String(payload?.status || payload?.state || "").toLowerCase();

    return (
      status.includes("complete") ||
      status.includes("completed") ||
      status.includes("success") ||
      status.includes("done") ||
      Boolean(payload?.report) ||
      Boolean(payload?.result) ||
      Boolean(payload?.final_report)
    );
  }

  if (!window.__opslensReportReadyFetchGuard) {
    window.__opslensReportReadyFetchGuard = true;

    const originalFetch = window.fetch.bind(window);

    window.fetch = async function (...args) {
      const response = await originalFetch(...args);

      try {
        const url = String(args[0] || "");
        const method = String(args[1]?.method || "GET").toUpperCase();

        if (url.includes("/api/investigations") && method === "GET") {
          response.clone().json().then((payload) => {
            if (payloadCompleted(payload)) {
              completeProgressWithNotification();
            }
          }).catch(() => {});
        }
      } catch {}

      return response;
    };
  }
})();


// =========================================================
// Startup scope autoselect
// Opens Investigate view and preselects node/namespace from URL.
// Example:
// /?namespace=opslens-payments&node=minikube#investigateView
// =========================================================

(function () {
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function getStartupScope() {
    const params = new URLSearchParams(window.location.search);

    const namespace =
      params.get("namespace") ||
      params.get("ns") ||
      localStorage.getItem("opslens_startup_namespace") ||
      "";

    const node =
      params.get("node") ||
      params.get("node_name") ||
      localStorage.getItem("opslens_startup_node") ||
      "";

    if (namespace) localStorage.setItem("opslens_startup_namespace", namespace);
    if (node) localStorage.setItem("opslens_startup_node", node);

    return { namespace, node };
  }

  function findSelect(kind) {
    const all = Array.from(document.querySelectorAll("select"));

    const candidates = all.filter((select) => {
      const text = [
        select.id,
        select.name,
        select.getAttribute("aria-label"),
        select.dataset?.field,
        select.dataset?.name,
      ].join(" ").toLowerCase();

      if (kind === "node") {
        return text.includes("node");
      }

      if (kind === "namespace") {
        return text.includes("namespace") || text.includes("ns");
      }

      return false;
    });

    return candidates[0] || null;
  }

  function setSelectValue(select, value) {
    if (!select || !value) return false;

    const options = Array.from(select.options || []);
    const exact = options.find((option) => option.value === value || option.textContent.trim() === value);

    if (exact) {
      select.value = exact.value;
    } else {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
      select.value = value;
    }

    select.dispatchEvent(new Event("input", { bubbles: true }));
    select.dispatchEvent(new Event("change", { bubbles: true }));

    return true;
  }

  function openInvestigateView() {
    if (window.location.hash !== "#investigateView") {
      window.location.hash = "#investigateView";
    }

    if (typeof showView === "function") {
      try {
        showView("investigateView");
      } catch {}
    }

    const investigateNav = Array.from(document.querySelectorAll("a, button")).find((el) => {
      const text = (el.textContent || "").trim().toLowerCase();
      const href = String(el.getAttribute("href") || "").toLowerCase();
      return text.includes("investigate") || href.includes("investigateview");
    });

    if (investigateNav) {
      try {
        investigateNav.click();
      } catch {}
    }
  }

  async function applyStartupScope() {
    const { namespace, node } = getStartupScope();

    if (!namespace && !node) return;

    openInvestigateView();

    // Wait for dropdowns to be populated by backend.
    for (let attempt = 0; attempt < 12; attempt++) {
      await sleep(350);

      const nodeSelect = findSelect("node");
      const namespaceSelect = findSelect("namespace");

      if (nodeSelect && node) {
        setSelectValue(nodeSelect, node);
      }

      // Namespace options may reload after node change.
      await sleep(200);

      const namespaceSelectAfterNode = findSelect("namespace") || namespaceSelect;

      if (namespaceSelectAfterNode && namespace) {
        setSelectValue(namespaceSelectAfterNode, namespace);
      }

      if ((!node || findSelect("node")?.value === node) && (!namespace || findSelect("namespace")?.value === namespace)) {
        break;
      }
    }
  }

  window.addEventListener("load", () => {
    setTimeout(() => {
      applyStartupScope();
    }, 900);
  });
})();


// =========================================================
// Final product UX patch:
// - local Markdown/JSON download
// - progress notification/hide
// - remove disclaimer from progress
// - collapse side menu after navigation
// =========================================================

(function () {
  function tryGetCurrentReport() {
    try {
      if (typeof currentReport !== "undefined" && currentReport) return currentReport;
    } catch {}

    try {
      const cached = JSON.parse(localStorage.getItem("opslens_cached_reports_v2") || "[]");
      if (Array.isArray(cached) && cached.length) {
        return cached[0].report || cached[0];
      }
    } catch {}

    return null;
  }

  function text(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.map(text).join("\n");
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  }

  function mdList(value) {
    if (!value) return "- Not found in collected evidence";

    if (Array.isArray(value)) {
      if (!value.length) return "- Not found in collected evidence";

      return value.map((item) => {
        if (item && typeof item === "object") {
          if (item.command) {
            return `- ${item.title ? `**${item.title}:** ` : ""}\`${item.command}\``;
          }
          return `- ${text(item)}`;
        }
        return `- ${text(item)}`;
      }).join("\n");
    }

    if (typeof value === "object") {
      return Object.entries(value)
        .map(([key, val]) => `- **${key}:** ${text(val) || "Not found in collected evidence"}`)
        .join("\n");
    }

    return `- ${text(value)}`;
  }

  function reportMarkdown(report) {
    const affected = report?.affected_resources || {};
    const fix = report?.recommended_fix || {};

    return `# ${report?.title || "OpsLens Report"}

## Status

| Field | Value |
|---|---|
| Severity | ${report?.severity || "not found"} |
| Confidence | ${report?.confidence || "not found"} |
| Namespace | ${affected.namespace || "not found in collected evidence"} |
| Node | ${affected.node || affected.node_name || "not found in collected evidence"} |
| Service | ${affected.service || "not found in collected evidence"} |
| Deployment | ${affected.deployment || "not found in collected evidence"} |

## Incident Summary

${report?.incident_summary || report?.summary || "No active incident was detected in the selected scope."}

## Evidence Trail

${mdList(report?.evidence_trail || report?.evidence)}

## Additional Findings

${mdList(report?.additional_findings || report?.additional_issues)}

## Root Cause Story

${report?.root_cause_story || report?.root_cause || "No root cause was identified because no active failure evidence was found."}

## Recommended Fix

${fix.strategy || report?.recommendation || "No remediation required. Continue monitoring."}

## Safe Commands

${mdList(fix.safe_commands || report?.safe_commands)}

## Verification Plan

${fix.verification_plan || report?.verification_plan || "Verify the selected namespace state."}

## Verification Commands

${mdList(fix.verification_commands || report?.verification_commands)}

---

OpsLens can make mistakes. Verify evidence and safe commands before applying changes.
`;
  }

  function downloadFile(filename, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");

    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();

    setTimeout(() => {
      URL.revokeObjectURL(url);
      a.remove();
    }, 500);
  }

  function exportFormat() {
    const select =
      document.querySelector("#exportFormat") ||
      document.querySelector("[name='exportFormat']") ||
      document.querySelector("#reportView select") ||
      document.querySelector(".export-card select");

    return String(select?.value || "markdown").toLowerCase();
  }

  function reportFilename(report, ext) {
    const affected = report?.affected_resources || {};
    const base = affected.service || affected.deployment || affected.namespace || "opslens-report";
    const clean = String(base).replace(/[^a-zA-Z0-9_-]+/g, "-");
    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "_");

    return `${clean}_${stamp}.${ext}`;
  }

  function looksLikeDownloadButton(el) {
    const button = el?.closest?.("button, a");
    if (!button) return null;

    const label = (button.textContent || "").trim().toLowerCase();
    const id = String(button.id || "").toLowerCase();
    const cls = String(button.className || "").toLowerCase();
    const href = String(button.getAttribute("href") || "").toLowerCase();

    const isDownload =
      label.includes("download") ||
      id.includes("download") ||
      cls.includes("download") ||
      href.includes("download");

    if (!isDownload) return null;

    const reportView = document.querySelector("#reportView");
    if (reportView && !reportView.contains(button)) return null;

    return button;
  }

  async function handleLocalDownload(event) {
    const button = looksLikeDownloadButton(event.target);
    if (!button) return;

    const report = tryGetCurrentReport();
    if (!report) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const format = exportFormat();
    const normalizedFormat =
      format.includes("pdf") ? "pdf" :
      format.includes("excel") || format.includes("xlsx") ? "xlsx" :
      format.includes("json") ? "json" :
      "markdown";

    try {
      const response = await fetch(`/api/export/report/${encodeURIComponent(normalizedFormat)}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "*/*",
        },
        body: JSON.stringify(report),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Export failed with status ${response.status}`);
      }

      const blob = await response.blob();

      let filename = `opslens-report.${normalizedFormat === "xlsx" ? "xlsx" : normalizedFormat}`;
      const disposition = response.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/i);
      if (match && match[1]) filename = match[1];

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();

      setTimeout(() => {
        URL.revokeObjectURL(url);
        a.remove();
      }, 500);
    } catch (error) {
      console.error("Export failed:", error);
      alert(`Export failed: ${error.message || error}`);
    }
  }

  ["pointerdown", "mousedown", "click"].forEach((eventName) => {
    document.addEventListener(eventName, handleLocalDownload, true);
  });

  function neutralizeBackendDownloadLinks() {
    const reportView = document.querySelector("#reportView");
    if (!reportView) return;

    reportView.querySelectorAll("a[href*='download'], button").forEach((el) => {
      const label = (el.textContent || "").toLowerCase();

      if (!label.includes("download") && !String(el.getAttribute("href") || "").includes("download")) return;

      el.removeAttribute("href");
      el.removeAttribute("target");
      el.dataset.localDownload = "true";
    });
  }

  setInterval(neutralizeBackendDownloadLinks, 700);

  function removeProgressDisclaimer() {
    document.querySelectorAll(".live-progress-disclaimer").forEach((el) => el.remove());
  }

  setInterval(removeProgressDisclaimer, 500);

  function ensureReportReadyToast() {
    let toast = document.querySelector(".opslens-report-ready-toast");

    if (toast) return toast;

    toast = document.createElement("div");
    toast.className = "opslens-report-ready-toast";
    toast.innerHTML = `
      <div class="report-ready-check">?</div>
      <div>
        <strong>Report ready</strong>
        <span>Investigation completed. Open Reports to review it.</span>
      </div>
      <button type="button" class="report-ready-open">Open</button>
    `;

    toast.querySelector(".report-ready-open").addEventListener("click", () => {
      location.hash = "#reportView";
      toast.classList.remove("show");
    });

    document.body.appendChild(toast);
    return toast;
  }

  function showReportReadyToast() {
    const toast = ensureReportReadyToast();

    toast.classList.add("show");

    clearTimeout(window.__opslensReportReadyToastTimer);
    window.__opslensReportReadyToastTimer = setTimeout(() => {
      toast.classList.remove("show");
    }, 5000);
  }

  function hideProgressBars() {
    document.querySelectorAll(
      ".opslens-live-progress, .global-status, .global-status-bar, .investigation-status, .investigation-status-bar, .status-bar, #globalStatus, #investigationStatus"
    ).forEach((bar) => {
      bar.classList.remove("show", "active", "running", "visible");
      bar.classList.add("completed");
      bar.style.opacity = "0";
      bar.style.pointerEvents = "none";
    });

    localStorage.removeItem("opslens_active_job_id");
    localStorage.removeItem("opslens_active_job_started_at");
    localStorage.removeItem("opslens_active_pipeline_stage");
    localStorage.removeItem("opslens_global_status");
  }

  function completeInvestigationUi() {
    const bar = document.querySelector(".opslens-live-progress");

    if (bar) {
      const stage = bar.querySelector(".live-progress-stage");
      const subtitle = bar.querySelector(".live-progress-subtitle");
      const fill = bar.querySelector(".live-progress-fill");

      if (stage) stage.textContent = "Completed";
      if (subtitle) subtitle.textContent = "Investigation completed. Report is ready.";
      if (fill) fill.style.width = "100%";
    }

    showReportReadyToast();
    setTimeout(hideProgressBars, 1600);
  }

  function payloadIsDone(payload) {
    const status = String(payload?.status || payload?.state || "").toLowerCase();

    return (
      status.includes("complete") ||
      status.includes("completed") ||
      status.includes("success") ||
      status.includes("done") ||
      Boolean(payload?.report) ||
      Boolean(payload?.result) ||
      Boolean(payload?.final_report)
    );
  }

  if (!window.__opslensFinalDoneFetchPatch) {
    window.__opslensFinalDoneFetchPatch = true;

    const originalFetch = window.fetch.bind(window);

    window.fetch = async function (...args) {
      const response = await originalFetch(...args);

      try {
        const url = String(args[0] || "");
        const method = String(args[1]?.method || "GET").toUpperCase();

        if (url.includes("/api/investigations") && method === "GET") {
          response.clone().json().then((payload) => {
            if (payloadIsDone(payload)) completeInvestigationUi();
          }).catch(() => {});
        }
      } catch {}

      return response;
    };
  }

  function collapseSideMenu() {
    document.body.classList.remove(
      "sidebar-open",
      "menu-open",
      "nav-open",
      "sidebar-expanded",
      "side-menu-open"
    );

    document.querySelectorAll(
      ".sidebar, .app-sidebar, .side-panel, .side-rail, .left-sidebar, .nav-sidebar, .rail"
    ).forEach((el) => {
      el.classList.remove("open", "opened", "expanded", "show", "is-open", "is-expanded");
      el.classList.add("collapsed");
    });

    document.querySelectorAll("[aria-expanded='true']").forEach((el) => {
      el.setAttribute("aria-expanded", "false");
    });
  }

  document.addEventListener("click", (event) => {
    const navItem = event.target.closest(
      ".sidebar a, .sidebar button, .app-sidebar a, .app-sidebar button, .side-panel a, .side-panel button, .side-rail a, .side-rail button, .nav-sidebar a, .nav-sidebar button, .rail a, .rail button"
    );

    if (!navItem) return;

    setTimeout(collapseSideMenu, 120);
  }, true);

  window.addEventListener("hashchange", () => {
    setTimeout(collapseSideMenu, 120);
  });
})();


// =========================================================
// Selected report export v2
// Last 5 cached reports + backend export by selected format.
// =========================================================

(function () {
  const CACHE_KEY = "opslens_cached_reports_v2";

  function readCachedReportsForExport() {
    try {
      const items = JSON.parse(localStorage.getItem(CACHE_KEY) || "[]");
      if (!Array.isArray(items)) return [];

      return items
        .map((item, index) => {
          const report = item.report || item;
          const affected = report.affected_resources || {};
          return {
            id: item.cache_id || item.record_id || item.id || `cached-${index}`,
            label: [
              report.title || "OpsLens Report",
              affected.namespace ? `ns:${affected.namespace}` : "",
              affected.service ? `svc:${affected.service}` : "",
              item.cached_at ? new Date(item.cached_at).toLocaleString() : "",
            ].filter(Boolean).join(" | "),
            report,
          };
        })
        .slice(0, 5);
    } catch {
      return [];
    }
  }

  function currentReportForExport() {
    try {
      if (typeof currentReport !== "undefined" && currentReport) {
        return currentReport;
      }
    } catch {}

    return null;
  }

  function ensureCurrentReportInExportCache() {
    const report = currentReportForExport();
    if (!report) return;

    const items = readCachedReportsForExport();
    const text = JSON.stringify(report);

    const exists = items.some((item) => JSON.stringify(item.report) === text);
    if (exists) return;

    const affected = report.affected_resources || {};
    const newItem = {
      cache_id: `current-${Date.now()}`,
      cached_at: new Date().toISOString(),
      title: report.title || "OpsLens Report",
      service: affected.service || affected.deployment || affected.namespace || "opslens-report",
      namespace: affected.namespace || "",
      report,
    };

    const raw = JSON.parse(localStorage.getItem(CACHE_KEY) || "[]");
    localStorage.setItem(CACHE_KEY, JSON.stringify([newItem, ...raw].slice(0, 5)));
  }

  function ensureExportReportSelector() {
    const reportView = document.querySelector("#reportView");
    if (!reportView) return null;

    let selector = document.querySelector("#opslensExportReportSelect");
    if (selector) return selector;

    const exportCard =
      reportView.querySelector(".export-card") ||
      reportView.querySelector("[class*='export']") ||
      reportView;

    const wrapper = document.createElement("div");
    wrapper.className = "opslens-export-report-picker";
    wrapper.innerHTML = `
      <label for="opslensExportReportSelect">Report to download</label>
      <select id="opslensExportReportSelect"></select>
      <small>Latest 5 cached reports are available for export.</small>
    `;

    exportCard.prepend(wrapper);

    return wrapper.querySelector("select");
  }

  function refreshExportReportSelector() {
    ensureCurrentReportInExportCache();

    const selector = ensureExportReportSelector();
    if (!selector) return;

    const previous = selector.value;
    const reports = readCachedReportsForExport();

    selector.innerHTML = "";

    if (!reports.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No cached reports available";
      selector.appendChild(option);
      return;
    }

    reports.forEach((item, index) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = `${index + 1}. ${item.label}`;
      selector.appendChild(option);
    });

    if (previous && Array.from(selector.options).some((opt) => opt.value === previous)) {
      selector.value = previous;
    }
  }

  function selectedReportForExport() {
    ensureCurrentReportInExportCache();

    const selector = document.querySelector("#opslensExportReportSelect");
    const reports = readCachedReportsForExport();

    if (selector && selector.value) {
      const selected = reports.find((item) => item.id === selector.value);
      if (selected?.report) return selected.report;
    }

    if (reports[0]?.report) return reports[0].report;

    return currentReportForExport();
  }

  function selectedExportFormat() {
    const select =
      document.querySelector("#exportFormat") ||
      document.querySelector("[name='exportFormat']") ||
      document.querySelector("#reportView select:not(#opslensExportReportSelect)") ||
      document.querySelector(".export-card select:not(#opslensExportReportSelect)");

    const value = String(select?.value || "markdown").toLowerCase();

    if (value.includes("pdf")) return "pdf";
    if (value.includes("excel") || value.includes("xlsx")) return "xlsx";
    if (value.includes("json")) return "json";
    return "markdown";
  }

  function isReportDownloadButton(target) {
    const button = target.closest("button, a");
    if (!button) return false;

    const reportView = document.querySelector("#reportView");
    if (reportView && !reportView.contains(button)) return false;

    const text = (button.textContent || "").toLowerCase();
    const id = String(button.id || "").toLowerCase();
    const cls = String(button.className || "").toLowerCase();
    const href = String(button.getAttribute("href") || "").toLowerCase();

    return (
      text.includes("download") ||
      id.includes("download") ||
      cls.includes("download") ||
      href.includes("download")
    );
  }

  async function exportSelectedReport(event) {
    if (!isReportDownloadButton(event.target)) return;

    const report = selectedReportForExport();
    if (!report) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    const format = selectedExportFormat();

    try {
      const response = await fetch(`/api/export/report/${encodeURIComponent(format)}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "*/*",
        },
        body: JSON.stringify(report),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Export failed with status ${response.status}`);
      }

      const blob = await response.blob();
      let filename = `opslens-report.${format === "xlsx" ? "xlsx" : format}`;

      const disposition = response.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/i);
      if (match?.[1]) filename = match[1];

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");

      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();

      setTimeout(() => {
        URL.revokeObjectURL(url);
        a.remove();
      }, 600);
    } catch (error) {
      console.error("Report export failed:", error);
      alert(`Report export failed: ${error.message || error}`);
    }
  }

  ["pointerdown", "mousedown", "click"].forEach((eventName) => {
    document.addEventListener(eventName, exportSelectedReport, true);
  });

  window.addEventListener("load", () => {
    setInterval(refreshExportReportSelector, 1000);
  });
})();


// =========================================================
// Progress spacing guard
// Adds page bottom spacing while progress bar is visible.
// =========================================================

(function () {
  function syncProgressSpacing() {
    const bar = document.querySelector(".opslens-live-progress");
    const isVisible =
      bar &&
      bar.classList.contains("show") &&
      !bar.classList.contains("completed") &&
      getComputedStyle(bar).opacity !== "0";

    document.body.classList.toggle("opslens-progress-running", Boolean(isVisible));
  }

  window.addEventListener("load", () => {
    setInterval(syncProgressSpacing, 300);
  });

  window.addEventListener("scroll", syncProgressSpacing, { passive: true });
})();

