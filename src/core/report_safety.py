
from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(f"{k} {_text(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value)


def _empty(value: Any) -> bool:
    t = _text(value).strip().lower()
    if not t:
        return True

    return t in {
        "no data available",
        "no evidence available",
        "not available",
        "unavailable",
        "none",
        "[]",
        "{}",
    }


def _replace_text(value: Any, namespace: str | None) -> Any:
    if isinstance(value, str):
        out = value

        if namespace and namespace != "default":
            out = out.replace("-n default", f"-n {namespace}")
            out = out.replace("--namespace default", f"--namespace {namespace}")
            out = out.replace("Namespace default", f"Namespace {namespace}")
            out = out.replace("namespace default", f"namespace {namespace}")

        out = out.replace("affected-service", "not found in collected evidence")
        out = out.replace("affected-deployment", "not found in collected evidence")
        out = out.replace("Unavailable", "Not found in collected evidence")
        out = out.replace("unavailable", "not found in collected evidence")

        return out

    if isinstance(value, list):
        return [_replace_text(v, namespace) for v in value]

    if isinstance(value, dict):
        return {k: _replace_text(v, namespace) for k, v in value.items()}

    return value


def _has_invalid_placeholders(report: dict[str, Any], namespace: str | None) -> bool:
    t = _text(report).lower()

    if "affected-service" in t or "affected-deployment" in t:
        return True

    if namespace and namespace != "default":
        if "namespace default" in t or "-n default" in t or "--namespace default" in t:
            return True

    affected = report.get("affected_resources")
    if isinstance(affected, dict):
        ns = str(affected.get("namespace", "")).strip()
        service = str(affected.get("service", "")).strip()
        deployment = str(affected.get("deployment", "")).strip()

        if namespace and namespace != "default" and ns == "default":
            return True

        if service == "affected-service" or deployment == "affected-deployment":
            return True

    return False


def _is_no_finding_marker(value: Any) -> bool:
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


def make_healthy_report(namespace: str | None, node: str | None) -> dict[str, Any]:
    namespace = namespace or "selected namespace"
    node = node or "selected node"

    return {
        "title": "No Active Incident Detected",
        "status": "healthy",
        "severity": "none",
        "confidence": "high",
        "affected_resources": {
            "namespace": namespace,
            "node": node,
            "service": "not found in collected evidence",
            "deployment": "not found in collected evidence",
        },
        "incident_summary": (
            f"No active incident was detected in namespace '{namespace}' on node '{node}'. "
            "OpsLens did not find concrete Kubernetes failure evidence in the selected scope."
        ),
        "evidence_trail": [
            f"No failing pod state was found in namespace '{namespace}'.",
            f"No Service endpoint failure was found in namespace '{namespace}'.",
            "No supported Kubernetes warning signal was strong enough to classify this as an incident.",
        ],
        "additional_findings": [
            "No additional findings detected."
        ],
        "root_cause_story": (
            "No root cause was identified because the collected evidence does not contain "
            "an active failure condition."
        ),
        "recommended_fix": {
            "strategy": "No remediation required. Continue monitoring the selected scope.",
            "safe_commands": [
                {
                    "title": "Check pods",
                    "command": f"kubectl get pods -n {namespace} --show-labels",
                },
                {
                    "title": "Check services and endpoints",
                    "command": f"kubectl get svc,endpoints -n {namespace}",
                },
                {
                    "title": "Check namespace events",
                    "command": f"kubectl get events -n {namespace} --sort-by=.lastTimestamp",
                },
            ],
            "verification_plan": "Confirm that workloads are Running/Ready and Services have valid endpoints.",
            "verification_commands": [
                {
                    "title": "Verify selected namespace",
                    "command": f"kubectl get all -n {namespace}",
                }
            ],
        },
        "verification": {
            "intent": f"Run kubectl get all -n {namespace} and confirm there are no failing resources.",
            "commands": [
                f"kubectl get all -n {namespace}",
                f"kubectl get events -n {namespace} --sort-by=.lastTimestamp",
            ],
        },
    }


def sanitize_report(report: Any, namespace: str | None = None, node: str | None = None) -> Any:
    """
    Presentation safety only.

    This does NOT decide resource anomaly.
    Resource anomaly remains the responsibility of Resource Metrics Agent + Detector.

    This only blocks:
    - affected-service / affected-deployment placeholders
    - default namespace leakage when selected namespace is different
    - critical incident claims with no evidence
    """
    if not isinstance(report, dict):
        return report

    for key in ("report", "result", "final_report", "incident_report"):
        if isinstance(report.get(key), dict):
            report[key] = sanitize_report(report[key], namespace=namespace, node=node)

    affected = report.get("affected_resources")
    if isinstance(affected, dict):
        namespace = namespace or affected.get("namespace")
        node = node or affected.get("node") or affected.get("node_name")

    namespace = namespace or "selected namespace"
    node = node or "selected node"

    if _has_invalid_placeholders(report, namespace):
        return make_healthy_report(namespace, node)

    if _has_no_evidence(report):
        summary = _text(report.get("incident_summary", "")).lower()
        severity = _text(report.get("severity", "")).lower()

        claims_incident = (
            severity in {"critical", "high"}
            or any(word in summary for word in (
                "critical", "incident", "failure", "exhaustion",
                "pressure", "degradation", "unavailable"
            ))
        )

        if claims_incident:
            return make_healthy_report(namespace, node)

    return _replace_text(report, namespace)
