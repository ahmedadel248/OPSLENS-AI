# OpsLens AI

**OpsLens AI** is an AI-powered multi-agent AIOps platform for Kubernetes incident investigation and root-cause analysis.

The system helps DevOps, SRE, and AIOps teams investigate infrastructure and application failures by collecting evidence from Kubernetes events, logs, workload configuration, node metrics, and pod-level telemetry. Specialized agents analyze these signals, a Supervisor Agent coordinates the investigation and correlates findings, and an LLM reasoning agent generates an evidence-based incident report with probable root cause, confidence level, recommended next actions, validation checks, and technical evidence.

---

## Project Goal

Modern cloud-native systems generate large volumes of operational signals from Kubernetes resources, logs, events, metrics, and configuration. During incidents, engineers often need to manually inspect multiple sources and correlate symptoms to identify the real root cause.

OpsLens AI aims to automate this investigation workflow by:

* Collecting evidence from Kubernetes workloads, services, events, logs, and metrics.
* Running specialized agents for different operational signal types.
* Detecting node-level and pod-level resource anomalies.
* Coordinating multi-agent findings through a Supervisor-driven orchestration layer.
* Separating the primary incident from related findings and noisy signals.
* Using an LLM reasoning agent to generate clear, evidence-based RCA reports.
* Providing safe recommended next actions and validation checks for human review.

---

## Key Features

### Multi-Agent Investigation Pipeline

OpsLens AI uses a modular multi-agent architecture where each agent focuses on a specific type of operational evidence:

* Kubernetes Events Agent
* Application Logs Agent
* Workload Configuration Agent
* Node Resource Metrics Agent
* Pod LSTM Metrics Agent
* Supervisor Agent
* LLM Reasoning Agent

This design keeps the system explainable, extensible, and easier to debug compared to a single monolithic incident analyzer.

---

### Supervisor-Driven Orchestration

The investigation workflow is coordinated through a **Supervisor-driven orchestration layer**.

The Supervisor coordinates agent execution, aggregates multi-agent findings, filters noise, identifies the primary incident, separates related findings, and passes structured evidence to the LLM reasoning agent for root-cause analysis.

This allows the system to avoid directly sending raw, noisy cluster data to the LLM. Instead, the LLM receives structured and evidence-grounded investigation context.

---

### Node-Level Anomaly Detection

OpsLens AI includes node-level resource analysis to detect abnormal infrastructure behavior such as unusual CPU or memory pressure at the node level.

This helps distinguish between:

* Infrastructure-level resource pressure.
* Application-specific workload failures.
* Pod-level resource anomalies.

Node-level anomaly detection is useful when several workloads on the same node may be affected by shared resource pressure.

---

### Pod-Level LSTM Anomaly Detection

OpsLens AI includes a time-aware LSTM-based Pod Metrics Agent for pod-level anomaly detection.

The model analyzes pod CPU and memory telemetry over time and detects abnormal behavior beyond static threshold-based monitoring. This allows the system to identify resource anomalies based on historical patterns rather than only fixed CPU or memory limits.

The Pod LSTM Metrics Agent helps detect cases such as:

* Abnormal Pod CPU usage.
* Abnormal Pod memory behavior.
* Resource patterns that deviate from learned telemetry history.

---

### Kubernetes Incident Analysis

OpsLens AI can investigate and reason over common Kubernetes failure patterns, including:

* Service selector mismatch.
* Empty or missing service endpoints.
* Readiness probe failures.
* CrashLoopBackOff and startup failures.
* Missing runtime configuration.
* OOMKilled workloads.
* Pod-level CPU and memory anomalies.
* Related but non-primary findings within the same namespace.

---

### LLM-Based Root-Cause Reasoning

The LLM reasoning agent is used for explanation and report generation, not for direct cluster execution.

The LLM receives structured evidence from the Supervisor and generates:

* Incident summary.
* Probable root cause.
* Root-cause story.
* Confidence level.
* Recommended next actions.
* Validation checks.
* Related findings.
* Technical evidence summary.

This makes the final report easier for engineers to understand while keeping the reasoning grounded in collected evidence.

---

### Safety and Evidence Alignment

OpsLens AI includes a Python safety and consistency layer to keep LLM output aligned with the collected evidence.

The safety layer helps ensure that:

* LLM recommendations are treated as recommended next actions, not guaranteed fixes.
* Suggested actions remain aligned with the identified incident.
* Dangerous or destructive commands are avoided.
* Report content remains consistent across the web interface and PDF export.
* The final output is suitable for human review before any real operational action.

---

## High-Level Architecture

```text
User Investigation Scope
        ↓
Collectors
        ↓
Specialized Agents
        ↓
Supervisor-Driven Orchestration
        ↓
Structured Evidence
        ↓
LLM Reasoning Agent
        ↓
Safety & Consistency Layer
        ↓
Final RCA Report
```

---

## Investigation Workflow

