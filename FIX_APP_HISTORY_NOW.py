from pathlib import Path
import re

app_path = Path("web/app.js")

if not app_path.exists():
    raise SystemExit("ERROR: web/app.js not found")

app = app_path.read_text(encoding="utf-8", errors="ignore")

# 1) امنع pollJob من حفظ التقرير في الفرونت
app = app.replace("      await saveCurrentReportToDatabase(currentReport);\n", "")
app = app.replace("      saveCurrentReportToDatabase(currentReport);\n", "")

# 2) امنع renderReport من cache المحلي
app = app.replace("  cacheReportLocally(report);\n\n", "")

# 3) خلي عرض التاريخ يستخدم created_at مش modified_at
app = app.replace(
    "const date = new Date(record.modified_at || record.created_at);",
    "const date = new Date(record.created_at || record.modified_at);"
)

# 4) صحح خطأ await await لو موجود
app = app.replace("await await renderBackendInvestigationRecords", "await renderBackendInvestigationRecords")

# 5) أضف override نهائي يمنع كل local/cache/frontend saves
hard_override = r'''

// =========================================================
// OpsLens FINAL history fix
// Frontend must NEVER save reports or create cached history.
// Backend DB is the only source of truth for investigation history.
// =========================================================
(function () {
  if (window.__opslensFinalHistoryFixApplied) return;
  window.__opslensFinalHistoryFixApplied = true;

  const HISTORY_KEYS = [
    "opslens_cached_reports",
    "opslens_cached_reports_v2",
    "opslens_investigation_records"
  ];

  try {
    HISTORY_KEYS.forEach((key) => localStorage.removeItem(key));
  } catch (_) {}

  function normalizeReport(value) {
    if (!value) return null;

    if (typeof value === "string") {
      try {
        return normalizeReport(JSON.parse(value));
      } catch (_) {
        return null;
      }
    }

    if (typeof value !== "object") return null;

    if (value.report && typeof value.report === "object") return value.report;

    return value;
  }

  function safeText(value) {
    return escapeHtml(value || "");
  }

  // Disable all frontend persistence.
  saveCurrentReportToDatabase = async function () {
    return null;
  };

  saveInvestigationRecord = function () {
    return;
  };

  cacheReportLocally = function () {
    return;
  };

  getCachedReports = function () {
    return [];
  };

  restoreLatestCachedReport = function () {
    return;
  };

  window.opslensCacheReportFinal = function () {
    return;
  };

  window.opslensSaveReportFinal = async function () {
    return null;
  };

  window.opslensRestoreLatestReportFinal = function () {
    return;
  };

  renderInvestigationRecords = function () {
    return loadBackendInvestigationHistory();
  };

  loadBackendInvestigationHistory = async function () {
    if (!investigationRecords) return;

    investigationRecords.innerHTML = `<p class="muted">Loading investigation history...</p>`;

    try {
      const result = await api("/api/db/history?limit=20");
      const records = result.records || [];

      if (!records.length) {
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
      investigationRecords.innerHTML = `
        <div class="history-error">
          <strong>Could not load backend history</strong>
          <p>${safeText(error.message)}</p>
        </div>
      `;
    }
  };

  renderBackendInvestigationRecords = function (records) {
    if (!investigationRecords) return;

    const unique = [];
    const seen = new Set();

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
      const date = new Date(record.created_at || record.modified_at);
      const stamp = Number.isNaN(date.getTime())
        ? (record.created_at || "")
        : date.toLocaleString();

      return `
        <div class="record-card backend-record" data-record-id="${safeText(record.record_id)}">
          <div>
            <strong>${safeText(record.service || "unknown-service")}</strong>
            <p>${safeText(record.title || "OpsLens Investigation")}</p>
          </div>
          <div>
            <small>Namespace</small>
            <span>${safeText(record.namespace || "unknown")}</span>
          </div>
          <div>
            <small>Severity</small>
            <span>${safeText(record.severity || "unknown")}</span>
          </div>
          <div>
            <small>Created</small>
            <span>${safeText(stamp)}</span>
          </div>
          <div class="record-actions">
            <button type="button" class="open-record-btn" data-record-id="${safeText(record.record_id)}">Open</button>
            <button type="button" class="download-record-btn" data-record-id="${safeText(record.record_id)}">PDF</button>
          </div>
        </div>
      `;
    }).join("");

    investigationRecords.querySelectorAll(".open-record-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const recordId = btn.dataset.recordId;
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
        window.location.href = `/api/db/history/${encodeURIComponent(recordId)}/report/pdf/download`;
      });
    });
  };

  // Clean export picker/cache UI if old code created it.
  function removeCachedExportPicker() {
    document.querySelectorAll(".opslens-export-report-picker").forEach((node) => node.remove());

    document.querySelectorAll("small").forEach((node) => {
      const text = (node.textContent || "").toLowerCase();
      if (text.includes("cached reports")) {
        node.remove();
      }
    });
  }

  window.addEventListener("load", () => {
    removeCachedExportPicker();
    loadBackendInvestigationHistory();
  });

  setInterval(removeCachedExportPicker, 1000);
})();
'''

if "OpsLens FINAL history fix" not in app:
    app = app.rstrip() + "\n\n" + hard_override.strip() + "\n"

app_path.write_text(app, encoding="utf-8")

print("DONE: web/app.js patched directly.")
print("Frontend will no longer save reports or create cached duplicate history.")
