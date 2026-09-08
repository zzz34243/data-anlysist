import json

from .base import BaseAgent


class MarketingAgent(BaseAgent):
    name, description = "marketing", "根据已验证洞察制定人群、渠道和节奏策略"

    def run(self, payload, context):
        insights, validation = payload.get("insights", {}), payload.get("validation", {})
        if not validation.get("valid", True): return {"status": "blocked", "reason": "验证未通过", "actions": []}
        product, channel, trend = (insights.get("top_product") or {}).get("name") or "高潜产品", (insights.get("top_channel") or {}).get("name") or "高转化渠道", insights.get("trend")
        actions = [{"priority":"P0", "audience":f"对{product}感兴趣的高意向人群", "channel":channel, "action":"投放转化素材并设置加购/复购优惠", "metric":"转化率、获客成本"}, {"priority":"P1", "audience":"历史购买用户", "channel":"私域/短信", "action":"按购买周期触达并设计组合包", "metric":"复购率、客单价"}, {"priority":"P1", "audience":"未转化访客", "channel":"信息流再营销", "action":"A/B 测试优惠门槛与文案", "metric":"点击率、加购率"}]
        if trend == "down": actions.insert(0, {"priority":"P0", "audience":"沉默/流失人群", "channel":channel, "action":"短期召回并观察增量 ROI", "metric":"召回率、ROI"})
        llm_advice = self.ask_json(
            system="你是资深市场营销分析师。只根据给定的聚合指标提出可执行建议，不虚构数据。返回 JSON，键为 rationale、risks、experiments；experiments 是最多 3 个包含 hypothesis、audience、metric 的对象。",
            prompt="请为下一周期补充策略建议。聚合洞察：" + json.dumps(insights, ensure_ascii=False) + "；验证结果：" + json.dumps(validation, ensure_ascii=False),
            context=context,
        )
        result = {"status":"ready", "objective":"提升下一周期销售与复购", "actions":actions, "guardrails":["先小预算测试再扩量", "按渠道核算增量 ROI"], "llm_used": bool(llm_advice)}
        if llm_advice:
            result["llm_advice"] = llm_advice
        if context.get("run_id"): self.memory.add_finding(actor=self.name, run_id=context["run_id"], agent_name=self.name, kind="strategy", title="营销策略", content=result)
        return result
