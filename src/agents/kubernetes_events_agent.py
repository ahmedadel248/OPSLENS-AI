import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class KubernetesEventsAgent:
    """
    Kubernetes Events Agent:
    - Collects Kubernetes cluster state.
    - Detects Kubernetes signals using KubernetesSignalDetector.
    - Optionally asks ResourceMetricsAgent for node-level metrics context.
    - Persists collected state and detected events to JSONL.
    """

    def __init__(
        self,
        collector,
        detector,
        metrics_agent=None,
        state_history_path: str = "data/kubernetes_state_history.jsonl",
        events_history_path: str = "data/kubernetes_events_history.jsonl",
        persist: bool = True,
    ):
        self.collector = collector
        self.detector = detector
        self.metrics_agent = metrics_agent

        self.persist = persist
        self.state_history_path = Path(state_history_path)
        self.events_history_path = Path(events_history_path)

        if self.persist:
            self.state_history_path.parent.mkdir(parents=True, exist_ok=True)
            self.events_history_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_history_path.touch(exist_ok=True)
            self.events_history_path.touch(exist_ok=True)

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def run(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        k8s_data = self.collector.collect()

        self._persist_state(k8s_data)

        signals = self.detector.detect(k8s_data)

        if limit is not None:
            signals = signals[:limit]

        events = []

        for signal in signals:
            event = self._build_event(signal)
            events.append(event)
            self._persist_event(event)

        return events

    def _build_event(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        signal_name = signal.get("signal", "KubernetesSignal")
        node_name = signal.get("node_name")

        metrics_context = self._get_metrics_context(signal)

        return {
            "source_agent": "kubernetes_events_agent",
            "agent": "kubernetes_events_agent",
            "event_type": "kubernetes_signal",

            # SupervisorAgent compatibility
            "anomaly_type": signal_name,

            "severity": signal.get("severity", "warning"),
            "timestamp": self._now_utc(),

            "namespace": signal.get("namespace"),
            "node_name": node_name,
            "pod_name": signal.get("pod_name"),
            "container_name": signal.get("container_name"),
            "service_name": signal.get("service_name"),

            "summary": signal.get(
                "summary",
                f"Kubernetes signal detected: {signal_name}"
            ),

            # Compatibility + RCA context
            "metrics": metrics_context,
            "metrics_context": metrics_context,

            "evidence": signal.get("evidence", []),
            "recommendations": signal.get("recommendations", []),

            "raw_signal": signal,
        }

    def _get_metrics_context(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        node_name = signal.get("node_name")

        if not node_name:
            return {
                "status": "not_available",
                "reason": "signal_has_no_node_name",
                "resource_anomaly": None,
            }

        if self.metrics_agent is None:
            return {
                "status": "not_available",
                "reason": "metrics_agent_not_attached",
                "node_name": node_name,
                "resource_anomaly": None,
            }

        if not hasattr(self.metrics_agent, "analyze_node"):
            return {
                "status": "not_available",
                "reason": "metrics_agent_has_no_analyze_node_method",
                "node_name": node_name,
                "resource_anomaly": None,
            }

        result = self.metrics_agent.analyze_node(node_name)

        return self._compact_metrics_context(result)

    def _compact_metrics_context(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if not result:
            return {
                "status": "not_available",
                "reason": "empty_metrics_result",
                "resource_anomaly": None,
            }

        keys = [
            "status",
            "context_source",
            "readings_used",
            "node_name",
            "resource_anomaly",
            "cpu_anomaly",
            "memory_anomaly",
            "severity",
            "actual_cpu",
            "predicted_cpu",
            "cpu_positive_error",
            "cpu_threshold",
            "cpu_pattern_anomaly",
            "cpu_pressure_anomaly",
            "actual_memory",
            "predicted_memory",
            "memory_positive_error",
            "memory_threshold",
            "memory_pattern_anomaly",
            "memory_pressure_anomaly",
            "timestamp",
            "timezone",
            "reason",
            "message",
            "required_readings",
            "available_memory_readings",
            "available_file_readings",
        ]

        return {
            key: result.get(key)
            for key in keys
            if key in result
        }

    def _persist_state(self, k8s_data: Dict[str, Any]) -> None:
        if not self.persist:
            return

        record = {
            "saved_at_utc": self._now_utc(),
            "agent": "kubernetes_events_agent",
            "state": k8s_data,
        }

        self._append_jsonl(self.state_history_path, record)

    def _persist_event(self, event: Dict[str, Any]) -> None:
        if not self.persist:
            return

        record = {
            "saved_at_utc": self._now_utc(),
            "agent": "kubernetes_events_agent",
            "event": event,
        }

        self._append_jsonl(self.events_history_path, record)

    def _append_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=self._json_default) + "\n")

    @staticmethod
    def _json_default(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()

        if isinstance(value, set):
            return list(value)

        return str(value)


