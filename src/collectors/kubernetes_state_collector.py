from typing import Any, Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


class KubernetesStateCollector:
    def __init__(
        self,
        namespace: Optional[str] = "default",
        all_namespaces: bool = False,
        load_config: bool = True,
    ):
        self.namespace = namespace
        self.all_namespaces = all_namespaces

        if load_config:
            self._load_kubernetes_config()

        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    def _load_kubernetes_config(self) -> None:
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()

    def _safe_to_dict_list(self, items: List[Any]) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in items]

    def collect(self) -> Dict[str, Any]:
        try:
            if self.all_namespaces:
                pods = self.core_v1.list_pod_for_all_namespaces()
                events = self.core_v1.list_event_for_all_namespaces()
                services = self.core_v1.list_service_for_all_namespaces()
                endpoints = self.core_v1.list_endpoints_for_all_namespaces()
                deployments = self.apps_v1.list_deployment_for_all_namespaces()
            else:
                namespace = self.namespace or "default"

                pods = self.core_v1.list_namespaced_pod(namespace)
                events = self.core_v1.list_namespaced_event(namespace)
                services = self.core_v1.list_namespaced_service(namespace)
                endpoints = self.core_v1.list_namespaced_endpoints(namespace)
                deployments = self.apps_v1.list_namespaced_deployment(namespace)

            nodes = self.core_v1.list_node()

            return {
                "collector": "kubernetes_state_collector",
                "namespace": self.namespace,
                "all_namespaces": self.all_namespaces,
                "pods": self._safe_to_dict_list(pods.items),
                "events": self._safe_to_dict_list(events.items),
                "services": self._safe_to_dict_list(services.items),
                "endpoints": self._safe_to_dict_list(endpoints.items),
                "deployments": self._safe_to_dict_list(deployments.items),
                "nodes": self._safe_to_dict_list(nodes.items),
                "error": None,
            }

        except ApiException as exc:
            return {
                "collector": "kubernetes_state_collector",
                "namespace": self.namespace,
                "all_namespaces": self.all_namespaces,
                "pods": [],
                "events": [],
                "services": [],
                "endpoints": [],
                "deployments": [],
                "nodes": [],
                "error": {
                    "type": "ApiException",
                    "status": exc.status,
                    "reason": exc.reason,
                    "body": exc.body,
                },
            }

        except Exception as exc:
            return {
                "collector": "kubernetes_state_collector",
                "namespace": self.namespace,
                "all_namespaces": self.all_namespaces,
                "pods": [],
                "events": [],
                "services": [],
                "endpoints": [],
                "deployments": [],
                "nodes": [],
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }



