from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import BaseAgent
from ..selection import filter_data


def _num(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(str(value).replace(",", "").replace("￥", "").replace("¥", ""))
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


class DataPreparationAgent(BaseAgent):
    name, description = "data_preparation", "读取、筛选、清洗并统一指标"

    def _load(self, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        if isinstance(payload.get("data"), list):
            return [dict(row) for row in payload["data"] if isinstance(row, dict)], "request.data"
        if payload.get("csv_path"):
            path = Path(payload["csv_path"])
            if not path.exists():
                raise FileNotFoundError(path)
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                return list(csv.DictReader(fh)), str(path)
        raise ValueError("需要提供 data 或 csv_path")

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        rows, source = self._load(payload)
        if not rows:
            raise ValueError("输入数据为空")
        keys = sorted({key for row in rows for key in row})
        lowered = {key.lower(): key for key in keys}
        def pick(*names: str) -> str | None:
            return next((lowered[name] for name in names if name in lowered), None)
        date_key, amount_key, quantity_key = pick("date", "日期", "time", "时间"), pick("amount", "sales", "revenue", "销售额", "金额"), pick("quantity", "qty", "销量", "数量")
        product_key, channel_key = pick("product", "产品", "sku", "品类"), pick("channel", "渠道")
        normalized, anomalies = [], []
        for index, raw in enumerate(rows):
            item = dict(raw)
            if date_key: item["date"] = _date(raw.get(date_key))
            if amount_key: item["amount"] = _num(raw.get(amount_key))
            if quantity_key: item["quantity"] = _num(raw.get(quantity_key))
            if product_key: item["product"] = str(raw.get(product_key) or "未分类")
            if channel_key: item["channel"] = str(raw.get(channel_key) or "未分类")
            flags = []
            if amount_key and (item.get("amount") is None or item.get("amount") < 0): flags.append("amount_invalid")
            if quantity_key and item.get("quantity") is None: flags.append("quantity_invalid")
            if date_key and item.get("date") is None: flags.append("date_invalid")
            item["anomaly_flags"] = flags
            if flags: anomalies.append({"row": index, "flags": flags})
            normalized.append(item)
        if date_key: normalized.sort(key=lambda r: str(r.get("date") or ""))
        gated = filter_data(normalized, selection=context.get("selection", {}), filters=payload.get("filters"), max_rows=int(context.get("max_filter_rows", 5000)))
        selected = gated["rows"]
        schema = {key: type(next((r.get(key) for r in selected if r.get(key) is not None), "")).__name__ for key in keys}
        summary = {"rows": len(selected), "columns": keys, "date_column": date_key, "amount_column": amount_key, "quantity_column": quantity_key, "product_column": product_key, "channel_column": channel_key, "anomaly_count": sum(1 for r in selected if r.get("anomaly_flags")), "total_amount": round(sum(r.get("amount") or 0 for r in selected), 2), "total_quantity": round(sum(r.get("quantity") or 0 for r in selected), 2), "filter": gated}
        return {"source_name": source, "rows": selected, "schema": schema, "summary": summary, "anomalies": anomalies, "selection": context.get("selection", {})}

