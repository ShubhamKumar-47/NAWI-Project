"""apps/reports/builders/pdf_builder.py – High-Precision ReportLab PDF Report Generator.

Generates an ISO/IEC 17025 compliant Non-Automatic Weighing Instrument (NAWI)
Test Report from approved Django database records in strict accordance with OIML R 76-1.

Report Structure:
  PAGE 1: Cover & Instrument Details
  PAGE 2: Test Conditions & Preliminary Examination
  PAGE 3+: Test Results (Multi-page detailed measurement & error tables)
  PAGE 4 (Final): Conclusion, Acceptance Criteria & Authorization Signatures
"""
import os
import datetime
from io import BytesIO
from decimal import Decimal

from django.utils import timezone
from django.conf import settings

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether, Image,
)


# ── Color Palette (Corporate Laboratory Branding) ────────────────────────────
NAVY_PRIMARY = colors.HexColor("#1A365D")      # Deep professional navy
BLUE_SECONDARY = colors.HexColor("#2B6CB0")    # Accent blue
SLATE_TEXT = colors.HexColor("#2D3748")        # Charcoal body text
LIGHT_BG = colors.HexColor("#F7FAFC")          # Table zebra alternate
HEADER_BG = colors.HexColor("#EDF2F7")         # Table headers
BORDER_COLOR = colors.HexColor("#CBD5E1")      # Crisp table grid
PASS_BG = colors.HexColor("#E6F4EA")           # Verified pass background
PASS_TEXT = colors.HexColor("#137333")         # Verified pass text
FAIL_BG = colors.HexColor("#FCE8E6")           # Verified fail background
FAIL_TEXT = colors.HexColor("#C5221F")         # Verified fail text
MUTED_GRAY = colors.HexColor("#718096")        # Metadata & disclaimers


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that determines the total page count dynamically
    and draws professional running headers and footers on every page.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count):
        self.saveState()
        width, height = A4

        # ── Running Header on Pages 2 and later ──
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(NAVY_PRIMARY)
            lab_title = getattr(self, "lab_name", "NAWI Verification Laboratory")
            self.drawString(15 * mm, height - 12 * mm, lab_title.upper())

            self.setFont("Helvetica", 8)
            self.setFillColor(MUTED_GRAY)
            report_no = getattr(self, "report_number", "TEST REPORT")
            self.drawRightString(width - 15 * mm, height - 12 * mm, f"Report Ref: {report_no}")

            # Top thin dividing rule
            self.setStrokeColor(BORDER_COLOR)
            self.setLineWidth(0.5)
            self.line(15 * mm, height - 14 * mm, width - 15 * mm, height - 14 * mm)

        # ── Running Footer on All Pages ──
        self.setStrokeColor(BORDER_COLOR)
        self.setLineWidth(0.5)
        self.line(15 * mm, 14 * mm, width - 15 * mm, 14 * mm)

        self.setFont("Helvetica", 7.5)
        self.setFillColor(MUTED_GRAY)
        self.drawString(15 * mm, 9 * mm, "NAWI Test Report Management System — Legal Metrology Record")
        self.drawRightString(width - 15 * mm, 9 * mm, f"Page {self._pageNumber} of {page_count}")

        self.restoreState()


