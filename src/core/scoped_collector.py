from typing import Any, Dict, List, Set


class ScopedCollector:
    """
    Wraps an existing collector and filters its output by InvestigationScope.

    Purpose:
    - Keep services/deployments/endpoints namespace-scoped.
    - Filter pods/logs/pod-related events by selected node when node_name is provided.
    """

    def __init__(self, collector: Any, scope: Any):
        self.collector = collector
        self.scope = scope

    def __getattr__(self, name: str) -> Any:
        return getattr(self.collector, name)

    def collect(self, *args, **kwargs):
        return self._call_and_filter("collect", *args, **kwargs)

    def collect_state(self, *args, **kwargs):
        return self._call_and_filter("collect_state", *args, **kwargs)

    def collect_logs(self, *args, **kwargs):
        return self._call_and_filter("collect_logs", *args, **kwargs)

    def run(self, *args, **kwargs):
        return self._call_and_filter("run", *args, **kwargs)

    def _call_and_filter(self, method_name: str, *args, **kwargs):
        method = getattr(self.collector, method_name)
        payload = method(*args, **kwargs)
        return self._filter_payload(payload)

    def _filter_payload(self, payload: Any) -> Any:
        if isinstance(payload, list):
            return [item for item in payload if self._keep_record(item)]

        if not isinstance(payload, dict):
            return payload

        result = dict(payload)

        pods = result.get("pods")
        kept_pod_names: Set[str] = set()

        if isinstance(pods, list):
            filtered_pods = [pod for pod in pods if self._keep_pod(pod)]
            result["pods"] = filtered_pods

            for pod in filtered_pods:
                name = pod.get("pod_name") or pod.get("name") or pod.get("metadata", {}).get("name")
                if name:
                    kept_pod_names.add(name)

        for key in ["logs", "log_records", "containers"]:
            if isinstance(result.get(key), list):
                result[key] = [item for item in result[key] if self._keep_record(item, kept_pod_names)]

        if isinstance(result.get("events"), list):
            result["events"] = [
                event for event in result["events"]
                if self._keep_event(event, kept_pod_names)
            ]

        # Services, endpoints, deployments are namespace-scoped, not node-scoped.
        for key in ["services", "endpoints", "deployments"]:
            if isinstance(result.get(key), list):
                result[key] = [item for item in result[key] if self._keep_namespace(item)]

        return result

    def _keep_namespace(self, item: Dict[str, Any]) -> bool:
        namespace = getattr(self.scope, "namespace", None)

        if not namespace:
            return True

        item_namespace = (
            item.get("namespace")
            or item.get("metadata", {}).get("namespace")
        )

        return not item_namespace or item_namespace == namespace

    def _keep_pod(self, pod: Dict[str, Any]) -> bool:
        if not self._keep_namespace(pod):
            return False

        node_name = getattr(self.scope, "node_name", None)

        if not node_name:
            return True

        pod_node = (
            pod.get("node_name")
            or pod.get("node")
            or pod.get("spec", {}).get("nodeName")
        )

        return not pod_node or pod_node == node_name

    def _keep_record(self, record: Any, kept_pod_names: Set[str] = None) -> bool:
        if not isinstance(record, dict):
            return True

        kept_pod_names = kept_pod_names or set()

        if not self._keep_namespace(record):
            return False

        node_name = getattr(self.scope, "node_name", None)

        if node_name:
            record_node = record.get("node_name") or record.get("node")

            if record_node and record_node != node_name:
                return False

        pod_name = record.get("pod_name") or record.get("pod")

        if kept_pod_names and pod_name and pod_name not in kept_pod_names:
            return False

        return True

    def _keep_event(self, event: Dict[str, Any], kept_pod_names: Set[str]) -> bool:
        if not self._keep_namespace(event):
            return False

        node_name = getattr(self.scope, "node_name", None)

        event_node = event.get("node_name") or event.get("node")
        if node_name and event_node and event_node != node_name:
            return False

        pod_name = (
            event.get("pod_name")
            or event.get("involved_object_name")
            or event.get("involvedObject", {}).get("name")
        )

        object_kind = (
            event.get("involved_object_kind")
            or event.get("involvedObject", {}).get("kind")
            or event.get("kind")
        )

        if object_kind and str(object_kind).lower() == "node":
            return not node_name or pod_name == node_name or event_node == node_name

        if kept_pod_names and pod_name:
            return pod_name in kept_pod_names

        return True
