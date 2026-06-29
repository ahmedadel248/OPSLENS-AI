from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


RELATED_THRESHOLD = 70


ALIASES = {
    "namespace": ["namespace", "namespace_name"],
    "node": ["node", "node_name", "selected_node"],
    "pod": ["pod", "pod_name", "podName"],
    "container": ["container", "container_name"],
    "service": ["service", "service_name", "serviceName"],
    "target_service": [
        "target_service",
        "target_service_name",
        "targetService",
        "downstream_service",
        "backend_service",
        "backend_service_name",
        "dependency_service",
    ],
    "deployment": [
        "deployment",
        "deployment_name",
        "workload",
        "workload_name",
        "replica_set",
        "replicaset",
    ],
    "port": ["port", "service_port", "target_port", "targetPort", "container_port"],
}


PRIORITY = {
    "ServiceTargetPortMismatch": 100,
    "ServiceSelectorMismatch": 98,
    "DeploymentSelectorTemplateMismatch": 96,
    "MissingImagePullSecret": 94,
    "ImagePullBackOff": 90,
    "ErrImagePull": 90,
    "InvalidImageName": 90,
    "CrashLoopBackOff": 88,
    "OOMKilled": 88,
    "FailedScheduling": 86,
    "NodeNotReady": 86,
    "PythonTraceback": 84,
    "FatalError": 84,
    "ConnectionRefused": 80,
    "TimeoutError": 78,
    "ImportError": 78,
    "DeploymentNoAvailableReplicas": 78,
    "EmptyServiceEndpoints": 72,
    "EmptyEndpoints": 72,
    "resource_anomaly": 76,
    "cpu_anomaly": 76,
    "memory_anomaly": 76,
    "cpu_memory_anomaly": 78,
    "Failed": 60,
    "LogReadError": 55,
    "GenericErrorLog": 50,
}


SEVERITY_SCORE = {
    "critical": 30,
    "high": 25,
    "warning": 10,
    "low": 5,
    "normal": 0,
}


KNOWN_TYPES = set(PRIORITY) | {
    "KubernetesWarningEvent",
    "Unhealthy",
    "ReadinessProbeFailed",
    "AgentExecutionError",
}


def event_type(event: Dict[str, Any]) -> str:
    return str(
        event.get("anomaly_type")
        or event.get("event_type")
        or event.get("type")
        or event.get("reason")
        or "Unknown"
    )


def value(event: Dict[str, Any], key: str) -> str:
    if not isinstance(event, dict):
        return ""

    affected = event.get("affected_resources") or {}
    if not isinstance(affected, dict):
        affected = {}

    keys = [key] + ALIASES.get(key, [])

    for name in keys:
        item = event.get(name)
        if item not in (None, "", [], {}):
            return str(item)

    for name in keys:
        item = affected.get(name)
        if item not in (None, "", [], {}):
            return str(item)

    return ""


def compact_signal(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "agent": event.get("agent_name") or event.get("source_agent") or event.get("agent"),
        "source_agent": event.get("source_agent") or event.get("agent_name") or event.get("agent"),
        "anomaly_type": event_type(event),
        "severity": event.get("severity", "warning"),
        "namespace": value(event, "namespace"),
        "node_name": value(event, "node"),
        "service_name": value(event, "service"),
        "target_service": value(event, "target_service"),
        "deployment_name": value(event, "deployment"),
        "pod_name": value(event, "pod"),
        "container_name": value(event, "container"),
        "summary": event.get("summary") or event.get("message") or event.get("reason") or "",
        "evidence": event.get("evidence") or event.get("details") or [],
    }


def _pod_belongs_to_deployment(pod: str, deployment: str) -> bool:
    if not pod or not deployment:
        return False

    pod = str(pod)
    deployment = str(deployment)

    return pod == deployment or pod.startswith(deployment + "-")


