import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.investigation_scope import InvestigationScope
from src.core.report_safety import sanitize_report
from src.core.scoped_collector import ScopedCollector
from src.core.root_cause_facts import build_root_cause_facts

from src.detectors.resource_detector import ResourceDetector
from src.agents.resource_metrics_agent import ResourceMetricsAgent

from src.collectors.kubernetes_metrics_collector import KubernetesMetricsCollector
from src.core.pod_resource_detector import PodResourceDetector
from src.agents.pod_lstm_metrics_agent import PodLSTMMetricsAgent

from src.collectors.kubernetes_state_collector import KubernetesStateCollector
from src.detectors.kubernetes_signal_detector import KubernetesSignalDetector
from src.agents.kubernetes_events_agent import KubernetesEventsAgent

from src.collectors.kubernetes_logs_collector import KubernetesLogsCollector
from src.detectors.logs_signal_detector import LogsSignalDetector
from src.agents.logs_agent import LogsAgent

from src.collectors.ansible_config_collector import AnsibleConfigCollector
from src.detectors.config_signal_detector import ConfigSignalDetector
from src.agents.ansible_config_agent import AnsibleConfigAgent

from src.agents.supervisor_agent import SupervisorAgent
from src.agents.gemini_reasoning_agent import GeminiReasoningAgent


def cleanup_runtime_cache():
    """
    Clear runtime cache/history so old incidents do not contaminate the next investigation.

    Final reports are preserved under data/final_incident_reports.
    """

    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)

    for jsonl_file in data_dir.glob("*.jsonl"):
        jsonl_file.unlink(missing_ok=True)

    runtime_dirs = [
        data_dir / "incident_reports",
        data_dir / "live",
        data_dir / "processed",
        data_dir / "raw",
    ]

    for directory in runtime_dirs:
        directory.mkdir(parents=True, exist_ok=True)

        for item in directory.iterdir():
            if item.name == ".gitkeep":
                continue

            if item.is_file():
                item.unlink(missing_ok=True)

            elif item.is_dir():
                import shutil
                shutil.rmtree(item, ignore_errors=True)

        (directory / ".gitkeep").touch(exist_ok=True)

    (data_dir / ".gitkeep").touch(exist_ok=True)


def seed_resource_anomaly(*args, **kwargs):
    """Disabled in product mode. Real resource anomalies must come from collectors/detectors."""
    return None



def build_pod_lstm_metrics_agent(scope: InvestigationScope):
    """
    Build Pod-level LSTM metrics agent.

    It reads pod_metrics from KubernetesMetricsCollector, keeps 11 readings per pod,
    and emits PodLSTMResourceAnomaly when actual CPU/memory is higher than expected.
    """
    try:
        try:
            pod_metrics_collector = KubernetesMetricsCollector(
                node_name=scope.node_name,
                namespace=scope.namespace,
                all_namespaces=False,
                poll_interval_seconds=30,
            )
        except TypeError:
            try:
                pod_metrics_collector = KubernetesMetricsCollector(
                    node_name=scope.node_name,
                    namespace=scope.namespace,
                    all_namespaces=False,
                )
            except TypeError:
                pod_metrics_collector = KubernetesMetricsCollector(
                    node_name=scope.node_name,
                )

        pod_lstm_detector = PodResourceDetector(
            "artifacts/pod_lstm_detector_v3_timeaware_minmax_pods_on_only"
        )

        return PodLSTMMetricsAgent(
            collector=pod_metrics_collector,
            detector=pod_lstm_detector,
            history_path="data/pod_lstm_metrics_history.jsonl",
            events_path="data/pod_lstm_events.jsonl",
            persist=True,
        )

    except Exception as exc:
        class DisabledPodLSTMAgent:
            def run(self):
                return [{
                    "agent": "pod_lstm_metrics",
                    "source_agent": "pod_lstm_metrics",
                    "event_type": "agent_execution_error",
                    "anomaly_type": "PodLSTMUnavailable",
                    "severity": "warning",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": "Pod LSTM metrics agent is unavailable.",
                    "evidence": [f"{type(exc).__name__}: {str(exc)}"],
                    "recommendations": [
                        "Check Pod LSTM artifact files under artifacts/pod_lstm_detector_v3_timeaware_minmax_pods_on_only.",
                        "Check TensorFlow/joblib installation.",
                        "Check Kubernetes metrics-server and pod_metrics collector output.",
                    ],
                }]

        return DisabledPodLSTMAgent()




