from pathlib import Path
import re

history_path = Path("src/api/history_store.py")
services_path = Path("src/api/services.py")

if not history_path.exists():
    raise SystemExit("ERROR: src/api/history_store.py not found")

if not services_path.exists():
    raise SystemExit("ERROR: src/api/services.py not found")

history = history_path.read_text(encoding="utf-8", errors="ignore")
services = services_path.read_text(encoding="utf-8", errors="ignore")

# =========================================================
# 1) history_store.py
# Fix duplicate records:
# Backend save with record_id=job_id and frontend accidental save without record_id
# must resolve to the SAME record_id.
# =========================================================

history = history.replace(
    '''    if not record_id:
        record_id = f"{safe(service)}_{stable_report_key(report)}"''',
    '''    if not record_id:
        record_id = stable_report_key(report)'''
)

# =========================================================
# 2) history_store.py
# Stop get_report from syncing old JSON files back into SQLite.
# =========================================================

history = history.replace(
    '''def get_report(record_id: str) -> Dict[str, Any]:
    sync_reports()

    with conn() as db:''',
    '''def get_report(record_id: str) -> Dict[str, Any]:
    init_db()

    with conn() as db:'''
)

# =========================================================
# 3) history_store.py
# Sort by created_at, not modified_at.
# =========================================================

history = history.replace(
    "ORDER BY datetime(modified_at) DESC",
    "ORDER BY datetime(created_at) DESC"
)

# =========================================================
# 4) history_store.py
# Remove the final "OpsLens time fix" override that forces created_at
# and modified_at to current Cairo time on every save.
# This was the reason created time kept updating.
# =========================================================

marker = "# =========================================================\n# OpsLens time fix"
idx = history.find(marker)

if idx != -1:
    history = history[:idx].rstrip() + "\n\n"

history_path.write_text(history, encoding="utf-8")

# =========================================================
# 5) services.py
# Fix evidence guard:
# Runtime incidents can have evidence in agent_reasoning,
# primary_signal, incident_groups, supporting_signals, etc.
# Do not convert them to Healthy report.
# =========================================================

old_func = '''def _opslens_report_has_empty_evidence(report):
    evidence = (
        report.get("evidence_trail")
        or report.get("evidence")
        or report.get("timeline")
        or report.get("investigation_evidence")
    )

    additional = (
        report.get("additional_findings")
        or report.get("additional_issues")
        or report.get("secondary_findings")
    )

    return _opslens_is_empty_evidence(evidence) and _opslens_is_empty_evidence(additional)
'''

new_func = '''def _opslens_report_has_empty_evidence(report):
    """
    Treat structured OpsLens signals as real evidence.
    Runtime incidents often arrive through agent_reasoning / primary_signal /
    incident_groups instead of evidence_trail.
    """
    evidence = (
        report.get("evidence_trail")
        or report.get("evidence")
        or report.get("timeline")
        or report.get("investigation_evidence")
        or report.get("agent_reasoning")
        or report.get("important_evidence")
        or report.get("primary_signal")
        or report.get("primary_incident_group")
        or report.get("incident_groups")
        or report.get("supporting_signals")
        or report.get("root_cause_facts")
    )

    additional = (
        report.get("additional_findings")
        or report.get("additional_issues")
        or report.get("secondary_findings")
        or report.get("separate_findings")
        or report.get("unclassified_findings")
    )

    return _opslens_is_empty_evidence(evidence) and _opslens_is_empty_evidence(additional)
'''

if old_func in services:
    services = services.replace(old_func, new_func)
else:
    print("WARN: _opslens_report_has_empty_evidence block not found exactly. It may already be changed.")

services_path.write_text(services, encoding="utf-8")

print("DONE: history_store.py and services.py patched.")
print("Fixed:")
print("- Duplicate history record IDs")
print("- created_at updating every refresh/save")
print("- JSON sync recreating old reports on open")
print("- Runtime incidents being converted to Healthy reports")
