from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from reportlab.graphics.shapes import Drawing, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle


def _register_font() -> str:
    for path in (Path("C:/Windows/Fonts/NotoSansSC-Regular.ttf"), Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simsun.ttc")):
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("ReportCJK", str(path)))
                return "ReportCJK"
            except Exception:
                continue
    return "Helvetica"


def _money(value: Any) -> str:
    try:
        return f"{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _safe(value: Any) -> str:
    return html.escape(str(value if value not in (None, "") else "未提供"))


def _chart(title: str, values: dict[str, Any], *, line: bool, font: str) -> Drawing:
    width, height = 175 * mm, 72 * mm
    drawing = Drawing(width, height)
    left, bottom, chart_w, chart_h = 20 * mm, 15 * mm, 145 * mm, 42 * mm
    if line and len(values) > 24:
        quarterly: dict[str, float] = {}
        for key, value in values.items():
            label = str(key); year = label[:4]
            try: period = f"{year}-Q{((int(label[5:7]) - 1) // 3) + 1}"
            except (TypeError, ValueError): period = year
            quarterly[period] = quarterly.get(period, 0) + float(value or 0)
        values = quarterly
    pairs = [(str(k), float(v or 0)) for k, v in values.items()]
    if line:
        pairs = sorted(pairs)
    else:
        pairs = sorted(pairs, key=lambda item: item[1], reverse=True)[:10]
    maximum = max((v for _, v in pairs), default=1) or 1
    drawing.add(String(width / 2, height - 8 * mm, title, textAnchor="middle", fontName=font, fontSize=12, fillColor=colors.HexColor("#172033")))
    drawing.add(Rect(left, bottom, chart_w, chart_h, strokeColor=colors.HexColor("#94a3b8"), fillColor=None))
    if not pairs:
        drawing.add(String(width / 2, bottom + chart_h / 2, "暂无可绘制数据", textAnchor="middle", fontName=font, fontSize=10, fillColor=colors.HexColor("#64748b")))
        return drawing
    if line:
        points = []
        for index, (label, value) in enumerate(pairs):
            x = left + (index / max(1, len(pairs) - 1)) * chart_w
            y = bottom + value / maximum * chart_h
            points.append((x, y))
            drawing.add(String(x, bottom - 4 * mm, label[-8:], textAnchor="middle", fontName=font, fontSize=6, fillColor=colors.HexColor("#475569")))
        drawing.add(PolyLine(points, strokeColor=colors.HexColor("#dc2626"), strokeWidth=2))
        for x, y in points:
            drawing.add(Rect(x - 1.2, y - 1.2, 2.4, 2.4, fillColor=colors.HexColor("#dc2626"), strokeColor=None))
    else:
        slot = chart_w / max(1, len(pairs))
        for index, (label, value) in enumerate(pairs):
            bar_h = value / maximum * chart_h
            x = left + index * slot + slot * 0.18
            drawing.add(Rect(x, bottom, slot * 0.64, bar_h, fillColor=colors.HexColor("#2563eb"), strokeColor=None))
            drawing.add(String(x + slot * 0.32, bottom - 4 * mm, label[:10], textAnchor="middle", fontName=font, fontSize=6, fillColor=colors.HexColor("#475569")))
    return drawing


