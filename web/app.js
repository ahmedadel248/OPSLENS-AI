
const $ = (id) => document.getElementById(id);

let currentJobId = null;
let currentReport = null;
let pollTimer = null;

const views = document.querySelectorAll(".view");
const navButtons = document.querySelectorAll(".nav-btn");

const nodeSelect = $("nodeSelect");
const namespaceSelect = $("namespaceSelect");
const namespaceInput = $("namespaceInput");
const scenarioSelect = $("scenarioSelect");
const applyScenario = $("applyScenario");
const resetNamespace = $("resetNamespace");
const demoMetrics = $("demoMetrics");
const waitSeconds = $("waitSeconds");
const runBtn = $("runBtn");

const apiStatus = $("apiStatus");
const jobStatus = $("jobStatus");
const jobMiniStatus = $("jobMiniStatus");
const jobIdLabel = $("jobId");
const clusterSummary = $("clusterSummary");
const latestSummary = $("latestSummary");

const pipeline = $("pipeline");
const pipelineHint = $("pipelineHint");

const emptyState = $("emptyState");
const reportSection = $("reportSection");
const reportTitle = $("reportTitle");
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
  views.forEach((view) => view.classList.toggle("hidden", view.id !== viewId));
  navButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.view === viewId));
}

navButtons.forEach((btn) => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});

function option(value, text = value) {
  const el = document.createElement("option");
  el.value = value;
  el.textContent = text;
  return el;
}

async function bootstrap() {
  renderPipeline([]);

  try {
    const health = await api("/api/health");
    apiStatus.textContent = `${health.service}: ${health.status}`;

    const [nodes, scenarios] = await Promise.all([
      api("/api/cluster/nodes"),
      api("/api/scenarios"),
    ]);

    nodeSelect.innerHTML = "";
    nodes.nodes.forEach((node) => nodeSelect.appendChild(option(node)));

    scenarioSelect.innerHTML = "";
    scenarioSelect.appendChild(option("", "No scenario"));
    scenarios.scenarios.forEach((scenario) => scenarioSelect.appendChild(option(scenario)));

    if (scenarios.scenarios.includes("multi_issue_k8s_chaos.yml")) {
      scenarioSelect.value = "multi_issue_k8s_chaos.yml";
    }

    await loadNamespacesForSelectedNode();

    clusterSummary.textContent = `Nodes: ${nodes.nodes.length}. Scenarios: ${scenarios.scenarios.length}.`;
  } catch (error) {
    apiStatus.textContent = `API error: ${error.message}`;
    apiStatus.style.color = "#fb7185";
    clusterSummary.textContent = "Could not load cluster details.";
  }
}

async function loadNamespacesForSelectedNode() {
  const node = nodeSelect.value;

  namespaceSelect.innerHTML = "";
  namespaceSelect.appendChild(option("", "Loading namespaces..."));

  try {
    let response;

    if (node) {
      response = await api(`/api/cluster/nodes/${encodeURIComponent(node)}/namespaces`);
    } else {
      response = await api("/api/cluster/namespaces");
    }

    const namespaces = response.namespaces || [];

    namespaceSelect.innerHTML = "";

    if (!namespaces.length) {
      namespaceSelect.appendChild(option("", "No namespaces with pods on this node"));
      return;
    }

    namespaces.forEach((ns) => namespaceSelect.appendChild(option(ns)));

    if (namespaces.includes("opslens-chaos")) {
      namespaceSelect.value = "opslens-chaos";
    }
  } catch (error) {
    namespaceSelect.innerHTML = "";
    namespaceSelect.appendChild(option("", "Could not load namespaces"));
  }
}

nodeSelect.addEventListener("change", loadNamespacesForSelectedNode);

function namespaceValue() {
  return namespaceInput.value.trim() || namespaceSelect.value;
}

