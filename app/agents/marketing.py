from __future__ import annotations

import json
from typing import Any

from .base import BaseAgent


class MarketingAgent(BaseAgent):
    name, description = "marketing", "基于已验证数据生成清晰、可执行的营销策略"

    @staticmethod
    def _text(value: Any, default: str) -> str:
        text = str(value or "").strip()
        return text or default

    @classmethod
    def _normalise_model_result(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Only a complete strategy structure may become the report's main advice."""
        if not isinstance(value, dict) or not isinstance(value.get("actions"), list):
            return None
        actions = []
        for index, raw in enumerate(value["actions"][:3]):
            if not isinstance(raw, dict):
                continue
            steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
            metrics = raw.get("metrics") if isinstance(raw.get("metrics"), list) else []
            steps = [str(item).strip() for item in steps if str(item).strip()][:3]
            metrics = [str(item).strip() for item in metrics if str(item).strip()][:3]
            if not all((raw.get("title"), raw.get("why"), steps, metrics)):
                continue
            actions.append(
                {
                    "priority": cls._text(raw.get("priority"), "优先执行" if index == 0 else "第二阶段"),
                    "title": cls._text(raw.get("title"), f"策略 {index + 1}"),
                    "goal": cls._text(raw.get("goal"), "改善下一周期销售表现"),
                    "why": cls._text(raw.get("why"), "依据当前销售趋势制定"),
                    "steps": steps,
                    "audience": cls._text(raw.get("audience"), "目标人群数据不足，需补充客户标签"),
                    "timing": cls._text(raw.get("timing"), "下一完整销售周期"),
                    "channel": cls._text(raw.get("channel"), "渠道数据不足，需结合实际渠道安排"),
                    "metrics": metrics,
                    "caveat": cls._text(raw.get("caveat"), "先小范围执行，再根据实际结果调整"),
                }
            )
        if not actions:
            return None
        risks = []
        for raw in value.get("risks", [])[:3] if isinstance(value.get("risks"), list) else []:
            if isinstance(raw, dict) and raw.get("risk"):
                risks.append({"risk": cls._text(raw.get("risk"), "数据存在局限"), "response": cls._text(raw.get("response"), "补充数据后复核")})
        return {
            "strategy_summary": cls._text(value.get("strategy_summary"), "下一周期先验证重点产品与关键销售时段，再逐步扩大投入。"),
            "actions": actions,
            "risks": risks,
        }

    @staticmethod
    def _fallback(insights: dict[str, Any], data_profile: dict[str, Any]) -> dict[str, Any]:
        """Conservative plain-language output used only when the model is unavailable."""
        product = (insights.get("top_product") or {}).get("name")
        peak = (insights.get("peak_period") or {}).get("period")
        trough = (insights.get("trough_period") or {}).get("period")
        product_label = str(product) if product and product != "未分类" else "销售额较高的产品"
        peak_label = str(peak) if peak else "历史销售较高的完整月份"
        trough_label = str(trough) if trough else "历史销售较低的完整月份"
        sales_metrics = ["下一完整周期销售额", "重点产品销售额占比"]
        if data_profile.get("has_quantity"):
            sales_metrics.append("销量")
        common = {
            "audience": "当前数据没有可靠的客户分群信息，需先补充客户标签",
            "channel": "当前数据没有可靠的渠道信息，需结合实际经营渠道执行",
            "caveat": "本建议只依据历史销售汇总，先小范围验证后再扩大执行",
        }
        actions = [
            {
                "priority": "优先执行",
                "title": "验证重点产品的组合销售",
                "goal": "在控制投入的前提下，提高下一周期销售额",
                "why": f"{product_label}在当前数据中的销售额较高，适合作为第一批测试对象。",
                "steps": [f"选择{product_label}及一至两个关联产品，设计简单组合方案", "设置原方案与组合方案两组，使用相同周期进行比较", "根据销售额和销量结果决定是否扩大范围"],
                "timing": f"下一完整销售周期；可优先参考{peak_label}前的备货与推广节奏",
                "metrics": sales_metrics[:3],
                **common,
            },
            {
                "priority": "第二阶段",
                "title": "针对销售低位期做小规模促销测试",
                "goal": "判断价格或组合调整能否改善低位期表现",
                "why": f"{trough_label}是历史销售低位，可用于检验促销是否带来真实增量。",
                "steps": ["选取少量产品设置短周期测试方案", "保留未参加活动的产品或时段作为对照", "测试结束后比较活动前后销售额，不达预期则停止"],
                "timing": f"接近{trough_label}的同类销售周期",
                "metrics": ["测试期销售额", "对照组销售额", "活动增量销售额"],
                **common,
            },
        ]
        return {
            "strategy_summary": "先用现有销售数据验证重点产品和低位期方案，再根据结果决定是否扩大投入。",
            "actions": actions,
            "risks": [{"risk": "缺少客户、渠道、点击和转化数据，无法判断具体投放人群与渠道效果。", "response": "后续在 Excel 中补充客户标签、渠道、曝光、点击和成交字段，再细化策略。"}],
        }

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        insights, validation = payload.get("insights", {}), payload.get("validation", {})
        summary = payload.get("summary") or {}
        if not validation.get("valid", True):
            return {"status": "blocked", "reason": "数据验证未通过，暂不生成营销策略", "actions": [], "llm_used": False, "generation_mode": "blocked"}

        channel_name = (insights.get("top_channel") or {}).get("name")
        data_profile = {
            "rows": summary.get("rows") or insights.get("analysis_rows"),
            "date_from": summary.get("date_from"),
            "date_to": summary.get("date_to"),
            "partial_periods": summary.get("partial_periods") or insights.get("partial_periods") or [],
            "has_product": bool(summary.get("product_column")) and (insights.get("top_product") or {}).get("name") not in (None, "未分类"),
            "has_channel": bool(summary.get("channel_column")) and channel_name not in (None, "未分类"),
            "has_quantity": bool(summary.get("quantity_column")),
            "available_columns": summary.get("columns") or [],
            "unsupported_metrics": ["客户意向", "复购率", "曝光量", "点击率", "转化率", "获客成本", "退货率", "好评率"],
        }
        model_value = self.ask_json(
            system=(
                "你是面向普通企业经营者的资深营销分析师。你的任务是把已验证的销售汇总指标转成明确、通俗、专业且能执行的建议。\n"
                "写作规则：\n"
                "1. 最多给 3 项策略，每项都回答：为什么做、具体做什么、什么时候做、如何衡量。使用短句和常用中文。\n"
                "2. 专业术语首次出现时用一句话解释；不要使用‘赋能、抓手、链路、打法、转化素材’等含糊行话。\n"
                "3. 只能使用输入中存在的数据。不得虚构客户意向、用户分群、渠道、曝光、点击、转化、获客成本、复购、好差评、退货或严格同比。\n"
                "4. 数据不支持人群或渠道判断时，对应字段直接写‘目标人群数据不足，需补充客户标签’或‘渠道数据不足，需结合实际渠道安排’，不要写‘未分类渠道’。\n"
                "   如果 has_channel=false，不仅 channel 字段不得指定渠道，title、goal、why、steps、timing、metrics 和 risks 中也不得出现线上、线下、门店、短信、私域、信息流等具体渠道或投放方式。\n"
                "   输入没有客户标签时，任何字段都不得声称现有客户、潜客、高意向、流失、复购或特定年龄地域人群。\n"
                "5. 不把商品名称推断成正式品类；确需描述时必须写‘根据商品名称推测’。不完整月份不能与完整月份直接比较。\n"
                "6. 数据依据 why 必须引用输入中的具体产品、时期、趋势或金额，但不要堆砌整张数据表。指标必须是当前数据能直接计算的指标。\n"
                "7. 只返回合法 JSON，不要 Markdown、解释或代码围栏。严格使用以下结构："
                '{"strategy_summary":"一句话重点","actions":[{"priority":"优先执行或第二阶段","title":"策略名称","goal":"要解决的问题","why":"数据依据","steps":["步骤1","步骤2"],"audience":"目标人群或缺失说明","timing":"建议时间","channel":"渠道或缺失说明","metrics":["指标1","指标2"],"caveat":"限制或前提"}],"risks":[{"risk":"风险","response":"应对方式"}]}'
            ),
            prompt=(
                "请为下一完整销售周期生成营销策略。\n"
                "已验证的汇总洞察：" + json.dumps(insights, ensure_ascii=False) + "\n"
                "数据字段可用性与限制：" + json.dumps(data_profile, ensure_ascii=False) + "\n"
                "验证结果：" + json.dumps(validation, ensure_ascii=False)
            ),
            context=context,
        )
        strategy = self._normalise_model_result(model_value)
        llm_used = strategy is not None
        if strategy is None:
            strategy = self._fallback(insights, data_profile)

        result = {
            "status": "ready",
            "objective": "用可验证的小规模行动改善下一周期销售表现",
            **strategy,
            "guardrails": ["先小范围测试，再根据结果扩大", "只使用当前数据能够计算的指标评估效果"],
            "llm_used": llm_used,
            "generation_mode": "model" if llm_used else "offline_fallback",
            "provider": getattr(self.llm, "provider_name", "offline") if llm_used else "offline",
            "model": getattr(self.llm, "model", "none") if llm_used else "none",
        }
        if context.get("run_id"):
            self.memory.add_finding(actor=self.name, run_id=context["run_id"], agent_name=self.name, kind="strategy", title="营销策略", content=result)
        return result