def build_pdf(*, path: Path, project_name: str, request: str, prepared: dict[str, Any], charts: dict[str, Any], insights: dict[str, Any], validation: dict[str, Any], strategy: dict[str, Any], executive_summary: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    font = _register_font()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CJKTitle", parent=styles["Title"], fontName=font, fontSize=25, leading=32, alignment=TA_CENTER, textColor=colors.HexColor("#163b6d"), spaceAfter=14))
    styles.add(ParagraphStyle(name="CJKH1", parent=styles["Heading1"], fontName=font, fontSize=16, leading=23, textColor=colors.HexColor("#163b6d"), spaceBefore=8, spaceAfter=8))
    styles.add(ParagraphStyle(name="CJKH2", parent=styles["Heading2"], fontName=font, fontSize=12, leading=18, textColor=colors.HexColor("#2563eb"), spaceBefore=6, spaceAfter=5))
    styles.add(ParagraphStyle(name="CJKBody", parent=styles["BodyText"], fontName=font, fontSize=9.5, leading=16, alignment=TA_LEFT, textColor=colors.HexColor("#293247"), spaceAfter=6))
    styles.add(ParagraphStyle(name="CJKSmall", parent=styles["BodyText"], fontName=font, fontSize=8.5, leading=14, alignment=TA_LEFT, textColor=colors.HexColor("#526176"), spaceAfter=4))

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState(); canvas.setFont(font, 8); canvas.setFillColor(colors.HexColor("#64748b")); canvas.drawString(18 * mm, 10 * mm, "多智能体销售分析报告"); canvas.drawRightString(192 * mm, 10 * mm, f"第 {document.page} 页"); canvas.restoreState()

    document = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm, title=f"{project_name}销售分析报告", author="多智能体销售分析")
    story: list[Any] = []
    summary = prepared.get("summary", {})
    story += [Spacer(1, 28 * mm), Paragraph(_safe(project_name) + "<br/>销售与营销分析报告", styles["CJKTitle"]), Paragraph("基于上传 Excel 数据的自动化分析结果", styles["CJKBody"]), Spacer(1, 10 * mm)]
    overview = [[Paragraph("分析目标", styles["CJKH2"]), Paragraph(_safe(request), styles["CJKBody"])], [Paragraph("数据来源", styles["CJKH2"]), Paragraph(_safe(prepared.get("source_name", "Excel 工作簿")), styles["CJKBody"])], [Paragraph("原始数据", styles["CJKH2"]), Paragraph(f"{summary.get('source_rows', summary.get('rows', 0))} 行", styles["CJKBody"])], [Paragraph("全量分析范围", styles["CJKH2"]), Paragraph(f"{summary.get('rows', 0)} 行；{_safe(summary.get('date_from'))} 至 {_safe(summary.get('date_to'))}", styles["CJKBody"])], [Paragraph("明细样本", styles["CJKH2"]), Paragraph(f"{summary.get('sampled_rows', summary.get('rows', 0))} 行，仅用于留档和抽查", styles["CJKBody"])], [Paragraph("销售额合计", styles["CJKH2"]), Paragraph(_money(summary.get("total_amount")), styles["CJKBody"])], [Paragraph("销量合计", styles["CJKH2"]), Paragraph(_money(summary.get("total_quantity")), styles["CJKBody"])]]
    story.append(Table(overview, colWidths=[34 * mm, 128 * mm], style=TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef4ff")), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)])))
    partial_note = "；不完整月份为 " + "、".join(summary.get("partial_periods") or []) if summary.get("partial_periods") else ""
    story += [PageBreak(), Paragraph("一、管理层摘要", styles["CJKH1"]), Paragraph(_safe(executive_summary or "本次分析已完成数据清洗、趋势计算、独立验证和营销策略生成。"), styles["CJKBody"]), Paragraph("二、核心数据与趋势", styles["CJKH1"]), Paragraph(f"本次使用筛选后的全量 {_safe(summary.get('rows', 0))} 行数据计算，日期范围为 {_safe(summary.get('date_from'))} 至 {_safe(summary.get('date_to'))}，覆盖 {_safe(summary.get('period_count', 0))} 个月{_safe(partial_note)}。销售额合计为 {_money(summary.get('total_amount'))}，销量合计为 {_money(summary.get('total_quantity'))}。异常行数为 {_safe(summary.get('anomaly_count', 0))}。最多 {_safe(summary.get('sampled_rows', summary.get('rows', 0)))} 行明细仅用于留档和抽查，不影响本页统计与图表。", styles["CJKBody"])]
    if charts.get("date_totals"): story.append(_chart("按日期销售额趋势", charts["date_totals"], line=True, font=font))
    if charts.get("totals"): story.append(_chart("产品销售额对比", charts["totals"], line=False, font=font))
    story += [Paragraph("三、分析洞察", styles["CJKH1"]), Paragraph(f"完整月份趋势：{_safe(insights.get('trend'))}，比较区间为 {_safe(insights.get('trend_period_from'))} 至 {_safe(insights.get('trend_period_to'))}，首末完整月销售额变化为 {_money(insights.get('first_last_change'))}。销售峰值期为 {_safe((insights.get('peak_period') or {}).get('period'))}，销售额 {_money((insights.get('peak_period') or {}).get('amount'))}；低值期为 {_safe((insights.get('trough_period') or {}).get('period'))}，销售额 {_money((insights.get('trough_period') or {}).get('amount'))}。核心产品：{_safe((insights.get('top_product') or {}).get('name'))}，对应销售额 {_money((insights.get('top_product') or {}).get('amount'))}。主要渠道：{_safe((insights.get('top_channel') or {}).get('name'))}，对应销售额 {_money((insights.get('top_channel') or {}).get('amount'))}。", styles["CJKBody"])]
    by_product = insights.get("by_product") or {}
    if by_product:
        total = float(summary.get("total_amount") or sum(float(value or 0) for value in by_product.values()) or 1)
        rows = [[Paragraph("产品", styles["CJKBody"]), Paragraph("销售额", styles["CJKBody"]), Paragraph("占比", styles["CJKBody"])]]
        rows += [[Paragraph(_safe(name), styles["CJKBody"]), Paragraph(_money(value), styles["CJKBody"]), Paragraph(f"{float(value or 0) / total:.1%}", styles["CJKBody"])] for name, value in list(by_product.items())[:12]]
        table_style = TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2ff")), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")])
        story.append(Table(rows, colWidths=[80 * mm, 45 * mm, 35 * mm], style=table_style))
    validation_block = KeepTogether([Paragraph("四、独立验证", styles["CJKH1"]), Paragraph(f"验证状态：{'通过' if validation.get('valid') else '未通过'}。" + "；".join(f"{_safe(key)}={_safe(value)}" for key, value in (validation.get("checks") or {}).items()), styles["CJKBody"])])
    source_text = "AI 模型根据已验证的汇总数据生成" if strategy.get("generation_mode") == "model" else "模型不可用，本页使用离线降级建议"
    story += [validation_block, Paragraph("五、营销策略建议", styles["CJKH1"]), Paragraph(_safe(strategy.get("strategy_summary", "暂时没有可用的策略摘要。")), styles["CJKBody"]), Paragraph(f"生成方式：{_safe(source_text)}", styles["CJKSmall"])]
    for action in strategy.get("actions", []):
        steps = "<br/>".join(f"{index}. {_safe(item)}" for index, item in enumerate(action.get("steps", []), 1)) or "未提供"
        metrics = "、".join(_safe(item) for item in action.get("metrics", [])) or "未提供"
        card = [
            [Paragraph(f"<b>{_safe(action.get('priority'))}｜{_safe(action.get('title'))}</b>", styles["CJKH2"])],
            [Paragraph(f"<b>目标：</b>{_safe(action.get('goal'))}", styles["CJKBody"])],
            [Paragraph(f"<b>为什么：</b>{_safe(action.get('why'))}", styles["CJKBody"])],
            [Paragraph(f"<b>怎么做：</b><br/>{steps}", styles["CJKBody"])],
            [Paragraph(f"<b>什么时候：</b>{_safe(action.get('timing'))}", styles["CJKBody"])],
            [Paragraph(f"<b>目标人群：</b>{_safe(action.get('audience'))}<br/><b>执行渠道：</b>{_safe(action.get('channel'))}", styles["CJKBody"])],
            [Paragraph(f"<b>如何衡量：</b>{metrics}", styles["CJKBody"])],
            [Paragraph(f"<b>前提与限制：</b>{_safe(action.get('caveat'))}", styles["CJKSmall"])],
        ]
        story.append(KeepTogether(Table(card, colWidths=[162 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2ff")), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b9cbea")), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))))
        story.append(Spacer(1, 4 * mm))
    if strategy.get("risks"):
        story.append(Paragraph("风险与应对", styles["CJKH2"]))
        for item in strategy.get("risks", []):
            story.append(Paragraph(f"<b>风险：</b>{_safe(item.get('risk'))}<br/><b>应对：</b>{_safe(item.get('response'))}", styles["CJKBody"]))
    story.append(KeepTogether([Paragraph("六、方法与限制", styles["CJKH1"]), Paragraph("本报告由数据准备、可视化、洞察、独立验证、营销策略和报告智能体协同生成。筛选后的全部数据先在本地按月、季度、年度、产品和渠道聚合；最多 5000 行的限制只用于保留明细样本，不影响销售额、销量、日期范围、趋势和图表。营销策略模型只接收已验证的汇总洞察和字段可用性，并直接生成策略主体；模型不可用或返回格式不完整时，系统会在报告中明确标注并使用谨慎的离线降级建议。好评、退货、点击和转化率只有在 Excel 中提供对应字段并接入相应专用分析模块后才会计算。", styles["CJKBody"])]))
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return path
