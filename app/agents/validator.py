from pathlib import Path
from .base import BaseAgent


class ValidatorAgent(BaseAgent):
    name, description = "validator", "复算指标、校验图表/报告并标记 Findings"

    def run(self, payload, context):
        rows, insights = payload.get("rows", []), payload.get("insights", {})
        total, grouped = round(sum(float(r.get("amount") or 0) for r in rows), 2), round(sum(float(v) for v in (insights.get("by_product") or {}).values()), 2)
        checks = {"row_count_positive": bool(rows), "total_amount_matches": abs(total-grouped) < .01 if insights.get("by_product") else True}
        report = payload.get("report")
        if report: checks["report_exists_and_non_empty"] = Path(str(report.get("path", ""))).is_file() and Path(str(report.get("path", ""))).stat().st_size > 0
        valid = all(checks.values()); verified = []
        if context.get("run_id"):
            for finding in self.memory.run_memory(context["run_id"])["findings"]:
                if finding["agent_name"] != self.name:
                    self.memory.validate_finding(actor=self.name, finding_id=finding["id"], status="verified" if valid else "rejected"); verified.append(finding["id"]) if valid else None
            self.memory.add_finding(actor=self.name, run_id=context["run_id"], agent_name=self.name, kind="validation", title="独立验证", content={"checks": checks, "verified": verified})
        return {"valid": valid, "checks": checks, "expected_total": total, "insight_total": grouped, "verified_finding_ids": verified}

