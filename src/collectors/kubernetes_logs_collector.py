from datetime import datetime, timezone
from typing import Any, Dict, Optional

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


class KubernetesLogsCollector:
    def __init__(
        self,
        namespace: Optional[str] = "default",
        all_namespaces: bool = False,
        tail_lines: int = 200,
        include_previous: bool = True,
        load_config: bool = True,
    ):
        self.namespace = namespace
        self.all_namespaces = all_namespaces
        self.tail_lines = tail_lines
        self.include_previous = include_previous

        if load_config:
            self._load_kubernetes_config()

        self.core_v1 = client.CoreV1Api()

    def _load_kubernetes_config(self) -> None:
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()

    def collect(self) -> Dict[str, Any]:
        try:
            if self.all_namespaces:
                pods_response = self.core_v1.list_pod_for_all_namespaces()
            else:
                namespace = self.namespace or "default"
                pods_response = self.core_v1.list_namespaced_pod(namespace)

            logs = []

            for pod in pods_response.items:
                metadata = pod.metadata
                spec = pod.spec
                status = pod.status

                namespace = metadata.namespace
                pod_name = metadata.name
                node_name = spec.node_name
                pod_phase = status.phase

                containers = list(spec.containers or [])
                init_containers = list(spec.init_containers or [])
                all_containers = containers + init_containers

                restart_counts = self._restart_counts_by_container(status)

                for container in all_containers:
                    container_name = container.name
                    restart_count = restart_counts.get(container_name, 0)

                    current_log, current_error = self._read_log(
                        pod_name=pod_name,
                        namespace=namespace,
                        container_name=container_name,
                        previous=False,
                    )

                    previous_log = ""
                    previous_error = None

                    if self.include_previous and restart_count > 0:
                        previous_log, previous_error = self._read_log(
                            pod_name=pod_name,
                            namespace=namespace,
                            container_name=container_name,
                            previous=True,
                        )

                    logs.append(
                        {
                            "namespace": namespace,
                            "pod_name": pod_name,
                            "container_name": container_name,
                            "node_name": node_name,
                            "pod_phase": pod_phase,
                            "restart_count": restart_count,
                            "current_log": current_log,
                            "previous_log": previous_log,
                            "current_log_error": current_error,
                            "previous_log_error": previous_error,
                        }
                    )

            return {
                "collector": "kubernetes_logs_collector",
                "collected_at": self._now_utc(),
                "namespace": self.namespace,
                "all_namespaces": self.all_namespaces,
                "tail_lines": self.tail_lines,
                "include_previous": self.include_previous,
                "logs": logs,
                "error": None,
            }

        except ApiException as exc:
            return self._error_response(
                "ApiException",
                {"status": exc.status, "reason": exc.reason, "body": exc.body},
            )

        except Exception as exc:
            return self._error_response(
                type(exc).__name__,
                {"message": str(exc)},
            )

    def _read_log(
        self,
        pod_name: str,
        namespace: str,
        container_name: str,
        previous: bool = False,
    ):
        try:
            log_text = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container_name,
                tail_lines=self.tail_lines,
                previous=previous,
            )
            return log_text or "", None

        except ApiException as exc:
            return "", {
                "type": "ApiException",
                "status": exc.status,
                "reason": exc.reason,
                "body": exc.body,
                "previous": previous,
            }

        except Exception as exc:
            return "", {
                "type": type(exc).__name__,
                "message": str(exc),
                "previous": previous,
            }

    def _restart_counts_by_container(self, status) -> Dict[str, int]:
        counts = {}

        for container_status in status.container_statuses or []:
            counts[container_status.name] = container_status.restart_count or 0

        for container_status in status.init_container_statuses or []:
            counts[container_status.name] = container_status.restart_count or 0

        return counts

    def _error_response(self, error_type: str, details: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "collector": "kubernetes_logs_collector",
            "collected_at": self._now_utc(),
            "namespace": self.namespace,
            "all_namespaces": self.all_namespaces,
            "tail_lines": self.tail_lines,
            "include_previous": self.include_previous,
            "logs": [],
            "error": {"type": error_type, **details},
        }

    @staticmethod
    def _now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()



