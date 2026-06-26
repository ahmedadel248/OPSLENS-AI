from pathlib import Path
from typing import Any, Dict, List, Set


class RuleBasedRunbookRetriever:
    """
    Rule-based runbook knowledge retriever.

    This is not a vector database.
    It maps structured incident signals to trusted runbook files.
    """

    SIGNAL_TO_RUNBOOK = {
        "ServiceTargetPortMismatch": "service_targetport_mismatch.md",
        "ServiceSelectorMismatch": "service_targetport_mismatch.md",
        "EmptyServiceEndpoints": "service_targetport_mismatch.md",

        "ConnectionRefused": "connection_refused.md",

        "Unhealthy": "readiness_probe_failed.md",
        "KubernetesWarningEvent": "readiness_probe_failed.md",

        "DeploymentNoAvailableReplicas": "deployment_no_available_replicas.md",

        "cpu_anomaly": "cpu_memory_anomaly.md",
        "memory_anomaly": "cpu_memory_anomaly.md",
        "cpu_memory_anomaly": "cpu_memory_anomaly.md",
        "resource_anomaly": "cpu_memory_anomaly.md",
    }

    def __init__(self, runbooks_dir: str = "knowledge_base/runbooks"):
        self.runbooks_dir = Path(runbooks_dir)

    def retrieve(self, supervisor_report: Dict[str, Any], max_runbooks: int = 5) -> List[Dict[str, str]]:
        signal_names = self._extract_signal_names(supervisor_report)

        selected_files = []
        seen_files = set()

        for signal in signal_names:
            filename = self.SIGNAL_TO_RUNBOOK.get(signal)

            if not filename or filename in seen_files:
                continue

            seen_files.add(filename)
            selected_files.append(filename)

            if len(selected_files) >= max_runbooks:
                break

        runbooks = []

        for filename in selected_files:
            path = self.runbooks_dir / filename

            if not path.exists():
                continue

            runbooks.append(
                {
                    "name": filename,
                    "path": str(path),
                    "content": path.read_text(encoding="utf-8"),
                }
            )

        return runbooks

    def _extract_signal_names(self, report: Dict[str, Any]) -> List[str]:
        names = []

        primary_signal = report.get("primary_signal") or {}
        if primary_signal.get("anomaly_type"):
            names.append(primary_signal["anomaly_type"])

        primary_anomaly = report.get("primary_anomaly_type")
        if primary_anomaly:
            names.append(primary_anomaly)

        for signal in report.get("supporting_signals", []) or []:
            if signal.get("anomaly_type"):
                names.append(signal["anomaly_type"])

        for evidence in report.get("evidence", []) or []:
            text = str(evidence)

            for known_signal in self.SIGNAL_TO_RUNBOOK:
                if known_signal in text:
                    names.append(known_signal)

        for contribution in (report.get("agent_contributions") or {}).values():
            for finding in contribution.get("findings", []) or []:
                if finding.get("anomaly_type"):
                    names.append(finding["anomaly_type"])

        return self._dedupe(names)

    def _dedupe(self, items: List[str]) -> List[str]:
        seen: Set[str] = set()
        result = []

        for item in items:
            if item in seen:
                continue

            seen.add(item)
            result.append(item)

        return result


