import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf


class ResourceDetector:
    """
    V7 Resource Detector:
    - Uses 20 historical readings to predict the next/current reading.
    - Uses Egypt timezone for hour_sin/hour_cos.
    - Uses positive error only: actual - predicted.
    - Adds pressure guardrails for high sustained CPU/Memory.
    """

    def __init__(self, artifact_dir: str = "artifacts/resource_detector_v7_egypt_timeaware"):
        self.artifact_dir = Path(artifact_dir)

        self.model_path = self.artifact_dir / "model.keras"
        self.x_scaler_path = self.artifact_dir / "x_scaler.pkl"
        self.y_scaler_path = self.artifact_dir / "y_scaler.pkl"
        self.config_path = self.artifact_dir / "config.json"

        self._validate_artifacts()

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.window_size = int(self.config.get("window_size", 20))
        self.features = list(self.config.get(
            "features",
            ["cpu_usage", "memory_usage", "hour_sin", "hour_cos"]
        ))

        thresholds = self.config.get("thresholds", {})
        self.cpu_threshold = float(thresholds.get("cpu_error_threshold", 0.1336273424293687))
        self.memory_threshold = float(thresholds.get("memory_error_threshold", 0.07642046739858067))

        pressure_thresholds = self.config.get("pressure_thresholds", {})
        self.cpu_pressure_threshold = float(pressure_thresholds.get("cpu_pressure_threshold", 0.85))
        self.memory_pressure_threshold = float(pressure_thresholds.get("memory_pressure_threshold", 0.85))

        self.timezone_name = self.config.get("timezone", "Africa/Cairo")
        self.timezone = ZoneInfo(self.timezone_name)

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
                "Missing detector artifact files:\n" + "\n".join(missing)
            )

    def _to_cairo_timestamp(self, value: Any) -> pd.Timestamp:
        if value is None or value == "":
            return pd.Timestamp.now(tz=self.timezone)

        ts = pd.to_datetime(value, utc=True, errors="coerce")

        if pd.isna(ts):
            return pd.Timestamp.now(tz=self.timezone)

        return ts.tz_convert(self.timezone)

    def _prepare_history_and_current(
        self,
        readings: List[Dict[str, Any]]
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        required_size = self.window_size + 1

        if len(readings) < required_size:
            raise ValueError(
                f"Need at least {required_size} readings: "
                f"{self.window_size} history + 1 current. Got {len(readings)}."
            )

        history = readings[-required_size:-1]
        current = readings[-1]

        history_df = pd.DataFrame(history).copy()

        if "cpu_usage" not in history_df.columns:
            raise ValueError("Missing cpu_usage in readings")

        if "memory_usage" not in history_df.columns:
            raise ValueError("Missing memory_usage in readings")

        if "timestamp" not in history_df.columns:
            now = pd.Timestamp.now(tz=self.timezone)
            history_df["timestamp"] = [
                now - pd.Timedelta(seconds=30 * (self.window_size - i))
                for i in range(self.window_size)
            ]

        history_df["timestamp_cairo"] = history_df["timestamp"].apply(self._to_cairo_timestamp)
        history_df["hour"] = history_df["timestamp_cairo"].dt.hour

        history_df["hour_sin"] = np.sin(2 * np.pi * history_df["hour"] / 24)
        history_df["hour_cos"] = np.cos(2 * np.pi * history_df["hour"] / 24)

        for col in self.features:
            if col not in history_df.columns:
                raise ValueError(f"Missing required feature: {col}")

        history_df["cpu_usage"] = history_df["cpu_usage"].astype(float).clip(0.0, 1.0)
        history_df["memory_usage"] = history_df["memory_usage"].astype(float).clip(0.0, 1.0)

        return history_df, current

    def _predict_scaled(self, X: np.ndarray) -> np.ndarray:
        pred = self.model.predict(X, verbose=0)

        if isinstance(pred, dict):
            cpu_pred = pred["cpu_output"]
            memory_pred = pred["memory_output"]

        elif isinstance(pred, (list, tuple)):
            output_names = list(getattr(self.model, "output_names", []))

            if "cpu_output" in output_names and "memory_output" in output_names:
                cpu_pred = pred[output_names.index("cpu_output")]
                memory_pred = pred[output_names.index("memory_output")]
            else:
                cpu_pred, memory_pred = pred

        else:
            if pred.shape[-1] == 2:
                cpu_pred = pred[:, 0:1]
                memory_pred = pred[:, 1:2]
            else:
                raise ValueError(
                    f"Unsupported model output shape: {pred.shape}"
                )

        return np.concatenate(
            [
                np.asarray(cpu_pred).reshape(-1, 1),
                np.asarray(memory_pred).reshape(-1, 1),
            ],
            axis=1
        )

    def detect(self, readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        history_df, current = self._prepare_history_and_current(readings)

        X = self.x_scaler.transform(history_df[self.features])
        X = X.reshape(1, self.window_size, len(self.features))

        pred_scaled = self._predict_scaled(X)
        pred = self.y_scaler.inverse_transform(pred_scaled)[0]

        predicted_cpu = float(np.clip(pred[0], 0.0, 1.0))
        predicted_memory = float(np.clip(pred[1], 0.0, 1.0))

        actual_cpu = float(np.clip(float(current.get("cpu_usage", 0.0)), 0.0, 1.0))
        actual_memory = float(np.clip(float(current.get("memory_usage", 0.0)), 0.0, 1.0))

        cpu_error = abs(actual_cpu - predicted_cpu)
        memory_error = abs(actual_memory - predicted_memory)

        cpu_positive_error = actual_cpu - predicted_cpu
        memory_positive_error = actual_memory - predicted_memory

        cpu_pattern_anomaly = bool(cpu_positive_error > self.cpu_threshold)
        memory_pattern_anomaly = bool(memory_positive_error > self.memory_threshold)

        cpu_pressure_anomaly = bool(actual_cpu >= self.cpu_pressure_threshold)
        memory_pressure_anomaly = bool(actual_memory >= self.memory_pressure_threshold)

        cpu_anomaly = bool(cpu_pattern_anomaly or cpu_pressure_anomaly)
        memory_anomaly = bool(memory_pattern_anomaly or memory_pressure_anomaly)

        resource_anomaly = bool(cpu_anomaly or memory_anomaly)

        anomaly_types = []
        if cpu_anomaly:
            anomaly_types.append("cpu_anomaly")
        if memory_anomaly:
            anomaly_types.append("memory_anomaly")

        severity = self._severity(
            actual_cpu=actual_cpu,
            actual_memory=actual_memory,
            resource_anomaly=resource_anomaly,
            cpu_pressure_anomaly=cpu_pressure_anomaly,
            memory_pressure_anomaly=memory_pressure_anomaly,
        )

        result = {
            "status": "anomaly" if resource_anomaly else "normal",
            "resource_anomaly": resource_anomaly,

            "cpu_anomaly": cpu_anomaly,
            "memory_anomaly": memory_anomaly,
            "anomaly_types": anomaly_types,
            "severity": severity,

            "actual_cpu": actual_cpu,
            "predicted_cpu": predicted_cpu,
            "cpu_error": float(cpu_error),
            "cpu_positive_error": float(cpu_positive_error),
            "cpu_threshold": self.cpu_threshold,
            "cpu_pattern_anomaly": cpu_pattern_anomaly,
            "cpu_pressure_anomaly": cpu_pressure_anomaly,
            "cpu_pressure_threshold": self.cpu_pressure_threshold,

            "actual_memory": actual_memory,
            "predicted_memory": predicted_memory,
            "memory_error": float(memory_error),
            "memory_positive_error": float(memory_positive_error),
            "memory_threshold": self.memory_threshold,
            "memory_pattern_anomaly": memory_pattern_anomaly,
            "memory_pressure_anomaly": memory_pressure_anomaly,
            "memory_pressure_threshold": self.memory_pressure_threshold,

            "node_name": current.get("node_name", "unknown"),
            "timestamp": str(current.get("timestamp", "")),
            "timezone": self.timezone_name,
            "window_size": self.window_size,
            "features": self.features,
        }

        if resource_anomaly:
            result["event"] = self._build_event(result)

        return result

    def _severity(
        self,
        actual_cpu: float,
        actual_memory: float,
        resource_anomaly: bool,
        cpu_pressure_anomaly: bool,
        memory_pressure_anomaly: bool,
    ) -> str:
        if not resource_anomaly:
            return "normal"

        if actual_cpu >= 0.95 or actual_memory >= 0.95:
            return "critical"

        if cpu_pressure_anomaly or memory_pressure_anomaly:
            return "high"

        return "warning"

    def _build_event(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": "resource_anomaly",
            "agent": "metrics_agent",
            "node_name": result["node_name"],
            "timestamp": result["timestamp"],
            "severity": result["severity"],
            "anomaly_types": result["anomaly_types"],
            "timezone": result["timezone"],

            "summary": self._build_summary(result),

            "evidence": {
                "actual_cpu": result["actual_cpu"],
                "predicted_cpu": result["predicted_cpu"],
                "cpu_error": result["cpu_error"],
                "cpu_positive_error": result["cpu_positive_error"],
                "cpu_threshold": result["cpu_threshold"],
                "cpu_pattern_anomaly": result["cpu_pattern_anomaly"],
                "cpu_pressure_anomaly": result["cpu_pressure_anomaly"],
                "cpu_pressure_threshold": result["cpu_pressure_threshold"],

                "actual_memory": result["actual_memory"],
                "predicted_memory": result["predicted_memory"],
                "memory_error": result["memory_error"],
                "memory_positive_error": result["memory_positive_error"],
                "memory_threshold": result["memory_threshold"],
                "memory_pattern_anomaly": result["memory_pattern_anomaly"],
                "memory_pressure_anomaly": result["memory_pressure_anomaly"],
                "memory_pressure_threshold": result["memory_pressure_threshold"],
            },

            "recommendation_hint": (
                "Check node resource pressure, recent workload changes, pod scheduling, "
                "resource requests/limits, and possible runaway processes."
            ),
        }

    def _build_summary(self, result: Dict[str, Any]) -> str:
        parts = []

        if result["cpu_anomaly"]:
            if result["cpu_pressure_anomaly"]:
                parts.append(
                    f"CPU pressure is high at {result['actual_cpu']:.2%}."
                )
            else:
                parts.append(
                    f"CPU usage is higher than expected: "
                    f"actual {result['actual_cpu']:.2%}, "
                    f"predicted {result['predicted_cpu']:.2%}."
                )

        if result["memory_anomaly"]:
            if result["memory_pressure_anomaly"]:
                parts.append(
                    f"Memory pressure is high at {result['actual_memory']:.2%}."
                )
            else:
                parts.append(
                    f"Memory usage is higher than expected: "
                    f"actual {result['actual_memory']:.2%}, "
                    f"predicted {result['predicted_memory']:.2%}."
                )

        return " ".join(parts) if parts else "No resource anomaly detected."

    def predict(self, readings: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.detect(readings)


