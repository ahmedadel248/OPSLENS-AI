
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.api.schemas import InvestigationRequest
from src.core.investigation_scope import InvestigationScope
from scripts.run_incident_investigation import run_investigation as run_opslens_investigation


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = PROJECT_ROOT / "scenarios"
LIVE_DIR = PROJECT_ROOT / "data" / "live"
REPORTS_DIR = PROJECT_ROOT / "data" / "final_incident_reports"

PROTECTED_NAMESPACES = {
    "default",
    "kube-system",
    "kube-public",
    "kube-node-lease",
}

JOBS: Dict[str, Dict[str, Any]] = {}

DEFAULT_STAGES = [
    ("scope", "Investigation Scope"),
    ("scenario", "Scenario Preparation"),
    ("collectors", "Collectors"),
    ("config_agent", "Config Agent"),
    ("logs_agent", "Logs Agent"),
    ("metrics_agent", "Metrics Agent + Model"),
    ("supervisor", "Supervisor Agent"),
    ("llm", "LLM Reasoning"),
    ("safety", "Command Safety Layer"),
    ("report", "Report Generated"),
]


def _new_stages() -> List[Dict[str, str]]:
    return [
        {"key": key, "label": label, "status": "pending"}
        for key, label in DEFAULT_STAGES
    ]


def _set_stage(job_id: str, key: str, status: str) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    for stage in job["stages"]:
        if stage["key"] == key:
            stage["status"] = status
            break


def _set_all_remaining(job_id: str, status: str) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    for stage in job["stages"]:
        if stage["status"] in {"pending", "running"}:
            stage["status"] = status


def _run_cmd(args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )

    if check and result.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            + " ".join(args)
            + "\nSTDOUT:\n"
            + result.stdout
            + "\nSTDERR:\n"
            + result.stderr
        )

    return result


def _kubectl_json(args: List[str]) -> Dict[str, Any]:
    result = _run_cmd(["kubectl", *args, "-o", "json"])
    return json.loads(result.stdout)


def list_nodes() -> List[str]:
    payload = _kubectl_json(["get", "nodes"])
    return [
        item.get("metadata", {}).get("name")
        for item in payload.get("items", [])
        if item.get("metadata", {}).get("name")
    ]


def list_namespaces() -> List[str]:
    payload = _kubectl_json(["get", "namespaces"])
    return [
        item.get("metadata", {}).get("name")
        for item in payload.get("items", [])
        if item.get("metadata", {}).get("name")
    ]


def list_scenarios() -> List[str]:
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(
        list(SCENARIOS_DIR.glob("*.yml"))
        + list(SCENARIOS_DIR.glob("*.yaml"))
    )

    return [path.name for path in files]


def _render_scenario_for_namespace(scenario_name: str, namespace: str, job_id: str) -> Path:
    source_path = SCENARIOS_DIR / scenario_name

    if not source_path.exists():
        raise FileNotFoundError(f"Scenario not found: {scenario_name}")

    text = source_path.read_text(encoding="utf-8")

    known_namespaces = [
        "opslens-chaos",
        "opslens-demo",
        "opslens-lab",
        "opslens-test",
    ]

    for known in known_namespaces:
        text = text.replace(known, namespace)

    LIVE_DIR.mkdir(parents=True, exist_ok=True)

    rendered_path = LIVE_DIR / f"rendered_{job_id}_{scenario_name}"
    rendered_path.write_text(text, encoding="utf-8")

    return rendered_path


def _reset_namespace(namespace: str) -> None:
    if namespace in PROTECTED_NAMESPACES:
        raise ValueError(f"Refusing to reset protected namespace: {namespace}")

    _run_cmd(["kubectl", "delete", "namespace", namespace, "--ignore-not-found"], check=False)


def _ensure_namespace(namespace: str) -> None:
    _run_cmd(["kubectl", "create", "namespace", namespace], check=False)


def _apply_scenario(request: InvestigationRequest, job_id: str) -> None:
    if not request.scenario_name:
        return

    rendered_path = _render_scenario_for_namespace(
        scenario_name=request.scenario_name,
        namespace=request.namespace,
        job_id=job_id,
    )

    _run_cmd(["kubectl", "apply", "-f", str(rendered_path)])


