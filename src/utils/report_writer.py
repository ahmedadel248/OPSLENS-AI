import json
from pathlib import Path

import pandas as pd


class ReportWriter:
    def __init__(self, output_dir="reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _flatten_report(self, report):
        event = report.get("source_event", {})
        metrics = event.get("metrics", {})

        return {
            "timestamp": report.get("timestamp"),
            "node_name": report.get("node_name"),
            "incident_title": report.get("incident_title"),
            "severity": report.get("severity"),
            "anomaly_type": report.get("anomaly_type"),

            "actual_cpu": metrics.get("actual_cpu"),
            "predicted_cpu": metrics.get("predicted_cpu"),
            "cpu_error": metrics.get("cpu_error"),
            "cpu_score": metrics.get("cpu_score"),
            "cpu_anomaly": metrics.get("cpu_anomaly"),

            "actual_memory": metrics.get("actual_memory"),
            "predicted_memory": metrics.get("predicted_memory"),
            "memory_error": metrics.get("memory_error"),
            "memory_score": metrics.get("memory_score"),
            "memory_anomaly": metrics.get("memory_anomaly"),

            "summary": report.get("summary"),
            "root_cause_hypothesis": report.get("root_cause_hypothesis"),
            "evidence": " | ".join(report.get("evidence", [])),
            "recommended_next_checks": " | ".join(report.get("recommended_next_checks", [])),
        }

    def _to_dataframe(self, reports):
        rows = [self._flatten_report(report) for report in reports]
        return pd.DataFrame(rows)

    def save_json(self, reports, filename="incident_reports.json"):
        path = self.output_dir / filename

        with open(path, "w", encoding="utf-8") as f:
            json.dump(reports, f, indent=4, ensure_ascii=False, default=str)

        return str(path)

    def save_csv(self, reports, filename="incident_reports.csv"):
        path = self.output_dir / filename

        df = self._to_dataframe(reports)
        df.to_csv(path, index=False, encoding="utf-8")

        return str(path)

    def save_excel(self, reports, filename="incident_reports.xlsx"):
        path = self.output_dir / filename

        df = self._to_dataframe(reports)

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Incidents", index=False)

            if not df.empty:
                summary_by_type = (
                    df.groupby("anomaly_type")
                    .size()
                    .reset_index(name="count")
                    .sort_values("count", ascending=False)
                )

                summary_by_severity = (
                    df.groupby("severity")
                    .size()
                    .reset_index(name="count")
                    .sort_values("count", ascending=False)
                )

                summary_by_node = (
                    df.groupby("node_name")
                    .size()
                    .reset_index(name="count")
                    .sort_values("count", ascending=False)
                )

                summary_by_type.to_excel(
                    writer,
                    sheet_name="Summary_By_Type",
                    index=False
                )

                summary_by_severity.to_excel(
                    writer,
                    sheet_name="Summary_By_Severity",
                    index=False
                )

                summary_by_node.to_excel(
                    writer,
                    sheet_name="Summary_By_Node",
                    index=False
                )

            workbook = writer.book

            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]

                sheet.freeze_panes = "A2"

                for column_cells in sheet.columns:
                    max_length = 0
                    column_letter = column_cells[0].column_letter

                    for cell in column_cells:
                        cell_value = str(cell.value) if cell.value is not None else ""
                        max_length = max(max_length, len(cell_value))

                    adjusted_width = min(max_length + 2, 45)
                    sheet.column_dimensions[column_letter].width = adjusted_width

                for cell in sheet[1]:
                    cell.style = "Headline 3"

        return str(path)

    def save_all(self, reports):
        json_path = self.save_json(reports)
        csv_path = self.save_csv(reports)
        excel_path = self.save_excel(reports)

        return {
            "json_path": json_path,
            "csv_path": csv_path,
            "excel_path": excel_path,
            "total_reports": len(reports)
        }



