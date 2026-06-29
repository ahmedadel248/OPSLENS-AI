from pathlib import Path
import re

path = Path("src/core/report_safety.py")

if not path.exists():
    raise SystemExit("ERROR: src/core/report_safety.py not found")

text = path.read_text(encoding="utf-8", errors="ignore")

old = '''def _has_no_evidence(report: dict[str, Any]) -> bool:
    evidence = (
        report.get("evidence_trail")
        or report.get("evidence")
        or report.get("timeline")
        or report.get("investigation_evidence")
    )

    findings = (
        report.get("additional_findings")
        or report.get("additional_issues")
        or report.get("secondary_findings")
    )

    return _empty(evidence) and _empty(findings)
'''

new = '''def _is_no_finding_marker(value: Any) -> bool:
    text = _text(value).strip().lower()

    if not text:
        return True

    no_finding_markers = {
        "no data available",
        "no evidence available",
        "not available",
        "unavailable",
        "none",
        "[]",
        "{}",
        "no additional findings detected.",
        "no additional findings detected",
        "no evidence rows available.",
        "no evidence rows available",
    }

    return text in no_finding_markers


def _has_no_evidence(report: dict[str, Any]) -> bool:
    """
    Decide only whether the report has any real collected evidence.

    Important:
    Runtime incidents may not always use evidence_trail.
    They can appear through:
    - agent_reasoning
    - primary_signal
    - primary_incident_group
    - incident_groups
    - supporting_signals
    - root_cause_facts
    - important_evidence

    If any of those exist, do NOT convert the report to Healthy.
    """

    evidence_candidates = [
        report.get("evidence_trail"),
        report.get("evidence"),
        report.get("timeline"),
        report.get("investigation_evidence"),
        report.get("agent_reasoning"),
        report.get("important_evidence"),
        report.get("primary_signal"),
        report.get("primary_incident"),
        report.get("primary_incident_group"),
        report.get("incident_groups"),
        report.get("supporting_signals"),
        report.get("root_cause_facts"),
    ]

    finding_candidates = [
        report.get("additional_findings"),
        report.get("additional_issues"),
        report.get("secondary_findings"),
        report.get("separate_findings"),
        report.get("unclassified_findings"),
    ]

    for item in evidence_candidates:
        if not _is_no_finding_marker(item):
            return False

    for item in finding_candidates:
        if not _is_no_finding_marker(item):
            return False

    return True
'''

if old not in text:
    raise SystemExit("ERROR: expected _has_no_evidence block not found. File may already be changed.")

text = text.replace(old, new, 1)

# Make verification shape consistent with frontend: dict with intent + commands
old_verification = '''        "verification": [
            f"Run kubectl get all -n {namespace} and confirm there are no failing resources."
        ],
'''

new_verification = '''        "verification": {
            "intent": f"Run kubectl get all -n {namespace} and confirm there are no failing resources.",
            "commands": [
                f"kubectl get all -n {namespace}",
                f"kubectl get events -n {namespace} --sort-by=.lastTimestamp",
            ],
        },
'''

text = text.replace(old_verification, new_verification, 1)

path.write_text(text, encoding="utf-8")

print("DONE: src/core/report_safety.py patched.")
print("Fixed:")
print("- agent_reasoning now counts as evidence")
print("- primary_signal now counts as evidence")
print("- incident_groups now count as evidence")
print("- runtime incidents will not be converted to No Active Incident just because evidence_trail is empty")
print("- healthy verification shape normalized for frontend")
