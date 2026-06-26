import time
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional

from kubernetes import client, config


class KubernetesMetricsCollector:
    def __init__(
        self,
        node_name: Optional[str] = None,
        poll_interval_seconds: int = 10,
        load_config: bool = True,
    ):
        self.node_name = node_name
        self.poll_interval_seconds = poll_interval_seconds

        if load_config:
            self._load_kubernetes_config()

        self.core_v1 = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()

    def _load_kubernetes_config(self) -> None:
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _parse_cpu_to_cores(self, cpu_value: str) -> float:
        # Examples: 232m, 123456789n, 2
        if cpu_value.endswith("n"):
            return float(cpu_value[:-1]) / 1_000_000_000

        if cpu_value.endswith("u"):
            return float(cpu_value[:-1]) / 1_000_000

        if cpu_value.endswith("m"):
            return float(cpu_value[:-1]) / 1000

        return float(cpu_value)

    def _parse_memory_to_bytes(self, memory_value: str) -> float:
        # Examples: 776Mi, 1024Ki, 2Gi
        units = {
            "Ki": 1024,
            "Mi": 1024 ** 2,
            "Gi": 1024 ** 3,
            "Ti": 1024 ** 4,
            "K": 1000,
            "M": 1000 ** 2,
            "G": 1000 ** 3,
        }

        for suffix, multiplier in units.items():
            if memory_value.endswith(suffix):
                return float(memory_value[:-len(suffix)]) * multiplier

        return float(memory_value)

    def _parse_cpu_capacity_to_cores(self, capacity_value: str) -> float:
        return self._parse_cpu_to_cores(capacity_value)

    def _parse_memory_capacity_to_bytes(self, capacity_value: str) -> float:
        return self._parse_memory_to_bytes(capacity_value)

    def _get_node_capacity(self) -> Dict[str, Dict[str, float]]:
        capacities = {}

        nodes = self.core_v1.list_node()

        for node in nodes.items:
            name = node.metadata.name
            capacity = node.status.capacity or {}

            cpu_capacity = capacity.get("cpu", "1")
            memory_capacity = capacity.get("memory", "1Ki")

            capacities[name] = {
                "cpu_cores": self._parse_cpu_capacity_to_cores(cpu_capacity),
                "memory_bytes": self._parse_memory_capacity_to_bytes(memory_capacity),
            }

        return capacities

    def collect_once(self) -> Dict[str, float]:
        node_capacities = self._get_node_capacity()

        metrics = self.custom_api.list_cluster_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            plural="nodes",
        )

        for item in metrics.get("items", []):
            name = item["metadata"]["name"]

            if self.node_name and name != self.node_name:
                continue

            usage = item.get("usage", {})

            cpu_cores_used = self._parse_cpu_to_cores(usage["cpu"])
            memory_bytes_used = self._parse_memory_to_bytes(usage["memory"])

            capacity = node_capacities.get(name, {})
            cpu_capacity = capacity.get("cpu_cores", 1)
            memory_capacity = capacity.get("memory_bytes", 1)

            cpu_usage = cpu_cores_used / cpu_capacity if cpu_capacity else 0.0
            memory_usage = memory_bytes_used / memory_capacity if memory_capacity else 0.0

            return {
                "timestamp": self._now_utc(),
                "node_name": name,
                "cpu_usage": float(cpu_usage),
                "memory_usage": float(memory_usage),
            }

        raise ValueError(
            f"No node metrics found for node_name={self.node_name}. "
            "Check kubectl top nodes and node name."
        )

    def stream(self, limit: Optional[int] = None) -> Iterator[Dict[str, float]]:
        count = 0

        while limit is None or count < limit:
            yield self.collect_once()
            count += 1

            if limit is None or count < limit:
                time.sleep(self.poll_interval_seconds)



