from pathlib import Path

app_path = Path("web/app.js")

if not app_path.exists():
    raise SystemExit("ERROR: web/app.js not found")

text = app_path.read_text(encoding="utf-8", errors="ignore")

# Fix created_at in completed job report.
text = text.replace(
    "currentReport.created_at = currentReport.created_at || new Date().toISOString();",
    "currentReport.created_at = currentReport.created_at || job.created_at || new Date().toISOString();"
)

marker = "// =========================================================\n// Backend investigation history"
idx = text.find(marker)

if idx == -1:
    raise SystemExit("ERROR: Backend investigation history marker not found")

clean_tail = r'''
// =========================================================
// Backend-only history and clean report/export controller
// This section intentionally replaces all old frontend cache/history/save code.
// =========================================================

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

function clearFrontendHistoryCache() {
  try {
    [
      "opslens_cached_reports",
      "opslens_cached_reports_v2",
      "opslens_investigation_records",
      "opslens_active_job_started_at",
      "opslens_active_pipeline_stage"
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
    const result = await api("/api/db/history?limit=20");
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
    const key = String(
      record.record_id ||
      [
        record.title || "",
        record.namespace || "",
        record.service || "",
        record.created_at || ""
      ].join("|")
    );

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
      if (!recordId) return;

      const report = await api(`/api/db/history/${encodeURIComponent(recordId)}`);
      currentReport = normalizeReport(report) || report;
      currentJobId = null;
      renderReport(currentReport);
      showView("reportView");
    });
  });

  investigationRecords.querySelectorAll(".download-record-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const recordId = btn.dataset.recordId;
      if (!recordId) return;
      window.location.href = `/api/db/history/${encodeURIComponent(recordId)}/report/pdf/download`;
    });
  });
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

if (downloadReportBtn) {
  downloadReportBtn.addEventListener("click", async () => {
    if (!currentReport) {
      alert("No report available to download.");
      return;
    }

    try {
      await postExport(currentReport, selectedDownloadFormat());
    } catch (error) {
      console.error("Download failed:", error);
      alert(`Download failed: ${error.message || error}`);
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
'''

app_path.write_text(text[:idx].rstrip() + "\n\n" + clean_tail.strip() + "\n", encoding="utf-8")

print("DONE: web/app.js cleaned.")
print("Removed old duplicated frontend history/cache/save/export wrappers.")
print("Frontend now reads history from backend only.")
