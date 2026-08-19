from __future__ import annotations

from io import BytesIO
from typing import Any, BinaryIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .weekly_report import RoutePoint, WeeklyHealthReport, group_lifestyle_events

INK = colors.HexColor("#182432")
BLUE = colors.HexColor("#4776E6")
TEAL = colors.HexColor("#16A085")
PALE = colors.HexColor("#F2F6FC")
MUTED = colors.HexColor("#66788A")


def render_weekly_report_pdf(report: WeeklyHealthReport) -> bytes:
    output = BytesIO()
    doc = _ReportDoc(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=17 * mm,
        title="7-day health report",
        author="Garmin Health Sync",
    )
    styles = _styles()
    story: list[Flowable] = []
    story.extend(_cover(report, styles))
    story.extend(_training(report, styles))
    story.extend(_recovery(report, styles))
    story.extend(_comprehensive(report, styles))
    story.extend(_pressure(report, styles))
    story.extend(_body(report, styles))
    story.extend(_lifestyle_appendix(report, styles))
    story.extend(_recommendations(report, styles))
    story.extend(_methodology(report, styles))
    doc.build(story)
    return output.getvalue()


class _ReportDoc(BaseDocTemplate):
    def __init__(self, filename: str | BinaryIO, **kwargs: Any) -> None:
        super().__init__(filename, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="main")
        self.addPageTemplates(PageTemplate(id="report", frames=frame, onPage=self._page))

    def _page(self, canvas: Canvas, doc: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(16 * mm, 10 * mm, "GARMIN HEALTH SYNC")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Page {self.page}")
        canvas.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("TitleX", parent=base["Title"], fontName="Helvetica-Bold", fontSize=28, leading=32, textColor=INK, spaceAfter=6),
        "eyebrow": ParagraphStyle("Eyebrow", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=BLUE, spaceAfter=8),
        "h1": ParagraphStyle("H1X", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=INK, spaceBefore=14, spaceAfter=8),
        "h2": ParagraphStyle("H2X", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=INK, spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("BodyX", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=INK, spaceAfter=6),
        "small": ParagraphStyle("SmallX", parent=base["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=MUTED),
        "metric": ParagraphStyle("Metric", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=18, leading=21, alignment=TA_CENTER, textColor=BLUE),
        "metric_label": ParagraphStyle("MetricLabel", parent=base["BodyText"], fontName="Helvetica", fontSize=7, leading=9, alignment=TA_CENTER, textColor=MUTED),
    }


def _cover(report: WeeklyHealthReport, s: dict[str, ParagraphStyle]) -> list[Flowable]:
    metrics = [
        (str(len(report.activities)), "WORKOUTS"),
        (f"{report.total_training_minutes:.0f}", "TRAINING MIN"),
        (str(len(report.pressure.readings)), "BP READINGS"),
        (str(len(report.body)), "BODY RECORDS"),
    ]
    cards = Table([[Paragraph(v, s["metric"]) for v, _ in metrics], [Paragraph(label, s["metric_label"]) for _, label in metrics]], colWidths=[43 * mm] * 4, rowHeights=[12 * mm, 7 * mm])
    cards.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E3F0")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5)]))
    result: list[Flowable] = [Paragraph("PERSONAL HEALTH SUMMARY", s["eyebrow"]), Paragraph("7-day health report", s["title"]), Paragraph(f"{report.start_date:%d %b %Y} - {report.end_date:%d %b %Y}", s["body"]), Spacer(1, 6 * mm), cards, Paragraph("Weekly overview", s["h1"])]
    for item in report.insights:
        source = (
            f" <link href='{item.source_url}' color='#4776E6'>{item.source_title}</link>"
            if item.source_url and item.source_title
            else ""
        )
        result.append(
            Paragraph(
                f"• <b>{item.category}</b> [{item.confidence}] {item.text}{source}",
                s["body"],
            )
        )
    unavailable = ", ".join(report.availability.unavailable) or "None"
    result.extend([Paragraph("Data availability", s["h2"]), Paragraph(f"Available: {', '.join(report.availability.available) or 'None'}<br/>Unavailable: {unavailable}", s["small"])])
    return result


def _training(report: WeeklyHealthReport, s: dict[str, ParagraphStyle]) -> list[Flowable]:
    rows = [["Date", "Activity", "Duration", "Distance", "Avg HR", "Load"]]
    for x in report.activities:
        rows.append([x.measured_at.strftime("%a %H:%M"), x.name[:30], f"{x.duration_minutes:.0f} min", _fmt(x.distance_km, " km"), _fmt(x.average_hr, " bpm"), _fmt(x.training_load)])
    if len(rows) == 1:
        rows.append(["-", "No activities available", "-", "-", "-", "-"])
    return [Paragraph("Training", s["h1"]), Paragraph("Workout summaries recorded by Garmin. Intensity-minute comparisons use Garmin's classifications and may be incomplete when the device was not worn.", s["small"]), _MiniChart([[x.duration_minutes for x in report.activities]], [BLUE]), _table(rows, [22, 57, 24, 24, 23, 20])]


def _recovery(report: WeeklyHealthReport, s: dict[str, ParagraphStyle]) -> list[Flowable]:
    rows = [["Day", "Steps", "Sleep", "Resting HR", "Stress", "Battery +/-", "Readiness"]]
    for x in report.recovery:
        rows.append([x.day.strftime("%a %d"), _fmt(x.steps), _fmt(x.sleep_hours, " h"), _fmt(x.resting_hr, " bpm"), _fmt(x.stress), f"{_fmt(x.body_battery_charged)}/{_fmt(x.body_battery_drained)}", _fmt(x.readiness_score)])
    return [Paragraph("Recovery and activity", s["h1"]), Paragraph(f"Training status: {report.training_status or 'Not available'}", s["body"]), _table(rows, [19, 22, 22, 29, 20, 30, 27])]


def _pressure(report: WeeklyHealthReport, s: dict[str, ParagraphStyle]) -> list[Flowable]:
    rows = [["Time", "Systolic", "Diastolic", "Pulse"]]
    for x in report.pressure.readings:
        rows.append([x.measured_at.strftime("%a %H:%M"), str(x.systolic), str(x.diastolic), _fmt(x.pulse)])
    if len(rows) == 1:
        rows.append(["-", "No readings", "-", "-"])
    average = f"Observed average: {_fmt(report.pressure.average_systolic)}/{_fmt(report.pressure.average_diastolic)} mmHg across {report.pressure.days_covered} day(s). {report.pressure.esc_category}."
    daily = [["Day", "Average", "Readings"]] + [[x.day.strftime("%a %d"), f"{x.systolic:.0f}/{x.diastolic:.0f}", str(x.count)] for x in report.pressure.daily_averages]
    if len(daily) == 1:
        daily.append(["-", "No daily averages", "-"])
    return [Paragraph("Blood pressure", s["h1"]), Paragraph(average, s["body"]), _MiniChart([[float(x.systolic) for x in report.pressure.readings], [float(x.diastolic) for x in report.pressure.readings]], [BLUE, TEAL]), Paragraph("Daily averages", s["h2"]), _table(daily, [56, 56, 56]), Paragraph("All readings", s["h2"]), _table(rows, [42, 42, 42, 42])]


def _comprehensive(report: WeeklyHealthReport, s: dict[str, ParagraphStyle]) -> list[Flowable]:
    result: list[Flowable] = [Paragraph("Comprehensive health metrics", s["h1"])]
    for chart in report.comprehensive.charts:
        result.append(Paragraph(chart.title, s["h2"]))
        result.append(_MiniChart([[value for value in series.values if value is not None] for series in chart.series], [colors.HexColor(series.color) for series in chart.series]))
        result.append(
            Paragraph(" · ".join(series.name for series in chart.series), s["small"])
        )
    nutrition = [["Day", "Hydration", "Goal", "Calories", "Protein", "Carbs", "Fat"]]
    for item in report.comprehensive.hydration_nutrition:
        nutrition.append([item.day.strftime("%a %d"), _fmt(item.hydration_ml, " ml"), _fmt(item.hydration_goal_ml, " ml"), _fmt(item.nutrition_calories), _fmt(item.protein_g, " g"), _fmt(item.carbs_g, " g"), _fmt(item.fat_g, " g")])
    result.extend([Paragraph("Hydration and nutrition totals", s["h2"]), _table(nutrition, [20, 27, 27, 25, 23, 23, 22])])
    return result


def _body(report: WeeklyHealthReport, s: dict[str, ParagraphStyle]) -> list[Flowable]:
    rows = [["Time", "Weight", "Body fat", "Muscle", "Source"]]
    for x in report.body:
        rows.append([x.measured_at.strftime("%a %H:%M"), f"{x.weight_kg:.1f} kg", _fmt(x.body_fat_pct, "%"), _fmt(x.muscle_mass_kg, " kg"), x.source])
    if len(rows) == 1:
        rows.append(["-", "No measurements", "-", "-", "-"])
    return [Paragraph("Weight and body composition", s["h1"]), Paragraph("BIA-derived composition is most useful as a consistently measured trend. Hydration, meals and recent exercise can affect readings.", s["small"]), _MiniChart([[x.weight_kg for x in report.body]], [TEAL]), _table(rows, [34, 31, 31, 31, 43])]


def _methodology(report: WeeklyHealthReport, s: dict[str, ParagraphStyle]) -> list[Flowable]:
    return [Paragraph("Methodology and limitations", s["h1"]), Paragraph("This report combines read-only Garmin Connect data, RENPHO scale measurements and blood-pressure readings stored in Garmin. It is intended for personal monitoring and discussion with a healthcare professional. It does not diagnose disease or prescribe treatment.", s["body"]), Paragraph("Blood pressure: repeated, correctly performed home measurements are more informative than a single reading. If a reading exceeds 180/120 mmHg, repeat it; seek urgent medical help when it remains very high or symptoms are present.", s["body"]), Paragraph("References", s["h2"]), Paragraph("World Health Organization. Guidelines on physical activity and sedentary behaviour (2020).<br/>European Society of Cardiology. 2024 Guidelines for elevated blood pressure and hypertension.<br/>American Heart Association. Home Blood Pressure Monitoring guidance.<br/>Consumer BIA values are indirect estimates affected by hydration and measurement conditions.", s["small"]), Spacer(1, 4 * mm), Paragraph(f"Generated {report.generated_at:%d %b %Y %H:%M %Z}", s["small"])]


def _recommendations(
    report: WeeklyHealthReport, s: dict[str, ParagraphStyle]
) -> list[Flowable]:
    result: list[Flowable] = [
        Paragraph("Practical next steps", s["h1"]),
        Paragraph(
            "Collected rule-based guidance for this week. Prioritize repeatable changes and discuss medical measurements with a qualified professional.",
            s["small"],
        ),
    ]
    result.extend(
        Paragraph(
            f"• <b>{item.category}</b> [{item.confidence}] {item.text}", s["body"]
        )
        for item in report.insights
    )
    return result


def _lifestyle_appendix(report: WeeklyHealthReport, s: dict[str, ParagraphStyle]) -> list[Flowable]:
    rows = [["Date", "Logged behaviors"]]
    for day, labels in group_lifestyle_events(report.comprehensive.lifestyle):
        rows.append([day.strftime("%d %b"), "  ·  ".join(labels)])
    if len(rows) == 1:
        rows.append(["-", "No lifestyle events"])
    result: list[Flowable] = [
        Paragraph("Lifestyle Logging - 30-day context", s["h1"]),
        _table(rows, [30, 138]),
    ]
    result.append(Paragraph("Observed associations", s["h2"]))
    if report.comprehensive.associations:
        for association in report.comprehensive.associations:
            result.append(Paragraph(f"{association.behavior} and {association.metric}: observed median difference {association.median_difference:+.1f} ({association.with_days} days with / {association.without_days} without). Association only; this does not establish causation.", s["small"]))
    else:
        result.append(Paragraph("Not enough repeated observations for behavior comparisons.", s["small"]))
    routes = [item for item in report.comprehensive.activity_details if item.route]
    if routes:
        result.append(Paragraph("Activity routes", s["h1"]))
        for activity in routes:
            result.extend(
                [
                    Paragraph(activity.location_name or "Activity route", s["h2"]),
                    _RouteChart(activity.route),
                ]
            )
    result.append(Paragraph("Extended Garmin appendix", s["h1"]))
    for domain in report.comprehensive.extended:
        result.append(Paragraph(f"{domain.name}: {domain.summary}", s["small"]))
    return result


def _table(rows: list[list[str]], widths_mm: list[float]) -> Table:
    table = Table(rows, colWidths=[x * mm for x in widths_mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("LEADING", (0, 0), (-1, -1), 9), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6DFE8")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table


def _fmt(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


class _MiniChart(Flowable):
    def __init__(self, series: list[list[float]], palette: list[colors.Color]) -> None:
        super().__init__()
        self.series = [values for values in series if values]
        self.palette = palette
        self.width = 170 * mm
        self.height = 35 * mm

    def draw(self) -> None:
        if not self.series:
            self.canv.setFillColor(MUTED)
            self.canv.setFont("Helvetica", 8)
            self.canv.drawString(0, self.height / 2, "No chart data")
            return
        all_values = [value for values in self.series for value in values]
        low, high = min(all_values), max(all_values)
        span = high - low or 1
        self.canv.setStrokeColor(colors.HexColor("#D6DFE8"))
        self.canv.line(0, 5, self.width, 5)
        for index, values in enumerate(self.series):
            self.canv.setStrokeColor(self.palette[index % len(self.palette)])
            self.canv.setFillColor(self.palette[index % len(self.palette)])
            self.canv.setLineWidth(2)
            points: list[tuple[float, float]] = []
            for offset, value in enumerate(values):
                x = self.width / 2 if len(values) == 1 else offset * self.width / (len(values) - 1)
                y = 8 + (value - low) / span * (self.height - 16)
                points.append((x, y))
            for first, second in zip(points, points[1:], strict=False):
                self.canv.line(first[0], first[1], second[0], second[1])
            for x, y in points:
                self.canv.circle(x, y, 2, fill=1, stroke=0)


class _RouteChart(Flowable):
    def __init__(self, points: tuple[RoutePoint, ...]) -> None:
        super().__init__()
        self.points = points
        self.width = 170 * mm
        self.height = 55 * mm

    def draw(self) -> None:
        if not self.points:
            return
        lats = [float(point.latitude) for point in self.points]
        lons = [float(point.longitude) for point in self.points]
        min_lat, max_lat, min_lon, max_lon = min(lats), max(lats), min(lons), max(lons)
        lat_span, lon_span = max_lat - min_lat or 1, max_lon - min_lon or 1
        coords = [((lon - min_lon) * self.width / lon_span, (lat - min_lat) * self.height / lat_span) for lat, lon in zip(lats, lons, strict=True)]
        self.canv.setStrokeColor(BLUE)
        self.canv.setLineWidth(2)
        for first, second in zip(coords, coords[1:], strict=False):
            self.canv.line(first[0], first[1], second[0], second[1])
