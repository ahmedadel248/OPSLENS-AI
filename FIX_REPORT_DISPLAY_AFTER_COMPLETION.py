from pathlib import Path
from datetime import datetime
import shutil
import re

path = Path("web/app.js")

if not path.exists():
    raise SystemExit("ERROR: web/app.js not found")

backup = path.with_name(f"app_backup_before_report_display_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}.js")
shutil.copy2(path, backup)
print(f"BACKUP CREATED: {backup}")

text = path.read_text(encoding="utf-8", errors="ignore")

def replace_async_function(src, name, body):
    pattern = rf"async function {re.escape(name)}\s*\([^)]*\)\s*\{{"
    match = re.search(pattern, src)

    if not match:
        raise SystemExit(f"ERROR: async function {name} not found")

    start = match.start()
    brace_start = src.find("{", match.start())
    depth = 0
    end = None

    for i in range(brace_start, len(src)):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        raise SystemExit(f"ERROR: could not find end of async function {name}")

    return src[:start] + body.strip() + src[end:]

new_handle_completed = r'''
async function handleCompletedJob(job, notify = true) {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  let report = normalizeReport(job && job.report);

  const reportLooksEmpty =
    !report ||
    (
      !report.title &&
      !report.incident_summary &&
      !report.root_cause_story &&
      !report.agent_reasoning &&
      !report.recommended_fix
    );

  if (reportLooksEmpty) {
    try {
      const history = await api("/api/db/history?limit=1");
      const latest = (history.records || [])[0];

      if (latest && latest.record_id) {
        const savedReport = await api(`/api/db/history/${encodeURIComponent(latest.record_id)}`);
        report = normalizeReport(savedReport) || savedReport;
      }
    } catch (error) {
      console.warn("Could not load completed report from backend history:", error);
    }
  }

  currentReport = report || {};
  currentReport.job_id = (job && job.job_id) || currentJobId || currentReport.job_id || "";
  currentReport.__opslens_job_id = currentReport.__opslens_job_id || currentReport.job_id;
  currentReport.created_at = currentReport.created_at || (job && job.created_at) || new Date().toISOString();
  currentReport.finished_at = currentReport.finished_at || (job && job.finished_at) || new Date().toISOString();

  renderReport(currentReport);

  try {
    await loadBackendInvestigationHistory();
  } catch (error) {
    console.warn("Could not refresh investigation history:", error);
  }

  finishActiveJob();
  clearGlobalStatus();

  showView("reportView");

  if (notify) {
    showToast("Investigation completed", "The RCA report is now displayed.", null, null, "success");
  }
}
'''

text = replace_async_function(text, "handleCompletedJob", new_handle_completed)

path.write_text(text, encoding="utf-8")

print("DONE: completed investigation now opens and displays reportView.")
