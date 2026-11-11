"""apps/reports/builders/docx_builder.py – High-Precision Word (.docx) Report Generator.

Generates an editable, ISO/IEC 17025 compliant Non-Automatic Weighing Instrument (NAWI)
Test Report from approved Django database records in strict accordance with OIML R 76-1.

Report Structure:
  PAGE 1: Cover Page & Instrument Metrological Characteristics
  PAGE 2: Test Conditions & Preliminary Visual/Zero Examination
  PAGE 3+: Test Results (Multi-page detailed measurement & calculation error tables)
  PAGE 4 (Final): Conclusion, Acceptance Criteria, Signatures & Legal Disclaimer
"""
import os
import re
import datetime
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from django.conf import settings

import docx
from docx.shared import Inches, Pt, RGBColor, Mm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn


# ── Color Palette (Matching PDF Laboratory Branding) ─────────────────────────
NAVY_PRIMARY = RGBColor(0x1A, 0x36, 0x5D)      # #1A365D - Deep professional navy
BLUE_SECONDARY = RGBColor(0x2B, 0x6C, 0xB0)    # #2B6CB0 - Accent blue
SLATE_TEXT = RGBColor(0x2D, 0x37, 0x48)        # #2D3748 - Charcoal body text
MUTED_GRAY = RGBColor(0x71, 0x80, 0x96)        # #718096 - Metadata & disclaimers
PASS_GREEN = RGBColor(0x13, 0x73, 0x33)        # #137333 - Verified pass text
FAIL_RED = RGBColor(0xC5, 0x22, 0x1F)          # #C5221F - Verified fail text
WHITE_TEXT = RGBColor(0xFF, 0xFF, 0xFF)

HEX_HEADER_BG = "EDF2F7"                       # Table headers light gray-blue
HEX_ZEBRA_BG = "F7FAFC"                        # Table zebra alternate row
HEX_BORDER = "CBD5E1"                          # Crisp table border
HEX_PASS_BG = "E6F4EA"                         # Verified pass green tint
HEX_FAIL_BG = "FCE8E6"                         # Verified fail red tint
HEX_NAVY = "1A365D"                            # Navy fill
HEX_LIGHT_GRAY = "F1F5F9"                      # Light container fill


# ── Low-Level XML Manipulation Helpers ───────────────────────────────────────

