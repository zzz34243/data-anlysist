from __future__ import annotations

from collections import defaultdict
from .base import BaseAgent


class InsightsAgent(BaseAgent):
    name, description = "insights", "分析趋势、异常与倾向"

    def run(self, payload, context):
        rows = payload.get("rows", []); product, channel, dates = defaultdict(float), defaultdict(float), defaultdict(float)
        for row in rows:
            amount = float(row.get("amount") or 0); product[str(row.get("product") or "未分类")] += amount; channel[str(row.get("channel") or "未分类")] += amount
            if row.get("date"): dates[str(row["date"])] += amount
        pairs = sorted(dates.items()); change = round(pairs[-1][1] - pairs[0][1], 2) if len(pairs) > 1 else None; trend = "up" if change and change > 0 else "down" if change and change < 0 else "flat_or_insufficient"
        top_product, top_channel = max(product.items(), key=lambda x:x[1], default=(None, 0)), max(channel.items(), key=lambda x:x[1], default=(None, 0))
        result = {"trend": trend, "first_last_change": change, "by_product": dict(sorted(product.items(), key=lambda x:x[1], reverse=True)), "by_channel": dict(sorted(channel.items(), key=lambda x:x[1], reverse=True)), "by_date": dict(pairs), "top_product": {"name": top_product[0], "amount": round(top_product[1], 2)}, "top_channel": {"name": top_channel[0], "amount": round(top_channel[1], 2)}, "anomaly_rows": sum(bool(r.get("anomaly_flags")) for r in rows)}
        if context.get("run_id"): self.memory.add_finding(actor=self.name, run_id=context["run_id"], agent_name=self.name, kind="insight", title="趋势与洞察", content=result)
        return result

