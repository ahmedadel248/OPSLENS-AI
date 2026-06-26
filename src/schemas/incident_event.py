from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_incident_event(
    source_agent: str,
    event_type: str,
    severity: str,
    summary: str,
    evidence: Dict[str, Any],
    timestamp: Optional[str] = None,
    node_name: Optional[str] = None,
    namespace: Optional[str] = None,
    pod_name: Optional[str] = None,
    container_name: Optional[str] = None,
    recommendations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "source_agent": source_agent,
        "event_type": event_type,
        "severity": severity,
        "timestamp": timestamp or now_utc(),
        "node_name": node_name,
        "namespace": namespace,
        "pod_name": pod_name,
        "container_name": container_name,
        "summary": summary,
        "evidence": evidence,
        "recommendations": recommendations or [],
    }



