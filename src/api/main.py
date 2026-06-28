from typing import Dict, Any


from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api import services as api_services
from src.api import history_store

from src.api.schemas import InvestigationRequest, FeedbackRequest
from src.api.services import (
    get_job,
    get_latest_job,
    get_latest_report_path,
    get_report_path,
    list_namespaces,
    list_nodes,
    list_scenarios,
    start_investigation_job,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"

app = FastAPI(
    title="OpsLens AI API",
    version="1.0.0",
    description="FastAPI bridge between OpsLens frontend and the investigation pipeline.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "opslens-api",
    }


@app.get("/api/cluster/nodes")
def api_nodes():
    try:
        return {"nodes": list_nodes()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/cluster/namespaces")
def api_namespaces():
    try:
        return {"namespaces": list_namespaces()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/scenarios")
def api_scenarios():
    try:
        return {"scenarios": list_scenarios()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/investigations")
def api_start_investigation(request: InvestigationRequest):
    try:
        return start_investigation_job(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/investigations/latest")
def api_latest_investigation():
    latest = get_latest_job()

    if not latest:
        raise HTTPException(status_code=404, detail="No investigation jobs found.")

    return latest


@app.get("/api/investigations/{job_id}")
def api_get_investigation(job_id: str):
    try:
        return get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/investigations/{job_id}/report/download")
def api_download_markdown_report(job_id: str):
    try:
        path = get_report_path(job_id, kind="markdown")
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type="text/markdown",
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/investigations/{job_id}/report/json/download")
def api_download_json_report(job_id: str):
    try:
        path = get_report_path(job_id, kind="json")
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type="application/json",
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/reports/latest/download")
def api_download_latest_markdown_report():
    try:
        path = get_latest_report_path(kind="markdown")
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type="text/markdown",
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/reports/latest/json/download")
def api_download_latest_json_report():
    try:
        path = get_latest_report_path(kind="json")
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type="application/json",
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))



# =========================================================
# OpsLens UI V2 API endpoints
# =========================================================

@app.get("/api/cluster/nodes/{node_name}/namespaces")
def api_namespaces_for_node(node_name: str):
    try:
        return {
            "node": node_name,
            "namespaces": api_services.list_namespaces_for_node(node_name),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/investigations/{job_id}/report/{export_format}/download")
def api_download_report_format(job_id: str, export_format: str):
    try:
        path = api_services.get_report_export_path(job_id, export_format)
        media_types = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json",
            "md": "text/markdown",
            "markdown": "text/markdown",
        }

        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type=media_types.get(export_format.lower(), "application/octet-stream"),
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/reports/latest/{export_format}/download")
def api_download_latest_report_format(export_format: str):
    try:
        path = api_services.get_latest_report_export_path(export_format)
        media_types = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json",
            "md": "text/markdown",
            "markdown": "text/markdown",
        }

        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type=media_types.get(export_format.lower(), "application/octet-stream"),
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))



@app.post("/api/feedback")
def api_feedback(request: FeedbackRequest):
    try:
        return api_services.save_feedback(request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



# =========================================================
# Persistent investigation history endpoints
# =========================================================

@app.get("/api/investigations/history")
def api_investigation_history(limit: int = 50):
    try:
        return {
            "records": api_services.list_investigation_history(limit=limit),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/investigations/history/{record_id}")
def api_investigation_history_record(record_id: str):
    try:
        return api_services.get_history_report(record_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/investigations/history/{record_id}/report/{export_format}/download")
def api_download_history_report(record_id: str, export_format: str):
    try:
        path = api_services.get_history_export_path(record_id, export_format)

        media_types = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json",
            "md": "text/markdown",
            "markdown": "text/markdown",
        }

        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type=media_types.get(export_format.lower(), "application/octet-stream"),
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))



