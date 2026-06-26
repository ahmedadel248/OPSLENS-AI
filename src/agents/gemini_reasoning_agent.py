import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.root_cause_facts import build_root_cause_facts
from src.knowledge.runbook_retriever import RuleBasedRunbookRetriever


class GeminiReasoningAgent:
    """
    Final incident reasoning agent.

    Gemini is responsible for:
    - Human-readable incident summary
    - Root-cause story
    - Remediation strategy
    - Recommended action plan

    Python is responsible for:
    - Safety validation
    - Preventing hallucinated resources
    - Converting safe LLM actions into executable commands only when facts are complete
    """

    def __init__(
        self,
        model: Optional[str] = None,
        output_dir: str = "data/final_incident_reports",
        persist: bool = True,
    ):
        self.model = model or os.getenv("GEMINI_MODEL")
        self.model_used = None
        self.retriever = RuleBasedRunbookRetriever()
        self.output_dir = Path(output_dir)
        self.persist = persist

        if self.persist:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def analyze(self, supervisor_report: Dict[str, Any]) -> Dict[str, Any]:
        supervisor_report = dict(supervisor_report)
        supervisor_report["root_cause_facts"] = supervisor_report.get("root_cause_facts") or build_root_cause_facts(supervisor_report)

        runbooks = self.retriever.retrieve(supervisor_report)
        compact_input = self._compact_supervisor_report(supervisor_report, runbooks)

        if os.getenv("GEMINI_API_KEY"):
            try:
                report = self._call_gemini(compact_input)
                report["generation_mode"] = "gemini"
            except Exception as exc:
                report = self._fallback(compact_input, f"{type(exc).__name__}: {exc}")
        else:
            report = self._fallback(compact_input, "GEMINI_API_KEY is not set.")

        report = self._sanitize_report(report, compact_input)
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        report["source_scenario"] = supervisor_report.get("scenario_name")
        report["retrieved_runbooks"] = compact_input.get("retrieved_runbooks", [])

        if self.persist:
            self._persist(report)

        return report

    def _system_instruction(self) -> str:
        prompt_path = Path("prompts/opslens_system_prompt.md")

        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8").strip()

        return "You are OpsLens Incident Reasoning Agent. Use only Supervisor facts and produce a safe human-readable incident report."

    def _resolve_model(self, client) -> str:
        if self.model:
            return self.model.replace("models/", "")

        try:
            candidates = []

            for model in client.models.list():
                name = getattr(model, "name", "") or ""
                actions = getattr(model, "supported_actions", []) or []

                if actions and "generateContent" not in actions:
                    continue

                short_name = name.replace("models/", "")
                lower = short_name.lower()

                blocked = ["embedding", "imagen", "veo", "tts", "image", "audio", "music", "robotics"]
                if any(word in lower for word in blocked):
                    continue

                score = 0
                if "flash-lite" in lower:
                    score += 100
                elif "flash" in lower:
                    score += 90
                elif "lite" in lower:
                    score += 80
                elif "pro" in lower:
                    score += 50

                if "latest" in lower:
                    score += 30

                if "preview" not in lower and "experimental" not in lower and "exp" not in lower:
                    score += 20

                candidates.append((score, short_name))

            if candidates:
                candidates.sort(reverse=True)
                return candidates[0][1]

        except Exception:
            pass

        return "gemini-flash-latest"

    def _call_gemini(self, compact_input: Dict[str, Any]) -> Dict[str, Any]:
        from google import genai
        from google.genai import types

        client = genai.Client()
        model_name = self._resolve_model(client)
        self.model_used = model_name

        prompt = self._build_prompt(compact_input)

        config = types.GenerateContentConfig(
            system_instruction=self._system_instruction(),
            response_mime_type="application/json",
            response_schema=self._schema(),
            temperature=0.2,
            max_output_tokens=1800,
        )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
        except Exception:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self._system_instruction(),
                    response_mime_type="application/json",
                    temperature=0.2,
                    max_output_tokens=1800,
                ),
            )

        result = self._parse_response(response)
        result["model_used"] = model_name
        return result

    def _build_prompt(self, compact_input: Dict[str, Any]) -> str:
        return f"""
Create the final OpsLens incident report from the structured input below.

You must produce:
1. incident summary
2. root cause story
3. recommended fix strategy
4. recommended actions
5. verification intent

Recommended actions must be logical actions, not raw commands.

For ServiceTargetPortMismatch, if facts are complete, include this action:
- action_type: align_service_target_port
- target_kind: service_and_deployment
- reason: explain why targetPort and readinessProbe must match containerPort
- risk: low

If the incident is unknown or no runbook is available:
- Still produce a remediation or investigation strategy from Supervisor facts.
- Use action_type: investigate_further when safe remediation is not certain.

Return JSON only.

Structured input:
{json.dumps(compact_input, indent=2, default=str)}
""".strip()

    def _schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "severity": {"type": "string"},
                "confidence": {"type": "string"},
                "affected_resources": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "service": {"type": "string"},
                        "deployment": {"type": "string"},
                        "node": {"type": "string"},
                    },
                },
                "incident_summary": {"type": "string"},
                "root_cause_story": {"type": "string"},
                "recommended_fix": {
                    "type": "object",
                    "properties": {
                        "strategy": {"type": "string"},
                        "actions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "action_type": {"type": "string"},
                                    "target_kind": {"type": "string"},
                                    "reason": {"type": "string"},
                                    "risk": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "verification": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string"},
                    },
                },
            },
            "required": [
                "title",
                "severity",
                "confidence",
                "affected_resources",
                "incident_summary",
                "root_cause_story",
                "recommended_fix",
                "verification",
            ],
        }

    def _parse_response(self, response) -> Dict[str, Any]:
        if getattr(response, "parsed", None):
            parsed = response.parsed
            if isinstance(parsed, dict):
                return parsed
            return json.loads(json.dumps(parsed, default=lambda obj: getattr(obj, "__dict__", str(obj))))

        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini returned an empty response.")

        text = text.strip()

        if text.startswith("```json"):
            text = text.replace("```json", "", 1).strip()

        if text.startswith("```"):
            text = text.replace("```", "", 1).strip()

        if text.endswith("```"):
            text = text[:-3].strip()

        return json.loads(text)

    def _compact_supervisor_report(
        self,
        supervisor_report: Dict[str, Any],
        runbooks: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        facts = supervisor_report.get("root_cause_facts") or build_root_cause_facts(supervisor_report)
        affected = supervisor_report.get("affected_resources") or {}
        primary = supervisor_report.get("primary_signal") or {}

        supporting = []

        for signal in supervisor_report.get("supporting_signals", []) or []:
            supporting.append(
                {
                    "source_agent": signal.get("source_agent"),
                    "anomaly_type": signal.get("anomaly_type"),
                    "severity": signal.get("severity"),
                    "summary": signal.get("summary"),
                    "namespace": signal.get("namespace"),
                    "node_name": signal.get("node_name"),
                    "service_name": signal.get("service_name"),
                    "deployment_name": signal.get("deployment_name"),
                    "pod_name": signal.get("pod_name"),
                }
            )

        important_evidence = []
        keep_keywords = [
            "service_port",
            "target_port",
            "available_container_ports",
            "ConnectionRefused",
            "Unhealthy",
            "DeploymentNoAvailableReplicas",
            "Metrics context",
            "Primary signal",
            "Supporting signal",
        ]

        for item in supervisor_report.get("evidence", []) or []:
            text = str(item)
            if any(keyword in text for keyword in keep_keywords):
                important_evidence.append(text)

        return {
            "incident_title": supervisor_report.get("incident_title"),
            "severity": supervisor_report.get("severity"),
            "confidence": supervisor_report.get("confidence"),
            "affected_resources": {
                "namespace": facts.get("namespace") or affected.get("namespace", "default"),
                "service": facts.get("service_name") or affected.get("service") or affected.get("service_name", ""),
                "deployment": facts.get("deployment_name") or affected.get("deployment") or affected.get("deployment_name", ""),
                "node": facts.get("node_name") or affected.get("node") or affected.get("node_name", ""),
            },
            "primary_signal": {
                "source_agent": primary.get("source_agent"),
                "anomaly_type": primary.get("anomaly_type"),
                "severity": primary.get("severity"),
                "summary": primary.get("summary"),
                "evidence": primary.get("evidence"),
            },
            "root_cause_facts": facts,
            "supporting_signals": supporting[:8],
            "important_evidence": important_evidence[:12],
            "retrieved_runbooks": [
                {
                    "name": item["name"],
                    "content_preview": item["content"][:1000],
                }
                for item in runbooks
            ],
            "runbook_available": bool(runbooks),
            "constraints": [
                "Use Supervisor facts as the source of truth.",
                "Knowledge Base guidance is optional; if missing, still reason from facts.",
                "Do not invent resource names or ports.",
                "Executable commands will be safety-validated outside the LLM.",
            ],
        }

    def _sanitize_report(self, report: Dict[str, Any], compact_input: Dict[str, Any]) -> Dict[str, Any]:
        report = dict(report)

        affected = compact_input.get("affected_resources") or {}
        facts = compact_input.get("root_cause_facts") or {}

        namespace = affected.get("namespace", "default")
        service = affected.get("service", "")
        deployment = affected.get("deployment", "")
        node = affected.get("node", "")

        report["title"] = report.get("title") or compact_input.get("incident_title") or "OpsLens Incident Report"
        report["severity"] = report.get("severity") or compact_input.get("severity", "unknown")
        report["confidence"] = report.get("confidence") or compact_input.get("confidence", "medium")
        report["affected_resources"] = {
            "namespace": namespace,
            "service": service,
            "deployment": deployment,
            "node": node,
        }

        # Backward-compatible fields
        if "incident_summary" not in report:
            report["incident_summary"] = report.get("problem_description", "")

        if "root_cause_story" not in report:
            report["root_cause_story"] = report.get("root_cause_analysis", "")

        report["root_cause_story"] = self._sanitize_root_cause_story(
            report.get("root_cause_story", ""),
            facts,
        )

        recommended_fix = report.get("recommended_fix") or {}
        strategy = recommended_fix.get("strategy") or recommended_fix.get("explanation") or "Review the incident facts and apply the safest remediation strategy."

        actions = recommended_fix.get("actions") or []
        actions = self._sanitize_actions(actions)

        operational_notes = self._extract_operational_notes(actions, facts)
        actions = self._filter_primary_actions(actions, facts)

        if not actions:
            actions = [
                {
                    "action_type": "investigate_further",
                    "target_kind": "cluster_resource",
                    "reason": "No safe remediation action was produced from the available facts.",
                    "risk": "low",
                }
            ]

        safe_commands = self._commands_from_actions(
            actions=actions,
            namespace=namespace,
            service=service,
            deployment=deployment,
            facts=facts,
        )

        if not safe_commands:
            safe_commands = self._safe_investigation_commands(namespace, service, deployment)

        report["operational_notes"] = operational_notes

        report["recommended_fix"] = {
            "strategy": strategy,
            "actions": actions,
            "commands": safe_commands[:5],
        }

        report["agent_reasoning"] = self._build_agent_reasoning(compact_input)

        verification_commands = [
            str(command).strip()
            for command in self._safe_verification_commands(namespace, service, deployment, compact_input)
            if str(command).strip()
        ]

        report["verification"] = {
            "intent": (report.get("verification") or {}).get(
                "intent",
                "Confirm that the affected workload becomes healthy and traffic can reach the backend service."
            ),
            "commands": verification_commands[:5],
        }

        return report

    def _sanitize_root_cause_story(self, story: str, facts: Dict[str, Any]) -> str:
        """
        Keep the LLM root-cause story focused on the confirmed primary cause.

        Example:
        If ServiceTargetPortMismatch is the primary root cause, resource pressure
        may be mentioned only as operational context, not as a proven cause.
        """

        story = str(story or "").strip()

        if facts.get("root_cause_type") != "ServiceTargetPortMismatch":
            return story

        if not story:
            return story

        sentences = re.split(r"(?<=[.!?])\s+", story)
        kept = []

        for sentence in sentences:
            lower = sentence.lower()

            mentions_metrics = (
                "cpu" in lower
                or "memory" in lower
                or "resource pressure" in lower
                or "node pressure" in lower
            )

            makes_causal_claim = (
                "exacerbat" in lower
                or "contribut" in lower
                or "caus" in lower
                or "impacting" in lower
                or "instability" in lower
            )

            if mentions_metrics and makes_causal_claim:
                continue

            kept.append(sentence)

        cleaned = " ".join(kept).strip()
        return cleaned or story

    def _extract_operational_notes(
        self,
        actions: List[Dict[str, str]],
        facts: Dict[str, Any],
    ) -> List[str]:
        notes: List[str] = []

        root_type = facts.get("root_cause_type")

        for action in actions:
            action_type = str(action.get("action_type", ""))
            reason = str(action.get("reason", ""))

            lower = f"{action_type} {reason}".lower()

            if root_type == "ServiceTargetPortMismatch" and (
                "cpu" in lower
                or "memory" in lower
                or "resource" in lower
                or "node pressure" in lower
            ):
                notes.append(
                    "The Metrics Agent also observed node resource pressure. Treat this as operational context and monitor it separately after the primary Service routing issue is fixed."
                )

        return self._dedupe(notes)

    def _filter_primary_actions(
        self,
        actions: List[Dict[str, str]],
        facts: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        root_type = facts.get("root_cause_type")

        if root_type != "ServiceTargetPortMismatch":
            return actions

        filtered: List[Dict[str, str]] = []

        for action in actions:
            action_type = str(action.get("action_type", ""))
            reason = str(action.get("reason", ""))
            lower = f"{action_type} {reason}".lower()

            if (
                "cpu" in lower
                or "memory" in lower
                or "resource" in lower
                or "node pressure" in lower
            ):
                continue

            filtered.append(action)

        return filtered

    def _sanitize_actions(self, actions: Any) -> List[Dict[str, str]]:
        if not isinstance(actions, list):
            return []

        safe_actions = []

        for action in actions:
            if not isinstance(action, dict):
                continue

            safe_actions.append(
                {
                    "action_type": str(action.get("action_type", "investigate_further")),
                    "target_kind": str(action.get("target_kind", "unknown")),
                    "reason": str(action.get("reason", "")),
                    "risk": str(action.get("risk", "unknown")),
                }
            )

        return safe_actions[:6]

    def _commands_from_actions(
        self,
        actions: List[Dict[str, str]],
        namespace: str,
        service: str,
        deployment: str,
        facts: Dict[str, Any],
    ) -> List[str]:
        commands: List[str] = []

        for action in actions:
            action_type = action.get("action_type")

            if action_type in {
                "align_service_target_port",
                "patch_service_target_port",
                "fix_service_target_port_mismatch",
            }:
                commands.extend(
                    self._build_service_target_port_commands(
                        namespace=namespace,
                        service=service,
                        deployment=deployment,
                        facts=facts,
                    )
                )

            elif action_type == "investigate_further":
                commands.extend(self._safe_investigation_commands(namespace, service, deployment))

        return self._dedupe(commands)

    def _build_service_target_port_commands(
        self,
        namespace: str,
        service: str,
        deployment: str,
        facts: Dict[str, Any],
    ) -> List[str]:
        root_type = facts.get("root_cause_type")

        if root_type != "ServiceTargetPortMismatch":
            return []

        if not namespace or not service or not deployment:
            return []

        if service == "affected-service" or deployment == "affected-deployment":
            return []

        container_port = facts.get("container_port")

        if container_port is None:
            container_ports = facts.get("container_ports") or []
            if container_ports:
                container_port = container_ports[0]

        if container_port is None:
            return []

        service_patch_file = "opslens_service_patch.json"
        deployment_patch_file = "opslens_deployment_patch.json"

        service_patch = (
            "@'\n"
            f"[{{\"op\":\"replace\",\"path\":\"/spec/ports/0/targetPort\",\"value\":{container_port}}}]\n"
            "'@ | Set-Content .\\" + service_patch_file + " -Encoding ascii\n"
            f"kubectl patch service {service} -n {namespace} --type=json --patch-file .\\{service_patch_file}\n"
            f"Remove-Item .\\{service_patch_file} -Force"
        )

        deployment_patch = (
            "@'\n"
            f"[{{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/readinessProbe/tcpSocket/port\",\"value\":{container_port}}}]\n"
            "'@ | Set-Content .\\" + deployment_patch_file + " -Encoding ascii\n"
            f"kubectl patch deployment {deployment} -n {namespace} --type=json --patch-file .\\{deployment_patch_file}\n"
            f"Remove-Item .\\{deployment_patch_file} -Force"
        )

        return [
            service_patch,
            deployment_patch,
            f"kubectl rollout status deployment/{deployment} -n {namespace}",
        ]

    def _safe_investigation_commands(self, namespace: str, service: str, deployment: str) -> List[str]:
        commands = []

        if service and service != "affected-service":
            commands.append(f"kubectl get svc {service} -n {namespace} -o yaml")

        if deployment and deployment != "affected-deployment":
            commands.append(f"kubectl describe deployment {deployment} -n {namespace}")

        commands.append(f"kubectl get pods -n {namespace} --show-labels")

        return commands

    def _safe_verification_commands(
        self,
        namespace: str,
        service: str,
        deployment: str,
        compact_input: Dict[str, Any],
    ) -> List[str]:
        commands: List[str] = []

        if deployment and deployment != "affected-deployment":
            commands.append(f"kubectl rollout status deployment/{deployment} -n {namespace}")

        if service and service != "affected-service":
            commands.append(f"kubectl get endpoints {service} -n {namespace}")

        commands.append(f"kubectl get pods -n {namespace}")

        if deployment and deployment != "affected-deployment":
            commands.append(f"kubectl describe deployment {deployment} -n {namespace}")

        frontend = self._extract_frontend_deployment(compact_input)
        if frontend:
            commands.append(f"kubectl logs deployment/{frontend} -n {namespace} --tail=20")

        return commands

    def _build_agent_reasoning(self, compact_input: Dict[str, Any]) -> List[Dict[str, str]]:
        primary = compact_input.get("primary_signal") or {}
        primary_type = primary.get("anomaly_type")

        if primary_type == "ServiceTargetPortMismatch":
            return [
                {
                    "agent": "Config Agent",
                    "finding": "ServiceTargetPortMismatch",
                    "meaning": "The Service targetPort is pointing to a port that the backend container is not actually exposing.",
                },
                {
                    "agent": "Kubernetes Events Agent",
                    "finding": "Unhealthy / Readiness failures",
                    "meaning": "Kubernetes reports health-check failures because the pod readiness probe is also checking the wrong port.",
                },
                {
                    "agent": "Logs Agent",
                    "finding": "ConnectionRefused",
                    "meaning": "Frontend/application logs confirm that traffic cannot successfully reach the backend service.",
                },
                {
                    "agent": "Metrics Agent",
                    "finding": "CPU/Memory anomaly",
                    "meaning": "Supporting context only; it may indicate node pressure, but it is not the direct cause of this Service routing failure.",
                },
            ]

        rows = []

        if primary_type:
            rows.append(
                {
                    "agent": self._canonical_agent_name(primary.get("source_agent")),
                    "finding": primary_type,
                    "meaning": primary.get("summary") or "This was selected as the primary signal.",
                }
            )

        for signal in compact_input.get("supporting_signals", []) or []:
            if len(rows) >= 4:
                break

            anomaly_type = signal.get("anomaly_type")
            if not anomaly_type:
                continue

            rows.append(
                {
                    "agent": self._canonical_agent_name(signal.get("source_agent")),
                    "finding": anomaly_type,
                    "meaning": signal.get("summary") or "This signal supports the investigation.",
                }
            )

        return rows[:4]

    def _canonical_agent_name(self, source_agent: Any) -> str:
        raw = str(source_agent or "").lower()

        mapping = {
            "ansible_config": "Config Agent",
            "ansible_config_agent": "Config Agent",
            "config": "Config Agent",
            "kubernetes_events": "Kubernetes Events Agent",
            "kubernetes_events_agent": "Kubernetes Events Agent",
            "logs": "Logs Agent",
            "logs_agent": "Logs Agent",
            "log_analyzer": "Logs Agent",
            "resource_metrics": "Metrics Agent",
            "resource_metrics_agent": "Metrics Agent",
            "metrics": "Metrics Agent",
            "metrics_agent": "Metrics Agent",
        }

        for key, value in mapping.items():
            if key in raw:
                return value

        return "Investigation Agent"

    def _fallback(self, compact_input: Dict[str, Any], reason: str) -> Dict[str, Any]:
        affected = compact_input.get("affected_resources") or {}

        return {
            "generation_mode": "template_fallback",
            "fallback_reason": reason,
            "title": compact_input.get("incident_title") or "OpsLens Incident Report",
            "severity": compact_input.get("severity", "unknown"),
            "confidence": compact_input.get("confidence", "medium"),
            "affected_resources": affected,
            "incident_summary": "OpsLens collected incident evidence, but the LLM was unavailable. A safe fallback report was generated from Supervisor facts.",
            "root_cause_story": "Review the evidence trail and run the safe inspection commands to confirm the active failure mode.",
            "recommended_fix": {
                "strategy": "Use safe investigation commands until LLM reasoning is available.",
                "actions": [
                    {
                        "action_type": "investigate_further",
                        "target_kind": "cluster_resource",
                        "reason": "LLM reasoning was unavailable.",
                        "risk": "low",
                    }
                ],
            },
            "verification": {
                "intent": "Confirm resource health after applying any remediation.",
            },
        }

    def _extract_frontend_deployment(self, compact_input: Dict[str, Any]) -> Optional[str]:
        text = json.dumps(compact_input, default=str)

        match = re.search(r"(fullstack-frontend-client)-[a-z0-9]+-[a-z0-9]+", text)
        if match:
            return match.group(1)

        for signal in compact_input.get("supporting_signals", []) or []:
            pod_name = signal.get("pod_name")
            if pod_name and "frontend" in pod_name:
                return self._deployment_from_pod_name(pod_name)

        return None

    def _deployment_from_pod_name(self, pod_name: str) -> str:
        match = re.match(r"^(.+)-[a-f0-9]{8,10}-[a-z0-9]{5}$", pod_name)
        if match:
            return match.group(1)
        return pod_name

    def _table_cell(self, value: Any) -> str:
        cell = str(value or "")
        cell = cell.replace("\\", "\\\\")
        cell = cell.replace("|", "\\|")
        cell = cell.replace("\r", " ")
        cell = cell.replace("\n", " ")
        return cell.strip()

    def _dedupe(self, items: List[str]) -> List[str]:
        seen = set()
        result = []

        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)

        return result

    def _persist(self, report: Dict[str, Any]) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_title = report.get("title", "incident").replace(" ", "_").replace("/", "_")

        json_path = self.output_dir / f"{timestamp}_{safe_title}.json"
        md_path = self.output_dir / f"{timestamp}_{safe_title}.md"

        report["json_report_path"] = str(json_path)
        report["markdown_report_path"] = str(md_path)

        with json_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

        with md_path.open("w", encoding="utf-8") as f:
            f.write(self.to_markdown(report))

    def to_markdown(self, report: Dict[str, Any]) -> str:
        affected = report.get("affected_resources") or {}
        recommended_fix = report.get("recommended_fix") or {}
        verification = report.get("verification") or {}

        namespace = affected.get("namespace", "")
        service = affected.get("service", "")
        deployment = affected.get("deployment", "")
        node = affected.get("node", "")

        lines = []

        lines.append(f"# {report.get('title')}")
        lines.append("")
        lines.append("## Incident Overview")
        lines.append("")
        lines.append(f"**Severity:** {report.get('severity')}")
        lines.append(f"**Confidence:** {report.get('confidence')}")
        lines.append(f"**Namespace:** {namespace}")
        lines.append(f"**Node:** {node}")
        lines.append(f"**Service:** {service}")

        if deployment:
            lines.append(f"**Deployment:** {deployment}")

        lines.append("")
        lines.append("## Incident Summary")
        lines.append(report.get("incident_summary", ""))

        lines.append("")
        lines.append("## Root Cause Story")
        lines.append(report.get("root_cause_story", ""))

        lines.append("")
        lines.append("## Evidence Trail")
        lines.append("")
        lines.append("| Agent | Key Finding | What It Means |")
        lines.append("|---|---|---|")

        for row in report.get("agent_reasoning", []):
            lines.append(
                f"| {self._table_cell(row.get('agent'))} | {self._table_cell(row.get('finding'))} | {self._table_cell(row.get('meaning'))} |"
            )

        lines.append("")
        lines.append("## Recommended Fix")
        lines.append("")
        lines.append("### Fix Strategy")
        lines.append(recommended_fix.get("strategy", ""))

        actions = recommended_fix.get("actions", [])
        if actions:
            lines.append("")
            lines.append("### Recommended Actions")

            for index, action in enumerate(actions, start=1):
                lines.append("")
                lines.append(f"**Action {index}:** `{action.get('action_type', '')}`")
                if action.get("reason"):
                    lines.append(f"- Reason: {action.get('reason')}")
                if action.get("risk"):
                    lines.append(f"- Risk: {action.get('risk')}")

        commands = recommended_fix.get("commands", [])
        if commands:
            lines.append("")
            lines.append("### Safe Remediation / Investigation Commands")

            for index, command in enumerate(commands, start=1):
                lines.append("")
                lines.append(f"**Step {index}:**")
                lines.append("")
                lines.append("```powershell")
                lines.append(command)
                lines.append("```")

        operational_notes = report.get("operational_notes", [])

        if operational_notes:
            lines.append("")
            lines.append("### Operational Notes")

            for note in operational_notes:
                lines.append(f"- {note}")

        lines.append("")
        lines.append("### Long-Term Prevention")
        lines.append(
            "After the live remediation, update the source Kubernetes manifests or Helm values so the corrected configuration remains consistent in future deployments."
        )

        lines.append("")
        lines.append("## Verification Plan")
        lines.append("")
        lines.append(verification.get("intent", ""))

        verification_commands = [
            str(command).strip()
            for command in verification.get("commands", [])
            if str(command).strip()
        ]

        for index, command in enumerate(verification_commands, start=1):
            lines.append("")
            lines.append(f"**Check {index}:**")
            lines.append("")
            lines.append("```powershell")
            lines.append(command)
            lines.append("```")

        lines.append("")
        return "\n".join(lines)
