import re
from typing import Any, Dict, List, Optional


class LogsSignalDetector:
    def __init__(self):
        self.patterns = [
            {
                "signal": "PythonTraceback",
                "severity": "critical",
                "patterns": [r"Traceback \(most recent call last\)", r"\bException\b"],
                "recommendations": [
                    "Inspect application stack trace.",
                    "Check recent code or configuration changes.",
                    "Check pod logs and previous container logs.",
                ],
            },
            {
                "signal": "ImportError",
                "severity": "critical",
                "patterns": [r"ModuleNotFoundError", r"ImportError"],
                "recommendations": [
                    "Verify application dependencies.",
                    "Check image build and installed packages.",
                    "Rebuild image with required dependencies.",
                ],
            },
            {
                "signal": "ConnectionRefused",
                "severity": "warning",
                "patterns": [r"connection refused", r"ConnectionRefused", r"ECONNREFUSED"],
                "recommendations": [
                    "Check target service availability.",
                    "Check service DNS, ports, and network policy.",
                    "Check if dependency pod is running.",
                ],
            },
            {
                "signal": "TimeoutError",
                "severity": "warning",
                "patterns": [r"timeout", r"timed out", r"TimeoutError", r"i/o timeout"],
                "recommendations": [
                    "Check dependency latency.",
                    "Check service/network connectivity.",
                    "Inspect upstream service health.",
                ],
            },
            {
                "signal": "PermissionDenied",
                "severity": "warning",
                "patterns": [r"permission denied", r"PermissionError", r"access denied", r"unauthorized", r"forbidden"],
                "recommendations": [
                    "Check file permissions, service account, RBAC, and secrets.",
                    "Check mounted volume permissions.",
                ],
            },
            {
                "signal": "OutOfMemoryLog",
                "severity": "critical",
                "patterns": [r"OOMKilled", r"OutOfMemory", r"out of memory", r"\bKilled\b"],
                "recommendations": [
                    "Check memory limits and memory usage.",
                    "Check for memory leaks.",
                    "Correlate with Metrics Agent memory anomaly.",
                ],
            },
            {
                "signal": "FatalError",
                "severity": "critical",
                "patterns": [r"\bfatal\b", r"\bpanic\b", r"segmentation fault", r"core dumped"],
                "recommendations": [
                    "Inspect application crash logs.",
                    "Check runtime dependencies and recent releases.",
                ],
            },
            {
                "signal": "GenericErrorLog",
                "severity": "warning",
                "patterns": [r"\berror\b", r"\bfailed\b", r"\bfailure\b"],
                "recommendations": [
                    "Inspect the matching log lines.",
                    "Check related Kubernetes events and application configuration.",
                ],
            },
        ]

    def detect(self, logs_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if logs_data.get("error"):
            return [
                self._build_signal(
                    signal="LogsCollectorError",
                    category="collector_error",
                    severity="critical",
                    summary="Logs collector failed to collect pod logs.",
                    evidence=[str(logs_data.get("error"))],
                    raw={"error": logs_data.get("error")},
                )
            ]

        signals = []

        for record in logs_data.get("logs", []) or []:
            signals.extend(self._detect_record(record))

        return self._deduplicate(signals)

    def _detect_record(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        namespace = record.get("namespace")
        pod_name = record.get("pod_name")
        container_name = record.get("container_name")
        node_name = record.get("node_name")
        restart_count = record.get("restart_count")

        if record.get("current_log_error"):
            signals.append(
                self._build_signal(
                    signal="LogReadError",
                    category="log_collection",
                    severity="warning",
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    node_name=node_name,
                    summary=f"Could not read logs for {pod_name}/{container_name}.",
                    evidence=[str(record.get("current_log_error"))],
                    raw={"current_log_error": record.get("current_log_error")},
                )
            )

        signals.extend(
            self._detect_text(
                text=record.get("current_log") or "",
                log_source="current",
                namespace=namespace,
                pod_name=pod_name,
                container_name=container_name,
                node_name=node_name,
                restart_count=restart_count,
            )
        )

        if record.get("previous_log"):
            signals.extend(
                self._detect_text(
                    text=record.get("previous_log") or "",
                    log_source="previous",
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    node_name=node_name,
                    restart_count=restart_count,
                )
            )

        return signals

    def _detect_text(
        self,
        text: str,
        log_source: str,
        namespace: Optional[str],
        pod_name: Optional[str],
        container_name: Optional[str],
        node_name: Optional[str],
        restart_count: Optional[int],
    ) -> List[Dict[str, Any]]:
        if not text.strip():
            return []

        signals = []

        for group in self.patterns:
            matched_lines = []
            matched_patterns = []

            for pattern in group["patterns"]:
                lines = self._matching_lines(text, pattern, limit=5)
                if lines:
                    matched_patterns.append(pattern)
                    matched_lines.extend(lines)

            if matched_lines:
                signals.append(
                    self._build_signal(
                        signal=group["signal"],
                        category="log_pattern",
                        severity=group["severity"],
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name=container_name,
                        node_name=node_name,
                        summary=f"{group['signal']} detected in {log_source} logs for {pod_name}/{container_name}.",
                        evidence=[
                            f"Log source: {log_source}",
                            f"Restart count: {restart_count}",
                            f"Matched patterns: {matched_patterns}",
                        ] + matched_lines[:5],
                        recommendations=group["recommendations"],
                        raw={
                            "log_source": log_source,
                            "matched_patterns": matched_patterns,
                            "restart_count": restart_count,
                        },
                    )
                )

        return signals

    def _matching_lines(self, text: str, pattern: str, limit: int = 5) -> List[str]:
        regex = re.compile(pattern, re.IGNORECASE)
        matches = []

        for line in text.splitlines():
            clean = line.strip()
            if not clean:
                continue

            if regex.search(clean):
                matches.append(clean[:500])

            if len(matches) >= limit:
                break

        return matches

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
        recommendations: Optional[List[str]] = None,
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
            "summary": summary,
            "evidence": [item for item in evidence if item],
            "recommendations": recommendations or [
                "Inspect pod logs, Kubernetes events, and related service dependencies."
            ],
            "raw": raw or {},
        }

    def _deduplicate(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        unique = []

        for signal in signals:
            key = (
                signal.get("signal"),
                signal.get("namespace"),
                signal.get("pod_name"),
                signal.get("container_name"),
                signal.get("node_name"),
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(signal)

        return unique