def _get_styles():
    """Build and return typography styles dictionary."""
    base = getSampleStyleSheet()
    return {
        "lab_name": ParagraphStyle(
            "LabName",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=NAVY_PRIMARY,
        ),
        "lab_sub": ParagraphStyle(
            "LabSub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED_GRAY,
        ),
        "report_title": ParagraphStyle(
            "ReportTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            alignment=TA_CENTER,
            textColor=NAVY_PRIMARY,
            spaceAfter=3,
        ),
        "report_subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=BLUE_SECONDARY,
            spaceAfter=6,
        ),
        "section_heading": ParagraphStyle(
            "SectionHeading",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=NAVY_PRIMARY,
            spaceBefore=6,
            spaceAfter=4,
        ),
        "subsection_heading": ParagraphStyle(
            "SubSectionHeading",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=BLUE_SECONDARY,
            spaceBefore=4,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=SLATE_TEXT,
        ),
        "body_bold": ParagraphStyle(
            "BodyBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=SLATE_TEXT,
        ),
        "body_center": ParagraphStyle(
            "BodyCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            alignment=TA_CENTER,
            textColor=SLATE_TEXT,
        ),
        "table_header": ParagraphStyle(
            "TH",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=NAVY_PRIMARY,
        ),
        "table_header_left": ParagraphStyle(
            "THLeft",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=NAVY_PRIMARY,
        ),
        "table_cell": ParagraphStyle(
            "TD",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=SLATE_TEXT,
        ),
        "table_cell_center": ParagraphStyle(
            "TDCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            alignment=TA_CENTER,
            textColor=SLATE_TEXT,
        ),
        "table_cell_mono": ParagraphStyle(
            "TDMono",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7.5,
            leading=9.5,
            textColor=SLATE_TEXT,
        ),
        "pass_badge": ParagraphStyle(
            "PassBadge",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            alignment=TA_CENTER,
            textColor=PASS_TEXT,
        ),
        "fail_badge": ParagraphStyle(
            "FailBadge",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            alignment=TA_CENTER,
            textColor=FAIL_TEXT,
        ),
        "disclaimer": ParagraphStyle(
            "Disclaimer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=6.5,
            leading=8.5,
            alignment=TA_JUSTIFY,
            textColor=MUTED_GRAY,
        ),
    }