def build_node_metrics_collector(scope: InvestigationScope):
    try:
        try:
            return KubernetesMetricsCollector(
                node_name=scope.node_name,
                namespace=scope.namespace,
                all_namespaces=False,
                poll_interval_seconds=30,
            )
        except TypeError:
            try:
                return KubernetesMetricsCollector(
                    node_name=scope.node_name,
                    namespace=scope.namespace,
                    all_namespaces=False,
                )
            except TypeError:
                return KubernetesMetricsCollector(node_name=scope.node_name)
    except Exception:
        return None


def build_pod_lstm_metrics_agent(scope: InvestigationScope):
    try:
        pod_metrics_collector = build_node_metrics_collector(scope)

        pod_lstm_detector = PodResourceDetector(
            "artifacts/pod_lstm_detector_v3_timeaware_minmax_pods_on_only"
        )

        return PodLSTMMetricsAgent(
            collector=pod_metrics_collector,
            detector=pod_lstm_detector,
            history_path="data/pod_lstm_metrics_history.jsonl",
            events_path="data/pod_lstm_events.jsonl",
            persist=True,
        )

    except Exception as exc:
        class DisabledPodLSTMAgent:
            def run(self):
                return [{
                    "agent": "pod_lstm_metrics",
                    "source_agent": "pod_lstm_metrics",
                    "event_type": "agent_health",
                    "anomaly_type": "PodLSTMUnavailable",
                    "severity": "low",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": "Pod LSTM metrics agent is unavailable.",
                    "evidence": [f"{type(exc).__name__}: {str(exc)}"],
                    "recommendations": [
                        "Check Pod LSTM artifact files.",
                        "Check TensorFlow/joblib installation.",
                        "Check Kubernetes metrics-server and pod metrics collector output.",
                    ],
                    "internal_agent_health": True,
                }]

        return DisabledPodLSTMAgent()



def build_agents(scope: InvestigationScope, demo_seed_metrics: bool = False):
    resource_detector = ResourceDetector(
        "artifacts/resource_detector_v7_egypt_timeaware"
    )

    node_metrics_collector = build_node_metrics_collector(scope)

    metrics_agent = ResourceMetricsAgent(
        node_metrics_collector,
        resource_detector,
        node_name=scope.node_name,
    )

    # Demo metric seeding removed for product mode.
    demo_seed_metrics = False

    agents = {
        "resource_metrics": metrics_agent,

        "pod_lstm_metrics": build_pod_lstm_metrics_agent(scope),

        "kubernetes_events": KubernetesEventsAgent(
            ScopedCollector(KubernetesStateCollector(namespace=scope.namespace), scope),
            KubernetesSignalDetector(),
            metrics_agent=metrics_agent,
        ),

        "logs": LogsAgent(
            ScopedCollector(KubernetesLogsCollector(namespace=scope.namespace, tail_lines=120), scope),
            LogsSignalDetector(),
            metrics_agent=metrics_agent,
        ),

        "ansible_config": AnsibleConfigAgent(
            ScopedCollector(AnsibleConfigCollector(wsl_distro="Ubuntu", namespace=scope.namespace), scope),
            ConfigSignalDetector(),
            metrics_agent=metrics_agent,
        ),
    }

    return agents



# =========================================================
# OpsLens preserve agent runtime status v1
# Keeps Supervisor agent execution status inside the final report.
# =========================================================

