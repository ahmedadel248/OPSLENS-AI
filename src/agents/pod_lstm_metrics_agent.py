from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import os
import time

from src.core.pod_resource_detector import PodResourceDetector


class PodLSTMMetricsAgent:
    """
    Collects pod metrics from KubernetesMetricsCollector and runs PodResourceDetector.

    It expects collector.collect_once() to return:
    {
      "pod_metrics": [
        {
          "namespace": "...",
          "pod_name": "...",
          "node_name": "...",
          "cpu_cores": 0.933,
          "memory_bytes": 7340032,
          "timestamp": "..."
        }
      ]
    }
    """

    def __init__(
        self,
        collector,
        detector: Optional[PodResourceDetector] = None,
        history_path: str = "data/pod_lstm_metrics_history.jsonl",
        events_path: str = "data/pod_lstm_events.jsonl",
        persist: bool = True,
    ):
        self.collector = collector
        self.detector = detector or PodResourceDetector()

        self.required_buffer_size = self.detector.window_size + 1

        self.buffers = defaultdict(
            lambda: deque(maxlen=self.required_buffer_size)
        )

        self.history_path = Path(history_path)
        self.events_path = Path(events_path)
        self.persist = persist

        if self.persist:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            self.history_path.touch(exist_ok=True)
            self.events_path.touch(exist_ok=True)

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _key(self, reading: Dict[str, Any]) -> str:
        namespace = reading.get("namespace") or "default"
        pod_name = reading.get("pod_name") or "unknown"
        return f"{namespace}/{pod_name}"

    def _reading_from_pod_metric(self, pod_metric: Dict[str, Any], fallback_timestamp: Optional[str] = None) -> Dict[str, Any]:
        timestamp = pod_metric.get("timestamp") or fallback_timestamp or self._now_utc()

        cpu_usage = None

        if "cpu_cores" in pod_metric:
            cpu_usage = float(pod_metric.get("cpu_cores") or 0.0)
        elif "cpu_millicores" in pod_metric:
            cpu_usage = float(pod_metric.get("cpu_millicores") or 0.0) / 1000.0
        elif "cpu_usage" in pod_metric:
            cpu_usage = float(pod_metric.get("cpu_usage") or 0.0)
        else:
            cpu_usage = 0.0

        memory_bytes = None

        if "memory_bytes" in pod_metric:
            memory_bytes = float(pod_metric.get("memory_bytes") or 0.0)
        elif "mem_bytes" in pod_metric:
            memory_bytes = float(pod_metric.get("mem_bytes") or 0.0)
        elif "memory_mib" in pod_metric:
            memory_bytes = float(pod_metric.get("memory_mib") or 0.0) * 1024 * 1024
        else:
            memory_bytes = 0.0

        return {
            "timestamp": timestamp,
            "namespace": pod_metric.get("namespace"),
            "pod_name": pod_metric.get("pod_name"),
            "node_name": pod_metric.get("node_name"),
            "cpu_usage": cpu_usage,
            "mem_bytes": memory_bytes,
            "memory_bytes": memory_bytes,
        }

    def process_reading(self, reading: Dict[str, Any]) -> Dict[str, Any]:
        key = self._key(reading)
        buffer = self.buffers[key]
        buffer.append(reading)

        result = self.detector.detect(list(buffer))
        result["agent"] = "pod_lstm_metrics_agent"
        result["key"] = key
        result["buffer_size"] = len(buffer)
        result["required_window"] = self.required_buffer_size

        self._persist_history(reading, result, list(buffer))

        if result.get("resource_anomaly") and result.get("event"):
            self._persist_event(result["event"])

        return result

    def collect_once(self) -> List[Dict[str, Any]]:
        if self.collector is None or not hasattr(self.collector, "collect_once"):
            return []

        payload = self.collector.collect_once()
        fallback_timestamp = payload.get("timestamp") or self._now_utc()
        pod_metrics = payload.get("pod_metrics") or []

        results = []

        for pod_metric in pod_metrics:
            reading = self._reading_from_pod_metric(
                pod_metric,
                fallback_timestamp=fallback_timestamp,
            )

            if not reading.get("pod_name"):
                continue

            result = self.process_reading(reading)
            results.append(result)

        return results

    def run(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        Supervisor-compatible run().

        The Pod LSTM needs window_size + 1 readings.
        With the trained model:
        - window_size = 10
        - required readings = 11
        - expected sampling interval = 30 seconds

        For a quick technical test only, you can override the sleep interval:
        PowerShell:
            $env:OPSLENS_POD_LSTM_SAMPLE_SECONDS="2"

        For the final/demo behavior, leave it unset so it uses 30 seconds.
        """
        events = []

        samples = int(limit or self.required_buffer_size)

        sleep_seconds = int(
            os.getenv(
                "OPSLENS_POD_LSTM_SAMPLE_SECONDS",
                str(getattr(self.detector, "sampling_interval_seconds", 30))
            )
        )

        for index in range(max(samples, 1)):
            results = self.collect_once()

            for result in results:
                if result.get("resource_anomaly") and result.get("event"):
                    events.append(result["event"])

            if index < samples - 1 and sleep_seconds > 0:
                time.sleep(sleep_seconds)

        return events

    def load_recent_readings_from_file(
        self,
        namespace: str,
        pod_name: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not self.history_path.exists():
            return []

        target_key = f"{namespace}/{pod_name}"
        readings = []

        with self.history_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except Exception:
                    continue

                if record.get("key") != target_key:
                    continue

                reading = record.get("reading")
                if reading:
                    readings.append(reading)

        if limit is None:
            limit = self.required_buffer_size

        return readings[-int(limit):]

    def analyze_pod(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        readings = self.load_recent_readings_from_file(
            namespace=namespace,
            pod_name=pod_name,
            limit=self.required_buffer_size,
        )

        return self.detector.detect(readings)


    def _json_safe(self, value: Any) -> Any:
        try:
            json.dumps(value, ensure_ascii=False, default=str)
            return value
        except Exception:
            if isinstance(value, dict):
                safe = {}
                for key, item in value.items():
                    if key in {"event", "raw_signal"}:
                        continue
                    safe[key] = self._json_safe(item)
                return safe

            if isinstance(value, list):
                return [self._json_safe(item) for item in value]

            return str(value)

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
            "agent": "pod_lstm_metrics_agent",
            "key": self._key(reading),
            "reading": reading,
            "buffer_size": len(buffer),
            "required_window": self.required_buffer_size,
            "result_status": result.get("status"),
            "resource_anomaly": result.get("resource_anomaly"),
            "result": self._json_safe(result),
        }

        self._append_jsonl(self.history_path, record)

    def _persist_event(self, event: Dict[str, Any]) -> None:
        if not self.persist:
            return

        record = {
            "saved_at_utc": self._now_utc(),
            "agent": "pod_lstm_metrics_agent",
            "event": self._json_safe(event),
        }

        self._append_jsonl(self.events_path, record)

    def _append_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

# =========================================================
# OpsLens final Pod LSTM buffer completion patch
# =========================================================
# OpsLens final Pod LSTM buffer completion patch
# Ensures the Pod LSTM reaches 11 readings before returning.
# Also hydrates in-memory buffers from history file after server restart.
# =========================================================

import os as _opslens_os
import time as _opslens_time


def _opslens_pod_lstm_hydrate_buffer(self, reading: Dict[str, Any]) -> None:
    key = self._key(reading)
    buffer = self.buffers[key]

    if len(buffer) > 0:
        return

    namespace = reading.get("namespace")
    pod_name = reading.get("pod_name")

    if not namespace or not pod_name:
        return

    try:
        previous_readings = self.load_recent_readings_from_file(
            namespace=namespace,
            pod_name=pod_name,
            limit=self.required_buffer_size - 1,
        )

        for item in previous_readings:
            buffer.append(item)

    except Exception:
        return


def _opslens_pod_lstm_process_reading(self, reading: Dict[str, Any]) -> Dict[str, Any]:
    _opslens_pod_lstm_hydrate_buffer(self, reading)

    key = self._key(reading)
    buffer = self.buffers[key]
    buffer.append(reading)

    result = self.detector.detect(list(buffer))
    result["agent"] = "pod_lstm_metrics_agent"
    result["key"] = key
    result["buffer_size"] = len(buffer)
    result["required_window"] = self.required_buffer_size

    self._persist_history(reading, result, list(buffer))

    if result.get("resource_anomaly") and result.get("event"):
        self._persist_event(result["event"])

    return result


def _opslens_pod_lstm_run(self, limit: int = None) -> List[Dict[str, Any]]:
    events = []

    max_attempts = int(
        limit
        or _opslens_os.getenv(
            "OPSLENS_POD_LSTM_MAX_ATTEMPTS",
            str(self.required_buffer_size + 2),
        )
    )

    sleep_seconds = int(
        _opslens_os.getenv(
            "OPSLENS_POD_LSTM_SAMPLE_SECONDS",
            str(getattr(self.detector, "sampling_interval_seconds", 30)),
        )
    )

    saw_model_decision = False
    last_results = []

    for index in range(max(max_attempts, 1)):
        results = self.collect_once()
        last_results = results

        for result in results:
            if result.get("resource_anomaly") and result.get("event"):
                events.append(result["event"])

            if result.get("status") in {"normal", "anomaly"}:
                saw_model_decision = True

        if saw_model_decision:
            break

        if index < max_attempts - 1 and sleep_seconds > 0:
            _opslens_time.sleep(sleep_seconds)

    self.last_results = last_results
    return events


PodLSTMMetricsAgent.process_reading = _opslens_pod_lstm_process_reading
PodLSTMMetricsAgent.run = _opslens_pod_lstm_run
