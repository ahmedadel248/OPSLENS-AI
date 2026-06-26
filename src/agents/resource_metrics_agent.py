import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class ResourceMetricsAgent:
    """
    Metrics Agent:
    - Collects live node metrics.
    - Keeps rolling buffer per node.
    - Sends 20 history readings + 1 current reading to ResourceDetector.
    - Automatically persists every reading/result to JSONL.
    - Persists anomaly events separately.
    - Exposes analyze_node(node_name) for other agents.
    """

    def __init__(
        self,
        collector,
        detector,
        history_path: str = "data/metrics_history.jsonl",
        events_path: str = "data/resource_events.jsonl",
        persist: bool = True,
    ):
        self.collector = collector
        self.detector = detector

        self.required_buffer_size = self.detector.window_size + 1

        self.buffers = defaultdict(
            lambda: deque(maxlen=self.required_buffer_size)
        )

        self.persist = persist

        self.history_path = Path(history_path)
        self.events_path = Path(events_path)

        if self.persist:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            self.history_path.touch(exist_ok=True)
            self.events_path.touch(exist_ok=True)

    def process_reading(self, reading: Dict[str, Any]) -> Dict[str, Any]:
        node_name = reading.get("node_name", "unknown")

        buffer = self.buffers[node_name]
        buffer.append(reading)

        if len(buffer) < self.required_buffer_size:
            result = {
                "status": "warming_up",
                "agent": "metrics_agent",
                "node_name": node_name,
                "buffer_size": len(buffer),
                "required_window": self.required_buffer_size,
            }

            self._persist_history(
                reading=reading,
                result=result,
                buffer=list(buffer),
            )

            return result

        detection_result = self.detector.detect(list(buffer))

        if detection_result["status"] == "anomaly":
            result = {
                "status": "anomaly",
                "agent": "metrics_agent",
                "node_name": node_name,
                "detection": detection_result,
                "event": detection_result.get("event"),
            }
        else:
            result = {
                "status": "normal",
                "agent": "metrics_agent",
                "node_name": node_name,
                "detection": detection_result,
            }

        self._persist_history(
            reading=reading,
            result=result,
            buffer=list(buffer),
        )

        if result["status"] == "anomaly":
            self._persist_event(result.get("event"))

        return result

    def run(self, limit: Optional[int] = None):
        if self.collector is None:
            raise ValueError("ResourceMetricsAgent.collector is None, so run() cannot collect live metrics.")

        for reading in self.collector.stream(limit=limit):
            yield self.process_reading(reading)

    def analyze_node(self, node_name: str) -> Dict[str, Any]:
        """
        Called by other agents.

        Priority:
        1. Use in-memory buffer if available.
        2. Fallback to data/metrics_history.jsonl.
        3. Return insufficient_history if there are not enough readings.
        """
        if not node_name:
            return {
                "status": "not_available",
                "reason": "missing_node_name",
                "resource_anomaly": None,
            }

        required = self.required_buffer_size

        in_memory_readings = list(self.buffers.get(node_name, []))
        if len(in_memory_readings) >= required:
            readings = in_memory_readings[-required:]

            try:
                result = self.detector.detect(readings)
                result["context_source"] = "metrics_agent_memory_buffer"
                result["readings_used"] = len(readings)
                return result
            except Exception as exc:
                return {
                    "status": "metrics_context_error",
                    "reason": type(exc).__name__,
                    "message": str(exc),
                    "node_name": node_name,
                    "context_source": "metrics_agent_memory_buffer",
                }

        file_readings = self.load_recent_readings_from_file(
            history_path=str(self.history_path),
            node_name=node_name,
            limit=required,
        )

        if len(file_readings) >= required:
            try:
                result = self.detector.detect(file_readings)
                result["context_source"] = "metrics_history_file"
                result["readings_used"] = len(file_readings)
                return result
            except Exception as exc:
                return {
                    "status": "metrics_context_error",
                    "reason": type(exc).__name__,
                    "message": str(exc),
                    "node_name": node_name,
                    "context_source": "metrics_history_file",
                }

        return {
            "status": "insufficient_history",
            "node_name": node_name,
            "required_readings": required,
            "available_memory_readings": len(in_memory_readings),
            "available_file_readings": len(file_readings),
            "resource_anomaly": None,
        }

    def get_recent_readings(
        self,
        node_name: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        readings = list(self.buffers.get(node_name, []))

        if limit is not None:
            return readings[-limit:]

        return readings

    @staticmethod
    def load_recent_readings_from_file(
        history_path: str,
        node_name: str,
        limit: int = 21,
    ) -> List[Dict[str, Any]]:
        path = Path(history_path)

        if not path.exists():
            return []

        readings = []

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                record = json.loads(line)

                reading = record.get("reading", {})
                if reading.get("node_name") == node_name:
                    readings.append(reading)

        return readings[-limit:]

    def _persist_history(
        self,
        reading: Dict[str, Any],
        result: Dict[str, Any],
        buffer: List[Dict[str, Any]],
    ) -> None:
        if not self.persist:
            return

        record = {
            "saved_at_utc": self._now_utc(),
            "agent": "metrics_agent",
            "status": result.get("status"),
            "node_name": result.get("node_name"),
            "reading": reading,
            "buffer_size": len(buffer),
            "required_window": self.required_buffer_size,
            "detection": result.get("detection", {}),
            "event": result.get("event"),
        }

        self._append_jsonl(self.history_path, record)

    def _persist_event(self, event: Optional[Dict[str, Any]]) -> None:
        if not self.persist:
            return

        if not event:
            return

        record = {
            "saved_at_utc": self._now_utc(),
            "agent": "metrics_agent",
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


# ---- Supervisor integration patch ----
_resource_metrics_original_init = ResourceMetricsAgent.__init__


def _resource_metrics_init(self, *args, node_name=None, **kwargs):
    self.node_name = node_name
    _resource_metrics_original_init(self, *args, **kwargs)


def _resource_metrics_run(self):
    """
    Supervisor-compatible run() method.

    It analyzes the selected node and returns a list of incident events.
    """

    if not getattr(self, "node_name", None):
        raise ValueError("ResourceMetricsAgent requires node_name before run().")

    result = self.analyze_node(self.node_name)

    if not isinstance(result, dict):
        return []

    status = result.get("status")
    resource_anomaly = result.get("resource_anomaly", False)

    if status not in {"anomaly", "critical"} and not resource_anomaly:
        return []

    if result.get("event"):
        return [result["event"]]

    anomaly_type = (
        result.get("anomaly_type")
        or result.get("type")
        or "resource_anomaly"
    )

    metrics = result.get("metrics") or result.get("current_reading") or {}

    event = {
        "source_agent": "resource_metrics_agent",
        "event_type": "resource_anomaly",
        "anomaly_type": anomaly_type,
        "severity": result.get("severity", "critical"),
        "node_name": self.node_name,
        "summary": result.get(
            "summary",
            f"Resource anomaly detected on node {self.node_name}: {anomaly_type}."
        ),
        "metrics": metrics,
        "evidence": result.get("evidence", []),
        "recommendations": result.get("recommendations", []),
        "raw_signal": result,
    }

    return [event]


ResourceMetricsAgent.__init__ = _resource_metrics_init
ResourceMetricsAgent.run = _resource_metrics_run