def _progress_ticker(job_id: str, stop_event: threading.Event) -> None:
    """
    V1 progress animation support.

    The real pipeline is currently synchronous, so this ticker gives the UI
    step-by-step movement while the backend investigation runs. When the
    real result returns, the worker marks all stages done/failed.
    """

    ordered = [
        "collectors",
        "config_agent",
        "logs_agent",
        "metrics_agent",
        "supervisor",
        "llm",
        "safety",
    ]

    for key in ordered:
        if stop_event.is_set():
            return

        _set_stage(job_id, key, "running")
        time.sleep(1.5)

        if stop_event.is_set():
            return

        _set_stage(job_id, key, "done")


def start_investigation_job(request: InvestigationRequest) -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_id = f"{timestamp}_{uuid4().hex[:8]}"

    JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "request": request.model_dump(),
        "stages": _new_stages(),
        "report": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "finished_at": None,
    }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, request),
        daemon=True,
    )
    thread.start()

    return get_job(job_id)


def _run_job(job_id: str, request: InvestigationRequest) -> None:
    stop_ticker = threading.Event()

    try:
        JOBS[job_id]["status"] = "running"

        _set_stage(job_id, "scope", "running")
        scope = InvestigationScope(
            node_name=request.node_name,
            namespace=request.namespace,
        )
        scope.validate()
        _set_stage(job_id, "scope", "done")

        _set_stage(job_id, "scenario", "running")

        if request.reset_namespace:
            _reset_namespace(request.namespace)

        _ensure_namespace(request.namespace)

        if request.apply_scenario:
            _apply_scenario(request, job_id)
            if request.wait_seconds:
                time.sleep(request.wait_seconds)

        _set_stage(job_id, "scenario", "done")

        ticker = threading.Thread(
            target=_progress_ticker,
            args=(job_id, stop_ticker),
            daemon=True,
        )
        ticker.start()

        final_report = run_opslens_investigation(
            scope=scope,
            demo_seed_metrics=request.demo_seed_metrics,
        )

        stop_ticker.set()
        _set_all_remaining(job_id, "done")

        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["report"] = final_report
        JOBS[job_id]["finished_at"] = datetime.now().isoformat()

    except Exception as exc:
        stop_ticker.set()
        _set_all_remaining(job_id, "failed")

        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = f"{type(exc).__name__}: {exc}"
        JOBS[job_id]["traceback"] = traceback.format_exc()
        JOBS[job_id]["finished_at"] = datetime.now().isoformat()


def get_job(job_id: str) -> Dict[str, Any]:
    if job_id not in JOBS:
        raise KeyError(f"Investigation job not found: {job_id}")

    return JOBS[job_id]


def get_latest_job() -> Optional[Dict[str, Any]]:
    if not JOBS:
        return None

    return list(JOBS.values())[-1]


def get_report_path(job_id: str, kind: str = "markdown") -> Path:
    job = get_job(job_id)
    report = job.get("report") or {}

    if kind == "json":
        path_value = report.get("json_report_path")
    else:
        path_value = report.get("markdown_report_path")

    if not path_value:
        raise FileNotFoundError(f"No {kind} report path found for job {job_id}")

    path = PROJECT_ROOT / path_value

    if not path.exists():
        raise FileNotFoundError(f"Report file does not exist: {path}")

    return path


