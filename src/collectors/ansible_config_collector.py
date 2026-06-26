import json
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException


class AnsibleConfigCollector:
    """
    Config Collector:
    - Runs Ansible node checks through WSL.
    - Collects Kubernetes config state from Kubernetes API.
    """

    def __init__(
        self,
        project_wsl_path: str = "/mnt/d/OpsLens-AI",
        inventory_path: str = "ansible/inventory/local_minikube.ini",
        playbook_path: str = "ansible/playbooks/minikube_config_check.yml",
        namespace: str = "default",
        wsl_distro: str = "Ubuntu",
        timeout_seconds: int = 120,
        collect_kubernetes_config: bool = True,
    ):
        self.project_wsl_path = project_wsl_path
        self.inventory_path = inventory_path
        self.playbook_path = playbook_path
        self.namespace = namespace
        self.wsl_distro = wsl_distro
        self.timeout_seconds = timeout_seconds
        self.collect_kubernetes_config = collect_kubernetes_config

    def collect(self) -> Dict[str, Any]:
        ansible_result = self._collect_ansible_node_config()

        kubernetes_config = {}
        kubernetes_error = None

        if self.collect_kubernetes_config:
            try:
                kubernetes_config = self._collect_kubernetes_config()
            except Exception as exc:
                kubernetes_error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }

        if ansible_result.get("error"):
            return {
                **ansible_result,
                "kubernetes": kubernetes_config,
                "kubernetes_error": kubernetes_error,
            }

        return {
            **ansible_result,
            "kubernetes": kubernetes_config,
            "kubernetes_error": kubernetes_error,
        }

    def _collect_ansible_node_config(self) -> Dict[str, Any]:
        bash_command = (
            f"cd {self.project_wsl_path} && "
            f"ansible-playbook -i {self.inventory_path} {self.playbook_path}"
        )

        command = [
            "wsl",
            "-d",
            self.wsl_distro,
            "--",
            "/bin/bash",
            "-lc",
            bash_command,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            parsed = self._parse_msg_json(result.stdout)

            if parsed is None:
                return {
                    "collector": "ansible_config_collector",
                    "collected_at": self._now_utc(),
                    "returncode": result.returncode,
                    "node_name": None,
                    "node": {},
                    "error": {
                        "type": "ParseError",
                        "message": "Could not parse Ansible debug msg.",
                        "command": " ".join(command),
                        "stdout_tail": result.stdout[-3000:],
                        "stderr_tail": result.stderr[-3000:],
                    },
                }

            if "msg" in parsed and isinstance(parsed["msg"], dict):
                parsed = parsed["msg"]

            node_name = parsed.get("node_name", "unknown")

            return {
                "collector": "ansible_config_collector",
                "collected_at": self._now_utc(),
                "returncode": result.returncode,
                "node_name": node_name,
                "node": parsed,
                "error": None,
            }

        except subprocess.TimeoutExpired:
            return self._error_response(
                "AnsibleTimeout",
                f"Ansible command timed out after {self.timeout_seconds} seconds.",
            )

        except FileNotFoundError:
            return self._error_response(
                "WSLNotFound",
                "wsl command was not found from Windows.",
            )

        except Exception as exc:
            return self._error_response(type(exc).__name__, str(exc))

    def _collect_kubernetes_config(self) -> Dict[str, Any]:
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()

        core_v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()

        pods = core_v1.list_namespaced_pod(self.namespace).items
        services = core_v1.list_namespaced_service(self.namespace).items
        endpoints = core_v1.list_namespaced_endpoints(self.namespace).items
        deployments = apps_v1.list_namespaced_deployment(self.namespace).items

        return {
            "namespace": self.namespace,
            "pods": [self._simplify_pod(pod) for pod in pods],
            "services": [self._simplify_service(service) for service in services],
            "endpoints": [self._simplify_endpoint(endpoint) for endpoint in endpoints],
            "deployments": [self._simplify_deployment(deployment) for deployment in deployments],
        }

    def _simplify_pod(self, pod) -> Dict[str, Any]:
        metadata = pod.metadata
        spec = pod.spec
        status = pod.status

        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "labels": metadata.labels or {},
            "node_name": spec.node_name,
            "phase": status.phase,
            "containers": [
                {
                    "name": container.name,
                    "image": container.image,
                    "ports": [
                        {
                            "name": port.name,
                            "container_port": port.container_port,
                            "protocol": port.protocol,
                        }
                        for port in (container.ports or [])
                    ],
                    "resources": {
                        "requests": (container.resources.requests or {}) if container.resources else {},
                        "limits": (container.resources.limits or {}) if container.resources else {},
                    },
                    "readiness_probe": container.readiness_probe is not None,
                    "liveness_probe": container.liveness_probe is not None,
                }
                for container in (spec.containers or [])
            ],
        }

    def _simplify_service(self, service) -> Dict[str, Any]:
        metadata = service.metadata
        spec = service.spec

        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "selector": spec.selector or {},
            "type": spec.type,
            "ports": [
                {
                    "name": port.name,
                    "port": port.port,
                    "target_port": port.target_port,
                    "protocol": port.protocol,
                }
                for port in (spec.ports or [])
            ],
        }

    def _simplify_endpoint(self, endpoint) -> Dict[str, Any]:
        metadata = endpoint.metadata
        subsets = endpoint.subsets or []

        simplified_subsets = []

        for subset in subsets:
            simplified_subsets.append(
                {
                    "addresses": [
                        {
                            "ip": address.ip,
                            "target_kind": address.target_ref.kind if address.target_ref else None,
                            "target_name": address.target_ref.name if address.target_ref else None,
                        }
                        for address in (subset.addresses or [])
                    ],
                    "not_ready_addresses": [
                        {
                            "ip": address.ip,
                            "target_kind": address.target_ref.kind if address.target_ref else None,
                            "target_name": address.target_ref.name if address.target_ref else None,
                        }
                        for address in (subset.not_ready_addresses or [])
                    ],
                    "ports": [
                        {
                            "name": port.name,
                            "port": port.port,
                            "protocol": port.protocol,
                        }
                        for port in (subset.ports or [])
                    ],
                }
            )

        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "subsets": simplified_subsets,
        }

    def _simplify_deployment(self, deployment) -> Dict[str, Any]:
        metadata = deployment.metadata
        spec = deployment.spec
        status = deployment.status

        pod_template = spec.template
        template_metadata = pod_template.metadata
        template_spec = pod_template.spec

        return {
            "name": metadata.name,
            "namespace": metadata.namespace,
            "replicas": spec.replicas or 0,
            "available_replicas": status.available_replicas or 0,
            "ready_replicas": status.ready_replicas or 0,
            "selector": spec.selector.match_labels or {},
            "template_labels": template_metadata.labels or {},
            "image_pull_secrets": [
                item.name for item in (template_spec.image_pull_secrets or [])
            ],
            "containers": [
                {
                    "name": container.name,
                    "image": container.image,
                    "ports": [
                        {
                            "name": port.name,
                            "container_port": port.container_port,
                            "protocol": port.protocol,
                        }
                        for port in (container.ports or [])
                    ],
                    "resources": {
                        "requests": (container.resources.requests or {}) if container.resources else {},
                        "limits": (container.resources.limits or {}) if container.resources else {},
                    },
                    "readiness_probe": container.readiness_probe is not None,
                    "liveness_probe": container.liveness_probe is not None,
                }
                for container in (template_spec.containers or [])
            ],
        }

    def _parse_msg_json(self, stdout: str) -> Optional[Dict[str, Any]]:
        marker = '"msg":'
        marker_index = stdout.find(marker)

        if marker_index == -1:
            return None

        start = stdout.find("{", marker_index)
        if start == -1:
            return None

        depth = 0
        end = None

        for index in range(start, len(stdout)):
            char = stdout[index]

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

                if depth == 0:
                    end = index + 1
                    break

        if end is None:
            return None

        json_text = stdout[start:end]

        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            return None

    def _error_response(self, error_type: str, message: str) -> Dict[str, Any]:
        return {
            "collector": "ansible_config_collector",
            "collected_at": self._now_utc(),
            "node_name": None,
            "node": {},
            "error": {
                "type": error_type,
                "message": message,
            },
        }

    @staticmethod
    def _now_utc() -> str:
        return datetime.now(timezone.utc).isoformat()



