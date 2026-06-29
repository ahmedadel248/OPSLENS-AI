
from __future__ import annotations

import json
import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = DATA_DIR / "final_incident_reports"
SCENARIOS_DIR = PROJECT_ROOT / "scenarios"
DB_PATH = DATA_DIR / "opslens.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    with conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                record_id TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                status TEXT DEFAULT 'completed',
                created_at TEXT DEFAULT '',
                modified_at TEXT DEFAULT '',
                service TEXT DEFAULT '',
                namespace TEXT DEFAULT '',
                node TEXT DEFAULT '',
                severity TEXT DEFAULT '',
                confidence TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                root_cause TEXT DEFAULT '',
                fix_strategy TEXT DEFAULT '',
                json_report_path TEXT DEFAULT '',
                markdown_report_path TEXT DEFAULT '',
                report_json TEXT DEFAULT '{}'
            )
        """)

        # Lightweight migration for older opslens.db files.
        required_report_columns = {
            "record_id": "TEXT DEFAULT ''",
            "title": "TEXT DEFAULT ''",
            "status": "TEXT DEFAULT 'completed'",
            "created_at": "TEXT DEFAULT ''",
            "modified_at": "TEXT DEFAULT ''",
            "service": "TEXT DEFAULT ''",
            "namespace": "TEXT DEFAULT ''",
            "node": "TEXT DEFAULT ''",
            "severity": "TEXT DEFAULT ''",
            "confidence": "TEXT DEFAULT ''",
            "summary": "TEXT DEFAULT ''",
            "root_cause": "TEXT DEFAULT ''",
            "fix_strategy": "TEXT DEFAULT ''",
            "json_report_path": "TEXT DEFAULT ''",
            "markdown_report_path": "TEXT DEFAULT ''",
            "report_json": "TEXT DEFAULT '{}'",
        }
        existing = {row[1] for row in db.execute("PRAGMA table_info(reports)").fetchall()}
        for name, definition in required_report_columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE reports ADD COLUMN {name} {definition}")

        db.execute("""
            CREATE TABLE IF NOT EXISTS scenarios (
                filename TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                impact TEXT DEFAULT '',
                expected TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            )
        """)


def safe(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)
    return value.strip("_") or "record"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def looks_like_report(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False

    keys = {
        "title",
        "incident_summary",
        "root_cause_story",
        "recommended_fix",
        "affected_resources",
        "agent_reasoning",
        "verification",
    }
    return bool(keys.intersection(payload.keys()))



def dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def fix_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"strategy": "\n".join(str(item) for item in value), "actions": [], "commands": []}
    if isinstance(value, str):
        return {"strategy": value, "actions": [], "commands": []}
    return {"strategy": "", "actions": [], "commands": []}


def normalize_report(report: Dict[str, Any]) -> Dict[str, Any]:
    report = dict(report or {})
    if not isinstance(report.get("affected_resources"), dict):
        report["affected_resources"] = {}
    report["recommended_fix"] = fix_to_dict(report.get("recommended_fix"))
    verification = report.get("verification")
    if isinstance(verification, dict):
        report["verification"] = verification
    elif isinstance(verification, list):
        report["verification"] = {"intent": "\n".join(str(item) for item in verification), "commands": []}
    elif isinstance(verification, str):
        report["verification"] = {"intent": verification, "commands": []}
    else:
        report["verification"] = {"intent": "", "commands": []}
    return report

def service_from_report(report: Dict[str, Any]) -> str:
    affected = dict_or_empty(report.get("affected_resources"))

    return (
        affected.get("service")
        or affected.get("service_name")
        or affected.get("workload")
        or affected.get("deployment")
        or affected.get("pod")
        or "unknown-service"
    )



def stable_report_key(report: Dict[str, Any]) -> str:
    for key in ("job_id", "__opslens_job_id", "investigation_id", "run_id"):
        value = report.get(key)
        if value:
            return safe(str(value))

    affected = report.get("affected_resources") or {}
    seed = {
        "title": report.get("title", ""),
        "summary": report.get("incident_summary", ""),
        "root": report.get("root_cause_story", ""),
        "service": service_from_report(report),
        "namespace": affected.get("namespace", ""),
        "node": affected.get("node", ""),
    }

    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_record(report: Dict[str, Any], json_path: Path, record_id: Optional[str] = None) -> Dict[str, Any]:
    report = normalize_report(report)
    affected = dict_or_empty(report.get("affected_resources"))
    fix = fix_to_dict(report.get("recommended_fix"))

    service = service_from_report(report)
    now = datetime.now().isoformat()
    created_at = report.get("created_at") or report.get("timestamp") or now

    if not record_id:
        record_id = safe(json_path.stem)

    report = dict(report)
    report["json_report_path"] = rel(json_path)
    report.setdefault("created_at", created_at)

    modified_at = datetime.fromtimestamp(json_path.stat().st_mtime).isoformat() if json_path.exists() else now

    return {
        "record_id": safe(record_id),
        "title": report.get("title") or "OpsLens Investigation",
        "status": "completed",
        "created_at": created_at,
        "modified_at": modified_at,
        "service": service,
        "namespace": affected.get("namespace", ""),
        "node": affected.get("node", "") or affected.get("node_name", ""),
        "severity": report.get("severity", "unknown"),
        "confidence": report.get("confidence", "unknown"),
        "summary": report.get("incident_summary", ""),
        "root_cause": report.get("root_cause_story", ""),
        "fix_strategy": fix.get("strategy", ""),
        "json_report_path": rel(json_path),
        "markdown_report_path": report.get("markdown_report_path", ""),
        "report_json": json.dumps(report, ensure_ascii=False),
    }


def upsert_report(record: Dict[str, Any]) -> None:
    init_db()

    with conn() as db:
        db.execute("""
            INSERT INTO reports (
                record_id, title, status, created_at, modified_at,
                service, namespace, node, severity, confidence,
                summary, root_cause, fix_strategy,
                json_report_path, markdown_report_path, report_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                title = excluded.title,
                status = excluded.status,
                created_at = reports.created_at,
                modified_at = excluded.modified_at,
                service = excluded.service,
                namespace = excluded.namespace,
                node = excluded.node,
                severity = excluded.severity,
                confidence = excluded.confidence,
                summary = excluded.summary,
                root_cause = excluded.root_cause,
                fix_strategy = excluded.fix_strategy,
                json_report_path = excluded.json_report_path,
                markdown_report_path = excluded.markdown_report_path,
                report_json = excluded.report_json
        """, (
            record["record_id"],
            record["title"],
            record["status"],
            record["created_at"],
            record["modified_at"],
            record["service"],
            record["namespace"],
            record["node"],
            record["severity"],
            record["confidence"],
            record["summary"],
            record["root_cause"],
            record["fix_strategy"],
            record["json_report_path"],
            record["markdown_report_path"],
            record["report_json"],
        ))


def save_report(report: Dict[str, Any], record_id: Optional[str] = None) -> Dict[str, Any]:
    init_db()
    report = normalize_report(report)

    if not looks_like_report(report):
        raise ValueError("Payload is not a valid OpsLens report.")

    service = service_from_report(report)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not record_id:
        record_id = stable_report_key(report)

    record_id = safe(record_id)
    json_path = REPORTS_DIR / f"{record_id}.json"

    report_to_save = dict(report)
    report_to_save["json_report_path"] = rel(json_path)
    report_to_save.setdefault(
        "created_at",
        report_to_save.get("generated_at")
        or report_to_save.get("timestamp")
        or datetime.now().isoformat()
    )

    json_path.write_text(
        json.dumps(report_to_save, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    record = build_record(report_to_save, json_path, record_id=record_id)
    upsert_report(record)
    return record


def candidate_json_files() -> List[Path]:
    dirs = [
        REPORTS_DIR,
        DATA_DIR / "reports",
        DATA_DIR / "live",
        PROJECT_ROOT / "data",
    ]

    found: List[Path] = []
    seen = set()

    for directory in dirs:
        if not directory.exists():
            continue

        for path in directory.rglob("*.json"):
            key = str(path.resolve()).lower()
            if key in seen:
                continue

            seen.add(key)
            found.append(path)

    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def sync_reports() -> None:
    init_db()

    for path in candidate_json_files():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if isinstance(payload, list):
            continue

        if not looks_like_report(payload):
            continue

        upsert_report(build_record(payload, path))


def list_reports(limit: int = 50) -> List[Dict[str, Any]]:
    # History source of truth is now SQLite writes from completed investigation jobs.
    # Do not re-sync old JSON artifacts here, because that recreates duplicate records
    # with current file timestamps.
    init_db()

    with conn() as db:
        rows = db.execute("""
            SELECT
                record_id, title, status, created_at, modified_at,
                service, namespace, node, severity, confidence,
                summary, root_cause, fix_strategy,
                json_report_path, markdown_report_path
            FROM reports
            ORDER BY datetime(created_at) DESC
            LIMIT ?
        """, (int(limit),)).fetchall()

    return [dict(row) for row in rows]


def get_report(record_id: str) -> Dict[str, Any]:
    init_db()

    with conn() as db:
        row = db.execute(
            "SELECT report_json FROM reports WHERE record_id = ?",
            (safe(record_id),),
        ).fetchone()

    if not row:
        raise FileNotFoundError(f"Report not found: {record_id}")

    return json.loads(row["report_json"])


def sync_scenarios() -> None:
    init_db()

    known = {
        "multi_issue_k8s_chaos.yml": {
            "title": "Multi-issue Kubernetes Incident",
            "description": "Primary service connectivity issue with secondary workload failures.",
            "impact": "Frontend cannot reach backend service.",
            "expected": "Primary RCA plus additional findings.",
        },
        "service_targetport_mismatch.yml": {
            "title": "Service TargetPort Mismatch",
            "description": "Service forwards traffic to the wrong targetPort.",
            "impact": "Service traffic fails.",
            "expected": "TargetPort mismatch is identified.",
        },
        "scenario_targetport_mismatch.yml": {
            "title": "Service TargetPort Mismatch",
            "description": "Service forwards traffic to the wrong targetPort.",
            "impact": "Service traffic fails.",
            "expected": "TargetPort mismatch is identified.",
        },
        "scenario_full_stack_incident.yml": {
            "title": "Full-stack Incident",
            "description": "Multiple symptoms for evidence correlation.",
            "impact": "Several resources show failure symptoms.",
            "expected": "Primary incident separated from secondary findings.",
        },
    }

    if not SCENARIOS_DIR.exists():
        return

    paths = sorted(list(SCENARIOS_DIR.glob("*.yml")) + list(SCENARIOS_DIR.glob("*.yaml")))

    with conn() as db:
        for path in paths:
            item = known.get(path.name, {})
            title = item.get("title") or path.stem.replace("_", " ").replace("-", " ").title()

            db.execute("""
                INSERT INTO scenarios (
                    filename, title, description, impact, expected, file_path, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(filename) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    impact = excluded.impact,
                    expected = excluded.expected,
                    file_path = excluded.file_path,
                    updated_at = excluded.updated_at
            """, (
                path.name,
                title,
                item.get("description") or "Kubernetes incident scenario.",
                item.get("impact") or "Impact depends on the scenario resources.",
                item.get("expected") or "OpsLens infers the RCA from evidence.",
                rel(path),
                datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            ))


def scenario_details() -> Dict[str, Dict[str, str]]:
    sync_scenarios()

    with conn() as db:
        rows = db.execute("""
            SELECT filename, title, description, impact, expected
            FROM scenarios
            ORDER BY filename ASC
        """).fetchall()

    return {
        row["filename"]: {
            "title": row["title"],
            "description": row["description"],
            "impact": f"Impact: {row['impact']}",
            "expected": f"Expected RCA: {row['expected']}",
        }
        for row in rows
    }


def debug_state() -> Dict[str, Any]:
    sync_scenarios()
    sync_reports()

    with conn() as db:
        report_count = db.execute("SELECT COUNT(*) AS c FROM reports").fetchone()["c"]
        scenario_count = db.execute("SELECT COUNT(*) AS c FROM scenarios").fetchone()["c"]
        latest = db.execute("""
            SELECT record_id, title, service, severity, modified_at
            FROM reports
            ORDER BY datetime(created_at) DESC
            LIMIT 5
        """).fetchall()

    return {
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "report_count": report_count,
        "scenario_count": scenario_count,
        "candidate_json_files": [rel(path) for path in candidate_json_files()[:20]],
        "latest_reports": [dict(row) for row in latest],
    }


init_db()

# =========================================================
# OpsLens final backend history dedupe v3
# =========================================================
# OpsLens final backend history dedupe v3
# One incident identity = one history record.
# =========================================================

_opslens_base_init_db = init_db


def init_db() -> None:
    _opslens_base_init_db()

    with conn() as db:
        existing = {row[1] for row in db.execute("PRAGMA table_info(reports)").fetchall()}

        if "incident_key" not in existing:
            db.execute("ALTER TABLE reports ADD COLUMN incident_key TEXT DEFAULT ''")

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_reports_created_at
            ON reports(created_at)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_reports_incident_key
            ON reports(incident_key)
        """)


def _opslens_norm_text(value: Any) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def _opslens_report_identity(report: Dict[str, Any]) -> str:
    report = normalize_report(report or {})
    affected = dict_or_empty(report.get("affected_resources"))

    seed = {
        "title": _opslens_norm_text(report.get("title", "")),
        "namespace": _opslens_norm_text(affected.get("namespace", "")),
        "node": _opslens_norm_text(affected.get("node") or affected.get("node_name") or ""),
        "service": _opslens_norm_text(service_from_report(report)),
        "deployment": _opslens_norm_text(affected.get("deployment") or affected.get("deployment_name") or ""),
        "summary": _opslens_norm_text(report.get("incident_summary", "")),
        "root": _opslens_norm_text(report.get("root_cause_story", "")),
        "scenario": _opslens_norm_text(report.get("source_scenario", "")),
    }

    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def stable_report_key(report: Dict[str, Any]) -> str:
    return _opslens_report_identity(report)


def _opslens_existing_record_for_identity(incident_key: str) -> Optional[str]:
    if not incident_key:
        return None

    init_db()

    with conn() as db:
        row = db.execute("""
            SELECT record_id
            FROM reports
            WHERE incident_key = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1
        """, (incident_key,)).fetchone()

    return row["record_id"] if row else None


def build_record(report: Dict[str, Any], json_path: Path, record_id: Optional[str] = None) -> Dict[str, Any]:
    report = normalize_report(report)
    affected = dict_or_empty(report.get("affected_resources"))
    fix = fix_to_dict(report.get("recommended_fix"))

    service = service_from_report(report)
    now = datetime.now().isoformat()
    created_at = report.get("created_at") or report.get("timestamp") or now
    incident_key = report.get("incident_key") or _opslens_report_identity(report)

    if not record_id:
        record_id = incident_key

    report = dict(report)
    report["record_id"] = safe(record_id)
    report["incident_key"] = incident_key
    report["json_report_path"] = rel(json_path)
    report.setdefault("created_at", created_at)

    modified_at = datetime.fromtimestamp(json_path.stat().st_mtime).isoformat() if json_path.exists() else now

    return {
        "record_id": safe(record_id),
        "incident_key": incident_key,
        "title": report.get("title") or "OpsLens Investigation",
        "status": "completed",
        "created_at": created_at,
        "modified_at": modified_at,
        "service": service,
        "namespace": affected.get("namespace", ""),
        "node": affected.get("node", "") or affected.get("node_name", ""),
        "severity": report.get("severity", "unknown"),
        "confidence": report.get("confidence", "unknown"),
        "summary": report.get("incident_summary", ""),
        "root_cause": report.get("root_cause_story", ""),
        "fix_strategy": fix.get("strategy", ""),
        "json_report_path": rel(json_path),
        "markdown_report_path": report.get("markdown_report_path", ""),
        "report_json": json.dumps(report, ensure_ascii=False),
    }


def upsert_report(record: Dict[str, Any]) -> None:
    init_db()

    incident_key = record.get("incident_key") or ""

    with conn() as db:
        if incident_key:
            existing = db.execute("""
                SELECT record_id
                FROM reports
                WHERE incident_key = ? AND record_id != ?
                ORDER BY datetime(created_at) DESC
                LIMIT 1
            """, (incident_key, record["record_id"])).fetchone()

            if existing:
                record["record_id"] = existing["record_id"]

        db.execute("""
            INSERT INTO reports (
                record_id, incident_key, title, status, created_at, modified_at,
                service, namespace, node, severity, confidence,
                summary, root_cause, fix_strategy,
                json_report_path, markdown_report_path, report_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                incident_key = excluded.incident_key,
                title = excluded.title,
                status = excluded.status,
                created_at = reports.created_at,
                modified_at = excluded.modified_at,
                service = excluded.service,
                namespace = excluded.namespace,
                node = excluded.node,
                severity = excluded.severity,
                confidence = excluded.confidence,
                summary = excluded.summary,
                root_cause = excluded.root_cause,
                fix_strategy = excluded.fix_strategy,
                json_report_path = excluded.json_report_path,
                markdown_report_path = excluded.markdown_report_path,
                report_json = excluded.report_json
        """, (
            record["record_id"],
            record.get("incident_key", ""),
            record["title"],
            record["status"],
            record["created_at"],
            record["modified_at"],
            record["service"],
            record["namespace"],
            record["node"],
            record["severity"],
            record["confidence"],
            record["summary"],
            record["root_cause"],
            record["fix_strategy"],
            record["json_report_path"],
            record["markdown_report_path"],
            record["report_json"],
        ))


def save_report(report: Dict[str, Any], record_id: Optional[str] = None) -> Dict[str, Any]:
    init_db()
    report = normalize_report(report)

    if not looks_like_report(report):
        raise ValueError("Payload is not a valid OpsLens report.")

    incident_key = _opslens_report_identity(report)
    existing_id = _opslens_existing_record_for_identity(incident_key)

    final_record_id = safe(existing_id or record_id or incident_key)
    json_path = REPORTS_DIR / f"{final_record_id}.json"

    report_to_save = dict(report)
    report_to_save["record_id"] = final_record_id
    report_to_save["incident_key"] = incident_key
    report_to_save["json_report_path"] = rel(json_path)
    report_to_save.setdefault(
        "created_at",
        report_to_save.get("generated_at")
        or report_to_save.get("timestamp")
        or datetime.now().isoformat()
    )

    json_path.write_text(
        json.dumps(report_to_save, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    record = build_record(report_to_save, json_path, record_id=final_record_id)
    upsert_report(record)
    return record


def _opslens_row_identity(row: Dict[str, Any]) -> str:
    if row.get("incident_key"):
        return row["incident_key"]

    try:
        report_json = row.get("report_json")
        if report_json:
            return _opslens_report_identity(json.loads(report_json))
    except Exception:
        pass

    seed = {
        "title": _opslens_norm_text(row.get("title", "")),
        "namespace": _opslens_norm_text(row.get("namespace", "")),
        "node": _opslens_norm_text(row.get("node", "")),
        "service": _opslens_norm_text(row.get("service", "")),
        "summary": _opslens_norm_text(row.get("summary", "")),
        "root": _opslens_norm_text(row.get("root_cause", "")),
    }

    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def list_reports(limit: int = 50) -> List[Dict[str, Any]]:
    init_db()

    with conn() as db:
        rows = db.execute("""
            SELECT
                record_id, incident_key, title, status, created_at, modified_at,
                service, namespace, node, severity, confidence,
                summary, root_cause, fix_strategy,
                json_report_path, markdown_report_path, report_json
            FROM reports
            ORDER BY datetime(created_at) DESC
            LIMIT ?
        """, (max(int(limit) * 5, int(limit)),)).fetchall()

    unique: List[Dict[str, Any]] = []
    seen = set()

    for row in rows:
        item = dict(row)
        identity = _opslens_row_identity(item)

        if identity in seen:
            continue

        seen.add(identity)
        item.pop("report_json", None)
        unique.append(item)

        if len(unique) >= int(limit):
            break

    return unique


def get_report(record_id: str) -> Dict[str, Any]:
    init_db()

    with conn() as db:
        row = db.execute(
            "SELECT report_json FROM reports WHERE record_id = ?",
            (safe(record_id),),
        ).fetchone()

    if not row:
        raise FileNotFoundError(f"Report not found: {record_id}")

    return json.loads(row["report_json"])


def debug_state() -> Dict[str, Any]:
    init_db()

    with conn() as db:
        report_count = db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        scenario_count = db.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0]
        latest = db.execute("""
            SELECT record_id, incident_key, title, service, severity, created_at, modified_at
            FROM reports
            ORDER BY datetime(created_at) DESC
            LIMIT 10
        """).fetchall()

    return {
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "report_count": report_count,
        "scenario_count": scenario_count,
        "candidate_json_files": [rel(path) for path in candidate_json_files()[:20]],
        "latest_reports": [dict(row) for row in latest],
    }


init_db()