def set_cell_background(cell, hex_color: str):
    """Set the shading background color of a Word table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    for child in list(tcPr):
        if child.tag.endswith("shd"):
            tcPr.remove(child)
    tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>'))


def set_table_borders(table, color=HEX_BORDER, sz="4", val="single"):
    """Apply crisp, uniform grid borders to a Word table."""
    tblPr = table._tbl.tblPr
    for child in list(tblPr):
        if child.tag.endswith("tblBorders"):
            tblPr.remove(child)
    borders_xml = f"""<w:tblBorders {nsdecls("w")}>
        <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:left w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:right w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:insideV w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
    </w:tblBorders>"""
    tblPr.append(parse_xml(borders_xml))


def set_table_margins(table, top=100, bottom=100, left=140, right=140):
    """Set inner cell padding/margins on a table in dxa (1 pt = 20 dxa)."""
    tblPr = table._tbl.tblPr
    for child in list(tblPr):
        if child.tag.endswith("tblCellMar"):
            tblPr.remove(child)
    mar_xml = f"""<w:tblCellMar {nsdecls("w")}>
        <w:top w:w="{top}" w:type="dxa"/>
        <w:bottom w:w="{bottom}" w:type="dxa"/>
        <w:left w:w="{left}" w:type="dxa"/>
        <w:right w:w="{right}" w:type="dxa"/>
    </w:tblCellMar>"""
    tblPr.append(parse_xml(mar_xml))


def set_row_header(row):
    """Mark a table row as a repeating header across page splits (<w:tblHeader/>)."""
    trPr = row._tr.get_or_add_trPr()
    trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))


def set_row_cant_split(row):
    """Prevent a table row from splitting across a page boundary (<w:cantSplit/>)."""
    trPr = row._tr.get_or_add_trPr()
    trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))


def add_field(paragraph, field_name: str):
    """Append a dynamic Word field (such as PAGE or NUMPAGES) to a paragraph."""
    fldSimple = OxmlElement("w:fldSimple")
    fldSimple.set(qn("w:instr"), field_name)
    paragraph._p.append(fldSimple)


def _format_cell_text(cell, text: str, default_size=8.0, default_color=SLATE_TEXT,
                       bold=False, italic=False, alignment=WD_ALIGN_PARAGRAPH.LEFT):
    """Format cell text supporting basic inline <strong> tags, newlines, and colors."""
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = cell.paragraphs[0]
    p.text = ""
    p.alignment = alignment
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = Pt(default_size + 3)

    raw_text = str(text or "")
    clean_text = raw_text.replace("<br/>", "\n").replace("<br>", "\n").replace("&mdash;", "—")

    # Split on <strong> tags
    tokens = re.split(r"(<strong>.*?</strong>|<em>.*?</em>)", clean_text)
    for token in tokens:
        if not token:
            continue
        if token.startswith("<strong>") and token.endswith("</strong>"):
            inner = token[8:-9]
            run = p.add_run(inner)
            run.font.name = "Calibri"
            run.font.size = Pt(default_size)
            run.font.bold = True
            run.font.color.rgb = default_color
        elif token.startswith("<em>") and token.endswith("</em>"):
            inner = token[4:-5]
            run = p.add_run(inner)
            run.font.name = "Calibri"
            run.font.size = Pt(default_size)
            run.font.italic = True
            run.font.color.rgb = default_color
        else:
            run = p.add_run(token)
            run.font.name = "Calibri"
            run.font.size = Pt(default_size)
            run.font.bold = bold
            run.font.italic = italic
            run.font.color.rgb = default_color


# ── Reusable Component Functions ─────────────────────────────────────────────

def add_document_heading(doc, text: str, level=1, space_before=14, space_after=6, color=None):
    """
    Reusable heading component with metrological corporate hierarchy.
    Levels:
      1: Major Section (13.5 pt, Bold, Navy #1A365D)
      2: Subsection (11 pt, Bold, Navy #1A365D)
      3: Sub-subsection (9.5 pt, Bold, Accent Blue #2B6CB0)
    """
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.keep_with_next = True

    run = p.add_run(text)
    run.font.name = "Calibri"
    run.font.bold = True

    if level == 1:
        run.font.size = Pt(13.5)
        run.font.color.rgb = color or NAVY_PRIMARY
        # Add subtle bottom accent rule under Level 1 headings
        pPr = p._p.get_or_add_pPr()
        bdr_xml = f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="3" w:color="{HEX_NAVY}"/></w:pBdr>'
        pPr.append(parse_xml(bdr_xml))
    elif level == 2:
        run.font.size = Pt(11.0)
        run.font.color.rgb = color or NAVY_PRIMARY
    else:
        run.font.size = Pt(9.5)
        run.font.color.rgb = color or BLUE_SECONDARY

    return p


def add_paragraph(doc, text: str = "", bold=False, italic=False, font_size=9.0,
                  color=SLATE_TEXT, space_before=0, space_after=6,
                  alignment=WD_ALIGN_PARAGRAPH.LEFT):
    """Reusable paragraph component with typography control."""
    p = doc.add_paragraph()
    p.alignment = alignment
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = Pt(font_size + 4)

    if text:
        tokens = re.split(r"(<strong>.*?</strong>|<em>.*?</em>)", text)
        for token in tokens:
            if not token:
                continue
            if token.startswith("<strong>") and token.endswith("</strong>"):
                run = p.add_run(token[8:-9])
                run.font.name = "Calibri"
                run.font.size = Pt(font_size)
                run.font.bold = True
                run.font.color.rgb = color
            elif token.startswith("<em>") and token.endswith("</em>"):
                run = p.add_run(token[4:-5])
                run.font.name = "Calibri"
                run.font.size = Pt(font_size)
                run.font.italic = True
                run.font.color.rgb = color
            else:
                run = p.add_run(token)
                run.font.name = "Calibri"
                run.font.size = Pt(font_size)
                run.font.bold = bold
                run.font.italic = italic
                run.font.color.rgb = color
    return p


def create_table(doc, num_rows: int, num_cols: int, col_widths=None, alignment=WD_TABLE_ALIGNMENT.CENTER):
    """Reusable base table builder with standard borders, cell margins, and alignments."""
    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.alignment = alignment
    set_table_borders(table, color=HEX_BORDER, sz="4", val="single")
    set_table_margins(table, top=100, bottom=100, left=140, right=140)

    if col_widths and len(col_widths) == num_cols:
        for c_idx, width in enumerate(col_widths):
            table.columns[c_idx].width = width
            for row in table.rows:
                row.cells[c_idx].width = width

    return table


def add_kv_table(doc, data_tuples, col_widths=None):
    """
    Reusable 2-column key-value specification table.
    Column 0: Shaded label (#EDF2F7), bold text.
    Column 1: Value cell with white background.
    """
    if not col_widths:
        col_widths = [Mm(55), Mm(125)]

    table = create_table(doc, len(data_tuples), 2, col_widths=col_widths)
    for r_idx, (k, v) in enumerate(data_tuples):
        row = table.rows[r_idx]
        set_row_cant_split(row)

        # Key cell
        c0 = row.cells[0]
        set_cell_background(c0, HEX_HEADER_BG)
        _format_cell_text(c0, k, default_size=8.0, default_color=NAVY_PRIMARY, bold=True)

        # Value cell
        c1 = row.cells[1]
        set_cell_background(c1, "FFFFFF")
        _format_cell_text(c1, v, default_size=8.0, default_color=SLATE_TEXT)

    # Add small spacing after table
    p_sp = doc.add_paragraph()
    p_sp.paragraph_format.space_before = Pt(0)
    p_sp.paragraph_format.space_after = Pt(4)
    return table


def add_data_table(doc, headers, data_rows, col_widths=None, repeat_header=True):
    """
    Reusable multi-page results table with:
    - Repeating header row on page split (<w:tblHeader/>)
    - Anti-split rows (<w:cantSplit/>)
    - Alternating row zebra shading (#F7FAFC)
    - PASS (#E6F4EA) and FAIL (#FCE8E6) badge highlighting
    """
    num_rows = len(data_rows) + 1
    num_cols = len(headers)
    table = create_table(doc, num_rows, num_cols, col_widths=col_widths)

    # ── Header Row ──
    h_row = table.rows[0]
    if repeat_header:
        set_row_header(h_row)
    set_row_cant_split(h_row)

    for c_idx, title in enumerate(headers):
        cell = h_row.cells[c_idx]
        set_cell_background(cell, HEX_HEADER_BG)
        align = WD_ALIGN_PARAGRAPH.CENTER if c_idx > 0 else WD_ALIGN_PARAGRAPH.LEFT
        _format_cell_text(cell, title, default_size=8.0, default_color=NAVY_PRIMARY, bold=True, alignment=align)

    # ── Data Rows ──
    for r_idx, r_data in enumerate(data_rows, start=1):
        row = table.rows[r_idx]
        set_row_cant_split(row)
        is_zebra = (r_idx % 2 == 0)
        row_bg = HEX_ZEBRA_BG if is_zebra else "FFFFFF"

        for c_idx, val in enumerate(r_data):
            cell = row.cells[c_idx]
            val_str = str(val).strip()

            # Result badge styling
            if val_str == "PASS":
                set_cell_background(cell, HEX_PASS_BG)
                _format_cell_text(cell, "PASS", default_size=8.0, default_color=PASS_GREEN, bold=True, alignment=WD_ALIGN_PARAGRAPH.CENTER)
            elif val_str == "FAIL":
                set_cell_background(cell, HEX_FAIL_BG)
                _format_cell_text(cell, "FAIL", default_size=8.0, default_color=FAIL_RED, bold=True, alignment=WD_ALIGN_PARAGRAPH.CENTER)
            else:
                set_cell_background(cell, row_bg)
                align = WD_ALIGN_PARAGRAPH.CENTER if c_idx > 0 else WD_ALIGN_PARAGRAPH.LEFT
                _format_cell_text(cell, val_str, default_size=7.5, default_color=SLATE_TEXT, alignment=align)

    p_sp = doc.add_paragraph()
    p_sp.paragraph_format.space_before = Pt(0)
    p_sp.paragraph_format.space_after = Pt(4)
    return table


def setup_report_header(section, lab_name: str, report_number: str):
    """
    Reusable running header component for page 2 and subsequent pages:
    - Left: Laboratory Name (Bold, Navy)
    - Right: Report Ref Number (Muted Gray)
    - Bottom dividing rule
    """
    header = section.header
    p = header.paragraphs[0]
    p.text = ""
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)

    # Add tab stops for right alignment
    p.paragraph_format.tab_stops.add_tab_stop(Mm(180), docx.enum.text.WD_TAB_ALIGNMENT.RIGHT)

    run_lab = p.add_run(lab_name.upper())
    run_lab.font.name = "Calibri"
    run_lab.font.size = Pt(8.0)
    run_lab.font.bold = True
    run_lab.font.color.rgb = NAVY_PRIMARY

    p.add_run("\t")

    run_ref = p.add_run(f"Report Ref: {report_number}")
    run_ref.font.name = "Calibri"
    run_ref.font.size = Pt(8.0)
    run_ref.font.color.rgb = MUTED_GRAY

    # Border rule under header
    pPr = p._p.get_or_add_pPr()
    bdr_xml = f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="4" w:space="4" w:color="{HEX_BORDER}"/></w:pBdr>'
    pPr.append(parse_xml(bdr_xml))


def setup_report_footer(section, system_text="NAWI Test Report Management System — Legal Metrology Record"):
    """
    Reusable running footer component with dynamic 'Page X of Y' fields:
    - Top dividing rule
    - Left: System accreditation title
    - Right: 'Page <PAGE> of <NUMPAGES>' dynamic Word field
    """
    footer = section.footer
    p = footer.paragraphs[0]
    p.text = ""
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(0)

    # Add tab stop at right margin
    p.paragraph_format.tab_stops.add_tab_stop(Mm(180), docx.enum.text.WD_TAB_ALIGNMENT.RIGHT)

    # Top border rule above footer
    pPr = p._p.get_or_add_pPr()
    bdr_xml = f'<w:pBdr {nsdecls("w")}><w:top w:val="single" w:sz="4" w:space="4" w:color="{HEX_BORDER}"/></w:pBdr>'
    pPr.append(parse_xml(bdr_xml))

    # Left text
    run_sys = p.add_run(system_text)
    run_sys.font.name = "Calibri"
    run_sys.font.size = Pt(7.5)
    run_sys.font.color.rgb = MUTED_GRAY

    p.add_run("\t")

    # Right page numbering
    run_pg = p.add_run("Page ")
    run_pg.font.name = "Calibri"
    run_pg.font.size = Pt(7.5)
    run_pg.font.color.rgb = MUTED_GRAY

    add_field(p, "PAGE")

    run_of = p.add_run(" of ")
    run_of.font.name = "Calibri"
    run_of.font.size = Pt(7.5)
    run_of.font.color.rgb = MUTED_GRAY

    add_field(p, "NUMPAGES")


def add_signature_block(doc, technician, reviewer, test_date: str, approval_date: str):
    """
    Reusable dual-signatory verification block:
    Left: Testing Officer (Metrologist)
    Right: Authorized Approval Authority (Reviewer)
    """
    col_w = Mm(88)
    table = create_table(doc, 1, 2, col_widths=[col_w, col_w])
    row = table.rows[0]
    set_row_cant_split(row)

    tech_name = technician.full_name if technician else "Laboratory Operator"
    tech_title = technician.job_title or "Metrology Technician" if technician else "Testing Officer"

    rev_name = reviewer.full_name if reviewer else "Dr. Robert Reviewer"
    rev_title = reviewer.job_title or "Authorized Technical Reviewer" if reviewer else "Technical Signatory"

    # Cell 0: Operator
    c0 = row.cells[0]
    set_cell_background(c0, HEX_ZEBRA_BG)
    _format_cell_text(
        c0,
        f"<strong>Testing Officer / Metrologist:</strong><br/>"
        f"{tech_name}<br/>"
        f"<em>{tech_title}</em><br/><br/>"
        f"Signature: __________________________<br/>"
        f"Date: {test_date}",
        default_size=8.0,
        default_color=SLATE_TEXT
    )

    # Cell 1: Reviewer
    c1 = row.cells[1]
    set_cell_background(c1, HEX_ZEBRA_BG)
    _format_cell_text(
        c1,
        f"<strong>Authorized Approval Authority:</strong><br/>"
        f"{rev_name}<br/>"
        f"<em>{rev_title}</em><br/><br/>"
        f"Signature: __________________________<br/>"
        f"Certified on: {approval_date}",
        default_size=8.0,
        default_color=SLATE_TEXT
    )

    p_sp = doc.add_paragraph()
    p_sp.paragraph_format.space_before = Pt(0)
    p_sp.paragraph_format.space_after = Pt(6)
    return table


# ── Main Document Construction Engine ────────────────────────────────────────

def build_docx_report(session, report_number: str = None) -> BytesIO:
    """
    Build an official, editable Microsoft Word (.docx) test report
    from approved TestSession records using python-docx.

    Args:
        session: TestSession instance (must be in APPROVED or REPORT_GENERATED status).
        report_number: Optional official report reference string.

    Returns:
        BytesIO: In-memory DOCX buffer ready for saving or downloading.
    """
    doc = docx.Document()

    # ── Page Setup (A4, 18mm top/bottom, 15mm left/right) ──
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(18)
    section.bottom_margin = Mm(18)
    section.left_margin = Mm(15)
    section.right_margin = Mm(15)

    # Different first page header/footer so cover page stays pristine
    section.different_first_page_header_footer = True

    inst = session.instrument
    org = session.organization

    # Standard report numbering
    if not report_number:
        rev_tag = f"-R{session.revision_number:02d}" if session.revision_number > 1 else "-R01"
        report_number = f"TR-{session.session_number}{rev_tag}"

    lab_name = org.name if org else "National Metrology Institute"

    # Setup running headers and footers for page 2+
    setup_report_header(section, lab_name, report_number)
    setup_report_footer(section)

    gen_date = timezone.localdate().strftime("%Y-%m-%d")
    test_date_str = session.test_date.strftime("%Y-%m-%d") if session.test_date else gen_date
    app_date_str = session.approved_at.strftime("%Y-%m-%d %H:%M") if session.approved_at else gen_date
    uom = inst.unit_of_measure or "g"

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 1: COVER AND INSTRUMENT METROLOGICAL SPECIFICATIONS
    # ══════════════════════════════════════════════════════════════════════════

    # ── Laboratory Logo & Branding Header ──
    logo_path = None
    if org and org.logo and os.path.exists(org.logo.path):
        logo_path = org.logo.path

    if logo_path:
        brand_table = doc.add_table(rows=1, cols=2)
        brand_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        brand_table.columns[0].width = Mm(42)
        brand_table.columns[1].width = Mm(138)
        brand_row = brand_table.rows[0]
        set_row_cant_split(brand_row)

        # Logo Cell
        c_logo = brand_row.cells[0]
        c_logo.width = Mm(42)
        c_logo.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p_logo = c_logo.paragraphs[0]
        p_logo.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p_logo.paragraph_format.space_before = Pt(0)
        p_logo.paragraph_format.space_after = Pt(0)
        try:
            p_logo.add_run().add_picture(logo_path, width=Mm(38))
        except Exception:
            p_logo.add_run(lab_name).font.bold = True

        # Info Cell
        c_info = brand_row.cells[1]
        c_info.width = Mm(138)
        c_info.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _format_cell_text(
            c_info,
            f"<strong>{lab_name}</strong><br/>"
            f"{org.address or 'Legal Metrology Verification Centre'}<br/>"
            f"Phone: {org.phone or 'N/A'} • Email: {org.email or 'metrology@lab.gov'}<br/>"
            f"Accreditation Body Ref: <strong>{org.accreditation_number or 'ISO/IEC 17025 Accredited Laboratory'}</strong>",
            default_size=8.0,
            default_color=SLATE_TEXT
        )
    else:
        add_paragraph(doc, lab_name, bold=True, font_size=15, color=NAVY_PRIMARY, space_after=2)
        add_paragraph(
            doc,
            f"{org.address or 'Legal Metrology Verification Centre'} • "
            f"Phone: {org.phone or 'N/A'} • Email: {org.email or 'metrology@lab.gov'}\n"
            f"Accreditation Body Ref: {org.accreditation_number or 'ISO/IEC 17025 Accredited Laboratory'}",
            font_size=8.0,
            color=MUTED_GRAY,
            space_after=4
        )

    # ── Report Title Banner ──
    add_paragraph(
        doc,
        "METROLOGICAL TEST REPORT",
        bold=True,
        font_size=16,
        color=NAVY_PRIMARY,
        space_before=8,
        space_after=2,
        alignment=WD_ALIGN_PARAGRAPH.CENTER
    )
    add_paragraph(
        doc,
        f"Non-Automatic Weighing Instrument (NAWI) — {session.get_oiml_edition_display()}",
        italic=True,
        font_size=10,
        color=BLUE_SECONDARY,
        space_before=0,
        space_after=8,
        alignment=WD_ALIGN_PARAGRAPH.CENTER
    )

    # ── Report Identification Table ──
    report_meta = [
        ["Report Number:", f"<strong>{report_number}</strong>"],
        ["Test ID / Reference:", session.session_number],
        ["Laboratory Tracking No:", session.lab_reference_number or "—"],
        ["Date of Test:", test_date_str],
        ["Date of Report Generation:", gen_date],
        ["Applicable Standard:", session.get_oiml_edition_display()],
    ]
    add_kv_table(doc, report_meta, [Mm(60), Mm(120)])

    # ── Client Details ──
    add_document_heading(doc, "1. Client / Owner Identification", level=1)
    client_meta = [
        ["Client / Customer Name:", inst.customer_name or (org.name if org else "—")],
        ["Laboratory / Site Location:", inst.location or (session.test_location or "Main Calibration Bay")],
    ]
    add_kv_table(doc, client_meta, [Mm(60), Mm(120)])

    # ── Instrument Metrological Details Table ──
    add_document_heading(doc, "2. Instrument Under Test (Metrological Characteristics)", level=1)
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
    add_kv_table(doc, inst_meta, [Mm(60), Mm(120)])

    add_paragraph(
        doc,
        "<em>Notice: The instrument characteristics detailed above represent the metrological basis "
        "under which maximum permissible errors (MPE) are evaluated in this report.</em>",
        font_size=7.5,
        color=MUTED_GRAY,
        space_before=4,
        space_after=8
    )

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 2: TEST CONDITIONS AND PRELIMINARY EXAMINATION
    # ══════════════════════════════════════════════════════════════════════════
    doc.add_page_break()

    add_document_heading(doc, "3. Environmental Test Conditions", level=1)
    add_paragraph(
        doc,
        "Environmental parameters recorded during measurement execution per OIML R 76-1 Clause 5.3.1:",
        font_size=8.5,
        space_after=4
    )

    temp_s = f"{session.temperature_start} °C" if session.temperature_start is not None else "—"
    temp_e = f"{session.temperature_end} °C" if session.temperature_end is not None else "—"
    hum_s = f"{session.humidity_start} %RH" if session.humidity_start is not None else "—"
    hum_e = f"{session.humidity_end} %RH" if session.humidity_end is not None else "—"

    env_headers = ["Parameter", "Start of Test", "End of Test", "Permissible Variation / Limit"]
    env_rows = [
        ["Ambient Temperature", temp_s, temp_e, "Max shift: 5°C per 12h (Class II) / 1°C per 12h (Class I)"],
        ["Relative Humidity", hum_s, hum_e, "Within laboratory working limits (30% – 70% RH)"],
        ["Physical Test Location", session.test_location or "Standard Calibration Laboratory", "—", "Cleanroom environment; draft shield engaged"],
    ]
    add_data_table(doc, env_headers, env_rows, [Mm(45), Mm(35), Mm(35), Mm(65)])

    # ── Reference Standards & Test Equipment ──
    add_document_heading(doc, "4. Reference Standards & Working Equipment", level=1)
    add_paragraph(
        doc,
        "Standard masses and metrological standards employed during testing maintain unbroken "
        "traceability to National and International Metrology Standards (SI units).",
        font_size=8.5,
        space_after=4
    )

    standards_text = session.reference_standards or "OIML Class E2 / F1 Standard Mass Set (Ref: MET-STD-M1; Traceability Cert #CAL-2026-NMC-089)"
    ref_table = [
        ["Reference Standard Set:", standards_text],
        ["Standard Accuracy Class:", "OIML R 111 Class E2 / F1 Working Standards"],
        ["Equipment Traceability Code:", session.lab_reference_number or "NMC-TR-2026-VAL"],
        ["Testing Officer / Metrologist:", f"{session.technician.full_name} ({session.technician.job_title or 'Metrologist'})" if session.technician else "Testing Officer"],
    ]
    add_kv_table(doc, ref_table, [Mm(60), Mm(120)])

    # ── Initial Visual & Functional Examination ──
    add_document_heading(doc, "5. Visual & Functional Examination (OIML R 76 §A.3 / §A.4)", level=1)
    prelim_headers = ["Examination Item", "Standard Requirement", "Status / Finding"]
    prelim_rows = [
        ["Descriptive Markings (§A.3)", "Class, Max, Min, e, d markings legible and complete", "PASS" if session.initial_examination_passed else "FAIL"],
        ["Levelling & Bubble Device", "Instrument level verified and stable throughout test", "PASS" if session.initial_examination_passed else "FAIL"],
        ["Zero-Setting Device (§A.4.1)", "Zero error within ±0.25 e (or ±0.5 d with auxiliary device)", "PASS" if session.zero_test_passed else "FAIL"],
        ["Zero-Tracking Device (§A.4.2)", "Zero indication operates within statutory limits", "PASS" if session.zero_test_passed else "FAIL"],
    ]
    add_data_table(doc, prelim_headers, prelim_rows, [Mm(55), Mm(80), Mm(45)])

    if session.initial_examination_notes or session.remarks:
        obs_text = session.initial_examination_notes or session.remarks
        add_paragraph(doc, f"<strong>Technician Observations:</strong> {obs_text}", font_size=8.5, space_before=4)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 3+: TEST RESULTS (DETAILED MEASUREMENT TABLES)
    # ══════════════════════════════════════════════════════════════════════════
    doc.add_page_break()

    add_document_heading(doc, "6. Detailed Metrological Test Results", level=1)
    add_paragraph(
        doc,
        "Individual observations, indicated readings, turning-point errors, and maximum permissible error (MPE) "
        "evaluations in accordance with the test procedures selected for this instrument.",
        font_size=8.5,
        space_after=6
    )

    # ── 6.1 Weighing Performance Test ──
    weighing_qs = session.weighing_measurements.all().order_by("test_type", "sequence_order")
    if weighing_qs.exists():
        add_document_heading(doc, "6.1 Weighing Performance Test (OIML R 76 §A.4.4 / §3.5 Table 1)", level=2)
        add_paragraph(
            doc,
            "Error E = I - L (or corrected turning-point error Ec = I + 0.5d - ΔL - L). "
            "Maximum Permissible Error (MPE) applied per Table 1 for initial verification.",
            italic=True,
            font_size=7.5,
            color=MUTED_GRAY,
            space_after=4
        )

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
        w_widths = [Mm(12), Mm(32), Mm(34), Mm(34), Mm(26), Mm(24), Mm(18)]
        add_data_table(doc, w_headers, w_rows, w_widths)

    # ── 6.2 Repeatability Test ──
    rep_qs = session.repeatability_measurements.all().order_by("series_name", "repetition_number")
    if rep_qs.exists():
        add_document_heading(doc, "6.2 Repeatability Test (OIML R 76 §A.4.10 / §3.6.1)", level=2)
        add_paragraph(
            doc,
            "Difference between results of successive weighings of the same nominal load shall not "
            "exceed the absolute value of the MPE for that load: (Imax - Imin) ≤ |MPE|.",
            italic=True,
            font_size=7.5,
            color=MUTED_GRAY,
            space_after=4
        )

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
        r_widths = [Mm(36), Mm(16), Mm(34), Mm(34), Mm(24), Mm(20), Mm(16)]
        add_data_table(doc, r_headers, r_rows, r_widths)

    # ── 6.3 Eccentricity Test ──
    ecc_qs = session.eccentricity_measurements.all().order_by("load_position")
    if ecc_qs.exists():
        add_document_heading(doc, "6.3 Eccentricity (Off-Centre Loading) Test (OIML R 76 §A.4.7 / §3.6.2)", level=2)
        add_paragraph(
            doc,
            "Loads applied in off-center positions across the load receptor surface. "
            "Maximum Permissible Error (MPE) evaluated per R 76 §3.6.2 at test load.",
            italic=True,
            font_size=7.5,
            color=MUTED_GRAY,
            space_after=4
        )

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
        e_widths = [Mm(45), Mm(32), Mm(32), Mm(28), Mm(25), Mm(18)]
        add_data_table(doc, e_headers, e_rows, e_widths)

    # ── 6.4 Discrimination Test ──
    disc_qs = session.discrimination_measurements.all()
    if disc_qs.exists():
        add_document_heading(doc, "6.4 Discrimination Test (OIML R 76 §A.4.8 / §3.8)", level=2)
        add_paragraph(
            doc,
            "An additional load of 1.4 d gently applied to the loaded instrument shall cause a "
            "permanent displacement of at least 1.0 d on the displayed indication.",
            italic=True,
            font_size=7.5,
            color=MUTED_GRAY,
            space_after=4
        )

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
        d_widths = [Mm(32), Mm(32), Mm(30), Mm(32), Mm(34), Mm(20)]
        add_data_table(doc, d_headers, d_rows, d_widths)

    # ── 6.5 Tare Weighing Test ──
    tare_qs = session.tare_measurements.all().order_by("tare_load")
    if tare_qs.exists():
        add_document_heading(doc, "6.5 Tare Weighing Test (OIML R 76 §A.4.6 / §3.5.3.4)", level=2)
        add_paragraph(
            doc,
            "Weighing accuracy verified with tare balancing activated. Net errors evaluated against Table 1 MPE.",
            italic=True,
            font_size=7.5,
            color=MUTED_GRAY,
            space_after=4
        )

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
        t_widths = [Mm(32), Mm(34), Mm(34), Mm(32), Mm(28), Mm(20)]
        add_data_table(doc, t_headers, t_rows, t_widths)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 4: CONCLUSION, ACCEPTANCE CRITERIA AND APPROVAL SIGNATURES
    # ══════════════════════════════════════════════════════════════════════════
    doc.add_page_break()

    add_document_heading(doc, "7. Test-Wise Procedure Summary", level=1)
    add_paragraph(
        doc,
        "Summary of metrological evaluations across all applicable OIML R 76 test procedures:",
        font_size=8.5,
        space_after=4
    )

    summary_headers = ["Applicable Test Procedure", "Governing Clause", "Total Observations", "Acceptance Status"]
    summary_rows = []

    if session.proc_initial_examination:
        summary_rows.append(["Visual & Functional Examination", "OIML R 76 §A.3 / §A.4", "1", "PASS" if session.initial_examination_passed else "FAIL"])
    if session.proc_zero_setting:
        z_count = session.zero_setting_measurements.count()
        z_pass = "PASS" if session.zero_test_passed else "FAIL"
        summary_rows.append(["Zero-Setting & Tracking Tests", "OIML R 76 §A.4.1 / §A.4.2", str(max(z_count, 1)), z_pass])
    if session.proc_weighing:
        w_fails = session.weighing_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Weighing Performance Tests", "OIML R 76 §A.4.4 / §3.5 Table 1", str(weighing_qs.count()), "FAIL" if w_fails > 0 else "PASS"])
    if session.proc_repeatability:
        r_fails = session.repeatability_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Repeatability Tests", "OIML R 76 §A.4.10 / §3.6.1", str(rep_qs.count()), "FAIL" if r_fails > 0 else "PASS"])
    if session.proc_eccentricity:
        e_fails = session.eccentricity_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Eccentricity (Off-Centre Loading)", "OIML R 76 §A.4.7 / §3.6.2", str(ecc_qs.count()), "FAIL" if e_fails > 0 else "PASS"])
    if session.proc_discrimination:
        d_fails = session.discrimination_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Discrimination Tests", "OIML R 76 §A.4.8 / §3.8", str(disc_qs.count()), "FAIL" if d_fails > 0 else "PASS"])
    if session.proc_tare:
        t_fails = session.tare_measurements.filter(pass_fail="FAIL").count()
        summary_rows.append(["Tare Weighing Tests", "OIML R 76 §A.4.6 / §3.5.3.4", str(tare_qs.count()), "FAIL" if t_fails > 0 else "PASS"])

    add_data_table(doc, summary_headers, summary_rows, [Mm(65), Mm(55), Mm(30), Mm(30)])

    # ── 8. Overall Metrological Conformity Decision ──
    add_document_heading(doc, "8. Overall Metrological Conformity Decision", level=1)
    is_pass = session.overall_result == "PASS"
    verdict_text = "COMPLIANT / PASS" if is_pass else "NON-COMPLIANT / FAIL"
    verdict_bg = HEX_PASS_BG if is_pass else HEX_FAIL_BG
    verdict_color = PASS_GREEN if is_pass else FAIL_RED

    verdict_tbl = create_table(doc, 1, 2, col_widths=[Mm(50), Mm(130)])
    v_row = verdict_tbl.rows[0]
    set_row_cant_split(v_row)

    c_v0 = v_row.cells[0]
    set_cell_background(c_v0, verdict_bg)
    _format_cell_text(c_v0, "<strong>FINAL VERDICT:</strong>", default_size=11.0, default_color=SLATE_TEXT, bold=True)

    c_v1 = v_row.cells[1]
    set_cell_background(c_v1, verdict_bg)
    _format_cell_text(c_v1, f"<strong>{verdict_text}</strong>", default_size=12.0, default_color=verdict_color, bold=True)

    p_sp = doc.add_paragraph()
    p_sp.paragraph_format.space_before = Pt(0)
    p_sp.paragraph_format.space_after = Pt(4)

    # ── Deviations & Remarks ──
    deviations = session.rejection_reason if session.status == "REJECTED" else "None. Testing performed without procedural deviations."
    tech_remarks = session.remarks or session.notes or "All observed indication errors were found within applicable maximum permissible error tolerances."

    rem_table = [
        ["Deviations / Exceptions:", deviations],
        ["Technical Remarks:", tech_remarks],
    ]
    add_kv_table(doc, rem_table, [Mm(50), Mm(130)])

    # ── 9. Approval & Authorization Signatures ──
    add_document_heading(doc, "9. Verification & Authorization Signatures", level=1)
    add_signature_block(doc, session.technician, session.reviewer, test_date_str, app_date_str)

    # ── 10. Statutory & Non-Certification Legal Disclaimer ──
    add_paragraph(
        doc,
        "<strong>STATUTORY & METROLOGICAL NOTICE:</strong> "
        "The test results and metrological evaluations reported herein relate solely to the specific instrument tested, "
        "identified by serial number, under the physical environmental conditions recorded at the time of testing. "
        "This report documents technical verification in compliance with OIML R 76-1:2006 / EN 45501:2015. "
        "This document does NOT constitute an OIML Certificate of Conformity or formal type approval accreditation "
        "unless separately authorized, registered, and substantiated by an accredited National Metrology Authority. "
        "This report shall not be reproduced, except in full, without the prior written approval of the issuing laboratory.",
        font_size=7.0,
        color=MUTED_GRAY,
        space_before=6,
        space_after=4,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
    )

    # Save to BytesIO stream
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf

