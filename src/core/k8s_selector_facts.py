
from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, List, Optional


SERVICE_SELECTOR_ROOT_TYPES = {
    "ServiceSelectorMismatch",
    "EmptyServiceEndpoints",
    "EmptyEndpoints",
}


def _run_json(args: List[str]) -> Optional[Dict[str, Any]]:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        return None

    try:
        return json.loads(result.stdout)
    except Exception:
        return None


def _pod_ready(pod: Dict[str, Any]) -> bool:
    status = pod.get("status") or {}
    phase = status.get("phase")

    if phase != "Running":
        return False

    conditions = status.get("conditions") or []

    for condition in conditions:
        if condition.get("type") == "Ready" and condition.get("status") == "True":
            return True

    return False


def _selector_matches(selector: Dict[str, str], labels: Dict[str, str]) -> bool:
    if not selector:
        return False

    for key, value in selector.items():
        if labels.get(key) != value:
            return False

    return True


def _looks_like_noise_resource(name: str, labels: Dict[str, str]) -> bool:
    text = " ".join(
        [
            name or "",
            labels.get("app", ""),
            labels.get("tier", ""),
            labels.get("component", ""),
        ]
    ).lower()

    noise_words = [
        "frontend",
        "client",
        "worker",
        "broken",
        "crashing",
        "crash",
        "image",
    ]

    return any(word in text for word in noise_words)


def _service_base_name(service_name: str) -> str:
    base = service_name or ""

    for suffix in ["-svc", "-service"]:
        if base.endswith(suffix):
            base = base[: -len(suffix)]

    return base


def _score_candidate_pod(
    pod: Dict[str, Any],
    selector_key: str,
    service_name: str,
) -> int:
    metadata = pod.get("metadata") or {}
    labels = metadata.get("labels") or {}
    pod_name = metadata.get("name", "")
    label_value = str(labels.get(selector_key, ""))

    score = 0
    service_base = _service_base_name(service_name)

    if _pod_ready(pod):
        score += 40

    if service_base and service_base in label_value:
        score += 40

    if service_base and label_value in service_base:
        score += 25

    if service_base and service_base in pod_name:
        score += 25

    if labels.get("tier") == "backend":
        score += 15

    if _looks_like_noise_resource(pod_name, labels):
        score -= 100

    return score


def _json_pointer_escape(value: str) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def enrich_service_selector_facts(
    facts: Dict[str, Any],
    namespace: Optional[str],
    service_name: Optional[str],
) -> Dict[str, Any]:
    enriched = dict(facts or {})

    root_type = enriched.get("root_cause_type")

    if root_type not in SERVICE_SELECTOR_ROOT_TYPES:
        return enriched

    if not namespace or not service_name:
        return enriched

    service_payload = _run_json(
        ["kubectl", "get", "svc", service_name, "-n", namespace, "-o", "json"]
    )

    if not service_payload:
        return enriched

    selector = ((service_payload.get("spec") or {}).get("selector") or {})

    if not isinstance(selector, dict) or not selector:
        return enriched

    enriched["service_selector"] = selector

    endpoint_payload = _run_json(
        ["kubectl", "get", "endpoints", service_name, "-n", namespace, "-o", "json"]
    )

    subsets = []
    if endpoint_payload:
        subsets = endpoint_payload.get("subsets") or []

    enriched["service_has_endpoints"] = bool(subsets)

    # Only auto-build a patch when the selector has one key.
    # Multi-key selectors need manual review to avoid unsafe changes.
    if len(selector) != 1:
        enriched["selector_patch_safe"] = False
        enriched["selector_patch_reason"] = "Service selector has multiple keys; manual validation is required."
        return enriched

    selector_key, wrong_value = next(iter(selector.items()))

    pods_payload = _run_json(["kubectl", "get", "pods", "-n", namespace, "-o", "json"])

    if not pods_payload:
        return enriched

    candidates = []

    for pod in pods_payload.get("items") or []:
        metadata = pod.get("metadata") or {}
        labels = metadata.get("labels") or {}

        if not labels:
            continue

        # Ignore pods already selected by the wrong selector.
        if _selector_matches(selector, labels):
            continue

        # We need a pod that has the same selector key with a different value.
        if selector_key not in labels:
            continue

        score = _score_candidate_pod(
            pod=pod,
            selector_key=selector_key,
            service_name=service_name,
        )

        if score <= 0:
            continue

        candidates.append((score, pod))

    if not candidates:
        enriched["selector_patch_safe"] = False
        enriched["selector_patch_reason"] = "No safe backend pod candidate was found for selector correction."
        return enriched

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_pod = candidates[0]

    best_metadata = best_pod.get("metadata") or {}
    best_labels = best_metadata.get("labels") or {}
    correct_value = best_labels.get(selector_key)

    if not correct_value or correct_value == wrong_value:
        enriched["selector_patch_safe"] = False
        enriched["selector_patch_reason"] = "Could not infer a different safe selector value."
        return enriched

    enriched["selector_patch_safe"] = True
    enriched["selector_key"] = selector_key
    enriched["selector_json_pointer_key"] = _json_pointer_escape(selector_key)
    enriched["wrong_selector_value"] = wrong_value
    enriched["correct_selector_value"] = correct_value
    enriched["expected_selector_value"] = correct_value
    enriched["candidate_backend_pod"] = best_metadata.get("name", "")
    enriched["candidate_backend_pod_labels"] = best_labels
    pod_name = best_metadata.get("name", "")
    inferred_deployment = ""

    owner_refs = best_metadata.get("ownerReferences") or []
    for owner in owner_refs:
        if owner.get("kind") == "ReplicaSet":
            replica_set_name = owner.get("name", "")
            parts = replica_set_name.rsplit("-", 1)
            inferred_deployment = parts[0] if len(parts) == 2 else replica_set_name
            break

    enriched["candidate_backend_deployment"] = inferred_deployment
    enriched["deployment_name"] = inferred_deployment or enriched.get("deployment_name", "")

    enriched["selector_patch_reason"] = (
        f"Service selector {selector_key}={wrong_value} does not match candidate backend pod "
        f"{pod_name} label {selector_key}={correct_value}."
    )

    return enriched
