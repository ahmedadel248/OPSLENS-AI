# OpsLens AI

**OpsLens AI** is an AI-powered Kubernetes incident investigation system designed to help DevOps, SRE, and AIOps teams understand infrastructure and application failures faster.

The system uses a multi-agent architecture to collect evidence from Kubernetes events, application logs, resource metrics, and configuration checks. A Supervisor Agent correlates these signals, identifies the most likely root cause, and passes structured facts to an LLM reasoning layer. The LLM generates a human-readable incident report, while a Python safety layer validates remediation actions and prevents hallucinated commands.

---

## Project Goal

Modern cloud-native systems generate large amounts of operational data from logs, metrics, events, and configuration files. During incidents, engineers often need to manually correlate these signals to understand what happened.

OpsLens AI aims to automate that investigation workflow by:

* Detecting Kubernetes and Linux operational issues.
* Collecting evidence from multiple sources.
* Correlating signals through a Supervisor Agent.
* Producing clear root-cause analysis.
* Recommending safe remediation steps.
* Generating final incident reports for engineers.

---

## Key Features

* **Multi-agent investigation pipeline**

  * Resource Metrics Agent
  * Kubernetes Events Agent
  * Logs Agent
  * Ansible Config Agent
  * Supervisor Agent
  * Gemini Reasoning Agent

* **Focused investigation scope**

  * Node-level scope
  * Namespace-level scope
  * Prevents noisy cluster-wide investigation

* **Resource anomaly detection**

  * LSTM-based resource detector
  * CPU and memory anomaly detection
  * Time-aware model features

* **Kubernetes incident analysis**

  * Service targetPort mismatch
  * Empty endpoints
  * Readiness probe failures
  * Deployment availability issues
  * Connection refused errors

* **LLM-based reasoning**

  * Human-readable incident summary
  * Root-cause story
  * Recommended fix strategy
  * Verification plan

* **Safety layer**

  * The LLM does not directly execute cluster actions.
  * Commands are generated or validated using trusted Supervisor facts.
  * Prevents hallucinated namespaces, services, deployments, and ports.

* **Runbook Knowledge Base**

  * Known incident patterns are mapped to trusted runbooks.
  * If no runbook exists, the LLM still reasons from Supervisor facts.

---

## High-Level Architecture

```text
User Investigation Scope
        ↓
Collectors
        ↓
Specialized Agents
        ↓
Supervisor Agent
        ↓
Runbook Knowledge Base
        ↓
Gemini Reasoning Agent
        ↓
Command Safety Layer
        ↓
Final Incident Report
```

---

## Agents

| Agent                   | Responsibility                                                         |
| ----------------------- | ---------------------------------------------------------------------- |
| Resource Metrics Agent  | Detects CPU and memory anomalies using the resource detector           |
| Kubernetes Events Agent | Reads Kubernetes lifecycle and control-plane signals                   |
| Logs Agent              | Reads application/runtime logs and extracts error signals              |
| Ansible Config Agent    | Checks Kubernetes/Linux configuration and service relationships        |
| Supervisor Agent        | Correlates all agent signals and selects the primary root cause        |
| Gemini Reasoning Agent  | Generates incident summary, root-cause story, and remediation strategy |

---

## LLM Reasoning Design

OpsLens AI separates reasoning from execution.

The LLM is responsible for:

* Explaining the incident in a clear operational story.
* Generating a remediation strategy.
* Suggesting high-level recommended actions.
* Reasoning from Supervisor facts even when no runbook exists.

Python is responsible for:

* Validating facts.
* Building safe commands only when evidence is complete.
* Preventing hallucinated resources.
* Rendering the final report.

This design allows flexible LLM reasoning while keeping remediation safe and evidence-based.

---

## Knowledge Base

OpsLens AI includes a rule-based runbook retriever.

Known signals are mapped to trusted markdown runbooks through:

```text
knowledge_base/runbook_registry.json
```

Example:

```json
{
  "ServiceTargetPortMismatch": "service_targetport_mismatch.md",
  "ConnectionRefused": "connection_refused.md",
  "Unhealthy": "readiness_probe_failed.md"
}
```

To add a new known incident:

1. Add a markdown runbook under:

```text
knowledge_base/runbooks/
```

2. Register the signal in:

```text
knowledge_base/runbook_registry.json
```

3. Re-run the investigation pipeline.

---

## Example Incident

A sample Kubernetes incident is included under:

```text
scenarios/service_targetport_mismatch.yml
```

This scenario simulates a backend service configured with the wrong `targetPort`, causing:

* Backend pods to fail readiness checks.
* Service endpoints to remain empty.
* Frontend logs to show connection refused errors.

OpsLens AI detects the configuration mismatch, correlates supporting evidence, and generates a remediation report.

---

## Project Structure

```text
OpsLens-AI/
├── ansible/
├── artifacts/
│   └── resource_detector_v7_egypt_timeaware/
├── data/
├── knowledge_base/
├── prompts/
├── scenarios/
├── scripts/
├── src/
│   ├── agents/
│   ├── collectors/
│   ├── core/
│   ├── detectors/
│   ├── knowledge/
│   ├── schemas/
│   ├── utils/
│   └── workflows/
├── requirements.txt
└── README.md
```

---

## Current Scope

Current version focuses on:

* Kubernetes
* Linux / Ansible checks
* Node and namespace scoped investigation
* Resource anomaly detection
* Incident report generation
* Safe remediation command generation

---

## Future Work

* FastAPI backend endpoint for triggering investigations.
* Web UI for selecting namespace and node.
* Multi-incident grouping for multiple unrelated failures on the same node.
* Real-time metrics collection from Kubernetes Metrics API or Prometheus.
* More Kubernetes incident scenarios.
* Expanded runbook knowledge base.
* CI checks and automated smoke tests.

---

## Security Notes

* Do not commit API keys, secrets, `.env` files, kubeconfig files, or cloud credentials.
* LLM-generated actions are not executed automatically.
* Remediation commands are safety-validated against structured Supervisor facts.
* Runtime reports and generated data are ignored by Git.

---

## Status

OpsLens AI is currently an active graduation project focused on AIOps, Kubernetes incident investigation, and LLM-assisted root-cause analysis.