def _opslens_preserve_agent_runtime(final_report, supervisor_report, agents):
    final_report = dict(final_report or {})
    supervisor_report = dict(supervisor_report or {})

    contributions = supervisor_report.get("agent_contributions") or {}

    if not isinstance(contributions, dict):
        contributions = {}

    # Ensure every configured agent appears, even if it produced no incident signal.
    for agent_name in (agents or {}).keys():
        if agent_name not in contributions:
            contributions[agent_name] = {
                "status": "ran",
                "finding": "No active signal detected.",
                "event_count": 0,
            }

    final_report["agent_contributions"] = contributions

    final_report["agent_run_status"] = [
        {
            "agent": agent_name,
            "status": value.get("status", "ran") if isinstance(value, dict) else "ran",
            "finding": (
                value.get("finding")
                if isinstance(value, dict) and value.get("finding")
                else "No active signal detected."
            ),
            "event_count": (
                value.get("event_count", 0)
                if isinstance(value, dict)
                else 0
            ),
        }
        for agent_name, value in contributions.items()
    ]

    # Preserve correlation/grouping metadata from Supervisor if Gemini omitted it.
    for key in [
        "primary_signal",
        "supporting_signals",
        "primary_incident_group",
        "incident_groups",
        "separate_findings",
        "unclassified_findings",
        "additional_findings",
        "incident_grouping_policy",
        "root_cause_facts",
    ]:
        if key not in final_report and key in supervisor_report:
            final_report[key] = supervisor_report.get(key)

    final_report["_opslens_supervisor_metadata_preserved"] = True

    return final_report


def run_investigation(scope: InvestigationScope, demo_seed_metrics: bool = False):
    scope.validate()

    agents = build_agents(scope, False)

    supervisor = SupervisorAgent(
        agents=agents,
        persist=True,
        debug=False,
    )

    supervisor_report = supervisor.investigate(
        scenario_name=f"focused_investigation_{scope.namespace}_{scope.node_name}"
    )

    supervisor_report["root_cause_facts"] = build_root_cause_facts(supervisor_report)

    final_agent = GeminiReasoningAgent()
    final_report = final_agent.analyze(supervisor_report)

    final_report = sanitize_report(
        final_report,
        namespace=scope.namespace,
        node=scope.node_name,
    )

    final_report = _opslens_preserve_agent_runtime(
        final_report=final_report,
        supervisor_report=supervisor_report,
        agents=agents,
    )

    return final_report


def main():
    parser = argparse.ArgumentParser(description="Run OpsLens focused incident investigation.")

    parser.add_argument("--node", required=True, help="Kubernetes node name selected by the user.")
    parser.add_argument("--namespace", required=True, help="Kubernetes namespace selected by the user.")
    parser.add_argument(
        "--demo-seed-metrics",
        action="store_true",
        help="Demo-only: seed fake resource anomaly readings.",
    )

    parser.add_argument(
        "--keep-runtime-cache",
        action="store_true",
        help="Keep runtime cache/history files after the run. Default is to clean them.",
    )

    args = parser.parse_args()

    if not args.keep_runtime_cache:
        cleanup_runtime_cache()

    scope = InvestigationScope(
        node_name=args.node,
        namespace=args.namespace,
    )

    try:
        final_report = run_investigation(
            scope=scope,
            demo_seed_metrics=args.demo_seed_metrics,
        )
    finally:
        if not args.keep_runtime_cache:
            cleanup_runtime_cache()

    preview = {
        "title": final_report.get("title"),
        "severity": final_report.get("severity"),
        "confidence": final_report.get("confidence"),
        "namespace": final_report.get("affected_resources", {}).get("namespace"),
        "node": final_report.get("affected_resources", {}).get("node"),
        "service": final_report.get("affected_resources", {}).get("service"),
        "recommended_fix": final_report.get("recommended_fix"),
        "verification": final_report.get("verification"),
        "markdown_report_path": final_report.get("markdown_report_path"),
    }

    print(json.dumps(preview, indent=2))


if __name__ == "__main__":
    main()