@app.get("/api/scenarios/details")
def api_scenario_details():
    try:
        return {
            "scenarios": api_services.list_scenario_details(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



# =========================================================
# Non-conflicting history API endpoints
# Route is intentionally /api/history/... to avoid conflict with:
# /api/investigations/{job_id}
# =========================================================

@app.get("/api/history/investigations")
def api_history_investigations(limit: int = 50):
    try:
        return {
            "records": api_services.list_investigation_history(limit=limit),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/history/investigations/{record_id}")
def api_history_investigation_record(record_id: str):
    try:
        return api_services.get_history_report(record_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/history/investigations/{record_id}/report/{export_format}/download")
def api_download_history_investigation_report(record_id: str, export_format: str):
    try:
        path = api_services.get_history_export_path(record_id, export_format)

        media_types = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json",
            "md": "text/markdown",
            "markdown": "text/markdown",
        }

        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type=media_types.get(export_format.lower(), "application/octet-stream"),
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))



@app.post("/api/reports/save")
def api_save_report_to_database(report: Dict[str, Any]):
    try:
        return api_services.save_report_to_database(report)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



@app.get("/api/history/debug")
def api_history_debug():
    try:
        return api_services.debug_history_state()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



# =========================================================
# Stable SQLite DB endpoints
# =========================================================

@app.get("/api/db/history")
def api_db_history(limit: int = 50):
    try:
        return {"records": history_store.list_reports(limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/db/history/{record_id}")
def api_db_history_record(record_id: str):
    try:
        return history_store.get_report(record_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/db/reports/save")
def api_db_save_report(report: dict):
    try:
        return history_store.save_report(report)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/db/scenarios/details")
def api_db_scenario_details():
    try:
        return {"scenarios": history_store.scenario_details()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/db/history/debug")
def api_db_history_debug():
    try:
        return history_store.debug_state()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/db/history/{record_id}/report/{export_format}/download")
def api_db_download_history_report(record_id: str, export_format: str):
    try:
        report = history_store.get_report(record_id)
        path = api_services._export_report(report, export_format, fallback_name=record_id)

        media_types = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "json": "application/json",
            "md": "text/markdown",
            "markdown": "text/markdown",
        }

        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type=media_types.get(export_format.lower(), "application/octet-stream"),
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# Serve frontend last.
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")



# =========================================================
# Direct report export endpoint
# Exports the selected report payload directly.
# Avoids stale DB/path based export bugs.
# =========================================================

from typing import Any as _Any
from io import BytesIO as _BytesIO
from fastapi import Body as _Body
from fastapi.responses import Response as _Response


def _export_safe_text(value: _Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{k}: {_export_safe_text(v)}" for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(_export_safe_text(v) for v in value)
    return str(value)


def _export_normalize_report(payload: _Any) -> dict:
    if isinstance(payload, dict):
        for key in ("report", "result", "final_report", "incident_report"):
            if isinstance(payload.get(key), dict):
                return payload[key]
        return payload

    if isinstance(payload, list):
        return {
            "title": "OpsLens Report",
            "severity": "not found",
            "confidence": "not found",
            "affected_resources": {},
            "incident_summary": "Report payload was received as a list.",
            "evidence_trail": payload,
            "additional_findings": [],
            "recommended_fix": {
                "strategy": "Review the exported evidence.",
                "safe_commands": [],
                "verification_plan": "Verify the selected Kubernetes scope.",
                "verification_commands": [],
            },
        }

    return {
        "title": "OpsLens Report",
        "severity": "not found",
        "confidence": "not found",
        "affected_resources": {},
        "incident_summary": _export_safe_text(payload) or "No report content found.",
        "evidence_trail": [],
        "additional_findings": [],
        "recommended_fix": {},
    }


def _export_list_markdown(value: _Any) -> str:
    if not value:
        return "- Not found in collected evidence"

    if isinstance(value, list):
        if not value:
            return "- Not found in collected evidence"

        lines = []
        for item in value:
            if isinstance(item, dict):
                command = item.get("command")
                title = item.get("title")
                if command:
                    lines.append(f"- {f'**{title}:** ' if title else ''}`{command}`")
                else:
                    lines.append(f"- {_export_safe_text(item)}")
            else:
                lines.append(f"- {_export_safe_text(item)}")
        return "\n".join(lines)

    if isinstance(value, dict):
        return "\n".join(
            f"- **{key}:** {_export_safe_text(val) or 'Not found in collected evidence'}"
            for key, val in value.items()
        )

    return f"- {_export_safe_text(value)}"


def _export_report_to_markdown(report_payload: _Any) -> str:
    report = _export_normalize_report(report_payload)
    affected = report.get("affected_resources") or {}
    fix = report.get("recommended_fix") or {}

    return f"""# {report.get("title") or "OpsLens Report"}

## Status

| Field | Value |
|---|---|
| Severity | {report.get("severity") or "not found"} |
| Confidence | {report.get("confidence") or "not found"} |
| Namespace | {affected.get("namespace") or "not found in collected evidence"} |
| Node | {affected.get("node") or affected.get("node_name") or "not found in collected evidence"} |
| Service | {affected.get("service") or "not found in collected evidence"} |
| Deployment | {affected.get("deployment") or "not found in collected evidence"} |

## Incident Summary

{report.get("incident_summary") or report.get("summary") or "No active incident was detected in the selected scope."}

## Evidence Trail

{_export_list_markdown(report.get("evidence_trail") or report.get("evidence"))}

## Additional Findings

{_export_list_markdown(report.get("additional_findings") or report.get("additional_issues"))}

## Root Cause Story

{report.get("root_cause_story") or report.get("root_cause") or "No root cause was identified because no active failure evidence was found."}

## Recommended Fix

{fix.get("strategy") or report.get("recommendation") or "No remediation required. Continue monitoring."}

## Safe Commands

{_export_list_markdown(fix.get("safe_commands") or report.get("safe_commands"))}

## Verification Plan

{fix.get("verification_plan") or report.get("verification_plan") or "Verify the selected namespace state."}

## Verification Commands

{_export_list_markdown(fix.get("verification_commands") or report.get("verification_commands"))}

---

OpsLens can make mistakes. Verify evidence and safe commands before applying changes.
"""


def _export_filename(report_payload: _Any, ext: str) -> str:
    report = _export_normalize_report(report_payload)
    affected = report.get("affected_resources") or {}

    base = (
        affected.get("service")
        or affected.get("deployment")
        or affected.get("namespace")
        or report.get("title")
        or "opslens-report"
    )

    clean = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(base)).strip("-") or "opslens-report"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{clean}_{stamp}.{ext}"


@app.post("/api/export/report/{export_format}")
async def export_report_direct(export_format: str, report_payload: _Any = _Body(...)):
    fmt = export_format.lower().strip()
    report = _export_normalize_report(report_payload)

    if fmt in {"md", "markdown"}:
        content = _export_report_to_markdown(report)
        return _Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{_export_filename(report, "md")}"'
            },
        )

    if fmt == "json":
        import json
        return _Response(
            content=json.dumps(report, indent=2, ensure_ascii=False),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{_export_filename(report, "json")}"'
            },
        )

    if fmt in {"xlsx", "excel"}:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "OpsLens Report"

        affected = report.get("affected_resources") or {}
        fix = report.get("recommended_fix") or {}

        rows = [
            ("Title", report.get("title") or "OpsLens Report"),
            ("Severity", report.get("severity") or "not found"),
            ("Confidence", report.get("confidence") or "not found"),
            ("Namespace", affected.get("namespace") or "not found in collected evidence"),
            ("Node", affected.get("node") or affected.get("node_name") or "not found in collected evidence"),
            ("Service", affected.get("service") or "not found in collected evidence"),
            ("Deployment", affected.get("deployment") or "not found in collected evidence"),
            ("Incident Summary", report.get("incident_summary") or report.get("summary") or ""),
            ("Evidence Trail", _export_safe_text(report.get("evidence_trail") or report.get("evidence"))),
            ("Additional Findings", _export_safe_text(report.get("additional_findings") or report.get("additional_issues"))),
            ("Root Cause Story", report.get("root_cause_story") or report.get("root_cause") or ""),
            ("Recommended Fix", fix.get("strategy") or report.get("recommendation") or ""),
            ("Safe Commands", _export_safe_text(fix.get("safe_commands") or report.get("safe_commands"))),
            ("Verification Plan", fix.get("verification_plan") or report.get("verification_plan") or ""),
            ("Verification Commands", _export_safe_text(fix.get("verification_commands") or report.get("verification_commands"))),
        ]

        ws.append(["Field", "Value"])
        for row in rows:
            ws.append(list(row))

        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 110

        stream = _BytesIO()
        wb.save(stream)
        stream.seek(0)

        return _Response(
            content=stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{_export_filename(report, "xlsx")}"'
            },
        )

    if fmt == "pdf":
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from xml.sax.saxutils import escape

        stream = _BytesIO()
        doc = SimpleDocTemplate(
            stream,
            pagesize=landscape(letter),
            rightMargin=0.45 * inch,
            leftMargin=0.45 * inch,
            topMargin=0.45 * inch,
            bottomMargin=0.45 * inch,
        )

        styles = getSampleStyleSheet()
        story = []

        markdown = _export_report_to_markdown(report)
        for line in markdown.splitlines():
            line = line.strip()

            if not line:
                story.append(Spacer(1, 8))
                continue

            if line.startswith("# "):
                story.append(Paragraph(f"<b>{escape(line[2:])}</b>", styles["Title"]))
            elif line.startswith("## "):
                story.append(Paragraph(f"<b>{escape(line[3:])}</b>", styles["Heading2"]))
            else:
                story.append(Paragraph(escape(line), styles["BodyText"]))

        doc.build(story)
        stream.seek(0)

        return _Response(
            content=stream.getvalue(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{_export_filename(report, "pdf")}"'
            },
        )

    return _Response(
        content=f"Unsupported export format: {export_format}",
        status_code=400,
        media_type="text/plain",
    )

