import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.incident_grouping import build_incident_grouping, related_supporting_events


class SupervisorAgent:
    """
    Clean Supervisor Agent.

    It runs specialized agents, collects their signals, selects the strongest
    root-cause signal, and produces one clean final incident report.

    Raw agent outputs are not included in the final report unless debug=True.
    """

    def __init__(
        self,
        agents: Dict[str, Any],
        reports_dir: str = "data/incident_reports",
        persist: bool = True,
        debug: bool = False,
    ):
        self.agents = agents
        self.reports_dir = Path(reports_dir)
        self.persist = persist
        self.debug = debug

        if self.persist:
            self.reports_dir.mkdir(parents=True, exist_ok=True)

    def investigate(
        self,
        scenario_name: str = "manual_investigation",
        trigger_event: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        agent_results = {}
        all_events = []

        for agent_name, agent in self.agents.items():
            try:
                events = agent.run()

                agent_results[agent_name] = {
                    "status": "completed",
                    "event_count": len(events),
                    "events": events,
                }

                for event in events:
                    normalized_event = {
                        **event,
                        "agent_name": agent_name,
                    }
                    all_events.append(normalized_event)

            except Exception as exc:
                error_event = {
                    "agent_name": agent_name,
                    "agent": agent_name,
                    "source_agent": agent_name,
                    "event_type": "agent_execution_error",
                    "anomaly_type": "AgentExecutionError",
                    "severity": "warning",
                    "timestamp": self._now_utc(),
                    "summary": f"{agent_name} failed during investigation.",
                    "evidence": [f"{type(exc).__name__}: {str(exc)}"],
                    "recommendations": ["Check this agent configuration and runtime dependencies."],
                }

                agent_results[agent_name] = {
                    "status": "failed",
                    "event_count": 1,
                    "events": [error_event],
                }

                all_events.append(error_event)

        primary_event = self._select_primary_event(all_events)
        supporting_events = self._select_supporting_events(all_events, primary_event)

        report = self._build_clean_report(
            scenario_name=scenario_name,
            trigger_event=trigger_event,
            primary_event=primary_event,
            supporting_events=supporting_events,
            agent_results=agent_results,
            all_events=all_events,
        )

        if self.persist:
            self._persist_report(report)

        return report

    def _build_clean_report(
        self,
        scenario_name: str,
        trigger_event: Optional[Dict[str, Any]],
        primary_event: Optional[Dict[str, Any]],
        supporting_events: List[Dict[str, Any]],
        agent_results: Dict[str, Any],
        all_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not primary_event:
            report = {
                "report_type": "clean_incident_report",
                "scenario_name": scenario_name,
                "generated_at": self._now_utc(),
                "incident_title": "No active incident detected",
                "severity": "normal",
                "confidence": "low",
                "affected_resources": {},
                "summary": "No active incident signals were detected by the available agents.",
                "root_cause_hypothesis": "No clear root cause is available because no agent reported an active incident.",
                "evidence": [],
                "recommended_fix": [
                    "No immediate fix is required.",
                    "Continue monitoring metrics, Kubernetes events, logs, and configuration checks.",
                ],
                "agent_contributions": self._agent_contributions(agent_results),
                "trigger_event": trigger_event,
            }

            if self.debug:
                report["debug"] = {
                    "all_events": all_events,
                    "agent_results": agent_results,
                }

            return report

        grouping = build_incident_grouping(
            all_events=all_events,
            primary_event=primary_event,
        )

        report = {
            "report_type": "clean_incident_report",
            "scenario_name": scenario_name,
            "generated_at": self._now_utc(),

            "incident_title": self._incident_title(primary_event),
            "severity": primary_event.get("severity", "warning"),
            "confidence": self._confidence(primary_event, supporting_events),

            "affected_resources": self._affected_resources(primary_event),

            "summary": self._summary(primary_event, supporting_events),
            "root_cause_hypothesis": self._root_cause(primary_event, supporting_events),

            "evidence": self._evidence(primary_event, supporting_events),
            "recommended_fix": self._recommended_fix(primary_event, supporting_events),

            "agent_contributions": self._agent_contributions(agent_results),

            "primary_signal": self._compact_signal(primary_event),
            "supporting_signals": [
                self._compact_signal(event)
                for event in supporting_events
            ],

            "primary_incident_group": grouping.get("primary_incident_group"),
            "incident_groups": grouping.get("incident_groups", []),
            "separate_findings": grouping.get("separate_findings", []),
            "unclassified_findings": grouping.get("unclassified_findings", []),
            "additional_findings": grouping.get("additional_findings", []),
            "incident_grouping_policy": grouping.get("incident_grouping_policy", {}),

            "trigger_event": trigger_event,
        }

        if self.debug:
            report["debug"] = {
                "all_events": all_events,
                "agent_results": agent_results,
            }

        return report

    def _select_primary_event(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not events:
            return None

        priority = {
            # Direct configuration causes
            "ServiceTargetPortMismatch": 100,
            "ServiceSelectorMismatch": 98,
            "DeploymentSelectorTemplateMismatch": 96,
            "MissingImagePullSecret": 94,

            # Node/config causes
            "KubeletDown": 96,
            "ContainerRuntimeIssue": 94,
            "HighDiskUsage": 88,
            "FirewallActive": 82,
            "HighMemoryUsage": 80,

            # Kubernetes object/runtime issues
            "ImagePullBackOff": 90,
            "ErrImagePull": 90,
            "InvalidImageName": 90,
            "CrashLoopBackOff": 88,
            "OOMKilled": 88,
            "FailedScheduling": 86,
            "NodeNotReady": 86,

            # Supporting config symptoms
            "DeploymentNoAvailableReplicas": 78,
            "EmptyServiceEndpoints": 72,

            # Logs
            "PythonTraceback": 84,
            "FatalError": 84,
            "ConnectionRefused": 80,
            "TimeoutError": 78,
            "ImportError": 78,
            "GenericErrorLog": 65,

            # Metrics
            "resource_anomaly": 76,
            "cpu_anomaly": 76,
            "memory_anomaly": 76,
            "cpu_memory_anomaly": 78,
        }

        severity_score = {
            "critical": 30,
            "high": 25,
            "warning": 10,
            "low": 5,
            "normal": 0,
        }

        def score(event: Dict[str, Any]) -> int:
            anomaly_type = event.get("anomaly_type")
            severity = event.get("severity", "warning")
            return priority.get(anomaly_type, 50) + severity_score.get(severity, 5)

        return sorted(events, key=score, reverse=True)[0]

    def _select_supporting_events(
        self,
        events: List[Dict[str, Any]],
        primary_event: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        # Evidence-based supporting selection.
        # Same namespace alone is not enough to classify a signal as supporting.
        return related_supporting_events(
            events=events,
            primary_event=primary_event,
            limit=8,
        )


    def _event_identity(self, event: Dict[str, Any]) -> tuple:
        return (
            event.get("agent_name"),
            event.get("anomaly_type"),
            event.get("namespace"),
            event.get("node_name"),
            event.get("pod_name"),
            event.get("service_name"),
            event.get("deployment_name"),
            event.get("container_name"),
            event.get("summary"),
        )

    def _incident_title(self, primary_event: Dict[str, Any]) -> str:
        anomaly_type = primary_event.get("anomaly_type", "Incident")
        service = primary_event.get("service_name")
        deployment = primary_event.get("deployment_name")
        pod = primary_event.get("pod_name")
        node = primary_event.get("node_name")

        if service:
            return f"{anomaly_type} detected on service {service}"

        if deployment:
            return f"{anomaly_type} detected on deployment {deployment}"

        if pod:
            return f"{anomaly_type} detected on pod {pod}"

        if node:
            return f"{anomaly_type} detected on node {node}"

        return f"{anomaly_type} detected"

    def _affected_resources(self, event: Dict[str, Any]) -> Dict[str, Any]:
        resources = {}

        for key in [
            "namespace",
            "node_name",
            "pod_name",
            "container_name",
            "service_name",
            "deployment_name",
        ]:
            value = event.get(key)
            if value:
                resources[key] = value

        return resources

    def _summary(
        self,
        primary_event: Dict[str, Any],
        supporting_events: List[Dict[str, Any]],
    ) -> str:
        base = primary_event.get("summary", "Incident signal detected.")

        if supporting_events:
            return f"{base} The supervisor found {len(supporting_events)} related supporting signal(s)."

        return base

    def _root_cause(
        self,
        primary_event: Dict[str, Any],
        supporting_events: List[Dict[str, Any]],
    ) -> str:
        anomaly_type = primary_event.get("anomaly_type")

        root_causes = {
            "ServiceTargetPortMismatch": (
                "The most likely root cause is a Kubernetes Service configuration error. "
                "The Service targetPort does not match the containerPort exposed by the matching pod."
            ),
            "ServiceSelectorMismatch": (
                "The most likely root cause is a Kubernetes Service selector mismatch. "
                "The Service selector does not match the labels of any running pod."
            ),
            "EmptyServiceEndpoints": (
                "The Service has no ready endpoints. This may be caused by pod readiness failures, "
                "selector mismatch, or a service/deployment configuration problem."
            ),
            "DeploymentNoAvailableReplicas": (
                "The Deployment has no available replicas. This may be caused by image pull errors, "
                "readiness failures, scheduling problems, or container startup issues."
            ),
            "MissingImagePullSecret": (
                "The Deployment appears to use a private registry image without a configured imagePullSecret."
            ),
            "ErrImagePull": (
                "The most likely root cause is an image pull failure caused by an invalid image, missing image, "
                "registry access problem, or missing imagePullSecret."
            ),
            "ImagePullBackOff": (
                "The most likely root cause is an image pull failure caused by registry access, image name/tag, "
                "or imagePullSecret configuration."
            ),
            "CrashLoopBackOff": (
                "The container is repeatedly crashing after startup. The likely cause is an application error, "
                "bad environment/configuration, missing dependency, or failing startup command."
            ),
            "OOMKilled": (
                "The container was killed due to memory pressure or insufficient memory limits."
            ),
            "PythonTraceback": (
                "Application logs contain a Python traceback, indicating an application-level runtime error."
            ),
            "ConnectionRefused": (
                "Application logs show a refused connection. The likely cause is a missing dependency, wrong service port, "
                "wrong targetPort, no ready endpoint, or network/configuration issue."
            ),
            "KubeletDown": (
                "The kubelet service is not active on the node, which can make the node unhealthy."
            ),
            "ContainerRuntimeIssue": (
                "The container runtime is unhealthy or inactive, which can prevent pods from running correctly."
            ),
            "HighDiskUsage": (
                "The node disk usage is high and may affect image pulls, container runtime, kubelet, or pod scheduling."
            ),
            "FirewallActive": (
                "The node firewall is active and may block required Kubernetes or application traffic."
            ),
        }

        return root_causes.get(
            anomaly_type,
            primary_event.get("summary", "A primary incident signal was detected.")
        )

    def _evidence(
        self,
        primary_event: Dict[str, Any],
        supporting_events: List[Dict[str, Any]],
    ) -> List[str]:
        evidence = []

        evidence.append(
            f"Primary signal from {primary_event.get('agent_name') or primary_event.get('agent')}: "
            f"{primary_event.get('anomaly_type')} ({primary_event.get('severity')})."
        )

        for item in primary_event.get("evidence", []) or []:
            evidence.append(str(item))

        metrics = primary_event.get("metrics") or primary_event.get("metrics_context") or {}
        if metrics:
            metrics_status = metrics.get("status")
            resource_anomaly = metrics.get("resource_anomaly")
            evidence.append(
                f"Metrics context: status={metrics_status}, resource_anomaly={resource_anomaly}."
            )

        for event in supporting_events:
            evidence.append(
                f"Supporting signal from {event.get('agent_name') or event.get('agent')}: "
                f"{event.get('anomaly_type')} - {event.get('summary')}"
            )

        return evidence[:12]

    def _recommended_fix(
        self,
        primary_event: Dict[str, Any],
        supporting_events: List[Dict[str, Any]],
    ) -> List[str]:
        fixes = []

        direct_fixes = {
            "ServiceTargetPortMismatch": [
                "Update the backend Service targetPort to match the backend containerPort 80.",
                "Update the backend readinessProbe port from 9999 to 80, or align it with the real application health port.",
                "Re-apply the manifests and verify the backend pod becomes Ready.",
                "Verify the affected Service endpoints are created.",
                "Verify the frontend/client logs no longer show ConnectionRefused.",
            ],
            "ServiceSelectorMismatch": [
                "Update the Service selector to match the pod labels, or update the pod template labels.",
                "Run kubectl get pods --show-labels and compare with the Service selector.",
            ],
            "MissingImagePullSecret": [
                "Create or reference the correct imagePullSecret in the Deployment.",
                "Verify registry credentials and image name/tag.",
            ],
            "ErrImagePull": [
                "Verify image name and tag.",
                "Check registry access and imagePullSecrets.",
            ],
            "ImagePullBackOff": [
                "Verify image name and tag.",
                "Check registry access and imagePullSecrets.",
            ],
            "ConnectionRefused": [
                "Verify the target service exists and has ready endpoints.",
                "Check Service port and targetPort configuration.",
                "Check application dependency URL/host/port configuration.",
            ],
        }

        for item in direct_fixes.get(primary_event.get("anomaly_type"), []):
            fixes.append(item)

        for item in primary_event.get("recommendations", []) or []:
            if item not in fixes:
                fixes.append(item)

        for event in supporting_events:
            # If the primary cause is a direct configuration issue, keep resource metrics
            # recommendations as evidence/context, not as the main fix.
            if (
                primary_event.get("anomaly_type") in {"ServiceTargetPortMismatch", "ServiceSelectorMismatch", "DeploymentSelectorTemplateMismatch"}
                and event.get("agent_name") == "resource_metrics"
            ):
                continue

            for item in event.get("recommendations", []) or []:
                if item not in fixes:
                    fixes.append(item)

        if not fixes:
            fixes.append("Inspect the primary signal evidence and validate the related Kubernetes resource configuration.")

        return fixes[:8]

    def _confidence(
        self,
        primary_event: Dict[str, Any],
        supporting_events: List[Dict[str, Any]],
    ) -> str:
        strong_direct_causes = {
            "ServiceTargetPortMismatch",
            "ServiceSelectorMismatch",
            "DeploymentSelectorTemplateMismatch",
            "MissingImagePullSecret",
        }

        if primary_event.get("anomaly_type") in strong_direct_causes:
            return "high"

        if primary_event.get("severity") in {"critical", "high"} and supporting_events:
            return "high"

        if primary_event.get("severity") in {"critical", "high"}:
            return "medium"

        return "low"

    def _agent_contributions(self, agent_results: Dict[str, Any]) -> Dict[str, Any]:
        contributions = {}

        for agent_name, result in agent_results.items():
            events = result.get("events", []) or []

            if result.get("status") != "completed":
                contributions[agent_name] = {
                    "status": result.get("status"),
                    "finding": "Agent failed during investigation.",
                }
                continue

            if not events:
                contributions[agent_name] = {
                    "status": "completed",
                    "finding": "No active signal detected.",
                }
                continue

            findings = []

            for event in events[:3]:
                findings.append(
                    {
                        "anomaly_type": event.get("anomaly_type"),
                        "severity": event.get("severity"),
                        "summary": event.get("summary"),
                    }
                )

            contributions[agent_name] = {
                "status": "completed",
                "event_count": len(events),
                "findings": findings,
            }

        return contributions

    def _compact_signal(self, event: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "agent": event.get("agent_name") or event.get("agent"),
            "event_type": event.get("event_type"),
            "anomaly_type": event.get("anomaly_type"),
            "severity": event.get("severity"),
            "namespace": event.get("namespace"),
            "node_name": event.get("node_name"),
            "pod_name": event.get("pod_name"),
            "container_name": event.get("container_name"),
            "service_name": event.get("service_name"),
            "deployment_name": event.get("deployment_name"),
            "summary": event.get("summary"),
        }

    def _persist_report(self, report: Dict[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        scenario_name = report.get("scenario_name", "incident").replace(" ", "_")

        json_path = self.reports_dir / f"{timestamp}_{scenario_name}.json"
        md_path = self.reports_dir / f"{timestamp}_{scenario_name}.md"

        report["json_report_path"] = str(json_path)
        report["markdown_report_path"] = str(md_path)

        with json_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=self._json_default)

        with md_path.open("w", encoding="utf-8") as f:
            f.write(self._to_markdown(report))

    def _to_markdown(self, report: Dict[str, Any]) -> str:
        lines = []

        lines.append(f"# {report.get('incident_title')}")
        lines.append("")
        lines.append(f"**Scenario:** {report.get('scenario_name')}")
        lines.append(f"**Severity:** {report.get('severity')}")
        lines.append(f"**Confidence:** {report.get('confidence')}")
        lines.append("")

        lines.append("## Affected Resources")
        resources = report.get("affected_resources") or {}

        if resources:
            for key, value in resources.items():
                lines.append(f"- **{key}:** {value}")
        else:
            lines.append("- None")

        lines.append("")
        lines.append("## Summary")
        lines.append(report.get("summary", ""))

        lines.append("")
        lines.append("## Root Cause Hypothesis")
        lines.append(report.get("root_cause_hypothesis", ""))

        lines.append("")
        lines.append("## Evidence")
        for item in report.get("evidence", []):
            lines.append(f"- {item}")

        lines.append("")
        lines.append("## Recommended Fix")
        for item in report.get("recommended_fix", []):
            lines.append(f"- {item}")

        lines.append("")
        lines.append("## Agent Contributions")
        for agent_name, contribution in report.get("agent_contributions", {}).items():
            lines.append(f"### {agent_name}")
            if "finding" in contribution:
                lines.append(f"- {contribution['finding']}")
            else:
                for finding in contribution.get("findings", []):
                    lines.append(
                        f"- {finding.get('anomaly_type')} ({finding.get('severity')}): {finding.get('summary')}"
                    )

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json_default(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()

        if isinstance(value, set):
            return list(value)

        return str(value)



