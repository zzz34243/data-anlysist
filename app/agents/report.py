import json
from pathlib import Path
from .base import BaseAgent
from ..pdf_report import build_pdf


class ReportAgent(BaseAgent):
    name, description = "report", "整合图表、结论和策略生成报告"

    def run(self, payload, context):
        prep, insights, validation, strategy, charts = payload.get("prepared", {}), payload.get("insights", {}), payload.get("validation", {}), payload.get("strategy", {}), payload.get("charts", {})
        chart_files = charts.get("charts", charts)
        executive_summary = self.ask(
            system="你是数据分析报告编辑。根据给定的确定性指标写一段 2-4 句中文管理层摘要，不要创造输入中不存在的数字。",
            prompt="项目：" + str(context.get("project_name", "数据分析")) + "；指标：" + json.dumps({"summary": prep.get("summary", {}), "insights": insights, "validation": validation}, ensure_ascii=False),
            context=context,
        )
        summary = prep.get("summary", {})
        lines = [f"# {context.get('project_name', '数据分析')}营销分析报告", "", f"规范 Prompt：{context.get('optimized_prompt', '')}", f"原始行数：{summary.get('source_rows', summary.get('rows', 0))}；全量分析行数：{summary.get('rows', 0)}；明细样本：{summary.get('sampled_rows', summary.get('rows', 0))}；销售额：{summary.get('total_amount', 0):.2f}"]
        if executive_summary:
            lines += ["", "## 管理层摘要", executive_summary]
        lines += ["", "## 趋势与洞察", f"- 日期范围：{summary.get('date_from')} 至 {summary.get('date_to')}", f"- 月度周期数：{summary.get('period_count', 0)}", f"- 不完整月份：{summary.get('partial_periods') or '无'}", f"- 趋势（完整月份）：{insights.get('trend')}，{insights.get('trend_period_from')} 至 {insights.get('trend_period_to')}", f"- 销售峰值期：{(insights.get('peak_period') or {}).get('period')}", f"- 销售低值期：{(insights.get('trough_period') or {}).get('period')}", f"- 核心产品：{(insights.get('top_product') or {}).get('name')}", f"- 主要渠道：{(insights.get('top_channel') or {}).get('name')}", "", "## 独立验证", f"- 状态：{'通过' if validation.get('valid') else '未通过'}", "", "## 营销策略建议", "", strategy.get("strategy_summary", "暂时没有可用的策略摘要。"), "", f"> 生成方式：{'AI 模型根据汇总数据生成' if strategy.get('generation_mode') == 'model' else '模型不可用，已使用离线降级建议'}"]
        for action in strategy.get("actions", []):
            lines += ["", f"### {action.get('priority', '建议')}｜{action.get('title', '未命名策略')}", f"- **目标：** {action.get('goal')}", f"- **数据依据：** {action.get('why')}", f"- **执行步骤：** {'；'.join(str(item) for item in action.get('steps', []))}", f"- **目标人群：** {action.get('audience')}", f"- **建议时间：** {action.get('timing')}", f"- **执行渠道：** {action.get('channel')}", f"- **衡量指标：** {'、'.join(str(item) for item in action.get('metrics', []))}", f"- **前提与限制：** {action.get('caveat')}"]
        if strategy.get("risks"):
            lines += ["", "### 风险与应对"]
            lines += [f"- {item.get('risk')} 应对：{item.get('response')}" for item in strategy.get("risks", [])]
        lines += ["", "## 图表", *[f"- {kind}: `{path}`" for kind, path in chart_files.items()]]
        markdown = "\n".join(lines) + "\n"
        report_dir = Path(context["storage_path"]) / "reports"
        path = report_dir / f"{context.get('run_id', 'adhoc')}-report.md"
        path.write_text(markdown, encoding="utf-8")
        pdf_path = report_dir / f"{context.get('run_id', 'adhoc')}-report.pdf"
        build_pdf(path=pdf_path, project_name=context.get("project_name", "数据分析"), request=context.get("request", ""), prepared=prep, charts={"totals": payload.get("charts", {}).get("totals", {}), "date_totals": payload.get("charts", {}).get("date_totals", {})}, insights=insights, validation=validation, strategy=strategy, executive_summary=executive_summary)
        if context.get("run_id"):
            self.memory.add_artifact(run_id=context["run_id"], artifact_type="report", path=str(path), description="Markdown report")
            self.memory.add_artifact(run_id=context["run_id"], artifact_type="pdf_report", path=str(pdf_path), description="PDF analysis report")
            self.memory.add_finding(actor=self.name, run_id=context["run_id"], agent_name=self.name, kind="report", title="最终报告", content={"path":str(path), "pdf_path": str(pdf_path)})
        return {"path": str(path), "pdf_path": str(pdf_path), "markdown": markdown, "llm_used": bool(executive_summary)}
