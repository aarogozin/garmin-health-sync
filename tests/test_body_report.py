from datetime import datetime
from io import BytesIO

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from garmin_sync import body_report
from garmin_sync.body_report import ReportProvider, _valid_vendor_pdf, body_composition_pdf
from garmin_sync.models import BERLIN
from garmin_sync.renpho_report import normalize_report


def test_body_composition_pdf_contains_normalized_values() -> None:
    report = normalize_report(
        {
            "reportId": "P26081501",
            "gender": 1,
            "measureAge": 37,
            "height": 186,
            "weight": 89.5,
            "weightMin": 64.7,
            "weightMax": 87.5,
            "bodyfat": 18.2,
            "bmi": 25.9,
            "water": 59.1,
            "bone": 5,
            "protein": 16,
            "sinew": 68,
            "smmMass": 42,
        },
        datetime(2026, 8, 15, 8, 30, tzinfo=BERLIN),
    )
    content = body_composition_pdf(report)
    reader = PdfReader(BytesIO(content))
    page = reader.pages[0]
    images = list((page["/Resources"].get("/XObject") or {}).values())

    assert len(reader.pages) == 1
    assert float(page.mediabox.width) == pytest.approx(595.28, abs=1)
    assert len(images) == 1
    image = images[0].get_object()
    assert image["/Width"] == 2480
    assert image["/Height"] == 3508


def test_report_font_falls_back_when_macos_fonts_are_unavailable(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(body_report, "FONT", tmp_path / "missing-regular.ttf")
    monkeypatch.setattr(body_report, "BOLD_FONT", tmp_path / "missing-bold.ttf")
    assert body_report._font(24).getbbox("Portable report") is not None


def test_provider_prefers_a_valid_vendor_pdf() -> None:
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.showPage()
    pdf.save()

    class Vendor:
        def fetch(self, report_id: str) -> tuple[bytes, str]:
            assert report_id == "P1"
            return output.getvalue(), "application/pdf"

    report = normalize_report(
        {"reportId": "P1", "weight": 80}, datetime(2026, 8, 15, tzinfo=BERLIN)
    )
    document = ReportProvider(Vendor()).resolve(report)
    assert document.source == "Original RENPHO"
    assert document.content == output.getvalue()


def test_provider_rejects_a_malformed_vendor_response() -> None:
    class Vendor:
        def fetch(self, report_id: str) -> tuple[bytes, str]:
            return b"not a PDF", "application/pdf"

    report = normalize_report(
        {"reportId": "P1", "weight": 80}, datetime(2026, 8, 15, tzinfo=BERLIN)
    )
    document = ReportProvider(Vendor()).resolve(report)
    assert document.source == "Rendered from RENPHO data"
    assert document.content.startswith(b"%PDF-")


def test_vendor_pdf_validation_rejects_wrong_type_and_oversized_body() -> None:
    assert not _valid_vendor_pdf(b"%PDF-1.4", "text/html")
    assert not _valid_vendor_pdf(b"%PDF-" + b"0" * (10 * 1024 * 1024), "application/pdf")
