"""Government Compliance Report PDF generator — doc 06 layout.

Renders:
  1. Header (product, scan date, source regulation version)
  2. Section A table: font-size checklist
  3. Section B table: 20-row mandatory-declaration checklist
  4. Overall summary + disclaimer
"""

from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BRAND_DARK = colors.HexColor("#132A22")
BRAND_GREEN = colors.HexColor("#198D55")
BORDER_COLOR = colors.HexColor("#D2DFD8")
TEXT_PRIMARY = colors.HexColor("#14221D")
TEXT_MUTED = colors.HexColor("#5F7367")

STATUS_COLORS = {
    "PASS": colors.HexColor("#15803D"),
    "FAIL": colors.HexColor("#DC2626"),
    "COULD NOT VERIFY": colors.HexColor("#B45309"),
    "NOT APPLICABLE": colors.HexColor("#5F7367"),
}


def _styles():
    base = getSampleStyleSheet()
    return {
        "DocTitle": ParagraphStyle(
            "DocTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, textColor=BRAND_DARK, alignment=0, spaceAfter=4,
        ),
        "DocSubtitle": ParagraphStyle(
            "DocSubtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=13, textColor=TEXT_MUTED,
        ),
        "Heading": ParagraphStyle(
            "Heading", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12.5, leading=16, textColor=BRAND_DARK, spaceBefore=12, spaceAfter=6,
        ),
        "HeaderCell": ParagraphStyle(
            "HeaderCell", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.5, leading=11.5, textColor=colors.white,
        ),
        "Cell": ParagraphStyle(
            "Cell", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.5, leading=11.5, textColor=TEXT_PRIMARY,
        ),
        "CellBold": ParagraphStyle(
            "CellBold", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.5, leading=11.5, textColor=BRAND_DARK,
        ),
        "Disclaimer": ParagraphStyle(
            "Disclaimer", parent=base["Italic"], fontName="Helvetica-Oblique",
            fontSize=7.5, leading=10.5, textColor=TEXT_MUTED,
        ),
    }


def _status_paragraph(status, styles):
    color_hex = STATUS_COLORS.get(status, TEXT_PRIMARY).hexval()[2:]
    return Paragraph(
        f"<b><font color='#{color_hex}'>{escape(status)}</font></b>",
        styles["Cell"],
    )


def _striped_table(rows, widths):
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(rows)):
        bg = colors.HexColor("#F8FAF8") if i % 2 == 1 else colors.white
        style.append(("BACKGROUND", (0, i), (-1, i), bg))
    table.setStyle(TableStyle(style))
    return table


def _summary_counts(counts):
    order = ["PASS", "FAIL", "COULD NOT VERIFY", "NOT APPLICABLE"]
    return " &nbsp;|&nbsp; ".join(
        f"<b>{escape(k)}</b>: {counts.get(k, 0)}" for k in order if counts.get(k)
    )