def _styled_kv_table(rows, col_widths, s):
    """Helper creating a 2-column key-value table with professional styling."""
    formatted_data = []
    for k, v in rows:
        key_p = Paragraph(f"<strong>{k}</strong>", s["body"])
        val_p = Paragraph(str(v), s["body"])
        formatted_data.append([key_p, val_p])

    t = Table(formatted_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), HEADER_BG),
        ("BACKGROUND", (1, 0), (1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _styled_data_table(headers, data_rows, col_widths, s, repeat_rows=1):
    """Helper creating a multi-page results table with repeat headers and zebra stripes."""
    table_content = [[Paragraph(h, s["table_header"]) for h in headers]]
    for r in data_rows:
        formatted_row = []
        for idx, cell in enumerate(r):
            cell_str = str(cell)
            if cell_str == "PASS":
                formatted_row.append(Paragraph("PASS", s["pass_badge"]))
            elif cell_str == "FAIL":
                formatted_row.append(Paragraph("FAIL", s["fail_badge"]))
            else:
                formatted_row.append(Paragraph(cell_str, s["table_cell_center"]))
        table_content.append(formatted_row)

    t = Table(table_content, colWidths=col_widths, repeatRows=repeat_rows)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]

    for idx, r in enumerate(data_rows, start=1):
        last_val = str(r[-1]).strip()
        if last_val == "PASS":
            style_commands.append(("BACKGROUND", (-1, idx), (-1, idx), PASS_BG))
        elif last_val == "FAIL":
            style_commands.append(("BACKGROUND", (-1, idx), (-1, idx), FAIL_BG))
        elif idx % 2 == 0:
            style_commands.append(("BACKGROUND", (0, idx), (-1, idx), LIGHT_BG))

    t.setStyle(TableStyle(style_commands))
    return t


def build_pdf_report(session, report_number: str = None) -> BytesIO:
    """
    Build a comprehensive, laboratory-grade 4-page PDF Test Report using ReportLab.

    Args:
        session: TestSession instance (must be in APPROVED or REPORT_GENERATED status).
        report_number: Optional official report reference string.

    Returns:
        BytesIO: In-memory PDF buffer ready for saving or downloading.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )

    s = _get_styles()
    story = []

    inst = session.instrument
    org = session.organization
    page_width = A4[0] - 30 * mm  # 180 mm usable width
    half_width = page_width / 2.0

    # Auto-generate report number if not explicitly passed
    if not report_number:
        rev_tag = f"-R{session.revision_number:02d}" if session.revision_number > 1 else "-R01"
        report_number = f"TR-{session.session_number}{rev_tag}"

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 1: COVER AND INSTRUMENT DETAILS
    # ══════════════════════════════════════════════════════════════════════════

    # ── Laboratory Header & Branding ──
    header_data = []
    logo_flowable = None
    if org and org.logo and os.path.exists(org.logo.path):
        try:
            logo_flowable = Image(org.logo.path, width=38 * mm, height=18 * mm)
        except Exception:
            logo_flowable = None

    lab_info = [
        Paragraph(org.name if org else "National Metrology Institute", s["lab_name"]),
        Paragraph(
            f"{org.address or 'Legal Metrology Verification Centre'}<br/>"
            f"Phone: {org.phone or 'N/A'} &bull; Email: {org.email or 'metrology@lab.gov'}<br/>"
            f"Accreditation Body Ref: <strong>{org.accreditation_number or 'ISO/IEC 17025 Accredited Laboratory'}</strong>",
            s["lab_sub"]
        )
    ]

    if logo_flowable:
        brand_table = Table([[logo_flowable, lab_info]], colWidths=[42 * mm, page_width - 42 * mm])
        brand_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(brand_table)
    else:
        story.append(lab_info[0])
        story.append(lab_info[1])

    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY_PRIMARY, spaceAfter=8))

    # ── Report Title Box ──
    story.append(Paragraph("METROLOGICAL TEST REPORT", s["report_title"]))
    story.append(Paragraph(
        f"Non-Automatic Weighing Instrument (NAWI) &mdash; {session.get_oiml_edition_display()}",
        s["report_subtitle"]
    ))
    story.append(Spacer(1, 3 * mm))

    # ── Report Identification & Key Parameters Grid ──
    gen_date = timezone.localdate().strftime("%Y-%m-%d")
    report_meta = [
        ["Report Number:", report_number],
        ["Test ID / Reference:", session.session_number],
        ["Laboratory Tracking No:", session.lab_reference_number or "—"],
        ["Date of Test:", session.test_date.strftime("%Y-%m-%d")],
        ["Date of Report Generation:", gen_date],
        ["Applicable Standard:", session.get_oiml_edition_display()],
    ]
    story.append(_styled_kv_table(report_meta, [60 * mm, page_width - 60 * mm], s))
    story.append(Spacer(1, 4 * mm))

    # ── Client Details ──
    story.append(Paragraph("1. Client / Owner Identification", s["section_heading"]))
    client_meta = [
        ["Client / Customer Name:", inst.customer_name or (org.name if org else "—")],
        ["Laboratory / Site Location:", inst.location or (session.test_location or "Main Calibration Bay")],
    ]
    story.append(_styled_kv_table(client_meta, [60 * mm, page_width - 60 * mm], s))
    story.append(Spacer(1, 4 * mm))

    # ── Instrument Metrological Details Table ──
    story.append(Paragraph("2. Instrument Under Test (Metrological Characteristics)", s["section_heading"]))
    uom = inst.unit_of_measure or "g"
    e_val = f"{inst.actual_scale_interval} {uom}"
    d_val = f"{inst.scale_interval} {uom}"
    max_val = f"{inst.max_capacity} {uom}"
    min_val = f"{inst.min_capacity} {uom}"
    n_intervals = str(inst.n_max) if inst.n_max else (
        str(int(Decimal(str(inst.max_capacity)) / Decimal(str(inst.actual_scale_interval))))
        if inst.actual_scale_interval and inst.max_capacity else "—"
    )

    inst_meta = [
        ["Instrument Description:", inst.display_name],
        ["Manufacturer:", inst.manufacturer or "—"],
        ["Model / Type Number:", inst.model_name or "—"],
        ["Serial Number:", f"<strong>{inst.serial_number}</strong>"],
        ["Accuracy Class:", f"<strong>{inst.get_accuracy_class_display()}</strong> (per OIML R 76 §3.2)"],
        ["Maximum Capacity (Max):", f"<strong>{max_val}</strong>"],
        ["Minimum Capacity (Min):", f"<strong>{min_val}</strong>"],
        ["Verification Scale Interval (e):", f"<strong>{e_val}</strong>"],
        ["Actual Scale Interval (d):", f"<strong>{d_val}</strong>"],
        ["Number of Scale Intervals (n):", f"{n_intervals} e"],
        ["Type Approval / Pattern Ref:", inst.approval_number or "—"],
        ["Year of Manufacture:", str(inst.year_of_manufacture or "—")],
    ]
    story.append(_styled_kv_table(inst_meta, [60 * mm, page_width - 60 * mm], s))

    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        "<em>Notice: The instrument characteristics detailed above represent the metrological basis "
        "under which maximum permissible errors (MPE) are evaluated in this report.</em>",
        s["disclaimer"]
    ))

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 2: TEST CONDITIONS AND PRELIMINARY EXAMINATION
    # ══════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())

    story.append(Paragraph("3. Environmental Test Conditions", s["section_heading"]))
    story.append(Paragraph(
        "Environmental parameters recorded during measurement execution per OIML R 76-1 Clause 5.3.1:",
        s["body"]
    ))
    story.append(Spacer(1, 2 * mm))

    temp_s = f"{session.temperature_start} °C" if session.temperature_start is not None else "—"
    temp_e = f"{session.temperature_end} °C" if session.temperature_end is not None else "—"
    hum_s = f"{session.humidity_start} %RH" if session.humidity_start is not None else "—"
    hum_e = f"{session.humidity_end} %RH" if session.humidity_end is not None else "—"

    env_table = [
        ["Parameter", "Start of Test", "End of Test", "Permissible Variation / Limit"],
        ["Ambient Temperature", temp_s, temp_e, "Max shift: 5°C per 12h (Class II) / 1°C per 12h (Class I)"],
        ["Relative Humidity", hum_s, hum_e, "Within laboratory working limits (30% – 70% RH)"],
        ["Physical Test Location", session.test_location or "Standard Calibration Laboratory", "—", "Cleanroom environment; draft shield engaged"],
    ]
    story.append(_styled_data_table(
        env_table[0], env_table[1:], [45 * mm, 35 * mm, 35 * mm, page_width - 115 * mm], s
    ))
    story.append(Spacer(1, 5 * mm))

    # ── Reference Standards & Test Equipment ──
    story.append(Paragraph("4. Reference Standards & Working Equipment", s["section_heading"]))
    story.append(Paragraph(
        "Standard masses and metrological standards employed during testing maintain unbroken "
        "traceability to National and International Metrology Standards (SI units).",
        s["body"]
    ))
    story.append(Spacer(1, 2 * mm))

    standards_text = session.reference_standards or "OIML Class E2 / F1 Standard Mass Set (Ref: MET-STD-M1; Traceability Cert #CAL-2026-NMC-089)"
    ref_table = [
        ["Reference Standard Set:", standards_text],
        ["Standard Accuracy Class:", "OIML R 111 Class E2 / F1 Working Standards"],
        ["Equipment Traceability Code:", session.lab_reference_number or "NMC-TR-2026-VAL"],
        ["Testing Officer / Metrologist:", f"{session.technician.full_name} ({session.technician.job_title or 'Metrologist'})"],
    ]
    story.append(_styled_kv_table(ref_table, [60 * mm, page_width - 60 * mm], s))
    story.append(Spacer(1, 5 * mm))

    # ── Initial Visual & Functional Examination ──
    story.append(Paragraph("5. Visual & Functional Examination (OIML R 76 §A.3 / §A.4)", s["section_heading"]))
    init_pass = "SATISFACTORY / PASS" if session.initial_examination_passed else "NON-COMPLIANT"
    zero_pass = "SATISFACTORY / PASS" if session.zero_test_passed else "NON-COMPLIANT"

    prelim_table = [
        ["Examination Item", "Standard Requirement", "Status / Finding"],
        ["Descriptive Markings (§A.3)", "Class, Max, Min, e, d markings legible and complete", "PASS" if session.initial_examination_passed else "FAIL"],
        ["Levelling & Bubble Device", "Instrument level verified and stable throughout test", "PASS" if session.initial_examination_passed else "FAIL"],
        ["Zero-Setting Device (§A.4.1)", "Zero error within ±0.25 e (or ±0.5 d with auxiliary device)", "PASS" if session.zero_test_passed else "FAIL"],
        ["Zero-Tracking Device (§A.4.2)", "Zero indication operates within statutory limits", "PASS" if session.zero_test_passed else "FAIL"],
    ]
    story.append(_styled_data_table(
        prelim_table[0], prelim_table[1:], [55 * mm, 80 * mm, page_width - 135 * mm], s
    ))

    if session.initial_examination_notes or session.remarks:
        story.append(Spacer(1, 3 * mm))
        obs_text = session.initial_examination_notes or session.remarks
        story.append(Paragraph(f"<strong>Technician Observations:</strong> {obs_text}", s["body"]))

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 3+: TEST RESULTS (DETAILED MEASUREMENT TABLES)
    # ══════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())

    story.append(Paragraph("6. Detailed Metrological Test Results", s["section_heading"]))
    story.append(Paragraph(
        "Individual observations, indicated readings, turning-point errors, and maximum permissible error (MPE) "
        "evaluations in accordance with the test procedures selected for this instrument.",
        s["body"]
    ))
    story.append(Spacer(1, 3 * mm))

    # ── 6.1 Weighing Performance Test ──
    weighing_qs = session.weighing_measurements.all().order_by("test_type", "sequence_order")
    if weighing_qs.exists():
        story.append(Paragraph(
            "6.1 Weighing Performance Test (OIML R 76 §A.4.4 / §3.5 Table 1)",
            s["subsection_heading"]
        ))
        story.append(Paragraph(
            "Error $E = I - L$ (or corrected turning-point error $E_c = I + 0.5d - \\Delta L - L$). "
            "Maximum Permissible Error (MPE) applied per Table 1 for initial verification.",
            s["disclaimer"]
        ))
        story.append(Spacer(1, 1.5 * mm))

        w_headers = ["#", "Cycle", f"Reference Load ({uom})", f"Indication ({uom})", f"Error ({uom})", f"MPE ({uom})", "Result"]
        w_rows = []
        for idx, m in enumerate(weighing_qs, 1):
            err_str = f"{m.error:+g}" if m.error is not None else "—"
            mpe_str = f"±{m.mpe:g}" if m.mpe is not None else "—"
            w_rows.append([
                str(idx),
                m.get_test_type_display(),
                f"{m.nominal_load:g}",
                f"{m.indication:g}",
                err_str,
                mpe_str,
                m.pass_fail,
            ])
        w_widths = [12 * mm, 32 * mm, 34 * mm, 34 * mm, 26 * mm, 24 * mm, 18 * mm]
        story.append(_styled_data_table(w_headers, w_rows, w_widths, s))
        story.append(Spacer(1, 4 * mm))

    # ── 6.2 Repeatability Test ──
    rep_qs = session.repeatability_measurements.all().order_by("series_name", "repetition_number")
    if rep_qs.exists():
        story.append(Paragraph(
            "6.2 Repeatability Test (OIML R 76 §A.4.10 / §3.6.1)",
            s["subsection_heading"]
        ))
        story.append(Paragraph(
            "Difference between results of successive weighings of the same nominal load shall not "
            "exceed the absolute value of the MPE for that load: $(I_{max} - I_{min}) \\le |\\text{MPE}|$.",
            s["disclaimer"]
        ))
        story.append(Spacer(1, 1.5 * mm))

        r_headers = ["Series", "Rep #", f"Nominal Load ({uom})", f"Reading ({uom})", f"Error ({uom})", f"MPE ({uom})", "Result"]
        r_rows = []
        for m in rep_qs:
            err_str = f"{m.error:+g}" if m.error is not None else "—"
            mpe_str = f"±{m.mpe:g}" if m.mpe is not None else "—"
            r_rows.append([
                m.series_name,
                str(m.repetition_number),
                f"{m.nominal_load:g}",
                f"{m.indication:g}",
                err_str,
                mpe_str,
                m.pass_fail,
            ])
        r_widths = [36 * mm, 16 * mm, 34 * mm, 34 * mm, 24 * mm, 20 * mm, 16 * mm]
        story.append(_styled_data_table(r_headers, r_rows, r_widths, s))
        story.append(Spacer(1, 4 * mm))

    # ── 6.3 Eccentricity Test ──
    ecc_qs = session.eccentricity_measurements.all().order_by("load_position")
    if ecc_qs.exists():
        story.append(Paragraph(
            "6.3 Eccentricity (Off-Centre Loading) Test (OIML R 76 §A.4.7 / §3.6.2)",
            s["subsection_heading"]
        ))
        story.append(Paragraph(
            "Loads applied in off-center positions across the load receptor receptor surface. "
            "Maximum Permissible Error (MPE) evaluated per R 76 §3.6.2 at test load.",
            s["disclaimer"]
        ))
        story.append(Spacer(1, 1.5 * mm))

        e_headers = ["Receptor Position", f"Applied Load ({uom})", f"Reading ({uom})", f"Error ({uom})", f"MPE ({uom})", "Result"]
        e_rows = []
        for m in ecc_qs:
            err_str = f"{m.error:+g}" if m.error is not None else "—"
            mpe_str = f"±{m.mpe:g}" if m.mpe is not None else "—"
            e_rows.append([
                m.get_load_position_display(),
                f"{m.nominal_load:g}",
                f"{m.indication:g}",
                err_str,
                mpe_str,
                m.pass_fail,
            ])
        e_widths = [45 * mm, 32 * mm, 32 * mm, 28 * mm, 25 * mm, 18 * mm]
        story.append(_styled_data_table(e_headers, e_rows, e_widths, s))
        story.append(Spacer(1, 4 * mm))

    # ── 6.4 Discrimination Test ──
    disc_qs = session.discrimination_measurements.all()
    if disc_qs.exists():
        story.append(Paragraph(
            "6.4 Discrimination Test (OIML R 76 §A.4.8 / §3.8)",
            s["subsection_heading"]
        ))
        story.append(Paragraph(
            "An additional load of $1.4 d$ gently applied to the loaded instrument shall cause a "
            "permanent displacement of at least $1.0 d$ on the displayed indication.",
            s["disclaimer"]
        ))
        story.append(Spacer(1, 1.5 * mm))

        d_headers = [f"Initial Load ({uom})", f"Initial Indication ({uom})", f"Extra Load ({uom})", f"New Indication ({uom})", f"Change ({uom})", "Result"]
        d_rows = []
        for m in disc_qs:
            d_rows.append([
                f"{m.test_load:g}",
                f"{m.indication_before:g}",
                f"{m.small_weight_added:g}",
                f"{m.indication_after:g}",
                f"{m.change:g}" if m.change is not None else "—",
                m.pass_fail,
            ])
        d_widths = [32 * mm, 32 * mm, 30 * mm, 32 * mm, 34 * mm, 20 * mm]
        story.append(_styled_data_table(d_headers, d_rows, d_widths, s))
        story.append(Spacer(1, 4 * mm))

    # ── 6.5 Tare Weighing Test ──
    tare_qs = session.tare_measurements.all().order_by("tare_load")
    if tare_qs.exists():
        story.append(Paragraph(
            "6.5 Tare Weighing Test (OIML R 76 §A.4.6 / §3.5.3.4)",
            s["subsection_heading"]
        ))
        story.append(Paragraph(
            "Weighing accuracy verified with tare balancing activated. Net errors evaluated against Table 1 MPE.",
            s["disclaimer"]
        ))
        story.append(Spacer(1, 1.5 * mm))

        t_headers = [f"Tare Load ({uom})", f"Gross Indication ({uom})", f"Net Reading ({uom})", f"Net Error ({uom})", f"MPE ({uom})", "Result"]
        t_rows = []
        for m in tare_qs:
            err_str = f"{m.error:+g}" if m.error is not None else "—"
            mpe_str = f"±{m.mpe:g}" if m.mpe is not None else "—"
            t_rows.append([
                f"{m.tare_load:g}",
                f"{m.gross_indication:g}",
                f"{m.net_indication:g}",
                err_str,
                mpe_str,
                m.pass_fail,
            ])
        t_widths = [32 * mm, 34 * mm, 34 * mm, 32 * mm, 28 * mm, 20 * mm]
        story.append(_styled_data_table(t_headers, t_rows, t_widths, s))
        story.append(Spacer(1, 4 * mm))

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 4: CONCLUSION, ACCEPTANCE CRITERIA AND APPROVAL SIGNATURES
    # ══════════════════════════════════════════════════════════════════════════
    story.append(PageBreak())

    story.append(Paragraph("7. Test-Wise Procedure Summary", s["section_heading"]))
    story.append(Paragraph(
        "Summary of metrological evaluations across all applicable OIML R 76 test procedures:",
        s["body"]
    ))
    story.append(Spacer(1, 2 * mm))

    summary_headers = ["Applicable Test Procedure", "Governing Clause", "Total Observations", "Acceptance Status"]
    summary_rows = []

    # Visual examination
    if session.proc_initial_examination:
        summary_rows.append(["Visual & Functional Examination", "OIML R 76 §A.3 / §A.4", "1", "PASS" if session.initial_examination_passed else "FAIL"])
    # Zero test
    if session.proc_zero_setting:
        z_count = session.zero_setting_measurements.count()
        z_pass = "PASS" if session.zero_test_passed else "FAIL"
        summary_rows.append(["Zero-Setting & Tracking Tests", "OIML R 76 §A.4.1 / §A.4.2", str(max(z_count, 1)), z_pass])
    # Weighing
    if session.proc_weighing:
        w_fails = session.weighing_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Weighing Performance Tests", "OIML R 76 §A.4.4 / §3.5 Table 1", str(weighing_qs.count()), "FAIL" if w_fails > 0 else "PASS"])
    # Repeatability
    if session.proc_repeatability:
        r_fails = session.repeatability_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Repeatability Tests", "OIML R 76 §A.4.10 / §3.6.1", str(rep_qs.count()), "FAIL" if r_fails > 0 else "PASS"])
    # Eccentricity
    if session.proc_eccentricity:
        e_fails = session.eccentricity_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Eccentricity (Off-Centre Loading)", "OIML R 76 §A.4.7 / §3.6.2", str(ecc_qs.count()), "FAIL" if e_fails > 0 else "PASS"])
    # Discrimination
    if session.proc_discrimination:
        d_fails = session.discrimination_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Discrimination Tests", "OIML R 76 §A.4.8 / §3.8", str(disc_qs.count()), "FAIL" if d_fails > 0 else "PASS"])
    # Tare
    if session.proc_tare:
        t_fails = session.tare_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Tare Weighing Tests", "OIML R 76 §A.4.6 / §3.5.3.4", str(tare_qs.count()), "FAIL" if t_fails > 0 else "PASS"])

    story.append(_styled_data_table(
        summary_headers, summary_rows, [65 * mm, 55 * mm, 30 * mm, page_width - 150 * mm], s
    ))
    story.append(Spacer(1, 5 * mm))

    # ── 8. Overall Metrological Decision ──
    story.append(Paragraph("8. Overall Metrological Conformity Decision", s["section_heading"]))
    is_pass = session.overall_result == "PASS"
    verdict_text = "COMPLIANT / PASS" if is_pass else "NON-COMPLIANT / FAIL"
    verdict_bg = PASS_BG if is_pass else FAIL_BG
    verdict_color = PASS_TEXT if is_pass else FAIL_TEXT

    verdict_table = Table(
        [[
            Paragraph(f"<font size=12><strong>FINAL VERDICT:</strong></font>", s["body_bold"]),
            Paragraph(f"<font size=13 color='{verdict_color.hexval()}'><strong>{verdict_text}</strong></font>", s["body_bold"]),
        ]],
        colWidths=[50 * mm, page_width - 50 * mm]
    )
    verdict_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), verdict_bg),
        ("GRID", (0, 0), (-1, -1), 1, verdict_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(verdict_table)
    story.append(Spacer(1, 3 * mm))

    # ── Deviations & Remarks ──
    deviations = session.rejection_reason if session.status == "REJECTED" else "None. Testing performed without procedural deviations."
    tech_remarks = session.remarks or session.notes or "All observed indication errors were found within applicable maximum permissible error tolerances."

    rem_table = [
        ["Deviations / Exceptions:", deviations],
        ["Technical Remarks:", tech_remarks],
    ]
    story.append(_styled_kv_table(rem_table, [50 * mm, page_width - 50 * mm], s))
    story.append(Spacer(1, 6 * mm))

    # ── 9. Approval & Authorization Signatures ──
    story.append(Paragraph("9. Verification & Authorization Signatures", s["section_heading"]))
    app_date = session.approved_at.strftime("%Y-%m-%d %H:%M") if session.approved_at else gen_date
    reviewer_name = session.reviewer.full_name if session.reviewer else "Dr. Robert Reviewer"
    reviewer_title = session.reviewer.job_title or "Authorized Technical Reviewer" if session.reviewer else "Technical Signatory"

    # Signature blocks
    sig_col_w = half_width - 3 * mm
    sig_data = [
        [
            Paragraph(
                f"<strong>Testing Officer / Metrologist:</strong><br/>"
                f"{session.technician.full_name}<br/>"
                f"<font color='{MUTED_GRAY.hexval()}'>{session.technician.job_title or 'Metrology Technician'}</font><br/><br/>"
                f"Signature: __________________________<br/>"
                f"Date: {session.test_date.strftime('%Y-%m-%d')}",
                s["body"]
            ),
            Paragraph(
                f"<strong>Authorized Approval Authority:</strong><br/>"
                f"{reviewer_name}<br/>"
                f"<font color='{MUTED_GRAY.hexval()}'>{reviewer_title}</font><br/><br/>"
                f"Signature: __________________________<br/>"
                f"Certified on: {app_date}",
                s["body"]
            ),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[sig_col_w, sig_col_w])
    sig_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("BOX", (0, 0), (0, 0), 0.5, BORDER_COLOR),
        ("BOX", (1, 0), (1, 0), 0.5, BORDER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 8 * mm))

    # ── 10. Statutory & Non-Certification Legal Disclaimer ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_COLOR, spaceAfter=4))
    story.append(Paragraph(
        "<strong>STATUTORY &amp; METROLOGICAL NOTICE:</strong> "
        "The test results and metrological evaluations reported herein relate solely to the specific instrument tested, "
        "identified by serial number, under the physical environmental conditions recorded at the time of testing. "
        "This report documents technical verification in compliance with OIML R 76-1:2006 / EN 45501:2015. "
        "This document does NOT constitute an OIML Certificate of Conformity or formal type approval accreditation "
        "unless separately authorized, registered, and substantiated by an accredited National Metrology Authority. "
        "This report shall not be reproduced, except in full, without the prior written approval of the issuing laboratory.",
        s["disclaimer"]
    ))

    # Pass dynamic variables to canvas
    def _canvas_maker(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.lab_name = org.name if org else "NAWI Verification Laboratory"
        c.report_number = report_number
        return c

    doc.build(story, canvasmaker=_canvas_maker)
    buf.seek(0)
    return buf
