from typing import Any, Dict, List, Optional, Tuple


class KubernetesSignalDetector:
    def __init__(
        self,
        high_restart_threshold: int = 5,
        excluded_namespaces: Optional[List[str]] = None,
    ):
        self.high_restart_threshold = high_restart_threshold
        self.excluded_namespaces = set(
            excluded_namespaces
            or [
                "kube-system",
                "kube-public",
                "kube-node-lease",
            ]
        )

        self.severity_by_reason = {
            "CrashLoopBackOff": "critical",
            "ImagePullBackOff": "critical",
            "ErrImagePull": "critical",
            "InvalidImageName": "critical",
            "CreateContainerConfigError": "critical",
            "CreateContainerError": "critical",
            "RunContainerError": "critical",
            "OOMKilled": "critical",
            "FailedScheduling": "warning",
            "Evicted": "warning",
            "NodeNotReady": "critical",
            "MemoryPressure": "critical",
            "DiskPressure": "critical",
            "PIDPressure": "critical",
            "NetworkUnavailable": "critical",
            "ServiceSelectorMismatch": "critical",
            "EmptyEndpoints": "warning",
            "PodFailed": "critical",
            "PodUnknown": "warning",
            "HighRestartCount": "warning",
            "KubernetesWarningEvent": "warning",
            "CollectorError": "critical",
        }

        self.recommendations_by_reason = {
            "CrashLoopBackOff": [
                "Check pod logs.",
                "Check container command, environment variables, and application startup errors.",
                "Check recent deployment changes.",
            ],
            "ImagePullBackOff": [
                "Verify image name and tag.",
                "Check registry access and imagePullSecrets.",
                "Check network access from the node to the image registry.",
            ],
            "ErrImagePull": [
                "Verify image exists in the registry.",
                "Check image tag spelling.",
                "Check registry authentication.",
            ],
            "InvalidImageName": [
                "Check image name format.",
                "Verify registry/image/tag syntax.",
            ],
            "OOMKilled": [
                "Check container memory limits.",
                "Check application memory usage.",
                "Consider increasing memory limit or optimizing memory consumption.",
            ],
            "FailedScheduling": [
                "Check node capacity and pod resource requests.",
                "Check taints, tolerations, node selectors, and affinity rules.",
            ],
            "HighRestartCount": [
                "Check pod logs and previous container logs.",
                "Inspect liveness/readiness probes.",
                "Check application crash patterns.",
            ],
            "ServiceSelectorMismatch": [
                "Compare service selector with pod labels.",
                "Check whether endpoints are created for the service.",
            ],
            "EmptyEndpoints": [
                "Check if pods matching the service selector are running.",
                "Verify service selector labels.",
            ],
            "NodeNotReady": [
                "Check node status.",
                "Check kubelet and container runtime.",
                "Check node network and resource pressure.",
            ],
        }

        self.ignored_transient_waiting_reasons = {
            "ContainerCreating",
            "PodInitializing",
        }

    def detect(self, k8s_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        if k8s_data.get("error"):
            signals.append(
                self._build_signal(
                    signal="CollectorError",
                    category="collector_error",
                    severity="critical",
                    summary="Kubernetes collector failed to collect cluster state.",
                    evidence=[str(k8s_data.get("error"))],
                    namespace=k8s_data.get("namespace"),
                    raw={"error": k8s_data.get("error")},
                )
            )
            return signals

        events = k8s_data.get("events", []) or []
        related_events = self._index_events(events)

        signals.extend(self._detect_pod_signals(k8s_data, related_events))
        signals.extend(self._detect_service_endpoint_signals(k8s_data))
        signals.extend(self._detect_node_signals(k8s_data))
        signals.extend(self._detect_warning_event_signals(events))

        return self._deduplicate(signals)

    def _detect_pod_signals(
        self,
        k8s_data: Dict[str, Any],
        related_events: Dict[Tuple[str, str], List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        signals = []

        for pod in k8s_data.get("pods", []) or []:
            metadata = pod.get("metadata") or {}
            status = pod.get("status") or {}
            spec = pod.get("spec") or {}

            pod_name = metadata.get("name")
            namespace = metadata.get("namespace") or k8s_data.get("namespace")

            if self._is_excluded_namespace(namespace):
                continue

            node_name = spec.get("node_name")
            phase = status.get("phase")

            pod_events = related_events.get((namespace, pod_name), [])

            if phase in {"Failed", "Unknown"}:
                signal_name = "PodFailed" if phase == "Failed" else "PodUnknown"
                signals.append(
                    self._build_signal(
                        signal=signal_name,
                        category="pod_phase",
                        severity=self._severity(signal_name),
                        namespace=namespace,
                        pod_name=pod_name,
                        node_name=node_name,
                        summary=f"Pod {pod_name} is in {phase} phase.",
                        evidence=self._event_evidence(pod_events) + [
                            f"Pod phase: {phase}",
                        ],
                        raw={"phase": phase},
                    )
                )

            container_statuses = status.get("container_statuses") or []

            for container_status in container_statuses:
                container_name = container_status.get("name")
                restart_count = container_status.get("restart_count", 0) or 0

                state = container_status.get("state") or {}
                waiting = state.get("waiting") or {}
                terminated = state.get("terminated") or {}

                waiting_reason = waiting.get("reason")
                waiting_message = waiting.get("message")

                if waiting_reason and waiting_reason not in self.ignored_transient_waiting_reasons:
                    signals.append(
                        self._build_signal(
                            signal=waiting_reason,
                            category="container_waiting",
                            severity=self._severity(waiting_reason),
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container_name,
                            node_name=node_name,
                            summary=f"Container {container_name} in pod {pod_name} is waiting: {waiting_reason}.",
                            evidence=self._event_evidence(pod_events) + [
                                f"Waiting reason: {waiting_reason}",
                                f"Waiting message: {waiting_message}",
                                f"Pod phase: {phase}",
                                f"Restart count: {restart_count}",
                            ],
                            raw={
                                "waiting_reason": waiting_reason,
                                "waiting_message": waiting_message,
                                "phase": phase,
                                "restart_count": restart_count,
                            },
                        )
                    )

                terminated_reason = terminated.get("reason")
                terminated_message = terminated.get("message")

                if terminated_reason and terminated_reason != "Completed":
                    signals.append(
                        self._build_signal(
                            signal=terminated_reason,
                            category="container_terminated",
                            severity=self._severity(terminated_reason),
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container_name,
                            node_name=node_name,
                            summary=f"Container {container_name} in pod {pod_name} terminated: {terminated_reason}.",
                            evidence=self._event_evidence(pod_events) + [
                                f"Terminated reason: {terminated_reason}",
                                f"Terminated message: {terminated_message}",
                                f"Restart count: {restart_count}",
                            ],
                            raw={
                                "terminated_reason": terminated_reason,
                                "terminated_message": terminated_message,
                                "restart_count": restart_count,
                            },
                        )
                    )

                last_state = container_status.get("last_state") or {}
                last_terminated = last_state.get("terminated") or {}
                last_reason = last_terminated.get("reason")

                if last_reason and last_reason != "Completed":
                    should_report_last_state = (
                        last_reason == "OOMKilled"
                        or restart_count > self.high_restart_threshold
                    )

                    if should_report_last_state:
                        signals.append(
                            self._build_signal(
                                signal=last_reason,
                                category="container_last_termination",
                                severity=self._severity(last_reason),
                                namespace=namespace,
                                pod_name=pod_name,
                                container_name=container_name,
                                node_name=node_name,
                                summary=f"Container {container_name} in pod {pod_name} previously terminated: {last_reason}.",
                                evidence=self._event_evidence(pod_events) + [
                                    f"Last terminated reason: {last_reason}",
                                    f"Restart count: {restart_count}",
                                ],
                                raw={
                                    "last_terminated_reason": last_reason,
                                    "restart_count": restart_count,
                                },
                            )
                        )

                if restart_count > self.high_restart_threshold:
                    signals.append(
                        self._build_signal(
                            signal="HighRestartCount",
                            category="container_restarts",
                            severity=self._severity("HighRestartCount"),
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container_name,
                            node_name=node_name,
                            summary=f"Container {container_name} in pod {pod_name} has high restart count.",
                            evidence=self._event_evidence(pod_events) + [
                                f"Restart count: {restart_count}",
                                f"Threshold: {self.high_restart_threshold}",
                            ],
                            raw={
                                "restart_count": restart_count,
                                "threshold": self.high_restart_threshold,
                            },
                        )
                    )

        return signals

    def _detect_service_endpoint_signals(self, k8s_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        endpoints_by_name = {
            (ep.get("metadata") or {}).get("name"): ep
            for ep in k8s_data.get("endpoints", []) or []
        }

        for service in k8s_data.get("services", []) or []:
            metadata = service.get("metadata") or {}
            spec = service.get("spec") or {}

            service_name = metadata.get("name")
            namespace = metadata.get("namespace") or k8s_data.get("namespace")

            if self._is_excluded_namespace(namespace):
                continue

            if service_name == "kubernetes":
                continue

            selector = spec.get("selector") or {}
            endpoint = endpoints_by_name.get(service_name)
            subsets = (endpoint or {}).get("subsets") or []

            if selector and not subsets:
                signals.append(
                    self._build_signal(
                        signal="ServiceSelectorMismatch",
                        category="service_endpoint",
                        severity=self._severity("ServiceSelectorMismatch"),
                        namespace=namespace,
                        service_name=service_name,
                        summary=f"Service {service_name} has selector but no ready endpoints.",
                        evidence=[
                            f"Service selector: {selector}",
                            "Endpoint subsets are empty.",
                        ],
                        raw={
                            "selector": selector,
                            "subsets": subsets,
                        },
                    )
                )

        for endpoint in k8s_data.get("endpoints", []) or []:
            metadata = endpoint.get("metadata") or {}
            endpoint_name = metadata.get("name")
            namespace = metadata.get("namespace") or k8s_data.get("namespace")

            if self._is_excluded_namespace(namespace):
                continue

            if endpoint_name == "kubernetes":
                continue

            subsets = endpoint.get("subsets") or []

            if not subsets:
                signals.append(
                    self._build_signal(
                        signal="EmptyEndpoints",
                        category="service_endpoint",
                        severity=self._severity("EmptyEndpoints"),
                        namespace=namespace,
                        service_name=endpoint_name,
                        summary=f"Endpoint {endpoint_name} has no subsets.",
                        evidence=[
                            "Endpoint subsets are empty.",
                        ],
                        raw={"subsets": subsets},
                    )
                )

        return signals

    def _detect_node_signals(self, k8s_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        for node in k8s_data.get("nodes", []) or []:
            metadata = node.get("metadata") or {}
            status = node.get("status") or {}

            node_name = metadata.get("name")
            conditions = status.get("conditions") or []

            for condition in conditions:
                condition_type = condition.get("type")
                condition_status = condition.get("status")
                reason = condition.get("reason")
                message = condition.get("message")

                if condition_type == "Ready" and condition_status != "True":
                    signals.append(
                        self._build_signal(
                            signal="NodeNotReady",
                            category="node_condition",
                            severity=self._severity("NodeNotReady"),
                            node_name=node_name,
                            summary=f"Node {node_name} is not Ready.",
                            evidence=[
                                f"Condition: Ready={condition_status}",
                                f"Reason: {reason}",
                                f"Message: {message}",
                            ],
                            raw=condition,
                        )
                    )

                if condition_type in {"MemoryPressure", "DiskPressure", "PIDPressure", "NetworkUnavailable"} and condition_status == "True":
                    signals.append(
                        self._build_signal(
                            signal=condition_type,
                            category="node_condition",
                            severity=self._severity(condition_type),
                            node_name=node_name,
                            summary=f"Node {node_name} reports {condition_type}.",
                            evidence=[
                                f"Condition: {condition_type}={condition_status}",
                                f"Reason: {reason}",
                                f"Message: {message}",
                            ],
                            raw=condition,
                        )
                    )

        return signals

    def _detect_warning_event_signals(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        signals = []

        for event in events:
            event_type = event.get("type")
            reason = event.get("reason")
            message = event.get("message")
            involved_object = event.get("involved_object") or {}

            if event_type != "Warning":
                continue

            namespace = involved_object.get("namespace") or (event.get("metadata") or {}).get("namespace")

            if self._is_excluded_namespace(namespace):
                continue

            object_kind = involved_object.get("kind")
            object_name = involved_object.get("name")

            signals.append(
                self._build_signal(
                    signal=reason or "KubernetesWarningEvent",
                    category="kubernetes_warning_event",
                    severity=self._severity(reason or "KubernetesWarningEvent"),
                    namespace=namespace,
                    pod_name=object_name if object_kind == "Pod" else None,
                    node_name=object_name if object_kind == "Node" else None,
                    service_name=object_name if object_kind == "Service" else None,
                    summary=f"Kubernetes warning event detected: {reason}.",
                    evidence=[
                        f"Object: {object_kind}/{object_name}",
                        f"Reason: {reason}",
                        f"Message: {message}",
                    ],
                    raw={
                        "event_type": event_type,
                        "reason": reason,
                        "message": message,
                        "object_kind": object_kind,
                        "object_name": object_name,
                    },
                )
            )

        return signals

    def _index_events(self, events: List[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        indexed = {}

        for event in events:
            involved_object = event.get("involved_object") or {}

            if involved_object.get("kind") != "Pod":
                continue

            namespace = involved_object.get("namespace") or (event.get("metadata") or {}).get("namespace")
            name = involved_object.get("name")

            if not namespace or not name:
                continue

            indexed.setdefault((namespace, name), []).append(event)

        return indexed

    def _event_evidence(self, events: List[Dict[str, Any]], limit: int = 3) -> List[str]:
        evidence = []
        warning_events = [event for event in events if event.get("type") == "Warning"]

        for event in warning_events[-limit:]:
            reason = event.get("reason")
            message = event.get("message")
            evidence.append(f"Kubernetes event: {reason} - {message}")

        return evidence

    def _is_excluded_namespace(self, namespace: Optional[str]) -> bool:
        return namespace in self.excluded_namespaces

    def _severity(self, reason: Optional[str]) -> str:
        if not reason:
            return "warning"

        return self.severity_by_reason.get(reason, "warning")

    def _recommendations(self, reason: Optional[str]) -> List[str]:
        if not reason:
            return ["Inspect Kubernetes events and object description."]

        return self.recommendations_by_reason.get(
            reason,
            ["Inspect Kubernetes events, pod description, and related logs."],
        )

    def _build_signal(
        self,
        signal: str,
        category: str,
        severity: str,
        summary: str,
        evidence: List[str],
        namespace: Optional[str] = None,
        pod_name: Optional[str] = None,
        container_name: Optional[str] = None,
        node_name: Optional[str] = None,
        service_name: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "signal": signal,
            "category": category,
            "severity": severity,
            "namespace": namespace,
            "pod_name": pod_name,
            "container_name": container_name,
            "node_name": node_name,
            "service_name": service_name,
            "summary": summary,
            "evidence": [item for item in evidence if item],
            "recommendations": self._recommendations(signal),
            "raw": raw or {},
        }

    def _deduplicate(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        unique_signals = []

        for signal in signals:
            key = (
                signal.get("signal"),
                signal.get("category"),
                signal.get("namespace"),
                signal.get("pod_name"),
                signal.get("container_name"),
                signal.get("node_name"),
                signal.get("service_name"),
            )

            if key in seen:
                continue

            seen.add(key)
            unique_signals.append(signal)

        return unique_signals