def create_compliance_pdf(product, compliance, scan_meta=None):
    """Build the PDF; returns bytes.

    product: {product_id, product_name, brand, ...}
    compliance: output of services.compliance.evaluate_compliance
    scan_meta: {scan_id, created_at}
    """
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = _styles()
    story = []

    scan_id = (scan_meta or {}).get("scan_id", "-")
    created = (scan_meta or {}).get("created_at", datetime.now(timezone.utc).isoformat())

    story.append(Paragraph("Government Compliance Report", styles["DocTitle"]))
    story.append(Paragraph(
        f"Product: <b>{escape(str(product.get('product_name') or 'Unknown product'))}</b>"
        f" &nbsp;|&nbsp; Brand: {escape(str(product.get('brand') or '-'))}"
        f" &nbsp;|&nbsp; Product ID: {escape(str(product.get('product_id', '-')))}",
        styles["DocSubtitle"],
    ))
    story.append(Paragraph(
        f"Scan: {escape(str(scan_id))} &nbsp;|&nbsp; Generated: {escape(str(created)[:19])}"
        f" &nbsp;|&nbsp; Checked against: <b>{escape(compliance['regulation_version'])}</b>",
        styles["DocSubtitle"],
    ))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.8, color=BRAND_GREEN, spaceAfter=8))

    # Calibration disclosure (doc 05 §4 honesty gate)
    calibration = compliance.get("calibration", {})
    story.append(Paragraph("Measurement Method Disclosure", styles["Heading"]))
    story.append(Paragraph(
        escape(str(calibration.get("note", calibration.get("method", "none")))),
        styles["Cell"],
    ))
    story.append(Spacer(1, 4))

    # --- Section A ----------------------------------------------------------
    section_a = compliance["section_a"]
    story.append(Paragraph("Section A — Font / Letter Size Checklist", styles["Heading"]))
    rows = [[
        Paragraph("Item", styles["HeaderCell"]),
        Paragraph("Required (mm)", styles["HeaderCell"]),
        Paragraph("Measured (mm)", styles["HeaderCell"]),
        Paragraph("Status", styles["HeaderCell"]),
        Paragraph("Citation", styles["HeaderCell"]),
    ]]
    for row in section_a["rows"]:
        rows.append([
            Paragraph(escape(row["item"]), styles["Cell"]),
            Paragraph(str(row["required_mm"] if row["required_mm"] is not None else "-"), styles["Cell"]),
            Paragraph(str(row["measured_mm"] if row["measured_mm"] is not None else "-"), styles["Cell"]),
            _status_paragraph(row["status"], styles),
            Paragraph(escape(row["citation"]), styles["Cell"]),
        ])
    story.append(_striped_table(rows, [64 * mm, 22 * mm, 22 * mm, 30 * mm, 44 * mm]))
    story.append(Paragraph(
        f"Section A summary: {_summary_counts(section_a['summary'])}",
        styles["Cell"],
    ))
    story.append(Spacer(1, 4))

    # --- Section B ----------------------------------------------------------
    section_b = compliance["section_b"]
    story.append(Paragraph("Section B — Mandatory Declaration Checklist", styles["Heading"]))
    rows = [[
        Paragraph("#", styles["HeaderCell"]),
        Paragraph("Requirement", styles["HeaderCell"]),
        Paragraph("Found", styles["HeaderCell"]),
        Paragraph("Status", styles["HeaderCell"]),
        Paragraph("Regulation", styles["HeaderCell"]),
        Paragraph("Note", styles["HeaderCell"]),
    ]]
    for row in section_b["rows"]:
        rows.append([
            Paragraph(escape(str(row["id"])), styles["Cell"]),
            Paragraph(escape(row["requirement"]), styles["Cell"]),
            Paragraph(
                "-" if row["found"] is None else ("Y" if row["found"] else "N"),
                styles["Cell"],
            ),
            _status_paragraph(row["status"], styles),
            Paragraph(escape(row["citation"]), styles["Cell"]),
            Paragraph(escape(row.get("note", "")), styles["Cell"]),
        ])
    story.append(_striped_table(rows, [8 * mm, 58 * mm, 10 * mm, 26 * mm, 34 * mm, 46 * mm]))
    story.append(Paragraph(
        f"Section B summary: {_summary_counts(section_b['summary'])}",
        styles["Cell"],
    ))
    story.append(Spacer(1, 8))

    # --- Overall ------------------------------------------------------------
    story.append(Paragraph("Overall Summary", styles["Heading"]))
    story.append(Paragraph(
        f"Font-size checks — {_summary_counts(compliance['summary']['font_size'])}",
        styles["Cell"],
    ))
    story.append(Paragraph(
        f"Mandatory declarations — {_summary_counts(compliance['summary']['declarations'])}",
        styles["Cell"],
    ))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.6, color=BORDER_COLOR, spaceAfter=8))
    story.append(Paragraph(
        f"<b>Disclaimer:</b> {escape(compliance['overall_note'])} "
        "COULD NOT VERIFY items are not PASSes — they require human review or "
        "additional capture. Absence of detection by OCR does not prove absence "
        "from the label.",
        styles["Disclaimer"],
    ))

    document.build(story)
    return output.getvalue()
