from typing import Any, Dict, List, Optional


class ConfigSignalDetector:
    """
    Detects node/config signals:
    - Node health/config from Ansible.
    - Kubernetes config issues from API state.
    """

    def __init__(
        self,
        disk_critical_threshold: float = 90.0,
        memory_critical_threshold: float = 90.0,
        memory_warning_threshold: float = 80.0,
        enable_best_practice_checks: bool = False,
    ):
        self.disk_critical_threshold = disk_critical_threshold
        self.memory_critical_threshold = memory_critical_threshold
        self.memory_warning_threshold = memory_warning_threshold
        self.enable_best_practice_checks = enable_best_practice_checks

    def detect(self, config_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        if config_data.get("error"):
            signals.append(
                self._build_signal(
                    signal="ConfigCollectorError",
                    category="collector_error",
                    severity="warning",
                    summary="Config collector failed.",
                    evidence=[str(config_data.get("error"))],
                    node_name=config_data.get("node_name"),
                    raw={"error": config_data.get("error")},
                )
            )
            return signals

        if config_data.get("kubernetes_error"):
            signals.append(
                self._build_signal(
                    signal="KubernetesConfigCollectorError",
                    category="collector_error",
                    severity="warning",
                    summary="Could not collect Kubernetes config state.",
                    evidence=[str(config_data.get("kubernetes_error"))],
                    node_name=config_data.get("node_name"),
                    raw={"kubernetes_error": config_data.get("kubernetes_error")},
                )
            )

        signals.extend(self._detect_node_config(config_data))
        signals.extend(self._detect_kubernetes_config(config_data))

        return self._deduplicate(signals)

    def _detect_node_config(self, config_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        node = config_data.get("node", {}) or {}
        node_name = config_data.get("node_name") or node.get("node_name")

        disk_percent = self._parse_percent(node.get("disk_usage"))
        memory_percent = self._parse_float(node.get("memory_usage_percent"))

        if disk_percent is not None and disk_percent >= self.disk_critical_threshold:
            signals.append(
                self._build_signal(
                    signal="HighDiskUsage",
                    category="node_disk",
                    severity="critical",
                    node_name=node_name,
                    summary=f"Node {node_name} disk usage is high at {disk_percent:.2f}%.",
                    evidence=[
                        f"disk_usage: {node.get('disk_usage')}",
                        f"threshold: {self.disk_critical_threshold}%",
                    ],
                    raw={"disk_usage_percent": disk_percent},
                )
            )

        if memory_percent is not None:
            severity = None

            if memory_percent >= self.memory_critical_threshold:
                severity = "critical"
            elif memory_percent >= self.memory_warning_threshold:
                severity = "warning"

            if severity:
                signals.append(
                    self._build_signal(
                        signal="HighMemoryUsage",
                        category="node_memory",
                        severity=severity,
                        node_name=node_name,
                        summary=f"Node {node_name} memory usage is high at {memory_percent:.2f}%.",
                        evidence=[
                            f"memory_usage: {node.get('memory_usage')}",
                            f"memory_usage_percent: {memory_percent:.2f}%",
                        ],
                        raw={"memory_usage_percent": memory_percent},
                    )
                )

        service_checks = {
            "kubelet_status": ("KubeletDown", "critical"),
            "containerd_status": ("ContainerRuntimeIssue", "critical"),
            "docker_status": ("DockerDown", "warning"),
        }

        for field, (signal_name, severity) in service_checks.items():
            value = node.get(field)

            if value and value not in {"active", "unknown"}:
                signals.append(
                    self._build_signal(
                        signal=signal_name,
                        category="node_service",
                        severity=severity,
                        node_name=node_name,
                        summary=f"{field} is not active on node {node_name}.",
                        evidence=[f"{field}: {value}"],
                        raw={field: value},
                    )
                )

        firewall_status = node.get("firewall_status")
        if firewall_status == "active":
            signals.append(
                self._build_signal(
                    signal="FirewallActive",
                    category="node_network",
                    severity="warning",
                    node_name=node_name,
                    summary=f"Firewall is active on node {node_name}.",
                    evidence=["firewall_status: active"],
                    raw={"firewall_status": firewall_status},
                )
            )

        return signals

    def _detect_kubernetes_config(self, config_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        kubernetes = config_data.get("kubernetes", {}) or {}

        signals = []
        signals.extend(self._detect_service_config(kubernetes))
        signals.extend(self._detect_deployment_config(kubernetes))

        return signals

    def _detect_service_config(self, kubernetes: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        pods = kubernetes.get("pods", []) or []
        services = kubernetes.get("services", []) or []
        endpoints = kubernetes.get("endpoints", []) or []

        endpoint_by_name = {endpoint.get("name"): endpoint for endpoint in endpoints}

        for service in services:
            service_name = service.get("name")

            if service_name == "kubernetes":
                continue

            namespace = service.get("namespace")
            selector = service.get("selector") or {}

            if not selector:
                continue

            matching_pods = [
                pod for pod in pods
                if self._labels_match_selector(pod.get("labels", {}), selector)
            ]

            if not matching_pods:
                signals.append(
                    self._build_signal(
                        signal="ServiceSelectorMismatch",
                        category="kubernetes_service_config",
                        severity="critical",
                        namespace=namespace,
                        service_name=service_name,
                        summary=f"Service {service_name} selector does not match any pods.",
                        evidence=[
                            f"service_selector: {selector}",
                            "matching_pods: 0",
                        ],
                        raw={"selector": selector},
                    )
                )
                continue

            endpoint = endpoint_by_name.get(service_name)
            subsets = (endpoint or {}).get("subsets") or []

            if not subsets:
                signals.append(
                    self._build_signal(
                        signal="EmptyServiceEndpoints",
                        category="kubernetes_service_config",
                        severity="warning",
                        namespace=namespace,
                        service_name=service_name,
                        summary=f"Service {service_name} has matching pods but no ready endpoints.",
                        evidence=[
                            f"service_selector: {selector}",
                            f"matching_pods: {[pod.get('name') for pod in matching_pods]}",
                            "endpoint_subsets: empty",
                        ],
                        raw={"selector": selector},
                    )
                )

            for service_port in service.get("ports", []) or []:
                target_port = service_port.get("target_port")
                port = service_port.get("port")

                if target_port is None:
                    target_port = port

                mismatch = self._target_port_mismatch(target_port, matching_pods)

                if mismatch:
                    signals.append(
                        self._build_signal(
                            signal="ServiceTargetPortMismatch",
                            category="kubernetes_service_config",
                            severity="critical",
                            namespace=namespace,
                            service_name=service_name,
                            summary=f"Service {service_name} targetPort does not match container ports.",
                            evidence=[
                                f"service_port: {port}",
                                f"target_port: {target_port}",
                                f"matching_pods: {[pod.get('name') for pod in matching_pods]}",
                                f"available_container_ports: {mismatch.get('available_ports')}",
                                f"available_named_ports: {mismatch.get('available_named_ports')}",
                            ],
                            raw={
                                "service_port": service_port,
                                "target_port": target_port,
                                **mismatch,
                            },
                        )
                    )

        return signals

    def _detect_deployment_config(self, kubernetes: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        deployments = kubernetes.get("deployments", []) or []

        for deployment in deployments:
            name = deployment.get("name")
            namespace = deployment.get("namespace")
            replicas = deployment.get("replicas") or 0
            available_replicas = deployment.get("available_replicas") or 0

            if replicas > 0 and available_replicas == 0:
                signals.append(
                    self._build_signal(
                        signal="DeploymentNoAvailableReplicas",
                        category="kubernetes_deployment_config",
                        severity="critical",
                        namespace=namespace,
                        deployment_name=name,
                        summary=f"Deployment {name} has no available replicas.",
                        evidence=[
                            f"desired_replicas: {replicas}",
                            f"available_replicas: {available_replicas}",
                        ],
                        raw={"replicas": replicas, "available_replicas": available_replicas},
                    )
                )

            selector = deployment.get("selector") or {}
            template_labels = deployment.get("template_labels") or {}

            if selector and not self._labels_match_selector(template_labels, selector):
                signals.append(
                    self._build_signal(
                        signal="DeploymentSelectorTemplateMismatch",
                        category="kubernetes_deployment_config",
                        severity="critical",
                        namespace=namespace,
                        deployment_name=name,
                        summary=f"Deployment {name} selector does not match pod template labels.",
                        evidence=[
                            f"selector: {selector}",
                            f"template_labels: {template_labels}",
                        ],
                        raw={"selector": selector, "template_labels": template_labels},
                    )
                )

            for container in deployment.get("containers", []) or []:
                image = container.get("image", "")
                image_pull_secrets = deployment.get("image_pull_secrets") or []

                if self._looks_like_private_registry(image) and not image_pull_secrets:
                    signals.append(
                        self._build_signal(
                            signal="MissingImagePullSecret",
                            category="kubernetes_deployment_config",
                            severity="warning",
                            namespace=namespace,
                            deployment_name=name,
                            container_name=container.get("name"),
                            summary=f"Deployment {name} uses a private-looking image without imagePullSecrets.",
                            evidence=[
                                f"image: {image}",
                                "imagePullSecrets: empty",
                            ],
                            raw={"image": image, "image_pull_secrets": image_pull_secrets},
                        )
                    )

                if self.enable_best_practice_checks:
                    resources = container.get("resources") or {}
                    requests = resources.get("requests") or {}
                    limits = resources.get("limits") or {}

                    if not requests or not limits:
                        signals.append(
                            self._build_signal(
                                signal="MissingResourceRequestsLimits",
                                category="kubernetes_deployment_config",
                                severity="warning",
                                namespace=namespace,
                                deployment_name=name,
                                container_name=container.get("name"),
                                summary=f"Container {container.get('name')} in deployment {name} has missing resource requests/limits.",
                                evidence=[
                                    f"requests: {requests}",
                                    f"limits: {limits}",
                                ],
                                raw={"resources": resources},
                            )
                        )

        return signals

    def _target_port_mismatch(self, target_port, matching_pods: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        available_ports = set()
        available_named_ports = set()

        for pod in matching_pods:
            for container in pod.get("containers", []) or []:
                for port in container.get("ports", []) or []:
                    container_port = port.get("container_port")
                    port_name = port.get("name")

                    if container_port is not None:
                        available_ports.add(int(container_port))

                    if port_name:
                        available_named_ports.add(port_name)

        if isinstance(target_port, int):
            if int(target_port) not in available_ports:
                return {
                    "available_ports": sorted(available_ports),
                    "available_named_ports": sorted(available_named_ports),
                }

        else:
            target_text = str(target_port)

            if target_text.isdigit():
                if int(target_text) not in available_ports:
                    return {
                        "available_ports": sorted(available_ports),
                        "available_named_ports": sorted(available_named_ports),
                    }
            else:
                if target_text not in available_named_ports:
                    return {
                        "available_ports": sorted(available_ports),
                        "available_named_ports": sorted(available_named_ports),
                    }

        return None

    def _labels_match_selector(self, labels: Dict[str, str], selector: Dict[str, str]) -> bool:
        for key, value in selector.items():
            if labels.get(key) != value:
                return False

        return True

    def _looks_like_private_registry(self, image: str) -> bool:
        if not image:
            return False

        # Docker image rule:
        # busybox:1.36 is a public image with a tag, not a private registry.
        # A registry exists only when the first component before "/" contains "." or ":" or is localhost.
        if "/" not in image:
            return False

        first_part = image.split("/")[0]
        return "." in first_part or ":" in first_part or first_part == "localhost"

    def _build_signal(
        self,
        signal: str,
        category: str,
        severity: str,
        summary: str,
        evidence: List[str],
        namespace: Optional[str] = None,
        node_name: Optional[str] = None,
        service_name: Optional[str] = None,
        deployment_name: Optional[str] = None,
        pod_name: Optional[str] = None,
        container_name: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "signal": signal,
            "category": category,
            "severity": severity,
            "namespace": namespace,
            "node_name": node_name,
            "service_name": service_name,
            "deployment_name": deployment_name,
            "pod_name": pod_name,
            "container_name": container_name,
            "summary": summary,
            "evidence": [item for item in evidence if item],
            "recommendations": self._recommendations(signal),
            "raw": raw or {},
        }

    def _recommendations(self, signal: str) -> List[str]:
        recommendations = {
            "HighDiskUsage": [
                "Check disk usage and clean unnecessary files.",
                "Inspect container logs, images, and volumes consuming disk.",
            ],
            "HighMemoryUsage": [
                "Check memory-heavy processes.",
                "Correlate with Metrics Agent memory anomaly.",
            ],
            "KubeletDown": [
                "Check kubelet service status.",
                "Restart kubelet if needed.",
                "Inspect kubelet logs and node readiness.",
            ],
            "ContainerRuntimeIssue": [
                "Check container runtime service.",
                "Inspect containerd/docker logs.",
            ],
            "FirewallActive": [
                "Check firewall rules.",
                "Verify Kubernetes NodePort and cluster networking.",
            ],
            "ServiceSelectorMismatch": [
                "Compare service selector with pod labels.",
                "Fix service selector or pod template labels.",
            ],
            "EmptyServiceEndpoints": [
                "Check pod readiness and endpoint generation.",
                "Verify service selector and readiness probes.",
            ],
            "ServiceTargetPortMismatch": [
                "Compare service targetPort with containerPort.",
                "Fix service targetPort or container port definition.",
            ],
            "DeploymentNoAvailableReplicas": [
                "Inspect deployment rollout status.",
                "Check pod events, image pull, scheduling, and readiness failures.",
            ],
            "DeploymentSelectorTemplateMismatch": [
                "Fix deployment selector or pod template labels.",
            ],
            "MissingImagePullSecret": [
                "Add imagePullSecrets or verify registry access.",
                "Check image registry authentication.",
            ],
        }

        return recommendations.get(signal, ["Inspect configuration and related Kubernetes objects."])

    def _parse_percent(self, value) -> Optional[float]:
        if value is None:
            return None

        try:
            return float(str(value).replace("%", "").strip())
        except Exception:
            return None

    def _parse_float(self, value) -> Optional[float]:
        if value is None:
            return None

        try:
            return float(str(value).strip())
        except Exception:
            return None

    def _deduplicate(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        unique = []

        for signal in signals:
            key = (
                signal.get("signal"),
                signal.get("category"),
                signal.get("namespace"),
                signal.get("node_name"),
                signal.get("service_name"),
                signal.get("deployment_name"),
                signal.get("pod_name"),
                signal.get("container_name"),
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(signal)

        return unique




