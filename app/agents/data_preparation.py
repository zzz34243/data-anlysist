from __future__ import annotations

import csv
import calendar
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import BaseAgent
from ..selection import apply_row_filters, filter_data


def _num(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(str(value).replace(",", "").replace("￥", "").replace("¥", ""))
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
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
            return [dict(row) for row in payload["data"] if isinstance(row, dict)], str(payload.get("source_name") or "request.data")
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
        date_key = pick("date", "日期", "time", "时间", "invoicedate", "orderdate", "order_date", "订单日期")
        amount_key = pick("amount", "sales", "revenue", "销售额", "金额")
        quantity_key, price_key = pick("quantity", "qty", "销量", "数量"), pick("price", "unitprice", "unit_price", "单价")
        product_key = pick("product", "产品", "sku", "品类", "description", "productname", "product_name", "stockcode")
        channel_key = pick("channel", "渠道")
        normalized, anomalies = [], []
        for index, raw in enumerate(rows):
            item = dict(raw)
            if date_key: item["date"] = _date(raw.get(date_key))
            if amount_key:
                item["amount"] = _num(raw.get(amount_key))
            elif quantity_key and price_key:
                quantity, price = _num(raw.get(quantity_key)), _num(raw.get(price_key))
                item["amount"] = quantity * price if quantity is not None and price is not None else None
            if quantity_key: item["quantity"] = _num(raw.get(quantity_key))
            if product_key: item["product"] = str(raw.get(product_key) or "未分类")
            if channel_key: item["channel"] = str(raw.get(channel_key) or "未分类")
            flags = []
            if (amount_key or price_key) and (item.get("amount") is None or item.get("amount") < 0): flags.append("amount_invalid")
            if quantity_key and item.get("quantity") is None: flags.append("quantity_invalid")
            if date_key and item.get("date") is None: flags.append("date_invalid")
            item["anomaly_flags"] = flags
            if flags: anomalies.append({"row": index, "flags": flags})
            normalized.append(item)
        if date_key: normalized.sort(key=lambda r: str(r.get("date") or ""))
        full_filtered = apply_row_filters(normalized, payload.get("filters"))
        gated = filter_data(normalized, selection=context.get("selection", {}), filters=payload.get("filters"), max_rows=int(context.get("max_filter_rows", 5000)))
        selected = gated["rows"]
        schema = {key: type(next((r.get(key) for r in selected if r.get(key) is not None), "")).__name__ for key in keys}
        by_month, by_quarter, by_year = defaultdict(float), defaultdict(float), defaultdict(float)
        by_product, by_channel = defaultdict(float), defaultdict(float)
        dates: list[str] = []
        total_amount = total_quantity = 0.0
        for row in full_filtered:
            amount = float(row.get("amount") or 0)
            quantity = float(row.get("quantity") or 0)
            total_amount += amount; total_quantity += quantity
            by_product[str(row.get("product") or "未分类")] += amount
            by_channel[str(row.get("channel") or "未分类")] += amount
            date = str(row.get("date") or "")[:10]
            if date:
                dates.append(date); month = date[:7]; year = date[:4]
                try: quarter = f"{year}-Q{((int(date[5:7]) - 1) // 3) + 1}"
                except (TypeError, ValueError): quarter = "日期格式异常"
                by_month[month] += amount; by_quarter[quarter] += amount; by_year[year] += amount
        product_top = dict(sorted(by_product.items(), key=lambda item: item[1], reverse=True)[:50])
        channel_top = dict(sorted(by_channel.items(), key=lambda item: item[1], reverse=True)[:50])
        date_from, date_to = (min(dates), max(dates)) if dates else (None, None)
        partial_periods: list[str] = []
        if date_from and int(date_from[8:10]) > 1: partial_periods.append(date_from[:7])
        if date_to and int(date_to[8:10]) < calendar.monthrange(int(date_to[:4]), int(date_to[5:7]))[1] and date_to[:7] not in partial_periods: partial_periods.append(date_to[:7])
        aggregates = {"by_month": dict(sorted(by_month.items())), "by_quarter": dict(sorted(by_quarter.items())), "by_year": dict(sorted(by_year.items())), "by_product": product_top, "by_channel": channel_top, "total_amount": round(total_amount, 2), "total_quantity": round(total_quantity, 2), "product_count": len(by_product), "channel_count": len(by_channel)}
        summary = {"source_rows": len(normalized), "rows": len(full_filtered), "sampled_rows": len(selected), "columns": keys, "date_column": date_key, "date_from": date_from, "date_to": date_to, "period_count": len(by_month), "partial_periods": partial_periods, "amount_column": amount_key or (f"{quantity_key} × {price_key}" if quantity_key and price_key else None), "quantity_column": quantity_key, "product_column": product_key, "channel_column": channel_key, "anomaly_count": sum(1 for row in full_filtered if row.get("anomaly_flags")), "total_amount": round(total_amount, 2), "total_quantity": round(total_quantity, 2), "filter": {key: value for key, value in gated.items() if key != "rows"}}
        return {"source_name": source, "rows": selected, "aggregates": aggregates, "schema": schema, "summary": summary, "anomalies": anomalies[:1000], "selection": context.get("selection", {})}
