from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol, cast

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .renpho_report import BodySegment, Impedance, RenphoReportData, ReportMetric

WIDTH = 2480
HEIGHT = 3508
BLUE = "#4868DF"
GREEN = "#11C5A0"
PALE = "#F0F1FF"
DARK = "#303235"
GRAY = "#777777"
ORANGE = "#FF7A3D"
FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
BOLD_FONT = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
MAX_VENDOR_PDF_BYTES = 10 * 1024 * 1024


class VendorReportFetcher(Protocol):
    def fetch(self, report_id: str) -> tuple[bytes, str] | None: ...


@dataclass(frozen=True, slots=True)
class ReportDocument:
    content: bytes
    source: str


class ReportProvider:
    def __init__(self, vendor: VendorReportFetcher | None = None) -> None:
        self.vendor = vendor

    def resolve(self, report: RenphoReportData) -> ReportDocument:
        if self.vendor is not None and report.report_id:
            try:
                candidate = self.vendor.fetch(report.report_id)
                if candidate is not None and _valid_vendor_pdf(*candidate):
                    return ReportDocument(candidate[0], "Original RENPHO")
            # Vendor failures intentionally fall back to the local renderer.
            except Exception:  # nosec B110
                pass
        return ReportDocument(body_composition_pdf(report), "Rendered from RENPHO data")


def body_composition_pdf(report: RenphoReportData) -> bytes:
    page = render_report_image(report)
    png = BytesIO()
    page.save(png, "PNG", optimize=True)
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    pdf.setTitle("Body Composition Analysis Report")
    pdf.drawImage(ImageReader(BytesIO(png.getvalue())), 0, 0, width=A4[0], height=A4[1])
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def render_report_image(report: RenphoReportData) -> Image.Image:
    renderer = _Renderer(report)
    renderer.draw_page()
    return renderer.image


