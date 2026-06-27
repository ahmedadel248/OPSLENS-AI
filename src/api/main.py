
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api import services as api_services

from src.api.schemas import InvestigationRequest
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


# Serve frontend last.
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