def relationship_score(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[int, List[str]]:
    a_type, b_type = event_type(a), event_type(b)

    a_ns, b_ns = value(a, "namespace"), value(b, "namespace")
    a_node, b_node = value(a, "node"), value(b, "node")
    a_pod, b_pod = value(a, "pod"), value(b, "pod")
    a_dep, b_dep = value(a, "deployment"), value(b, "deployment")
    a_svc, b_svc = value(a, "service"), value(b, "service")
    a_target, b_target = value(a, "target_service"), value(b, "target_service")

    score = 0
    reasons: List[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    if a_pod and b_pod and a_pod == b_pod:
        add(100, f"Both signals affect the same pod '{a_pod}'.")

    if a_dep and b_dep and a_dep == b_dep:
        add(85, f"Both signals affect the same deployment/workload '{a_dep}'.")

    if a_pod and b_dep and _pod_belongs_to_deployment(a_pod, b_dep):
        add(80, f"Pod '{a_pod}' belongs to deployment/workload '{b_dep}'.")

    if b_pod and a_dep and _pod_belongs_to_deployment(b_pod, a_dep):
        add(80, f"Pod '{b_pod}' belongs to deployment/workload '{a_dep}'.")

    if a_svc and b_svc and a_svc == b_svc:
        add(90, f"Both signals affect the same service '{a_svc}'.")

    if a_svc and b_target and a_svc == b_target:
        add(90, f"The second signal targets the first signal's service '{a_svc}'.")

    if b_svc and a_target and b_svc == a_target:
        add(90, f"The first signal targets the second signal's service '{b_svc}'.")

    service_chain_types = {
        "ServiceSelectorMismatch",
        "ServiceTargetPortMismatch",
        "EmptyServiceEndpoints",
        "EmptyEndpoints",
        "DeploymentNoAvailableReplicas",
        "ConnectionRefused",
        "TimeoutError",
        "Unhealthy",
        "ReadinessProbeFailed",
        "KubernetesWarningEvent",
    }

    if (
        a_type in service_chain_types
        and b_type in service_chain_types
        and (
            (a_svc and b_svc and a_svc == b_svc)
            or (a_svc and b_target and a_svc == b_target)
            or (b_svc and a_target and b_svc == a_target)
        )
    ):
        add(
            95,
            "Signals form a service availability chain: config/endpoints/readiness/client connectivity.",
        )

    runtime_types = {
        "ImagePullBackOff",
        "ErrImagePull",
        "InvalidImageName",
        "CrashLoopBackOff",
        "OOMKilled",
        "PythonTraceback",
        "FatalError",
        "ImportError",
        "GenericErrorLog",
        "Failed",
        "LogReadError",
        "MissingImagePullSecret",
        "DeploymentNoAvailableReplicas",
    }

    if a_type in runtime_types and b_type in runtime_types and (
        (a_dep and b_dep and a_dep == b_dep)
        or (a_pod and b_pod and a_pod == b_pod)
        or (a_pod and b_dep and _pod_belongs_to_deployment(a_pod, b_dep))
        or (b_pod and a_dep and _pod_belongs_to_deployment(b_pod, a_dep))
    ):
        add(85, "Runtime/image/log signals affect the same workload or pod.")

    resource_types = {
        "resource_anomaly",
        "cpu_anomaly",
        "memory_anomaly",
        "cpu_memory_anomaly",
        "HighMemoryUsage",
        "OOMKilled",
        "FailedScheduling",
        "NodeNotReady",
    }

    if a_type in resource_types and b_type in resource_types and a_node and b_node and a_node == b_node:
        add(80, f"Resource-related signals affect the same node '{a_node}'.")

    if (
        {"OOMKilled", "memory_anomaly", "HighMemoryUsage", "cpu_memory_anomaly"} & {a_type, b_type}
        and a_node
        and b_node
        and a_node == b_node
    ):
        add(90, "Memory pressure and OOM/resource symptoms affect the same node.")

    if (
        {"cpu_anomaly", "resource_anomaly", "cpu_memory_anomaly"} & {a_type, b_type}
        and {"ReadinessProbeFailed", "Unhealthy", "KubernetesWarningEvent", "TimeoutError"} & {a_type, b_type}
        and a_node
        and b_node
        and a_node == b_node
    ):
        add(65, "CPU/resource pressure may explain readiness or timeout symptoms on the same node.")

    if a_node and b_node and a_node == b_node:
        add(25, f"Both signals are on the same node '{a_node}', but this alone is weak evidence.")

    if a_ns and b_ns and a_ns == b_ns:
        add(10, f"Both signals are in namespace '{a_ns}', but namespace alone is not enough to merge incidents.")

    if not reasons:
        reasons.append("No structured resource relationship was found.")

    return score, reasons


def confidence_from_score(score: int) -> str:
    if score >= 90:
        return "high"
    if score >= RELATED_THRESHOLD:
        return "medium"
    if score >= 45:
        return "low"
    return "none"


def is_unknown_signal(event: Dict[str, Any]) -> bool:
    anomaly = event_type(event)

    if anomaly in KNOWN_TYPES:
        return False

    lower = anomaly.lower()
    return (
        anomaly in {"Unknown", "GenericErrorLog", "AgentExecutionError"}
        or "unknown" in lower
        or "generic" in lower
    )


def possible_causes(event: Dict[str, Any]) -> List[str]:
    anomaly = event_type(event)
    agent = str(event.get("agent_name") or event.get("source_agent") or event.get("agent") or "").lower()

    if "log" in agent or anomaly in {"GenericErrorLog", "PythonTraceback", "FatalError", "ImportError", "LogReadError"}:
        return [
            "Application runtime bug or unhandled exception.",
            "Missing or invalid environment variable.",
            "Dependency service is unavailable or refusing connections.",
            "Incorrect startup command, entrypoint, or application configuration.",
        ]

    if "kubernetes" in agent or anomaly in {"KubernetesWarningEvent", "Unhealthy", "Failed"}:
        return [
            "Readiness or liveness probe configuration issue.",
            "Image pull or container startup problem.",
            "Scheduling or resource constraint.",
            "Workload configuration mismatch.",
        ]

    if "config" in agent:
        return [
            "Service selector does not match pod labels.",
            "Service targetPort does not match container port.",
            "Deployment or service relationship is misconfigured.",
            "Required Kubernetes or Linux configuration is missing.",
        ]

    if "resource" in agent or anomaly in {"resource_anomaly", "cpu_anomaly", "memory_anomaly"}:
        return [
            "CPU pressure on the selected node.",
            "Memory pressure or insufficient resource limits.",
            "Noisy neighbor workload affecting the node.",
            "Resource requests/limits are not aligned with actual workload behavior.",
        ]

    return [
        "Application-level failure.",
        "Kubernetes object lifecycle issue.",
        "Configuration mismatch.",
        "Resource pressure or dependency failure.",
    ]


def verification_needed(event: Dict[str, Any]) -> List[str]:
    namespace = value(event, "namespace") or "<namespace>"
    pod = value(event, "pod")
    deployment = value(event, "deployment")
    service = value(event, "service") or value(event, "target_service")

    checks = [
        f"kubectl get events -n {namespace} --sort-by=.lastTimestamp",
        f"kubectl get pods -n {namespace} -o wide",
    ]

    if pod:
        checks.append(f"kubectl logs -n {namespace} {pod} --tail=120")

    if deployment:
        checks.append(f"kubectl describe deployment -n {namespace} {deployment}")

    if service:
        checks.append(f"kubectl get svc,endpoints -n {namespace} {service} -o wide")

    checks.append("Verify recent configuration changes and dependent services.")
    return checks


def event_identity(event: Dict[str, Any]) -> tuple:
    return (
        event.get("agent_name") or event.get("agent"),
        event_type(event),
        value(event, "namespace"),
        value(event, "node"),
        value(event, "pod"),
        value(event, "service"),
        value(event, "deployment"),
        value(event, "container"),
        event.get("summary"),
    )


def related_supporting_events(
    events: List[Dict[str, Any]],
    primary_event: Optional[Dict[str, Any]],
    limit: int = 8,
) -> List[Dict[str, Any]]:
    if not primary_event:
        return []

    primary_id = event_identity(primary_event)
    ranked = []

    for event in events or []:
        if event_identity(event) == primary_id:
            continue

        score, reasons = relationship_score(primary_event, event)

        if score >= RELATED_THRESHOLD:
            ranked.append((score, event, reasons))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [event for _, event, _ in ranked[:limit]]


def _event_priority(event: Dict[str, Any]) -> int:
    return PRIORITY.get(event_type(event), 45) + SEVERITY_SCORE.get(str(event.get("severity", "warning")).lower(), 5)


def _select_cluster_root(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return sorted(events, key=_event_priority, reverse=True)[0]


def _cluster_events(events: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    clusters: List[List[Dict[str, Any]]] = []

    for event in events:
        placed = False

        for cluster in clusters:
            if any(relationship_score(event, existing)[0] >= RELATED_THRESHOLD for existing in cluster):
                cluster.append(event)
                placed = True
                break

        if not placed:
            clusters.append([event])

    return clusters


def _related_signals_inside_cluster(cluster: List[Dict[str, Any]], root: Dict[str, Any]) -> List[Dict[str, Any]]:
    root_id = event_identity(root)
    rows = []

    for event in cluster:
        if event_identity(event) == root_id:
            continue

        score, reasons = relationship_score(root, event)

        rows.append(
            {
                "signal": compact_signal(event),
                "relationship_score": score,
                "relationship_confidence": confidence_from_score(score),
                "relationship_reason": reasons,
            }
        )

    rows.sort(key=lambda item: item.get("relationship_score", 0), reverse=True)
    return rows


def _resource(signal: Dict[str, Any]) -> str:
    return (
        signal.get("service_name")
        or signal.get("target_service")
        or signal.get("deployment_name")
        or signal.get("pod_name")
        or signal.get("node_name")
        or signal.get("namespace")
        or "scope resource"
    )


def _finding_row_from_group(item: Dict[str, Any], unclassified: bool = False) -> Dict[str, str]:
    signal = item.get("signal") or {}
    resource = _resource(signal)
    related = item.get("related_signals") or []
    related_types = [
        str((entry.get("signal") or {}).get("anomaly_type"))
        for entry in related
        if (entry.get("signal") or {}).get("anomaly_type")
    ]

    if unclassified:
        causes = "; ".join(item.get("possible_causes") or [])
        verify = "; ".join(item.get("verification_needed") or [])
        return {
            "resource": str(resource),
            "finding": f"Unclassified abnormal signal: {signal.get('anomaly_type', 'Unknown')}. Possible causes: {causes}",
            "impact": f"This is a hypothesis only and must be verified. Suggested checks: {verify}",
            "priority": "Investigate",
        }

    suffix = f" Related signals: {', '.join(related_types)}." if related_types else ""

    return {
        "resource": str(resource),
        "finding": f"{signal.get('anomaly_type', 'Finding')} detected as a separate incident group.{suffix}",
        "impact": item.get("reason", "No proven causal relationship to the primary incident."),
        "priority": "Follow-up",
    }


def build_incident_grouping(
    all_events: List[Dict[str, Any]],
    primary_event: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    policy = {
        "owner": "SupervisorAgent",
        "approach": "evidence_based_relationship_scoring_with_secondary_grouping",
        "related_threshold": RELATED_THRESHOLD,
        "same_namespace_rule": "same namespace alone is not enough to merge incidents",
        "secondary_grouping_rule": "signals unrelated to the primary incident are grouped together when they affect the same pod, deployment, service, target service, or node-level resource chain",
        "unknown_rule": "unknown findings are kept with possible causes and verification steps, not confirmed root causes",
    }

    if not primary_event:
        return {
            "primary_incident_group": None,
            "incident_groups": [],
            "separate_findings": [],
            "unclassified_findings": [],
            "additional_findings": [],
            "incident_grouping_policy": policy,
        }

    primary_id = event_identity(primary_event)

    primary_related = []
    non_primary_unrelated = []

    for event in all_events or []:
        if event_identity(event) == primary_id:
            continue

        score, reasons = relationship_score(primary_event, event)

        if score >= RELATED_THRESHOLD:
            primary_related.append(
                {
                    "signal": compact_signal(event),
                    "relationship_score": score,
                    "relationship_confidence": confidence_from_score(score),
                    "relationship_reason": reasons,
                }
            )
        else:
            non_primary_unrelated.append(event)

    primary_group = {
        "group_id": "primary",
        "group_type": "primary_incident",
        "root_signal": compact_signal(primary_event),
        "related_signals": sorted(primary_related, key=lambda item: item.get("relationship_score", 0), reverse=True),
        "relationship_summary": (
            "Signals in this group are treated as one incident chain because they share strong structured evidence "
            "such as same service, target service, deployment, pod, or node-level resource relationship."
        ),
        "grouping_rule": f"relationship_score >= {RELATED_THRESHOLD}",
    }

    if is_unknown_signal(primary_event):
        primary_group["group_type"] = "primary_unclassified_incident"
        primary_group["possible_causes"] = possible_causes(primary_event)
        primary_group["verification_needed"] = verification_needed(primary_event)
        primary_group["relationship_summary"] = (
            "The selected primary signal is abnormal but not fully classified. Possible causes are hypotheses only."
        )

    incident_groups = [primary_group]
    separate_findings = []
    unclassified_findings = []

    secondary_clusters = _cluster_events(non_primary_unrelated)

    separate_index = 1
    unclassified_index = 1

    for cluster in secondary_clusters:
        root = _select_cluster_root(cluster)
        root_signal = compact_signal(root)
        related_signals = _related_signals_inside_cluster(cluster, root)

        has_known_signal = any(not is_unknown_signal(item) for item in cluster)
        cluster_unknown = not has_known_signal

        item = {
            "signal": root_signal,
            "related_signals": related_signals,
            "group_size": len(cluster),
            "relationship_score": 0,
            "relationship_confidence": "none",
            "relationship_reason": [
                "This incident group is separate from the primary incident.",
                "Its signals are grouped together because they affect the same workload/resource chain.",
                "Same namespace alone was not used as the reason for grouping.",
            ],
            "reason": (
                "This incident group was not merged into the primary incident because no strong structured "
                "relationship to the primary service/workload was found."
            ),
        }

        if cluster_unknown:
            item["classification"] = "unclassified_finding"
            item["possible_causes"] = possible_causes(root)
            item["verification_needed"] = verification_needed(root)
            unclassified_findings.append(item)

            incident_groups.append(
                {
                    "group_id": f"unclassified-{unclassified_index}",
                    "group_type": "unclassified_finding",
                    "root_signal": root_signal,
                    "related_signals": related_signals,
                    "relationship_summary": (
                        "OpsLens detected this abnormal signal group, but there is not enough structured evidence "
                        "to connect it to the primary incident. Possible causes are hypotheses only."
                    ),
                    "possible_causes": item["possible_causes"],
                    "verification_needed": item["verification_needed"],
                    "grouping_rule": "unknown signal group or weak relationship to primary",
                }
            )
            unclassified_index += 1

        else:
            item["classification"] = "separate_finding"
            separate_findings.append(item)

            incident_groups.append(
                {
                    "group_id": f"separate-{separate_index}",
                    "group_type": "separate_finding",
                    "root_signal": root_signal,
                    "related_signals": related_signals,
                    "relationship_summary": item["reason"],
                    "grouping_rule": (
                        f"relationship_score_to_primary < {RELATED_THRESHOLD}; "
                        f"secondary cluster grouped by internal relationship_score >= {RELATED_THRESHOLD}"
                    ),
                }
            )
            separate_index += 1

    additional_findings = [_finding_row_from_group(item, unclassified=False) for item in separate_findings]
    additional_findings.extend(_finding_row_from_group(item, unclassified=True) for item in unclassified_findings)

    return {
        "primary_incident_group": primary_group,
        "incident_groups": incident_groups,
        "separate_findings": separate_findings,
        "unclassified_findings": unclassified_findings,
        "additional_findings": additional_findings,
        "incident_grouping_policy": policy,
    }