class _Renderer:
    def __init__(self, report: RenphoReportData) -> None:
        self.report = report
        self.image = Image.new("RGB", (WIDTH, HEIGHT), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.regular = _font(29)
        self.small = _font(24)
        self.tiny = _font(20)
        self.bold = _font(31, bold=True)
        self.heading = _font(38, bold=True)

    def draw_page(self) -> None:
        self._header()
        self._composition_table()
        self._analysis_bars()
        self._segments()
        self._impedance()
        self._right_column()
        self.draw.text(
            (100, 3420),
            "Note: Results are for fitness and health monitoring only and are not a substitute for medical equipment.",
            fill=DARK,
            font=self.tiny,
        )

    def _header(self) -> None:
        self.draw.text((100, 55), "RENPHO", fill=BLUE, font=_font(78, bold=True))
        self.draw.text((105, 145), "Empower Your Wellness", fill=BLUE, font=self.regular)
        self.draw.line((610, 55, 610, 190), fill=DARK, width=2)
        self.draw.text(
            (690, 78), "Body Composition Analysis Report", fill=DARK, font=_font(66, bold=True)
        )
        self.draw.rectangle((0, 238, WIDTH, 267), fill=PALE)
        fields = [
            f"ID: {_text(self.report.report_id)}",
            f"Gender: {self.report.gender}",
            f"Age: {_number(self.report.age, 0)}",
            f"Height: {_number(self.report.height_cm, 1)} cm",
            f"Test Date: {self.report.measured_at:%b %d, %Y %H:%M:%S}",
        ]
        x = 100
        for index, value in enumerate(fields):
            self.draw.text((x, 300), value, fill=DARK, font=self.regular)
            width = self.draw.textlength(value, font=self.regular)
            x += int(width) + 80
            if index < len(fields) - 1:
                self.draw.line((x - 40, 292, x - 40, 350), fill=GRAY, width=2)

    def _section(self, title: str, x: int, y: int, width: int) -> None:
        self.draw.text((x, y), title, fill=DARK, font=self.heading)
        start = x + int(self.draw.textlength(title, font=self.heading)) + 45
        self.draw.line((start, y + 27, x + width, y + 27), fill="#999999", width=2)

    def _composition_table(self) -> None:
        x, y, width = 100, 405, 1340
        self._section("Body Composition Analysis", x, y, width)
        top = y + 78
        columns = [x, x + 365, x + 730, x + 1045, x + width]
        self.draw.rectangle((x, top, x + width, top + 80), fill=BLUE)
        for index, title in enumerate(("", "Measurement (kg)", "Optimal Range", "Evaluation")):
            self._center_text(title, columns[index], columns[index + 1], top + 24, self.small, "white")
        metrics = [
            ("Weight", self.report.weight),
            ("Body Fat Mass", self.report.body_fat_mass),
            ("Bone Mass", self.report.bone_mass),
            ("Protein Mass", self.report.protein_mass),
            ("Body Water Mass", self.report.water_mass),
            ("Muscle Mass", self.report.muscle_mass),
            ("Skeletal Muscle Mass", self.report.skeletal_muscle_mass),
        ]
        for row, (label, metric) in enumerate(metrics):
            row_top = top + 80 + row * 78
            self.draw.rectangle((x, row_top, columns[1], row_top + 78), fill=PALE)
            self.draw.text((x + 30, row_top + 23), label, fill=DARK, font=self.small)
            self._center_text(_metric_value(metric), columns[1], columns[2], row_top + 23, self.small)
            self.draw.rectangle((columns[2], row_top, columns[3], row_top + 78), fill=PALE)
            self._center_text(_range(metric), columns[2], columns[3], row_top + 23, self.small)
            self._center_text(metric.evaluation, columns[3], columns[4], row_top + 23, self.small)
            self.draw.line((x, row_top + 78, x + width, row_top + 78), fill="#CCCCCC", width=1)

    def _analysis_bars(self) -> None:
        x, width = 100, 1340
        y = 1125
        self._section("Muscle and Fat Analysis", x, y, width)
        rows = [
            ("Weight (kg)", self.report.weight, 55, 205),
            ("Skeletal Muscle\nMass (kg)", self.report.skeletal_muscle_mass, 70, 170),
            ("Body Fat Mass (kg)", self.report.body_fat_mass, 40, 520),
        ]
        self._bar_group(x, y + 70, rows)
        y = 1635
        self._section("Obesity Analysis", x, y, width)
        rows2 = [
            ("BMI (kg/m²)", self.report.bmi, 10, 55),
            ("Body Fat\nPercentage (%)", self.report.body_fat_percentage, 0, 50),
        ]
        self._bar_group(x, y + 70, rows2)

    def _bar_group(
        self, x: int, y: int, rows: Sequence[tuple[str, ReportMetric, float, float]]
    ) -> None:
        label_w = 365
        bar_x = x + label_w
        bar_w = 975
        header_h = 78
        self.draw.rectangle((x, y, bar_x, y + header_h), fill=PALE)
        thirds = (0.21, 0.39, 1.0)
        starts = (0.0, thirds[0], thirds[1])
        for label, start, end, color in zip(
            ("Low", "Standard", "High"), starts, thirds, (BLUE, GREEN, BLUE), strict=True
        ):
            left = bar_x + int(bar_w * start)
            right = bar_x + int(bar_w * end)
            self.draw.rectangle((left, y, right, y + header_h), fill=color)
            self._center_text(label, left, right, y + 25, self.small, "white")
        for index, (label, metric, low, high) in enumerate(rows):
            top = y + header_h + index * 105
            self.draw.rectangle((x, top, bar_x, top + 105), fill=PALE)
            self._multiline(label, x + 30, top + 18, self.small)
            self.draw.line((bar_x, top + 80, bar_x + bar_w, top + 80), fill="#AAAAAA", width=1)
            for tick in range(11):
                tx = bar_x + int(bar_w * tick / 10)
                self.draw.line((tx, top + 60, tx, top + 83), fill="#999999", width=1)
            if metric.value is not None:
                ratio = max(0.02, min(0.98, (metric.value - low) / (high - low)))
                value_x = bar_x + int(bar_w * ratio)
                self.draw.rounded_rectangle((bar_x, top + 58, value_x, top + 80), 10, fill=GREEN)
                self.draw.text((value_x + 12, top + 51), _number(metric.value, 2), DARK, self.small)

    def _segments(self) -> None:
        y = 2070
        self._section("Segmental Fat Analysis", 100, y, 650)
        self._section("Muscle Balance", 800, y, 640)
        self._body_figure(375, y + 150, ORANGE, muscle=False)
        self._body_figure(1070, y + 150, "#3596EC", muscle=True)
        positions = [
            ("Left Arm", self.report.left_arm, 100, y + 75),
            ("Right Arm", self.report.right_arm, 520, y + 75),
            ("Trunk", self.report.trunk, 100, y + 330),
            ("Left Leg", self.report.left_leg, 100, y + 610),
            ("Right Leg", self.report.right_leg, 520, y + 610),
        ]
        for name, segment, sx, sy in positions:
            self._segment_text(name, segment, sx, sy, muscle=False)
            self._segment_text(name, segment, sx + 700, sy, muscle=True)

    def _body_figure(self, cx: int, top: int, color: str, *, muscle: bool) -> None:
        self.draw.ellipse((cx - 35, top, cx + 35, top + 72), outline="#AAAAAA", width=2)
        self.draw.polygon(
            [(cx - 55, top + 82), (cx + 55, top + 82), (cx + 80, top + 300), (cx - 80, top + 300)],
            outline="#AAAAAA",
            fill="white",
        )
        for dx in (-1, 1):
            self.draw.line((cx + dx * 60, top + 100, cx + dx * 125, top + 390), fill="#AAAAAA", width=5)
            self.draw.line((cx + dx * 50, top + 300, cx + dx * 85, top + 610), fill="#AAAAAA", width=6)
        if muscle:
            self.draw.ellipse((cx - 55, top + 105, cx + 55, top + 265), fill=color)
            self.draw.ellipse((cx - 110, top + 115, cx - 65, top + 310), fill=color)
            self.draw.ellipse((cx + 65, top + 115, cx + 110, top + 310), fill=color)
            self.draw.ellipse((cx - 75, top + 305, cx - 20, top + 535), fill=color)
            self.draw.ellipse((cx + 20, top + 305, cx + 75, top + 535), fill=color)
        else:
            self.draw.ellipse((cx - 90, top + 120, cx - 55, top + 280), fill=color)
            self.draw.ellipse((cx + 55, top + 120, cx + 90, top + 280), fill=color)
            self.draw.ellipse((cx - 65, top + 220, cx + 65, top + 360), fill=color)
            self.draw.ellipse((cx - 75, top + 350, cx - 35, top + 520), fill=color)
            self.draw.ellipse((cx + 35, top + 350, cx + 75, top + 520), fill=color)

    def _segment_text(
        self, name: str, segment: BodySegment, x: int, y: int, *, muscle: bool
    ) -> None:
        metric = segment.muscle if muscle else segment.fat
        color = "#3596EC" if muscle else ORANGE
        self.draw.text((x, y), name, fill=DARK, font=self.small)
        evaluation = _segment_evaluation(metric.percentage, muscle=muscle)
        self.draw.text((x, y + 38), f"• {_number(metric.mass, 2)} kg  {evaluation}", fill=color, font=self.tiny)
        self.draw.text((x, y + 72), f"• {_number(metric.percentage, 1)}%", fill=BLUE, font=self.tiny)
        self.draw.text((x, y + 106), f"• {_number(metric.standard, 2)} kg", fill="#15A823", font=self.tiny)

    def _impedance(self) -> None:
        x, y, width = 100, 3030, 1340
        self._section("Bioelectrical Impedance", x, y, width)
        top = y + 72
        columns = [x + i * width // 6 for i in range(7)]
        headers = ["Z (Ω)", "Right Arm", "Left Arm", "Trunk", "Right Leg", "Left Leg"]
        self.draw.rectangle((x, top, x + width, top + 78), fill=BLUE)
        for i, label in enumerate(headers):
            self._center_text(label, columns[i], columns[i + 1], top + 25, self.small, "white")
        pairs = (("20 (kHz)", self.report.impedance_20khz), ("100 (kHz)", self.report.impedance_100khz))
        for row, (label, values) in enumerate(pairs):
            row_y = top + 78 + row * 72
            cells = [label, *_impedance_values(values)]
            for i, value in enumerate(cells):
                if i % 2 == 0:
                    self.draw.rectangle((columns[i], row_y, columns[i + 1], row_y + 72), fill=PALE)
                self._center_text(value, columns[i], columns[i + 1], row_y + 23, self.small)

    def _right_column(self) -> None:
        x, width = 1600, 780
        self._section("Body Score", x, 405, width)
        score = _number(self.report.body_score, 0)
        score_font = _font(100, bold=True)
        self.draw.text((x, 500), score, fill=BLUE, font=score_font)
        score_w = self.draw.textlength(score, font=score_font)
        self.draw.text((x + int(score_w), 565), "/100 Points", fill=DARK, font=_font(48, bold=True))
        self._multiline(
            "* The total score reflects the evaluated value of\nbody composition.\nA muscular person may exceed 100 points.",
            x,
            650,
            self.small,
        )
        self._section("Target to optimal weight", x, 835, width)
        targets = [
            ("Optimal Weight", self.report.optimal_weight),
            ("Target to optimal weight", self.report.weight_control),
            ("Target to optimal fat mass", self.report.fat_control),
            ("Target to optimal muscle mass", self.report.muscle_control),
        ]
        for row, (label, value) in enumerate(targets):
            yy = 920 + row * 64
            self.draw.text((x, yy), label, fill=DARK, font=self.small)
            self._right_text(f"{_number(value, 2)} kg", x + width, yy, self.small)
        self._section("Obesity Assessment", x, 1230, width)
        self._assessment("BMI", self.report.bmi.value, self.report.bmi.evaluation, x, 1325)
        self._assessment("Body Fat Percentage", self.report.body_fat_percentage.value, self.report.body_fat_percentage.evaluation, x, 1530)
        self._assessment("Obesity Assessment", self.report.obesity_degree, _obesity_evaluation(self.report.obesity_degree), x, 1770, suffix="%")
        self._body_type(x, 2000, width)
        self._other_indicators(x, 2910, width)

    def _assessment(self, label: str, value: float | None, selected: str, x: int, y: int, *, suffix: str = "") -> None:
        self.draw.text((x, y), f"{label}: {_number(value, 1)}{suffix}", fill=DARK, font=self.bold)
        for index, option in enumerate(("Low", "Standard", "High")):
            self._checkbox(x + index * 250, y + 78, option, option == selected)

    def _checkbox(self, x: int, y: int, label: str, checked: bool) -> None:
        self.draw.rounded_rectangle((x, y, x + 34, y + 34), 6, outline="#999999", width=4)
        if checked:
            self.draw.rounded_rectangle((x, y, x + 34, y + 34), 6, fill=BLUE)
            self.draw.line((x + 8, y + 17, x + 15, y + 25, x + 28, y + 8), fill="white", width=4)
        self.draw.text((x + 48, y - 1), label, fill=DARK, font=self.small)

    def _body_type(self, x: int, y: int, width: int) -> None:
        self._section("Body Type Assessment", x, y, width)
        top = y + 85
        cell_w, cell_h = width // 3, 170
        labels = ["Athletic", "Slightly\nAbove Range", "Overweight", "Muscular", "Healthy\nRange", "Elevated\nBody Fat", "Lean &\nMuscular", "Slim Build", "Hidden\nBody Fat"]
        selected = _body_type_index(self.report.body_type)
        for index, label in enumerate(labels):
            col, row = index % 3, index // 3
            left, upper = x + col * cell_w, top + row * cell_h
            fill = BLUE if index == selected else PALE
            color = "white" if index == selected else DARK
            self.draw.rectangle((left, upper, left + cell_w, upper + cell_h), fill=fill, outline="white")
            self._center_multiline(label, left, left + cell_w, upper + 55, self.small, color)
        self.draw.text((x - 5, top + 530), "18.5", fill=DARK, font=self.tiny)
        self.draw.text((x - 5, top + 190), "25", fill=DARK, font=self.tiny)
        self._center_text("Body Fat Percentage (%)", x, x + width, top + 3 * cell_h + 55, self.tiny)

    def _other_indicators(self, x: int, y: int, width: int) -> None:
        self._section("Other Indicators", x, y, width)
        values = [
            ("Visceral Fat", self.report.visceral_fat, ""),
            ("BMR", self.report.bmr, " kcal"),
            ("Fat-Free Mass", self.report.fat_free_mass, " kg"),
            ("Subcutaneous Fat", self.report.subcutaneous_fat, "%"),
            ("SMI", self.report.smi, " kg/m²"),
            ("Metabolic Age", self.report.metabolic_age, ""),
            ("WHR (Waist-to-Hip Ratio)", self.report.whr, ""),
        ]
        for row, (label, value, suffix) in enumerate(values):
            yy = y + 80 + row * 58
            self.draw.text((x, yy), label, fill=DARK, font=self.small)
            self._right_text(f"{_number(value, 2)}{suffix}", x + width, yy, self.small)

    def _center_text(self, text: str, left: int, right: int, y: int, font: ImageFont.FreeTypeFont, fill: str = DARK) -> None:
        width = self.draw.textlength(text, font=font)
        self.draw.text((left + (right - left - width) / 2, y), text, fill=fill, font=font)

    def _right_text(self, text: str, right: int, y: int, font: ImageFont.FreeTypeFont) -> None:
        self.draw.text((right - self.draw.textlength(text, font=font), y), text, fill=DARK, font=font)

    def _multiline(self, text: str, x: int, y: int, font: ImageFont.FreeTypeFont) -> None:
        self.draw.multiline_text((x, y), text, fill=DARK, font=font, spacing=5)

    def _center_multiline(self, text: str, left: int, right: int, y: int, font: ImageFont.FreeTypeFont, fill: str) -> None:
        box = self.draw.multiline_textbbox((0, 0), text, font=font, align="center")
        width = box[2] - box[0]
        self.draw.multiline_text((left + (right - left - width) / 2, y), text, fill=fill, font=font, align="center")


def _valid_vendor_pdf(content: bytes, content_type: str) -> bool:
    if content_type.split(";", 1)[0].strip().lower() != "application/pdf":
        return False
    if not content.startswith(b"%PDF-") or len(content) > MAX_VENDOR_PDF_BYTES:
        return False
    try:
        reader = PdfReader(BytesIO(content))
        if len(reader.pages) != 1:
            return False
        box = reader.pages[0].mediabox
        return abs(float(box.width) - 595) < 3 and abs(float(box.height) - 842) < 3
    except Exception:
        return False


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = BOLD_FONT if bold else FONT
    if path.exists():
        return ImageFont.truetype(str(path), size)
    # Pillow ships a scalable fallback, keeping report generation portable to
    # minimal Linux containers without adding an operating-system font package.
    return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size=size))


