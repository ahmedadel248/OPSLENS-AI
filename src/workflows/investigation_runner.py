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


def build_agents(scope: InvestigationScope, demo_seed_metrics: bool = False):
    resource_detector = ResourceDetector(
        "artifacts/resource_detector_v7_egypt_timeaware"
    )

    metrics_agent = ResourceMetricsAgent(
        None,
        resource_detector,
        node_name=scope.node_name,
    )

    # Demo metric seeding removed for product mode.
    demo_seed_metrics = False

    agents = {
        "resource_metrics": metrics_agent,

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

    return sanitize_report(final_report, namespace=scope.namespace, node=scope.node_name)


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


