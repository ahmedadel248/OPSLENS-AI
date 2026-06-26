import json
import re
from typing import Any, Dict, List, Optional


def build_root_cause_facts(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build structured root-cause facts from the Supervisor report.

    These facts are the trusted input for the LLM and the command safety layer.
    """

    affected = report.get("affected_resources") or {}
    primary = report.get("primary_signal") or {}

    facts: Dict[str, Any] = {
        "root_cause_type": primary.get("anomaly_type") or report.get("primary_anomaly_type"),
        "namespace": affected.get("namespace") or _find_namespace(report),
        "service_name": affected.get("service_name") or affected.get("service") or _find_service_name(report),
        "deployment_name": affected.get("deployment_name") or affected.get("deployment") or _find_deployment_name(report),
        "node_name": affected.get("node_name") or affected.get("node") or _find_node_name(report),
    }

    evidence_text = "\n".join(str(item) for item in report.get("evidence", []) or [])
    full_text = json.dumps(report, default=str)

    service_port = _search_int(r"service_port:\s*(\d+)", evidence_text)
    target_port = _search_int(r"target_port:\s*(\d+)", evidence_text)
    readiness_probe_port = _search_int(r"readinessProbe.*?port[:=]\s*(\d+)", full_text)

    container_ports = _search_ports(r"available_container_ports:\s*\[([0-9,\s]+)\]", evidence_text)

    if service_port is not None:
        facts["service_port"] = service_port

    if target_port is not None:
        facts["target_port"] = target_port

    if container_ports:
        facts["container_ports"] = container_ports
        facts["container_port"] = container_ports[0]

    if readiness_probe_port is not None:
        facts["readiness_probe_port"] = readiness_probe_port
    elif target_port is not None:
        facts["readiness_probe_port"] = target_port

    return {key: value for key, value in facts.items() if value not in (None, "", [])}


def _search_int(pattern: str, text: str) -> Optional[int]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None

    try:
        return int(match.group(1))
    except Exception:
        return None


def _search_ports(pattern: str, text: str) -> List[int]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return []

    ports = []

    for value in match.group(1).split(","):
        value = value.strip()
        if value.isdigit():
            ports.append(int(value))

    return ports


def _find_namespace(report: Dict[str, Any]) -> str:
    text = json.dumps(report, default=str)
    match = re.search(r'"namespace"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match else "default"


def _find_service_name(report: Dict[str, Any]) -> str:
    text = json.dumps(report, default=str)

    patterns = [
        r'"service_name"\s*:\s*"([^"]+)"',
        r'"service"\s*:\s*"([^"]+)"',
        r"service\s+([a-zA-Z0-9.-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return "affected-service"


def _find_deployment_name(report: Dict[str, Any]) -> str:
    text = json.dumps(report, default=str)

    patterns = [
        r'"deployment_name"\s*:\s*"([^"]+)"',
        r'"deployment"\s*:\s*"([^"]+)"',
        r"Deployment\s+([a-zA-Z0-9.-]+)\s+has no available replicas",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return "affected-deployment"


def _find_node_name(report: Dict[str, Any]) -> str:
    text = json.dumps(report, default=str)

    patterns = [
        r'"node_name"\s*:\s*"([^"]+)"',
        r'"node"\s*:\s*"([^"]+)"',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return ""
