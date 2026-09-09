from __future__ import annotations

from collections import defaultdict
from .base import BaseAgent


class InsightsAgent(BaseAgent):
    name, description = "insights", "分析趋势、异常与倾向"

    def run(self, payload, context):
        rows = payload.get("rows", []); aggregates = payload.get("aggregates") or {}; summary = payload.get("summary") or {}
        product, channel, dates = dict(aggregates.get("by_product") or {}), dict(aggregates.get("by_channel") or {}), dict(aggregates.get("by_month") or {})
        if not aggregates:
            product_fallback, channel_fallback, date_fallback = defaultdict(float), defaultdict(float), defaultdict(float)
            for row in rows:
                amount = float(row.get("amount") or 0); product_fallback[str(row.get("product") or "未分类")] += amount; channel_fallback[str(row.get("channel") or "未分类")] += amount
                if row.get("date"): date_fallback[str(row["date"])[:7]] += amount
            product, channel, dates = dict(product_fallback), dict(channel_fallback), dict(date_fallback)
        pairs = sorted(dates.items()); partial_periods = set(summary.get("partial_periods") or []); complete_pairs = [pair for pair in pairs if pair[0] not in partial_periods] or pairs
        change = round(complete_pairs[-1][1] - complete_pairs[0][1], 2) if len(complete_pairs) > 1 else None; trend = "up" if change and change > 0 else "down" if change and change < 0 else "flat_or_insufficient"
        top_product, top_channel = max(product.items(), key=lambda x:x[1], default=(None, 0)), max(channel.items(), key=lambda x:x[1], default=(None, 0))
        peak = max(complete_pairs, key=lambda item: item[1], default=(None, 0)); trough = min(complete_pairs, key=lambda item: item[1], default=(None, 0))
        result = {"trend": trend, "first_last_change": change, "trend_period_from": complete_pairs[0][0] if complete_pairs else None, "trend_period_to": complete_pairs[-1][0] if complete_pairs else None, "partial_periods": sorted(partial_periods), "by_product": dict(sorted(product.items(), key=lambda x:x[1], reverse=True)[:20]), "by_channel": dict(sorted(channel.items(), key=lambda x:x[1], reverse=True)[:20]), "by_date": dict(pairs), "top_product": {"name": top_product[0], "amount": round(top_product[1], 2)}, "top_channel": {"name": top_channel[0], "amount": round(top_channel[1], 2)}, "peak_period": {"period": peak[0], "amount": round(peak[1], 2)}, "trough_period": {"period": trough[0], "amount": round(trough[1], 2)}, "period_count": len(pairs), "analysis_rows": summary.get("rows", len(rows)), "anomaly_rows": summary.get("anomaly_count", sum(bool(r.get("anomaly_flags")) for r in rows)), "aggregation_scope": "all_filtered_rows" if aggregates else "detail_rows"}
        if context.get("run_id"): self.memory.add_finding(actor=self.name, run_id=context["run_id"], agent_name=self.name, kind="insight", title="趋势与洞察", content=result)
        return result
