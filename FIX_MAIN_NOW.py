from pathlib import Path
import re

main_path = Path("src/api/main.py")

if not main_path.exists():
    raise SystemExit("ERROR: src/api/main.py not found")

main = main_path.read_text(encoding="utf-8", errors="ignore")

# =========================================================
# 1) Stable record_id for frontend accidental saves
# =========================================================

old_record_func = '''def _record_id_for_report(report: Dict[str, Any]) -> str:
    # Stable ID prevents the same report from being saved several times by repeated UI renders.
    for key in ("record_id", "id"):
        if report.get(key):
            return history_store.safe(report[key])

    if report.get("json_report_path"):
        return history_store.safe(Path(str(report["json_report_path"])).stem)

    stable_source = json.dumps(report, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha1(stable_source.encode("utf-8")).hexdigest()[:12]
    return history_store.safe(f"{_report_service(report)}_{digest}")
'''

new_record_func = '''def _record_id_for_report(report: Dict[str, Any]) -> str:
    """
    Stable ID for history records.

    Do NOT hash the full report because fields like created_at, modified_at,
    json paths, and export paths can change between renders and create duplicates.
    Prefer job_id. Otherwise hash only stable incident identity fields.
    """
    for key in ("job_id", "__opslens_job_id", "investigation_id", "run_id", "record_id", "id"):
        value = report.get(key)
        if value:
            return history_store.safe(str(value))

    if report.get("json_report_path"):
        return history_store.safe(Path(str(report["json_report_path"])).stem)

    affected = report.get("affected_resources") or {}

    stable_source = {
        "title": report.get("title", ""),
        "namespace": affected.get("namespace", ""),
        "service": affected.get("service") or affected.get("service_name") or "",
        "deployment": affected.get("deployment") or affected.get("deployment_name") or "",
        "node": affected.get("node") or affected.get("node_name") or "",
        "summary": report.get("incident_summary", ""),
        "root": report.get("root_cause_story", ""),
        "scenario": report.get("source_scenario", ""),
    }

    raw = json.dumps(stable_source, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return history_store.safe(digest)
'''

if old_record_func in main:
    main = main.replace(old_record_func, new_record_func, 1)
    print("OK: _record_id_for_report patched")
else:
    print("SKIP/WARN: _record_id_for_report block not found exactly")

# =========================================================
# 2) History route should not default to 3 records
# =========================================================

main = main.replace(
    '@app.get("/api/db/history")\ndef api_db_history(limit: int = 3)',
    '@app.get("/api/db/history")\ndef api_db_history(limit: int = 20)'
)

print("OK: /api/db/history default limit set to 20")

# =========================================================
# 3) Make v2 export routes use the clean export pipeline
# instead of markdown-to-PDF raw rendering.
# =========================================================

old_v2_routes = '''@app.post("/api/v2/export/{export_format}")
async def opslens_v2_export(export_format: str, report_payload=Body(...)):
    report = _ops_as_dict(report_payload)
    affected = report.get("affected_resources") or {}
    fallback = (
        affected.get("service")
        or affected.get("service_name")
        or report.get("record_id")
        or "opslens-report"
    )

    path, media_type = _ops_make_export_file(report, export_format, fallback_name=fallback)
    return FileResponse(path=str(path), filename=path.name, media_type=media_type)


@app.get("/api/v2/history/{record_id}/download/{export_format}")
def opslens_v2_history_download(record_id: str, export_format: str):
    report = history_store.get_report(record_id)
    path, media_type = _ops_make_export_file(report, export_format, fallback_name=record_id)
    return FileResponse(path=str(path), filename=path.name, media_type=media_type)
'''

new_v2_routes = '''@app.post("/api/v2/export/{export_format}")
async def opslens_v2_export(export_format: str, report_payload=Body(...)):
    # Keep v2 route for compatibility, but use the clean export pipeline.
    report = _normalize_report(_ops_as_dict(report_payload))
    affected = report.get("affected_resources") or {}
    fallback = (
        affected.get("service")
        or affected.get("service_name")
        or report.get("record_id")
        or "opslens-report"
    )

    return _file_response(_export_payload(report, export_format, fallback_name=fallback))


@app.get("/api/v2/history/{record_id}/download/{export_format}")
def opslens_v2_history_download(record_id: str, export_format: str):
    # Keep v2 route for compatibility, but use the clean export pipeline.
    report = history_store.get_report(record_id)
    return _file_response(_export_payload(report, export_format, fallback_name=record_id))
'''

if old_v2_routes in main:
    main = main.replace(old_v2_routes, new_v2_routes, 1)
    print("OK: v2 export routes now use clean export pipeline")
else:
    print("SKIP/WARN: v2 export route block not found exactly")

main_path.write_text(main, encoding="utf-8")

print("")
print("DONE: src/api/main.py patched.")
