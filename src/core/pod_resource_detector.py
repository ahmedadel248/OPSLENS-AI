from pathlib import Path
from typing import Any, Dict, List
import json
import math

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf


class PodResourceDetector:
    """
    Pod-level LSTM detector.

    Input:
    - last 10 readings as history
    - 1 current reading

    Features:
    - hour_sin
    - hour_cos
    - cpu_usage
    - mem_usage = log1p(memory_bytes)

    Outputs:
    - predicted cpu_usage
    - predicted mem_usage
    """

    def __init__(
        self,
        artifact_dir: str = "artifacts/pod_lstm_detector_v3_timeaware_minmax_pods_on_only",
    ):
        self.artifact_dir = Path(artifact_dir)

        self.model_path = self.artifact_dir / "model.keras"
        self.x_scaler_path = self.artifact_dir / "x_scaler.pkl"
        self.y_scaler_path = self.artifact_dir / "y_scaler.pkl"
        self.config_path = self.artifact_dir / "config.json"

        self._validate_artifacts()

        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))

        self.window_size = int(self.config.get("window_size", 10))
        self.sampling_interval_seconds = int(self.config.get("sampling_interval_seconds", 30))

        self.features = list(self.config.get(
            "features",
            ["hour_sin", "hour_cos", "cpu_usage", "mem_usage"]
        ))

        self.targets = list(self.config.get(
            "targets",
            ["cpu_usage", "mem_usage"]
        ))

        self.cpu_threshold = float(self.config.get("cpu_threshold", 0.0))
        self.memory_threshold = float(self.config.get("memory_threshold", 0.0))

        self.model = tf.keras.models.load_model(self.model_path, compile=False)
        self.x_scaler = joblib.load(self.x_scaler_path)
        self.y_scaler = joblib.load(self.y_scaler_path)

    def _validate_artifacts(self) -> None:
        missing = []

        for path in [
            self.model_path,
            self.x_scaler_path,
            self.y_scaler_path,
            self.config_path,
        ]:
            if not path.exists():
                missing.append(str(path))

        if missing:
            raise FileNotFoundError(
                "Missing Pod LSTM artifact files:\n" + "\n".join(missing)
            )

    def _timestamp_to_hour(self, value: Any) -> float:
        ts = pd.to_datetime(value, errors="coerce")

        if pd.isna(ts):
            ts = pd.Timestamp.now()

        return float(ts.hour + ts.minute / 60.0)

    def _cpu_from_reading(self, reading: Dict[str, Any]) -> float:
        """
        Expected live scale:
        - cpu_usage already 0..1, or
        - CPU (%) field, or
        - cpu_cores, where 933m = 0.933 cores.
        """
        if "cpu_usage" in reading:
            value = float(reading.get("cpu_usage") or 0.0)
        elif "CPU (%)" in reading:
            value = float(reading.get("CPU (%)") or 0.0)
        elif "cpu_cores" in reading:
            value = float(reading.get("cpu_cores") or 0.0)
        elif "cpu_millicores" in reading:
            value = float(reading.get("cpu_millicores") or 0.0) / 1000.0
        else:
            value = 0.0

        # لو جاية 0-100%
        if value > 1.5:
            value = value / 100.0

        return float(max(value, 0.0))

    def _memory_bytes_from_reading(self, reading: Dict[str, Any]) -> float:
        if "mem_bytes" in reading:
            return float(reading.get("mem_bytes") or 0.0)

        if "MEM (B)" in reading:
            return float(reading.get("MEM (B)") or 0.0)

        if "memory_bytes" in reading:
            return float(reading.get("memory_bytes") or 0.0)

        if "memory_mib" in reading:
            return float(reading.get("memory_mib") or 0.0) * 1024 * 1024

        return 0.0

    def _build_row(self, reading: Dict[str, Any]) -> Dict[str, float]:
        hour = self._timestamp_to_hour(reading.get("timestamp"))

        cpu_usage = self._cpu_from_reading(reading)
        mem_bytes = self._memory_bytes_from_reading(reading)
        mem_usage = math.log1p(max(mem_bytes, 0.0))

        return {
            "hour_sin": math.sin(2 * math.pi * hour / 24.0),
            "hour_cos": math.cos(2 * math.pi * hour / 24.0),
            "cpu_usage": cpu_usage,
            "mem_usage": mem_usage,
        }

    def _predict_scaled(self, X: np.ndarray) -> np.ndarray:
        pred = self.model.predict(X, verbose=0)

        if isinstance(pred, dict):
            cpu_pred = pred["cpu_output"]
            mem_pred = pred["mem_output"]

        elif isinstance(pred, (list, tuple)):
            output_names = list(getattr(self.model, "output_names", []))

            if "cpu_output" in output_names and "mem_output" in output_names:
                cpu_pred = pred[output_names.index("cpu_output")]
                mem_pred = pred[output_names.index("mem_output")]
            else:
                cpu_pred, mem_pred = pred[0], pred[1]

        else:
            raise ValueError("Unexpected Pod LSTM prediction output format.")

        return np.concatenate(
            [
                np.asarray(cpu_pred).reshape(-1, 1),
                np.asarray(mem_pred).reshape(-1, 1),
            ],
            axis=1,
        )

    def detect(self, readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        required = self.window_size + 1

        if len(readings) < required:
            return {
                "status": "insufficient_history",
                "required_readings": required,
                "available_readings": len(readings),
                "resource_anomaly": None,
            }

        selected = readings[-required:]

        history = selected[:-1]
        current = selected[-1]

        history_rows = [self._build_row(item) for item in history]
        current_row = self._build_row(current)

        history_df = pd.DataFrame(history_rows)
        X = self.x_scaler.transform(history_df[self.features])
        X = X.reshape(1, self.window_size, len(self.features))

        pred_scaled = self._predict_scaled(X)
        pred = self.y_scaler.inverse_transform(pred_scaled)[0]

        actual_cpu = float(current_row["cpu_usage"])
        actual_mem = float(current_row["mem_usage"])

        predicted_cpu = float(pred[0])
        predicted_mem = float(pred[1])

        cpu_positive_error = actual_cpu - predicted_cpu
        mem_positive_error = actual_mem - predicted_mem

        cpu_anomaly = bool(cpu_positive_error > self.cpu_threshold)
        mem_anomaly = bool(mem_positive_error > self.memory_threshold)

        resource_anomaly = bool(cpu_anomaly or mem_anomaly)

        result = {
            "status": "anomaly" if resource_anomaly else "normal",
            "agent": "pod_lstm_detector",
            "event_type": "pod_lstm_resource_anomaly",
            "resource_anomaly": resource_anomaly,

            "cpu_anomaly": cpu_anomaly,
            "memory_anomaly": mem_anomaly,

            "actual_cpu": actual_cpu,
            "predicted_cpu": predicted_cpu,
            "cpu_positive_error": float(cpu_positive_error),
            "cpu_threshold": self.cpu_threshold,

            "actual_mem_log": actual_mem,
            "predicted_mem_log": predicted_mem,
            "memory_positive_error": float(mem_positive_error),
            "memory_threshold": self.memory_threshold,

            "namespace": current.get("namespace"),
            "pod_name": current.get("pod_name"),
            "node_name": current.get("node_name"),
            "timestamp": str(current.get("timestamp", "")),
            "window_size": self.window_size,
            "sampling_interval_seconds": self.sampling_interval_seconds,
            "features": self.features,
        }

        if resource_anomaly:
            result["event"] = self._build_event(result)

        return result

    def _build_event(self, result: Dict[str, Any]) -> Dict[str, Any]:
        anomaly_types = []

        if result.get("cpu_anomaly"):
            anomaly_types.append("pod_cpu_lstm_anomaly")

        if result.get("memory_anomaly"):
            anomaly_types.append("pod_memory_lstm_anomaly")

        severity = "critical" if result.get("actual_cpu", 0.0) >= 0.90 else "warning"

        summary_parts = []

        if result.get("cpu_anomaly"):
            summary_parts.append(
                f"Pod CPU is higher than expected: actual {result['actual_cpu']:.4f}, "
                f"predicted {result['predicted_cpu']:.4f}."
            )

        if result.get("memory_anomaly"):
            summary_parts.append(
                f"Pod memory is higher than expected: actual log {result['actual_mem_log']:.4f}, "
                f"predicted log {result['predicted_mem_log']:.4f}."
            )

        return {
            "source_agent": "pod_lstm_metrics_agent",
            "agent": "pod_lstm_metrics_agent",
            "event_type": "pod_lstm_resource_anomaly",
            "anomaly_type": "PodLSTMResourceAnomaly",
            "severity": severity,
            "namespace": result.get("namespace"),
            "pod_name": result.get("pod_name"),
            "node_name": result.get("node_name"),
            "timestamp": result.get("timestamp"),
            "summary": " ".join(summary_parts),
            "anomaly_types": anomaly_types,
            "metrics": {
                "actual_cpu": result.get("actual_cpu"),
                "predicted_cpu": result.get("predicted_cpu"),
                "cpu_positive_error": result.get("cpu_positive_error"),
                "cpu_threshold": result.get("cpu_threshold"),
                "actual_mem_log": result.get("actual_mem_log"),
                "predicted_mem_log": result.get("predicted_mem_log"),
                "memory_positive_error": result.get("memory_positive_error"),
                "memory_threshold": result.get("memory_threshold"),
            },
            "evidence": [
                f"Pod: {result.get('namespace')}/{result.get('pod_name')}",
                f"Node: {result.get('node_name')}",
                f"Window size: {result.get('window_size')} readings",
                f"Sampling interval: {result.get('sampling_interval_seconds')} seconds",
            ],
            "recommendations": [
                "Inspect the pod workload and recent traffic pattern.",
                "Check resource requests and limits.",
                "Check whether this pod-level anomaly is related to the primary Kubernetes incident or is a separate noisy-neighbor finding.",
            ],
            "raw_signal": {
                key: value
                for key, value in result.items()
                if key not in {"event", "raw_signal"}
            },
        }

    def predict(self, readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.detect(readings)
