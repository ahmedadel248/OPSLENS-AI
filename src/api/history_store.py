
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
SCENARIOS_DIR = PROJECT_ROOT / "scenarios"
DB_PATH = DATA_DIR / "opslens.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def conn() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    with conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                record_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT DEFAULT 'completed',
                created_at TEXT NOT NULL,
                modified_at TEXT NOT NULL,
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
                report_json TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS scenarios (
                filename TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                impact TEXT DEFAULT '',
                expected TEXT DEFAULT '',
                file_path TEXT NOT NULL,
                updated_at TEXT NOT NULL
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


def service_from_report(report: Dict[str, Any]) -> str:
    affected = report.get("affected_resources") or {}

    return (
        affected.get("service")
        or affected.get("service_name")
        or affected.get("workload")
        or affected.get("deployment")
        or affected.get("pod")
        or "unknown-service"
    )


def build_record(report: Dict[str, Any], json_path: Path, record_id: Optional[str] = None) -> Dict[str, Any]:
    affected = report.get("affected_resources") or {}
    fix = report.get("recommended_fix") or {}

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
        "node": affected.get("node", ""),
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
                created_at = excluded.created_at,
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

    if not looks_like_report(report):
        raise ValueError("Payload is not a valid OpsLens report.")

    service = service_from_report(report)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not record_id:
        record_id = f"{safe(service)}_{stamp}"

    record_id = safe(record_id)
    json_path = REPORTS_DIR / f"{record_id}.json"

    report_to_save = dict(report)
    report_to_save["json_report_path"] = rel(json_path)
    report_to_save.setdefault("created_at", datetime.now().isoformat())

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
    sync_reports()

    with conn() as db:
        rows = db.execute("""
            SELECT
                record_id, title, status, created_at, modified_at,
                service, namespace, node, severity, confidence,
                summary, root_cause, fix_strategy,
                json_report_path, markdown_report_path
            FROM reports
            ORDER BY datetime(modified_at) DESC
            LIMIT ?
        """, (int(limit),)).fetchall()

    return [dict(row) for row in rows]


def get_report(record_id: str) -> Dict[str, Any]:
    sync_reports()

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
            ORDER BY datetime(modified_at) DESC
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
