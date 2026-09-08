import json
from pathlib import Path
from .base import BaseAgent


class ReportAgent(BaseAgent):
    name, description = "report", "整合图表、结论和策略生成报告"

    def run(self, payload, context):
        prep, insights, validation, strategy, charts = payload.get("prepared", {}), payload.get("insights", {}), payload.get("validation", {}), payload.get("strategy", {}), payload.get("charts", {})
        executive_summary = self.ask(
            system="你是数据分析报告编辑。根据给定的确定性指标写一段 2-4 句中文管理层摘要，不要创造输入中不存在的数字。",
            prompt="项目：" + str(context.get("project_name", "数据分析")) + "；指标：" + json.dumps({"summary": prep.get("summary", {}), "insights": insights, "validation": validation}, ensure_ascii=False),
            context=context,
        )
        lines = [f"# {context.get('project_name', '数据分析')}营销分析报告", "", f"规范 Prompt：{context.get('optimized_prompt', '')}", f"数据行数：{prep.get('summary', {}).get('rows', 0)}；销售额：{prep.get('summary', {}).get('total_amount', 0):.2f}"]
        if executive_summary:
            lines += ["", "## 管理层摘要", executive_summary]
        lines += ["", "## 趋势与洞察", f"- 趋势：{insights.get('trend')}", f"- 核心产品：{(insights.get('top_product') or {}).get('name')}", f"- 主要渠道：{(insights.get('top_channel') or {}).get('name')}", "", "## 独立验证", f"- 状态：{'通过' if validation.get('valid') else '未通过'}", "", "## 营销策略"]
        if strategy.get("llm_advice"):
            lines += ["", "### 模型补充建议", "```json", json.dumps(strategy["llm_advice"], ensure_ascii=False, indent=2), "```"]
        lines += [f"- **{a.get('priority')}** {a.get('audience')}｜{a.get('channel')}：{a.get('action')}（{a.get('metric')}）" for a in strategy.get('actions', [])]
        lines += ["", "## 图表", *[f"- {kind}: `{path}`" for kind, path in charts.items()]]
        markdown = "\n".join(lines) + "\n"; path = Path(context["storage_path"]) / "reports" / f"{context.get('run_id', 'adhoc')}-report.md"; path.write_text(markdown, encoding="utf-8")
        if context.get("run_id"): self.memory.add_artifact(run_id=context["run_id"], artifact_type="report", path=str(path), description="Markdown report"); self.memory.add_finding(actor=self.name, run_id=context["run_id"], agent_name=self.name, kind="report", title="最终报告", content={"path":str(path)})
        return {"path": str(path), "markdown": markdown, "llm_used": bool(executive_summary)}