def _metric_value(metric: ReportMetric) -> str:
    return _number(metric.value, 2)


def _range(metric: ReportMetric) -> str:
    if metric.minimum is None or metric.maximum is None:
        return "Not available"
    return f"{metric.minimum:.2f}-{metric.maximum:.2f}"


def _number(value: float | int | None, decimals: int) -> str:
    if value is None:
        return "Not available"
    if decimals == 0:
        return str(int(round(float(value))))
    return f"{float(value):.{decimals}f}".rstrip("0").rstrip(".")


def _text(value: str | None) -> str:
    return value or "Not available"


def _impedance_values(values: Impedance) -> list[str]:
    return [_number(values.right_arm, 1), _number(values.left_arm, 1), _number(values.trunk, 1), _number(values.right_leg, 1), _number(values.left_leg, 1)]


def _obesity_evaluation(value: float | None) -> str:
    if value is None:
        return "Not available"
    if value < 90:
        return "Low"
    if value <= 110:
        return "Standard"
    return "High"


def _body_type_index(value: int | None) -> int:
    return {7: 1}.get(value, 4) if value is not None else 4


def _segment_evaluation(percentage: float | None, *, muscle: bool) -> str:
    if percentage is None:
        return "Not available"
    low, high = (90, 115) if muscle else (80, 160)
    if percentage < low:
        return "Low"
    if percentage > high:
        return "High"
    return "Standard"
