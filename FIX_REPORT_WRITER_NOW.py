from pathlib import Path

path = Path("src/utils/report_writer.py")

if not path.exists():
    raise SystemExit("ERROR: src/utils/report_writer.py not found")

path.write_text(r'''from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


class ReportWriter:
    """
    Clean OpsLens report writer.

    Supports current OpsLens report shape:
    - affected_resources
    - incident_summary
    - root_cause_story
    - agent_reasoning
    - additional_findings
    - recommended_fix
    - verification

    No raw Markdown in PDF.
    No duplicated title.
    """

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _reports_list(self, reports: Any) -> List[Dict[str, Any]]:
        if isinstance(reports, dict):
            return [reports]
        if isinstance(reports, list):
            return [item for item in reports if isinstance(item, dict)]
        return []

    def _text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return "\n".join(
                f"{key}: {self._text(val)}"
                for key, val in value.items()
                if self._text(val)
            )
        if isinstance(value, list):
            return "\n".join(self._text(item) for item in value if self._text(item))
        return str(value)

    def _safe_filename(self, value: str, fallback: str = "opslens_report") -> str:
        value = str(value or fallback).strip()
        allowed = []

        for char in value:
            if char.isalnum() or char in {"-", "_", "."}:
                allowed.append(char)
            elif char.isspace():
                allowed.append("_")
            else:
                allowed.append("_")

        name = "".join(allowed).strip("_")
        return name or fallback

    def _affected(self, report: Dict[str, Any]) -> Dict[str, Any]:
        affected = report.get("affected_resources")
        return affected if isinstance(affected, dict) else {}

    def _fix(self, report: Dict[str, Any]) -> Dict[str, Any]:
        fix = report.get("recommended_fix")
        if isinstance(fix, dict):
            return fix
        if isinstance(fix, str):
            return {"strategy": fix, "actions": [], "commands": []}
        if isinstance(fix, list):
            return {"strategy": self._text(fix), "actions": [], "commands": []}
        return {"strategy": "", "actions": [], "commands": []}

    def _verification(self, report: Dict[str, Any]) -> Dict[str, Any]:
        verification = report.get("verification")
        if isinstance(verification, dict):
            return verification
        if isinstance(verification, str):
            return {"intent": verification, "commands": []}
        if isinstance(verification, list):
            return {"intent": self._text(verification), "commands": []}
        return {"intent": "", "commands": []}

    def _service(self, report: Dict[str, Any]) -> str:
        affected = self._affected(report)
        return (
            affected.get("service")
            or affected.get("service_name")
            or affected.get("workload")
            or affected.get("deployment")
            or affected.get("pod")
            or "unknown-service"
        )

    def _flatten_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        affected = self._affected(report)
        fix = self._fix(report)
        verification = self._verification(report)

        return {
            "created_at": report.get("created_at") or report.get("timestamp") or "",
            "title": report.get("title") or report.get("incident_title") or "OpsLens Incident Report",
            "status": report.get("status") or "completed",
            "severity": report.get("severity") or "unknown",
            "confidence": report.get("confidence") or "unknown",
            "namespace": affected.get("namespace", ""),
            "node": affected.get("node") or affected.get("node_name") or "",
            "service": affected.get("service") or affected.get("service_name") or "",
            "deployment": affected.get("deployment") or affected.get("deployment_name") or "",
            "pod": affected.get("pod") or affected.get("pod_name") or "",
            "incident_summary": report.get("incident_summary") or report.get("summary") or "",
            "root_cause_story": report.get("root_cause_story") or report.get("root_cause_hypothesis") or "",
            "fix_strategy": fix.get("strategy", ""),
            "verification_intent": verification.get("intent", ""),
            "evidence_count": len(report.get("agent_reasoning") or report.get("evidence_trail") or []),
            "additional_findings_count": len(report.get("additional_findings") or []),
        }

    def _to_dataframe(self, reports: Any) -> pd.DataFrame:
        return pd.DataFrame([self._flatten_report(report) for report in self._reports_list(reports)])

    def _evidence_rows(self, report: Dict[str, Any]) -> List[List[str]]:
        rows = []

        for item in report.get("agent_reasoning") or []:
            if isinstance(item, dict):
                rows.append([
                    item.get("agent", ""),
                    item.get("finding", ""),
                    item.get("meaning", ""),
                ])
            else:
                rows.append(["Evidence", self._text(item), ""])

        if not rows:
            for item in report.get("evidence_trail") or report.get("evidence") or []:
                rows.append(["Evidence", self._text(item), ""])

        return rows

    def _additional_rows(self, report: Dict[str, Any]) -> List[List[str]]:
        rows = []

        for item in report.get("additional_findings") or []:
            if isinstance(item, dict):
                rows.append([
                    item.get("resource", ""),
                    item.get("finding", ""),
                    item.get("impact", ""),
                    item.get("priority", ""),
                ])
            else:
                rows.append(["", self._text(item), "", ""])

        return rows

    def _commands_rows(self, report: Dict[str, Any]) -> List[List[str]]:
        fix = self._fix(report)
        verification = self._verification(report)

        rows = []

        for command in fix.get("commands") or fix.get("safe_commands") or []:
            if isinstance(command, dict):
                rows.append(["Remediation", command.get("title", ""), command.get("command", self._text(command))])
            else:
                rows.append(["Remediation", "", self._text(command)])

        for command in verification.get("commands") or verification.get("verification_commands") or []:
            if isinstance(command, dict):
                rows.append(["Verification", command.get("title", ""), command.get("command", self._text(command))])
            else:
                rows.append(["Verification", "", self._text(command)])

        return rows

    def save_json(self, reports: Any, filename: str = "incident_reports.json") -> str:
        path = self.output_dir / filename
        payload = self._reports_list(reports)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return str(path)

    def save_csv(self, reports: Any, filename: str = "incident_reports.csv") -> str:
        path = self.output_dir / filename
        df = self._to_dataframe(reports)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return str(path)

    def save_excel(self, reports: Any, filename: str = "incident_reports.xlsx") -> str:
        path = self.output_dir / filename
        reports_list = self._reports_list(reports)
        summary_df = self._to_dataframe(reports_list)

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="Summary", index=False)

            if reports_list:
                first = reports_list[0]

                pd.DataFrame(
                    self._evidence_rows(first),
                    columns=["Agent", "Finding", "Meaning"]
                ).to_excel(writer, sheet_name="Evidence", index=False)

                pd.DataFrame(
                    self._additional_rows(first),
                    columns=["Resource", "Finding", "Impact", "Priority"]
                ).to_excel(writer, sheet_name="Additional Findings", index=False)

                pd.DataFrame(
                    self._commands_rows(first),
                    columns=["Type", "Title", "Command"]
                ).to_excel(writer, sheet_name="Commands", index=False)

            workbook = writer.book

            for sheet in workbook.worksheets:
                sheet.freeze_panes = "A2"

                for column_cells in sheet.columns:
                    max_length = 0
                    column_letter = column_cells[0].column_letter

                    for cell in column_cells:
                        value = str(cell.value) if cell.value is not None else ""
                        max_length = max(max_length, len(value))

                    sheet.column_dimensions[column_letter].width = min(max_length + 2, 70)

        return str(path)

    def save_markdown(self, reports: Any, filename: str = "incident_report.md") -> str:
        reports_list = self._reports_list(reports)
        report = reports_list[0] if reports_list else {}

        affected = self._affected(report)
        fix = self._fix(report)
        verification = self._verification(report)

        lines = [
            f"# {report.get('title') or 'OpsLens Incident Report'}",
            "",
            "## Overview",
            f"- Severity: {report.get('severity', 'unknown')}",
            f"- Confidence: {report.get('confidence', 'unknown')}",
            f"- Namespace: {affected.get('namespace', '')}",
            f"- Node: {affected.get('node') or affected.get('node_name') or ''}",
            f"- Service: {affected.get('service') or affected.get('service_name') or ''}",
            f"- Deployment: {affected.get('deployment') or affected.get('deployment_name') or ''}",
            "",
            "## Incident Summary",
            self._text(report.get("incident_summary") or report.get("summary")),
            "",
            "## Root Cause",
            self._text(report.get("root_cause_story") or report.get("root_cause_hypothesis")),
            "",
            "## Evidence",
        ]

        evidence_rows = self._evidence_rows(report)
        if evidence_rows:
            for agent, finding, meaning in evidence_rows:
                lines.append(f"- {agent}: {finding} — {meaning}")
        else:
            lines.append("- No evidence rows available.")

        lines.extend([
            "",
            "## Recommended Fix",
            self._text(fix.get("strategy")),
            "",
            "## Verification",
            self._text(verification.get("intent")),
            "",
            "## Commands",
        ])

        command_rows = self._commands_rows(report)
        if command_rows:
            for kind, title, command in command_rows:
                label = f"{kind}: {title}".strip(": ")
                lines.append(f"- {label}: `{command}`")
        else:
            lines.append("- No commands available.")

        path = self.output_dir / filename
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return str(path)

    def save_pdf(self, reports: Any, filename: str = "incident_report.pdf") -> str:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        reports_list = self._reports_list(reports)
        report = reports_list[0] if reports_list else {}

        affected = self._affected(report)
        fix = self._fix(report)
        verification = self._verification(report)

        path = self.output_dir / filename

        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            rightMargin=1.35 * cm,
            leftMargin=1.35 * cm,
            topMargin=1.25 * cm,
            bottomMargin=1.25 * cm,
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "OpsLensTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            spaceAfter=10,
        )

        section_style = ParagraphStyle(
            "OpsLensSection",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            spaceBefore=10,
            spaceAfter=6,
        )

        body_style = ParagraphStyle(
            "OpsLensBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            spaceAfter=6,
        )

        header_style = ParagraphStyle(
            "OpsLensTableHeader",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
        )

        cell_style = ParagraphStyle(
            "OpsLensTableCell",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            wordWrap="CJK",
        )

        code_style = ParagraphStyle(
            "OpsLensCode",
            parent=styles["BodyText"],
            fontName="Courier",
            fontSize=7.5,
            leading=9,
            wordWrap="CJK",
        )

        def clean(value: Any) -> str:
            return html.escape(self._text(value)).replace("\n", "<br/>")

        def p(value: Any, style=body_style):
            story.append(Paragraph(clean(value), style))

        def heading(value: str):
            story.append(Spacer(1, 4))
            story.append(Paragraph(clean(value), section_style))

        def table(headers: List[str], rows: List[List[Any]], widths: List[float] | None = None):
            if not rows:
                p("No data available.")
                return

            page_width = A4[0] - (2.7 * cm)

            if widths is None:
                widths = [page_width / len(headers)] * len(headers)

            data = [[Paragraph(clean(cell), header_style) for cell in headers]]

            for row in rows:
                data.append([Paragraph(clean(cell), cell_style) for cell in row])

            tbl = Table(data, colWidths=widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))

            story.append(tbl)
            story.append(Spacer(1, 8))

        story = []

        story.append(Paragraph(clean(report.get("title") or "OpsLens Incident Report"), title_style))

        overview_rows = [
            ["Severity", report.get("severity", "unknown")],
            ["Confidence", report.get("confidence", "unknown")],
            ["Namespace", affected.get("namespace", "")],
            ["Node", affected.get("node") or affected.get("node_name") or ""],
            ["Service", affected.get("service") or affected.get("service_name") or ""],
            ["Deployment", affected.get("deployment") or affected.get("deployment_name") or ""],
        ]

        table(["Field", "Value"], overview_rows, [4.0 * cm, 13.0 * cm])

        heading("Incident Summary")
        p(report.get("incident_summary") or report.get("summary"))

        heading("Root Cause")
        p(report.get("root_cause_story") or report.get("root_cause_hypothesis"))

        heading("Evidence")
        table(
            ["Agent", "Finding", "Meaning"],
            self._evidence_rows(report),
            [3.5 * cm, 5.3 * cm, 8.2 * cm],
        )

        heading("Additional Findings")
        table(
            ["Resource", "Finding", "Impact", "Priority"],
            self._additional_rows(report),
            [4.0 * cm, 4.5 * cm, 6.0 * cm, 2.5 * cm],
        )

        heading("Recommended Fix")
        p(fix.get("strategy", ""))

        actions = fix.get("actions") or []

        if actions:
            action_rows = []
            for action in actions:
                if isinstance(action, dict):
                    action_rows.append([
                        action.get("action_type", ""),
                        action.get("target_kind", ""),
                        action.get("reason", ""),
                        action.get("risk", ""),
                    ])
                else:
                    action_rows.append(["Action", "", self._text(action), ""])

            table(
                ["Action", "Target", "Reason", "Risk"],
                action_rows,
                [3.5 * cm, 3.0 * cm, 8.0 * cm, 2.5 * cm],
            )

        heading("Verification")
        p(verification.get("intent", ""))

        command_rows = self._commands_rows(report)

        if command_rows:
            for index, row in enumerate(command_rows, start=1):
                story.append(Paragraph(clean(f"{row[0]} Command {index}"), body_style))
                story.append(Paragraph(clean(row[2]), code_style))
                story.append(Spacer(1, 5))
        else:
            p("No commands available.")

        doc.build(story)

        return str(path)

    def save_all(self, reports: Any) -> Dict[str, Any]:
        reports_list = self._reports_list(reports)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        return {
            "json_path": self.save_json(reports_list, f"incident_reports_{stamp}.json"),
            "csv_path": self.save_csv(reports_list, f"incident_reports_{stamp}.csv"),
            "excel_path": self.save_excel(reports_list, f"incident_reports_{stamp}.xlsx"),
            "markdown_path": self.save_markdown(reports_list, f"incident_report_{stamp}.md"),
            "pdf_path": self.save_pdf(reports_list, f"incident_report_{stamp}.pdf"),
            "total_reports": len(reports_list),
        }
''', encoding="utf-8")

print("DONE: src/utils/report_writer.py replaced with clean OpsLens writer.")
