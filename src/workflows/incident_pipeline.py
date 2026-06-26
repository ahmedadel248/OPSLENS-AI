import os
from typing import Any, Dict, Optional

from src.legacy.collectors.mock_metrics_collectorllector import MockMetricsCollector
from src.detectors.resource_detector import ResourceDetector
from src.agents.resource_metrics_agent import ResourceMetricsAgent
from src.agents.supervisor_agent import SupervisorAgent
from src.utils.report_writer import ReportWriter


def extract_event(output: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(output, dict):
        return None

    if "anomaly_type" in output:
        return output

    if output.get("status") == "anomaly" and isinstance(output.get("event"), dict):
        return output["event"]

    if isinstance(output.get("event"), dict):
        return output["event"]

    if isinstance(output.get("anomaly_event"), dict):
        return output["anomaly_event"]

    if isinstance(output.get("incident_event"), dict):
        return output["incident_event"]

    return None


def run_mock_pipeline(limit: Optional[int] = None):
    csv_path = os.getenv("CSV_PATH", "data/raw/node_telemetry_pods_on.csv")
    node_name = os.getenv("NODE_NAME", "vm-node")
    artifacts_dir = os.getenv("ARTIFACTS_DIR", "artifacts/resource_detector_v2")
    output_dir = os.getenv("REPORTS_DIR", "reports")

    collector = MockMetricsCollector(csv_path=csv_path, node_name=node_name)
    detector = ResourceDetector(artifacts_dir=artifacts_dir)
    metrics_agent = ResourceMetricsAgent(collector=collector, detector=detector)

    supervisor = SupervisorAgent()
    report_writer = ReportWriter(output_dir=output_dir)

    raw_outputs_count = 0
    events = []
    reports = []

    for output in metrics_agent.run(limit=limit):
        raw_outputs_count += 1

        event = extract_event(output)

        if event is None:
            continue

        events.append(event)

        report = supervisor.handle_event(event)
        reports.append(report)

    saved_paths = {}

    if reports:
        saved_paths = report_writer.save_all(reports)

    print("=" * 80)
    print("OpsLens Mock Metrics Pipeline Completed")
    print("=" * 80)
    print(f"Raw agent outputs : {raw_outputs_count}")
    print(f"Events extracted  : {len(events)}")
    print(f"Reports created   : {len(reports)}")

    if saved_paths:
        print("Saved reports:")
        for name, path in saved_paths.items():
            print(f"- {name}: {path}")
    else:
        print("No reports saved because no incidents were detected.")

    print("=" * 80)

    return {
        "raw_outputs_count": raw_outputs_count,
        "events": events,
        "reports": reports,
        "saved_paths": saved_paths,
    }


def run_from_env():
    limit = int(os.getenv("RUN_LIMIT", "500"))
    mode = os.getenv("OPSLENS_MODE", "mock").lower()

    if mode == "mock":
        return run_mock_pipeline(limit=limit)

    raise ValueError(f"Unsupported OPSLENS_MODE={mode}. Currently supported: mock")




