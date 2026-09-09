from pathlib import Path
from .base import BaseAgent


class ValidatorAgent(BaseAgent):
    name, description = "validator", "复算指标、校验图表/报告并标记 Findings"

    def run(self, payload, context):
        rows, insights = payload.get("rows", []), payload.get("insights", {})
        summary, aggregates = payload.get("summary") or {}, payload.get("aggregates") or {}
        total = round(float(summary.get("total_amount", sum(float(r.get("amount") or 0) for r in rows))), 2)
        grouped = round(float(aggregates.get("total_amount", sum(float(v) for v in (insights.get("by_product") or {}).values()))), 2)
        checks = {"row_count_positive": int(summary.get("rows", len(rows))) > 0, "full_aggregate_total_matches": abs(total-grouped) < .01}
        report = payload.get("report")
        if report:
            markdown_path, pdf_path = Path(str(report.get("path", ""))), Path(str(report.get("pdf_path", "")))
            checks["report_exists_and_non_empty"] = markdown_path.is_file() and markdown_path.stat().st_size > 0
            checks["pdf_exists_and_non_empty"] = pdf_path.is_file() and pdf_path.stat().st_size > 0
        valid = all(checks.values()); verified = []
        if context.get("run_id"):
            for finding in self.memory.run_memory(context["run_id"])["findings"]:
                if finding["agent_name"] != self.name:
                    self.memory.validate_finding(actor=self.name, finding_id=finding["id"], status="verified" if valid else "rejected"); verified.append(finding["id"]) if valid else None
            self.memory.add_finding(actor=self.name, run_id=context["run_id"], agent_name=self.name, kind="validation", title="独立验证", content={"checks": checks, "verified": verified})
        return {"valid": valid, "checks": checks, "expected_total": total, "insight_total": grouped, "verified_finding_ids": verified}
