from __future__ import annotations

import html
from collections import defaultdict
from pathlib import Path
from typing import Any

from .base import BaseAgent


class VisualizationAgent(BaseAgent):
    name, description = "visualization", "生成柱状对比图和线性趋势图"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        aggregates = payload.get("aggregates") or {}
        totals = dict(aggregates.get("by_product") or {})
        dates = dict(aggregates.get("by_month") or {})
        if not aggregates:
            rows = payload.get("rows", []); totals_fallback, dates_fallback = defaultdict(float), defaultdict(float)
            for row in rows:
                amount = float(row.get("amount") or 0)
                totals_fallback[str(row.get("product") or row.get("channel") or "未分类")] += amount
                if row.get("date"): dates_fallback[str(row["date"])[:7]] += amount
            totals, dates = dict(totals_fallback), dict(dates_fallback)
        totals = dict(sorted(totals.items(), key=lambda item: item[1], reverse=True)[:10])
        out = Path(context["storage_path"]) / "charts"; out.mkdir(parents=True, exist_ok=True)
        run_id = context.get("run_id", "adhoc")
        charts = {}
        if "bar" in context.get("selection", {}).get("chart_types", ["bar", "line"]):
            charts["bar"] = self._bar(out / f"{run_id}-bar.svg", totals)
        if "line" in context.get("selection", {}).get("chart_types", ["bar", "line"]):
            charts["line"] = self._line(out / f"{run_id}-line.svg", dates)
        for kind, path in charts.items():
            if context.get("run_id"):
                self.memory.add_artifact(run_id=run_id, artifact_type="chart", path=str(path), description=kind)
                self.memory.add_finding(actor=self.name, run_id=run_id, agent_name=self.name, kind="chart", title=f"{kind} chart", content={"path": str(path), "values": dict(totals if kind == "bar" else dates), "scope": "all_filtered_rows"})
        return {"charts": {k: str(v) for k, v in charts.items()}, "totals": dict(totals), "date_totals": dict(sorted(dates.items()))}

    @staticmethod
    def _bar(path: Path, totals: dict[str, float]) -> Path:
        w, h, left, top, cw, ch = 760, 420, 80, 40, 640, 290; maximum = max(totals.values(), default=1) or 1; slot = cw / max(1, len(totals)); body = []
        for i, (label, value) in enumerate(sorted(totals.items(), key=lambda x: x[1], reverse=True)):
            bh, x = value / maximum * ch, left + i * slot + slot * .15; y = top + ch - bh
            body += [f'<rect x="{x:.1f}" y="{y:.1f}" width="{slot*.7:.1f}" height="{bh:.1f}" fill="#2563eb"><title>{html.escape(label)} {value:.2f}</title></rect>', f'<text x="{x+slot*.35:.1f}" y="{top+ch+22}" text-anchor="middle" font-size="12">{html.escape(label[:12])}</text>']
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><rect width="100%" height="100%" fill="white"/><text x="380" y="24" text-anchor="middle" font-size="18">产品销售额 Top 10</text><line x1="{left}" y1="{top+ch}" x2="720" y2="{top+ch}" stroke="#334155"/>{"".join(body)}</svg>', encoding="utf-8"); return path

    @staticmethod
    def _line(path: Path, dates: dict[str, float]) -> Path:
        w, h, left, top, cw, ch = 760, 420, 70, 40, 650, 290; pairs = sorted(dates.items()); maximum = max(dates.values(), default=1) or 1; points = []
        for i, (label, value) in enumerate(pairs):
            x = left + (i / max(1, len(pairs)-1)) * cw; y = top + ch - value / maximum * ch; points.append((x, y, label))
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points); labels = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#dc2626"/><text x="{x:.1f}" y="{top+ch+22}" text-anchor="middle" font-size="11">{html.escape(label[-5:])}</text>' for x, y, label in points)
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><rect width="100%" height="100%" fill="white"/><text x="380" y="24" text-anchor="middle" font-size="18">月度销售额趋势</text><line x1="{left}" y1="{top+ch}" x2="720" y2="{top+ch}" stroke="#334155"/><polyline points="{poly}" fill="none" stroke="#dc2626" stroke-width="3"/>{labels}</svg>', encoding="utf-8"); return path