1. The user selects the investigation scope, including node, namespace, and incident focus.
2. Collectors gather Kubernetes events, workload state, logs, configuration data, and metrics.
3. Specialized agents analyze each evidence type independently.
4. The Supervisor coordinates the investigation and correlates agent findings.
5. The Supervisor identifies the primary incident and separates related findings from noise.
6. Structured evidence is passed to the LLM reasoning agent.
7. The LLM generates an evidence-based RCA report.
8. The safety layer validates the output and keeps recommendations aligned with collected evidence.
9. The final report is displayed in the interface and can be exported as a PDF.

---

## Agents

| Agent                        | Responsibility                                                                                                                           |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Kubernetes Events Agent      | Reads Kubernetes lifecycle events and detects signals such as failed probes, restarts, BackOff states, and workload availability issues. |
| Application Logs Agent       | Analyzes application and container logs to extract runtime errors, tracebacks, fatal startup messages, and connection failures.          |
| Workload Configuration Agent | Inspects Kubernetes workload configuration, service relationships, selectors, probes, endpoints, and availability signals.               |
| Node Resource Metrics Agent  | Detects abnormal node-level CPU and memory behavior to identify possible infrastructure pressure.                                        |
| Pod LSTM Metrics Agent       | Uses a time-aware LSTM model to detect abnormal pod-level CPU and memory behavior from telemetry history.                                |
| Supervisor Agent             | Coordinates agent execution, aggregates findings, identifies the primary incident, filters noise, and prepares structured evidence.      |
| LLM Reasoning Agent          | Converts structured evidence into a human-readable root-cause analysis report with recommended next actions and validation checks.       |

---

## LLM Reasoning Design

OpsLens AI separates evidence collection, reasoning, and execution.

The LLM is responsible for:

* Explaining the incident in a clear operational story.
* Connecting technical evidence to probable root cause.
* Generating recommended next actions.
* Producing validation checks.
* Creating a readable RCA report for engineers.

Python and deterministic logic are responsible for:

* Collecting Kubernetes evidence.
* Running detection agents.
* Structuring Supervisor findings.
* Validating and sanitizing report output.
* Preventing unsafe or hallucinated remediation guidance.

This design allows flexible LLM reasoning while keeping the investigation evidence-based and safe for human review.

---

## Runbook Knowledge Base

OpsLens AI includes a runbook knowledge base for known operational patterns.

Known signals can be mapped to trusted markdown runbooks through:

```text
knowledge_base/runbook_registry.json
```

Runbooks provide additional remediation context and operational guidance when the detected incident matches a known pattern.

Example structure:

```text
knowledge_base/
├── runbook_registry.json
└── runbooks/
```

---

## Reproducible Kubernetes Incident Cases

The project includes reproducible Kubernetes incident cases to validate the investigation pipeline end-to-end.

Examples include:

* Service selector mismatch.
* Readiness probe failure.
* CrashLoop startup error.
* Missing environment variable traceback.
* OOMKilled worker.
* Pod CPU anomaly.
* Readiness issue with a related CPU-heavy neighbor pod.

These cases are used to test evidence collection, agent analysis, Supervisor correlation, LLM reasoning, and final report generation.

---

## Technology Stack

* **Python**
* **FastAPI**
* **Kubernetes**
* **kubectl**
* **Kubernetes Metrics API**
* **TensorFlow / Keras**
* **LSTM-based anomaly detection**
* **Gemini LLM**
* **HTML, CSS, JavaScript**
* **PDF report generation**
* **Runbook knowledge base**

---

## Project Structure

```text
OpsLens-AI/
├── ansible/
├── artifacts/
├── data/
├── knowledge_base/
│   ├── runbook_registry.json
│   └── runbooks/
├── prompts/
├── reports/
├── scenarios/
├── src/
│   ├── agents/
│   ├── api/
│   ├── collectors/
│   ├── core/
│   ├── knowledge/
│   ├── schemas/
│   ├── utils/
│   └── workflows/
├── tools/
├── web/
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── requirements.txt
└── README.md
```

---

## Current Scope

The current version focuses on:

* Kubernetes incident investigation.
* Node and namespace scoped analysis.
* Multi-agent evidence collection and correlation.
* Node-level resource anomaly detection.
* Pod-level LSTM anomaly detection.
* LLM-assisted root-cause analysis.
* Evidence-based recommended next actions.
* PDF and interface-based incident report generation.
* Reproducible Kubernetes incident validation cases.

---

## Future Work

Planned future enhancements include:

* Integrating LangGraph for more advanced stateful multi-agent orchestration.
* Adding Prometheus support for richer historical metrics.
* Expanding the runbook knowledge base.
* Adding more Kubernetes and Linux incident categories.
* Improving multi-incident grouping across larger namespaces.
* Adding automated smoke tests and CI checks.
* Supporting more advanced report comparison and incident history analytics.

---

## Security Notes

* LLM-generated recommendations are not executed automatically.
* Recommended actions are intended for human review before execution.
* Destructive commands are avoided or filtered by the safety layer.
* API keys, secrets, kubeconfig files, `.env` files, and cloud credentials should not be committed.
* Runtime reports and generated investigation data should be excluded from source control when appropriate.

---

## Status

OpsLens AI is an active graduation project focused on multi-agent AIOps, Kubernetes incident investigation, anomaly detection, Supervisor-driven orchestration, and LLM-assisted root-cause analysis.
