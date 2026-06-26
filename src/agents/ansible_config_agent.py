import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class AnsibleConfigAgent:
    def __init__(
        self,
        collector,
        detector,
        metrics_agent=None,
        state_history_path: str = "data/config_state_history.jsonl",
        events_path: str = "data/config_events.jsonl",
        persist: bool = True,
    ):
        self.collector = collector
        self.detector = detector
        self.metrics_agent = metrics_agent

        self.persist = persist
        self.state_history_path = Path(state_history_path)
        self.events_path = Path(events_path)

        if self.persist:
            self.state_history_path.parent.mkdir(parents=True, exist_ok=True)
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_history_path.touch(exist_ok=True)
            self.events_path.touch(exist_ok=True)

    def run(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        config_state = self.collector.collect()

        self._persist_state(config_state)

        signals = self.detector.detect(config_state)

        if limit is not None:
            signals = signals[:limit]

        events = []

        for signal in signals:
            event = self._build_event(signal)
            events.append(event)
            self._persist_event(event)

        return events

    def _build_event(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        signal_name = signal.get("signal", "ConfigSignal")
        node_name = signal.get("node_name")

        if not node_name:
            node_name = self._infer_node_from_signal(signal)

        metrics_context = self._get_metrics_context(node_name)

        return {
            "source_agent": "ansible_config_agent",
            "agent": "ansible_config_agent",
            "event_type": "config_signal",

            "anomaly_type": signal_name,

            "severity": signal.get("severity", "warning"),
            "timestamp": self._now_utc(),

            "namespace": signal.get("namespace"),
            "node_name": node_name,
            "service_name": signal.get("service_name"),
            "deployment_name": signal.get("deployment_name"),
            "pod_name": signal.get("pod_name"),
            "container_name": signal.get("container_name"),

            "summary": signal.get("summary", f"Config signal detected: {signal_name}"),

            "metrics": metrics_context,
            "metrics_context": metrics_context,

            "evidence": signal.get("evidence", []),
            "recommendations": signal.get("recommendations", []),

            "raw_signal": signal,
        }

    def _infer_node_from_signal(self, signal: Dict[str, Any]) -> Optional[str]:
        # Kubernetes object config signals may not belong to a single node.
        # For local Minikube demo, use minikube as the only node context.
        if signal.get("category", "").startswith("kubernetes_"):
            return "minikube"

        return None

    def _get_metrics_context(self, node_name: Optional[str]) -> Dict[str, Any]:
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
            "actual_memory",
            "cpu_positive_error",
            "memory_positive_error",
            "cpu_pressure_anomaly",
            "memory_pressure_anomaly",
            "reason",
            "message",
        ]

        return {key: result.get(key) for key in keys if key in result}

    def _persist_state(self, config_state: Dict[str, Any]) -> None:
        if not self.persist:
            return

        record = {
            "saved_at_utc": self._now_utc(),
            "agent": "ansible_config_agent",
            "state": config_state,
        }

        self._append_jsonl(self.state_history_path, record)

    def _persist_event(self, event: Dict[str, Any]) -> None:
        if not self.persist:
            return

        record = {
            "saved_at_utc": self._now_utc(),
            "agent": "ansible_config_agent",
            "event": event,
        }

        self._append_jsonl(self.events_path, record)

    def _append_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=self._json_default) + "\n")

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



