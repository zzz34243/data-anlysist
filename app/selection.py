from __future__ import annotations

from typing import Any


DEFAULT_DATA_TYPES: dict[str, dict[str, list[str]]] = {
    "offline": {
        "positive": ["product_sales", "product_search_volume", "product_positive_reviews"],
        "negative": ["product_returns_refunds", "product_negative_reviews"],
    },
    "online": {
        "positive": ["total_downloads", "daily_active_users", "average_usage_duration", "user_positive_reviews", "search_discussion_volume"],
        "negative": ["uninstalls", "user_negative_reviews"],
    },
}

DATA_TYPE_LABELS = {
    "product_sales": "产品销量", "product_search_volume": "产品网络搜索量", "product_positive_reviews": "产品好评",
    "product_returns_refunds": "产品退货退款", "product_negative_reviews": "产品差评", "total_downloads": "总下载量",
    "daily_active_users": "每日在线用户", "average_usage_duration": "平均使用时长", "user_positive_reviews": "用户好评",
    "search_discussion_volume": "搜索量/讨论度", "uninstalls": "用户卸载量", "user_negative_reviews": "用户差评",
}


def resolve_selection(product_mode: str = "offline", requested_types: list[str] | None = None, chart_types: list[str] | None = None) -> dict[str, Any]:
    mode = product_mode if product_mode in DEFAULT_DATA_TYPES else "offline"
    allowed = DEFAULT_DATA_TYPES[mode]
    requested = requested_types or [*allowed["positive"], *allowed["negative"]]
    selected = [item for item in requested if item in DATA_TYPE_LABELS and item in (*allowed["positive"], *allowed["negative"])]
    charts = [item for item in (chart_types or ["bar", "line"]) if item in {"bar", "line"}] or ["bar", "line"]
    return {"product_mode": mode, "positive": [item for item in selected if item in allowed["positive"]], "negative": [item for item in selected if item in allowed["negative"]], "labels": {item: DATA_TYPE_LABELS[item] for item in selected}, "chart_types": charts}


def filter_data(rows: list[dict[str, Any]], *, selection: dict[str, Any], filters: dict[str, Any] | None = None, max_rows: int = 5000) -> dict[str, Any]:
    """Fixed gate used before any model call. It filters, limits and records excluded rows."""
    filters = filters or {}
    allowed_types = set(selection.get("positive", []) + selection.get("negative", []))
    working = list(rows)
    date_from = str(filters["date_from"]) if filters.get("date_from") else None
    date_to = str(filters["date_to"]) if filters.get("date_to") else None
    product = str(filters["product"]) if filters.get("product") else None
    channel = str(filters["channel"]) if filters.get("channel") else None
    def keep(row: dict[str, Any]) -> bool:
        date = str(row.get("date") or row.get("日期") or "")
        return (not date_from or date >= date_from) and (not date_to or date <= date_to) and (not product or str(row.get("product") or row.get("产品") or "") == product) and (not channel or str(row.get("channel") or row.get("渠道") or "") == channel)
    filtered = [row for row in working if keep(row)]
    requested_limit = filters.get("limit", max_rows)
    try:
        limit = min(max_rows, max(1, int(requested_limit)))
    except (TypeError, ValueError) as exc:
        raise ValueError("filters.limit 必须是正整数") from exc
    truncated = len(filtered) > limit
    filtered = filtered[:limit]
    return {"rows": filtered, "excluded_count": len(working) - len(filtered), "truncated": truncated, "limit": limit, "filters": filters, "allowed_data_types": sorted(allowed_types)}


def optimize_prompt(request: str, *, selection: dict[str, Any], date_range: str | None = None) -> dict[str, Any]:
    text = (request or "").strip()
    if not text:
        raise ValueError("request 不能为空")
    period = date_range or "按输入数据中的日期范围"
    data_labels = "、".join(selection.get("labels", {}).values()) or "默认数据指标"
    charts = "、".join("柱状对比图" if item == "bar" else "线性趋势图" for item in selection.get("chart_types", ["bar", "line"]))
    prompt = f"请提取{period}内的{data_labels}，统一数据口径，制作{charts}，并返回当前表现、趋势异常与后续营销方案报告。用户原始要求：{text}"
    return {"original_request": text, "optimized_prompt": prompt, "period": period, "data_types": selection.get("labels", {}), "chart_types": selection.get("chart_types", ["bar", "line"]), "report_focus": ["current_performance", "trend_and_anomaly", "future_marketing_plan"]}


def devote() -> list[dict[str, Any]]:
    """Fixed delegation map. The orchestrator is the only caller allowed to persist it."""
    return [
        {"step_order": 1, "agent": "data_preparation", "title": "按筛选门禁读取、清洗并统一指标", "allowed_inputs": ["raw_data", "selection", "filters"]},
        {"step_order": 2, "agent": "visualization", "title": "生成柱状对比图和线性趋势图", "allowed_inputs": ["prepared_data", "selection"]},
        {"step_order": 3, "agent": "insights", "title": "计算趋势、异常和用户倾向", "allowed_inputs": ["prepared_data"]},
        {"step_order": 4, "agent": "validator", "title": "独立复算指标并验证 Findings", "allowed_inputs": ["prepared_data", "insights"]},
        {"step_order": 5, "agent": "marketing", "title": "基于已验证结论制定策略", "allowed_inputs": ["insights", "validation"]},
        {"step_order": 6, "agent": "report", "title": "整合图表、分析结论与营销策略", "allowed_inputs": ["prepared_data", "charts", "insights", "validation", "strategy"]},
        {"step_order": 7, "agent": "validator", "title": "复核最终报告完整性", "allowed_inputs": ["report", "insights", "prepared_data"]},
    ]