function renderPipeline(stages) {
  pipeline.innerHTML = "";

  const fallback = [
    ["scope", "Investigation Scope", "pending"],
    ["scenario", "Scenario Preparation", "pending"],
    ["collectors", "Collectors", "pending"],
    ["config_agent", "Config Agent", "pending"],
    ["logs_agent", "Logs Agent", "pending"],
    ["metrics_agent", "Metrics Agent + Model", "pending"],
    ["supervisor", "Supervisor Agent", "pending"],
    ["llm", "LLM Reasoning", "pending"],
    ["safety", "Command Safety Layer", "pending"],
    ["report", "Report Generated", "pending"],
  ].map(([key, label, status]) => ({ key, label, status }));

  const finalStages = stages && stages.length ? stages : fallback;

  finalStages.forEach((stage) => {
    const card = document.createElement("div");
    card.className = `stage ${stage.status}`;

    card.innerHTML = `
      <div class="stage-dot"></div>
      <h4>${escapeHtml(stage.label)}</h4>
      <p>${escapeHtml(stage.status)}</p>
    `;

    pipeline.appendChild(card);
  });
}

function setJobHeader(job) {
  const status = job.status || "unknown";

  jobStatus.textContent = status;
  jobMiniStatus.textContent = job.job_id ? `Job ${status}: ${job.job_id}` : "No job yet";
  jobIdLabel.textContent = job.job_id ? `Job: ${job.job_id}` : "No job yet";

  if (status === "running") {
    pipelineHint.textContent = "Agents are investigating the selected scope...";
  } else if (status === "completed") {
    pipelineHint.textContent = "Investigation completed successfully.";
  } else if (status === "failed") {
    pipelineHint.textContent = "Investigation failed.";
  } else {
    pipelineHint.textContent = "Waiting for investigation.";
  }
}

async function runInvestigation() {
  const payload = {
    node_name: nodeSelect.value,
    namespace: namespaceValue(),
    scenario_name: scenarioSelect.value || null,
    apply_scenario: applyScenario.checked && Boolean(scenarioSelect.value),
    reset_namespace: resetNamespace.checked,
    demo_seed_metrics: demoMetrics.checked,
    wait_seconds: Number(waitSeconds.value || 45),
  };

  if (!payload.node_name || !payload.namespace) {
    alert("Please select node and namespace.");
    return;
  }

  if (payload.reset_namespace) {
    const ok = confirm(`Reset namespace '${payload.namespace}'? This will delete resources in that namespace.`);
    if (!ok) return;
  }

  runBtn.disabled = true;
  runBtn.textContent = "Investigation running...";
  showView("pipelineView");

  try {
    const job = await api("/api/investigations", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    currentJobId = job.job_id;
    setJobHeader(job);
    renderPipeline(job.stages);

    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollJob, 1200);
  } catch (error) {
    alert(`Failed to start investigation:\n${error.message}`);
    runBtn.disabled = false;
    runBtn.textContent = "Run Investigation";
  }
}

async function pollJob() {
  if (!currentJobId) return;

  try {
    const job = await api(`/api/investigations/${currentJobId}`);

    setJobHeader(job);
    renderPipeline(job.stages);

    if (job.status === "completed") {
      clearInterval(pollTimer);
      pollTimer = null;

      runBtn.disabled = false;
      runBtn.textContent = "Run Investigation";

      currentReport = job.report || {};
      latestSummary.textContent = `${currentReport.title || "Completed investigation"} - ${currentReport.severity || "unknown"}`;
      renderReport(currentReport);
      showView("reportView");
    }

    if (job.status === "failed") {
      clearInterval(pollTimer);
      pollTimer = null;

      runBtn.disabled = false;
      runBtn.textContent = "Run Investigation";

      alert(`Investigation failed:\n${job.error || "Unknown error"}`);
    }
  } catch (error) {
    clearInterval(pollTimer);
    pollTimer = null;

    runBtn.disabled = false;
    runBtn.textContent = "Run Investigation";

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

  renderEvidence(report.agent_reasoning || []);
  renderAdditional(report.additional_findings || []);
  renderFix(report.recommended_fix || {});
  renderVerification(report.verification || {});
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
        <button class="copy-btn" data-command="${encodeURIComponent(command)}">Copy</button>
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
