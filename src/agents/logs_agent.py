import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class LogsAgent:
    def __init__(
        self,
        collector,
        detector,
        metrics_agent=None,
        logs_history_path: str = "data/logs_history.jsonl",
        log_events_path: str = "data/log_events.jsonl",
        persist: bool = True,
    ):
        self.collector = collector
        self.detector = detector
        self.metrics_agent = metrics_agent

        self.persist = persist
        self.logs_history_path = Path(logs_history_path)
        self.log_events_path = Path(log_events_path)

        if self.persist:
            self.logs_history_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_events_path.parent.mkdir(parents=True, exist_ok=True)
            self.logs_history_path.touch(exist_ok=True)
            self.log_events_path.touch(exist_ok=True)

    def run(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        logs_data = self.collector.collect()

        self._persist_logs(logs_data)

        signals = self.detector.detect(logs_data)

        if limit is not None:
            signals = signals[:limit]

        events = []

        for signal in signals:
            event = self._build_event(signal)
            events.append(event)
            self._persist_event(event)

        return events

    def _build_event(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        signal_name = signal.get("signal", "LogSignal")
        node_name = signal.get("node_name")

        metrics_context = self._get_metrics_context(node_name)

        return {
            "source_agent": "logs_agent",
            "agent": "logs_agent",
            "event_type": "log_signal",

            "anomaly_type": signal_name,

            "severity": signal.get("severity", "warning"),
            "timestamp": self._now_utc(),

            "namespace": signal.get("namespace"),
            "node_name": node_name,
            "pod_name": signal.get("pod_name"),
            "container_name": signal.get("container_name"),

            "summary": signal.get("summary", f"Log signal detected: {signal_name}"),

            "metrics": metrics_context,
            "metrics_context": metrics_context,

            "evidence": signal.get("evidence", []),
            "recommendations": signal.get("recommendations", []),

            "raw_signal": signal,
        }

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

    def _persist_logs(self, logs_data: Dict[str, Any]) -> None:
        if not self.persist:
            return

        record = {
            "saved_at_utc": self._now_utc(),
            "agent": "logs_agent",
            "logs_data": logs_data,
        }

        self._append_jsonl(self.logs_history_path, record)

    def _persist_event(self, event: Dict[str, Any]) -> None:
        if not self.persist:
            return

        record = {
            "saved_at_utc": self._now_utc(),
            "agent": "logs_agent",
            "event": event,
        }

        self._append_jsonl(self.log_events_path, record)

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