def get_latest_report_path(kind: str = "markdown") -> Path:
    completed_jobs = [
        job for job in JOBS.values()
        if job.get("status") == "completed" and job.get("report")
    ]

    if completed_jobs:
        return get_report_path(completed_jobs[-1]["job_id"], kind=kind)

    pattern = "*.json" if kind == "json" else "*.md"
    files = sorted(REPORTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        raise FileNotFoundError("No reports found.")

    return files[0]


# =========================================================
# OpsLens UI V2 additions:
# - node-scoped namespace filtering
# - PDF / Excel / Markdown / JSON report exports
# =========================================================

EXPORTS_DIR = REPORTS_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def list_namespaces_for_node(node_name: str) -> List[str]:
    """
    Kubernetes namespaces are cluster-scoped, not node-scoped.

    This function returns namespaces that currently have at least one Pod
    scheduled on the selected node. This matches the UI behavior:
    user selects node -> UI shows relevant namespaces for that node.
    """

    if not node_name:
        return list_namespaces()

    result = _run_cmd(
        [
            "kubectl",
            "get",
            "pods",
            "-A",
            "--field-selector",
            f"spec.nodeName={node_name}",
            "-o",
            "json",
        ]
    )

    payload = json.loads(result.stdout)

    namespaces = sorted(
        {
            item.get("metadata", {}).get("namespace")
            for item in payload.get("items", [])
            if item.get("metadata", {}).get("namespace")
        }
    )

    return namespaces


def _safe_filename(value: str) -> str:
    allowed = []

    for char in str(value or "opslens_report"):
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
        elif char.isspace():
            allowed.append("_")

    result = "".join(allowed).strip("_")
    return result or "opslens_report"


def _report_base_name(report: Dict[str, Any], fallback: str = "opslens_report") -> str:
    title = report.get("title") or fallback
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _safe_filename(f"{timestamp}_{title}")[:140]


def _latest_json_report_path() -> Path:
    files = sorted(REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        raise FileNotFoundError("No JSON reports found.")

    return files[0]


def _load_report_from_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _report_from_job(job_id: str) -> Dict[str, Any]:
    job = get_job(job_id)
    report = job.get("report")

    if not report:
        raise FileNotFoundError(f"No report available for job {job_id}")

    return report


def _paragraph_text(value: Any) -> str:
    import html

    text = str(value or "")
    return html.escape(text).replace("\n", "<br/>")


def _write_pdf_report(report: Dict[str, Any], output_path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        Preformatted,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="OpsTitle",
            parent=styles["Title"],
            fontSize=20,
            leading=24,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="OpsHeading",
            parent=styles["Heading2"],
            fontSize=13,
            leading=16,
            spaceBefore=12,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="OpsBody",
            parent=styles["BodyText"],
            fontSize=9.5,
            leading=13,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="OpsSmall",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10,
        )
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
    )

    story = []

    def heading(text: str):
        story.append(Paragraph(_paragraph_text(text), styles["OpsHeading"]))

    def para(text: Any):
        story.append(Paragraph(_paragraph_text(text), styles["OpsBody"]))

    def table(headers, rows):
        if not rows:
            para("No data available.")
            return

        data = [
            [Paragraph(_paragraph_text(cell), styles["OpsSmall"]) for cell in headers]
        ]

        for row in rows:
            data.append([Paragraph(_paragraph_text(cell), styles["OpsSmall"]) for cell in row])

        tbl = Table(data, repeatRows=1, hAlign="LEFT")
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(tbl)
        story.append(Spacer(1, 10))

    affected = report.get("affected_resources") or {}
    fix = report.get("recommended_fix") or {}
    verification = report.get("verification") or {}

    story.append(Paragraph(_paragraph_text(report.get("title", "OpsLens Incident Report")), styles["OpsTitle"]))
    para(f"Severity: {report.get('severity', 'unknown')} | Confidence: {report.get('confidence', 'unknown')}")
    para(f"Namespace: {affected.get('namespace', '')} | Node: {affected.get('node', '')} | Service: {affected.get('service', '')}")

    heading("Incident Summary")
    para(report.get("incident_summary", ""))

    heading("Primary Root Cause")
    para(report.get("root_cause_story", ""))

    heading("Evidence Trail")
    evidence_rows = [
        [
            row.get("agent", ""),
            row.get("finding", ""),
            row.get("meaning", ""),
        ]
        for row in report.get("agent_reasoning", []) or []
    ]
    table(["Agent", "Finding", "Meaning"], evidence_rows)

    heading("Additional Findings")
    additional_rows = [
        [
            row.get("resource", ""),
            row.get("finding", ""),
            row.get("impact", ""),
            row.get("priority", ""),
        ]
        for row in report.get("additional_findings", []) or []
    ]
    table(["Resource", "Finding", "Impact", "Priority"], additional_rows)

    heading("Recommended Fix")
    para(fix.get("strategy", ""))

    action_rows = [
        [
            action.get("action_type", ""),
            action.get("target_kind", ""),
            action.get("reason", ""),
            action.get("risk", ""),
        ]
        for action in fix.get("actions", []) or []
    ]
    table(["Action", "Target", "Reason", "Risk"], action_rows)

    heading("Safe Commands")
    commands = fix.get("commands", []) or []
    if commands:
        for index, command in enumerate(commands, start=1):
            para(f"Command {index}")
            story.append(Preformatted(str(command), styles["Code"]))
            story.append(Spacer(1, 8))
    else:
        para("No commands available.")

    heading("Verification Plan")
    para(verification.get("intent", ""))

    verification_commands = verification.get("commands", []) or []
    if verification_commands:
        for index, command in enumerate(verification_commands, start=1):
            para(f"Check {index}")
            story.append(Preformatted(str(command), styles["Code"]))
            story.append(Spacer(1, 8))

    doc.build(story)
    return output_path


def _write_excel_report(report: Dict[str, Any], output_path: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    header_fill = PatternFill("solid", fgColor="0F172A")
    header_font = Font(color="FFFFFF", bold=True)
    title_font = Font(size=14, bold=True)
    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def style_sheet(ws):
        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = border

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font

        for col in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(col)].width = 28

    def write_rows(ws, headers, rows):
        ws.append(headers)
        for row in rows:
            ws.append(row)
        style_sheet(ws)

    affected = report.get("affected_resources") or {}
    fix = report.get("recommended_fix") or {}
    verification = report.get("verification") or {}
    facts = report.get("root_cause_facts") or {}

    ws = wb.active
    ws.title = "Summary"
    ws.append(["Field", "Value"])
    summary_rows = [
        ["Title", report.get("title", "")],
        ["Severity", report.get("severity", "")],
        ["Confidence", report.get("confidence", "")],
        ["Namespace", affected.get("namespace", "")],
        ["Node", affected.get("node", "")],
        ["Service", affected.get("service", "")],
        ["Deployment", affected.get("deployment", "")],
        ["Incident Summary", report.get("incident_summary", "")],
        ["Primary Root Cause", report.get("root_cause_story", "")],
        ["Fix Strategy", fix.get("strategy", "")],
        ["Verification Intent", verification.get("intent", "")],
    ]
    for row in summary_rows:
        ws.append(row)
    style_sheet(ws)
    ws["A1"].font = title_font

    ws = wb.create_sheet("Evidence Trail")
    write_rows(
        ws,
        ["Agent", "Finding", "Meaning"],
        [
            [row.get("agent", ""), row.get("finding", ""), row.get("meaning", "")]
            for row in report.get("agent_reasoning", []) or []
        ],
    )

    ws = wb.create_sheet("Additional Findings")
    write_rows(
        ws,
        ["Resource", "Finding", "Impact", "Priority"],
        [
            [
                row.get("resource", ""),
                row.get("finding", ""),
                row.get("impact", ""),
                row.get("priority", ""),
            ]
            for row in report.get("additional_findings", []) or []
        ],
    )

    ws = wb.create_sheet("Actions")
    write_rows(
        ws,
        ["Action Type", "Target Kind", "Reason", "Risk"],
        [
            [
                row.get("action_type", ""),
                row.get("target_kind", ""),
                row.get("reason", ""),
                row.get("risk", ""),
            ]
            for row in fix.get("actions", []) or []
        ],
    )

    ws = wb.create_sheet("Safe Commands")
    write_rows(
        ws,
        ["Type", "Command"],
        [["Remediation", command] for command in fix.get("commands", []) or []]
        + [["Verification", command] for command in verification.get("commands", []) or []],
    )

    ws = wb.create_sheet("Root Cause Facts")
    write_rows(
        ws,
        ["Fact", "Value"],
        [[key, json.dumps(value, ensure_ascii=False)] for key, value in facts.items()],
    )

    wb.save(output_path)
    return output_path


def _export_report(report: Dict[str, Any], export_format: str, fallback_name: str) -> Path:
    fmt = export_format.lower().strip()
    base = _report_base_name(report, fallback=fallback_name)

    if fmt in {"md", "markdown"}:
        md_path_value = report.get("markdown_report_path")
        if not md_path_value:
            raise FileNotFoundError("Markdown report path is missing.")
        return PROJECT_ROOT / md_path_value

    if fmt == "json":
        json_path_value = report.get("json_report_path")
        if not json_path_value:
            raise FileNotFoundError("JSON report path is missing.")
        return PROJECT_ROOT / json_path_value

    if fmt == "pdf":
        output_path = EXPORTS_DIR / f"{base}.pdf"
        return _write_pdf_report(report, output_path)

    if fmt in {"xlsx", "excel"}:
        output_path = EXPORTS_DIR / f"{base}.xlsx"
        return _write_excel_report(report, output_path)

    raise ValueError(f"Unsupported report format: {export_format}")


def get_report_export_path(job_id: str, export_format: str) -> Path:
    report = _report_from_job(job_id)
    return _export_report(report, export_format, fallback_name=job_id)


def get_latest_report_export_path(export_format: str) -> Path:
    completed_jobs = [
        job for job in JOBS.values()
        if job.get("status") == "completed" and job.get("report")
    ]

    if completed_jobs:
        latest = completed_jobs[-1]
        return get_report_export_path(latest["job_id"], export_format)

    json_path = _latest_json_report_path()
    report = _load_report_from_json(json_path)
    return _export_report(report, export_format, fallback_name=json_path.stem)

