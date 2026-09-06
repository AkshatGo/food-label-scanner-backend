import sys
from io import BytesIO
from xml.sax.saxutils import escape
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
)

BRAND_DARK = colors.HexColor("#132A22")
BRAND_GREEN = colors.HexColor("#198D55")
BRAND_MINT = colors.HexColor("#E6F8EE")
BORDER_COLOR = colors.HexColor("#D2DFD8")
TEXT_PRIMARY = colors.HexColor("#14221D")
TEXT_MUTED = colors.HexColor("#5F7367")

FRIENDLY_FIELDS = {
    "fssai_license": "FSSAI License / Logo",
    "fssai_license_number": "FSSAI License Number",
    "ingredient_declaration": "Ingredients List",
    "ingredients_list": "Ingredients List",
    "nutrition_information": "Nutritional Information",
    "nutritional_info": "Nutritional Information",
    "allergen_declaration": "Allergen Warning / Declaration",
    "vegetarian_mark": "Vegetarian / Non-Veg Mark",
    "batch_number": "Batch / Lot Number",
    "batch_lot_code_number": "Batch / Lot Code",
    "batch_lot_or_code_number": "Batch / Lot Code",
    "net_quantity": "Net Quantity Declaration",
    "net_quantity_value": "Net Quantity Value",
    "date_marking": "Date Marking (Mfg / Pkd)",
    "date_of_manufacture_or_packaging": "Date of Packaging / Mfg",
    "expiry_date": "Expiry / Use By Date",
    "expiry_or_use_by_date": "Expiry / Use By Date",
    "manufacturer": "Manufacturer Name & Address",
    "manufacturer_statement": "Manufacturer Details",
    "manufacturer_or_brand_owner_address": "Manufacturer / Brand Address",
    "instructions_for_use": "Instructions for Use / Storage",
}


def _text(value):
    return escape(str(value if value not in (None, "") else "Not detected by OCR"))


def _format_dict_points(val):
    if not val:
        return "None"
    if isinstance(val, dict):
        return ", ".join(f"{k.replace('_', ' ').title()}: {v}" for k, v in val.items())
    return str(val)


def _get_styles():
    base = getSampleStyleSheet()
    styles = {
        "DocTitle": ParagraphStyle(
            "DocTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=BRAND_DARK,
            alignment=0,
            spaceAfter=4,
        ),
        "DocSubtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=TEXT_MUTED,
        ),
        "Heading": ParagraphStyle(
            "Heading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=BRAND_DARK,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "HeaderCell": ParagraphStyle(
            "HeaderCell",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=13,
            textColor=colors.white,
        ),
        "CellBold": ParagraphStyle(
            "CellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12.5,
            textColor=BRAND_DARK,
        ),
        "CellNormal": ParagraphStyle(
            "CellNormal",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12.5,
            textColor=TEXT_PRIMARY,
        ),
        "StatusDetected": ParagraphStyle(
            "StatusDetected",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#15803D"),
        ),
        "StatusReview": ParagraphStyle(
            "StatusReview",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#B45309"),
        ),
        "StatusIssue": ParagraphStyle(
            "StatusIssue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#DC2626"),
        ),
        "Disclaimer": ParagraphStyle(
            "Disclaimer",
            parent=base["Italic"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=11,
            textColor=TEXT_MUTED,
        ),
    }
    return styles


def _table(rows, widths, is_striped=True):
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if is_striped and len(rows) > 1:
        for i in range(1, len(rows)):
            bg = colors.HexColor("#F8FAF8") if i % 2 == 1 else colors.white
            style.append(("BACKGROUND", (0, i), (-1, i), bg))
    table.setStyle(TableStyle(style))
    return table


def _value_rows(mapping, styles):
    rows = [[
        Paragraph("Field", styles["HeaderCell"]),
        Paragraph("Value", styles["HeaderCell"])
    ]]
    name = mapping.get("name")
    category = str(mapping.get("category", "solid")).lower()
    fallback_name = "Liquid Product" if category == "liquid" else "Solid Product"
    if not name or str(name).strip().lower() in {"sen", "unknown", "none", "scanned food item", "scanned label"} or len(str(name).strip()) <= 3:
        display_name = fallback_name
    else:
        display_name = str(name).strip()

    cleaned_mapping = {
        "Product Name": display_name,
        "Product Category": category.title() + " Product",
    }
    for k, v in mapping.items():
        if k in {"name", "category", "category_confidence"}:
            continue
        cleaned_mapping[k.replace("_", " ").title()] = str(v)

    for key, value in cleaned_mapping.items():
        rows.append([
            Paragraph(key, styles["CellBold"]),
            Paragraph(_text(value), styles["CellNormal"])
        ])
    return rows


def _fssai_rows(fssai, styles):
    rows = [[
        Paragraph("Status", styles["HeaderCell"]),
        Paragraph("Requirement / Finding", styles["HeaderCell"]),
        Paragraph("Meaning & Action", styles["HeaderCell"])
    ]]
    statuses = fssai.get("statuses", [])
    if statuses:
        for item in statuses:
            status = item.get("status", "NOT_DETECTED")
            raw_field = str(item.get("field", ""))
            field_name = FRIENDLY_FIELDS.get(raw_field, raw_field.replace("_", " ").title())

            if status == "DETECTED":
                status_p = Paragraph("Detected &#x2713;", styles["StatusDetected"])
                meaning_p = Paragraph("Confirmed present on label by OCR", styles["CellNormal"])
            elif status == "POTENTIAL_ISSUE":
                status_p = Paragraph("Notice &#x26A0;", styles["StatusIssue"])
                meaning_p = Paragraph("Manual verification advised", styles["CellNormal"])
            else:
                status_p = Paragraph("Review Required", styles["StatusReview"])
                meaning_p = Paragraph("Manual label review required; not a legal violation", styles["CellNormal"])

            rows.append([status_p, Paragraph(field_name, styles["CellBold"]), meaning_p])
    else:
        for status, key in [("DETECTED", "detected"), ("NOT_DETECTED", "not_detected"), ("POTENTIAL_ISSUE", "potential_issues"), ("WARNING", "warnings")]:
            value = fssai.get(key, {})
            if isinstance(value, dict):
                items = list(value.keys())
            elif isinstance(value, list):
                items = value
            else:
                items = [str(value)] if value else []

            for raw_field in items:
                field_name = FRIENDLY_FIELDS.get(str(raw_field), str(raw_field).replace("_", " ").title())
                if status == "DETECTED":
                    status_p = Paragraph("Detected &#x2713;", styles["StatusDetected"])
                    meaning_p = Paragraph("Confirmed present on label by OCR", styles["CellNormal"])
                elif status == "POTENTIAL_ISSUE":
                    status_p = Paragraph("Notice &#x26A0;", styles["StatusIssue"])
                    meaning_p = Paragraph("Manual verification advised", styles["CellNormal"])
                else:
                    status_p = Paragraph("Review Required", styles["StatusReview"])
                    meaning_p = Paragraph("Manual label review required; not a legal violation", styles["CellNormal"])

                rows.append([status_p, Paragraph(field_name, styles["CellBold"]), meaning_p])
    return rows


def _nutrition_rows(scan, styles):
    nutrition = scan.get("nutrition_details", {}).get("all_detected_rows", scan.get("nutrition", {}))
    rows = [[
        Paragraph("Nutrient / Declaration", styles["HeaderCell"]),
        Paragraph("Amount", styles["HeaderCell"]),
        Paragraph("Unit", styles["HeaderCell"])
    ]]
    for name, value in nutrition.items():
        if isinstance(value, dict):
            disp_name = name.replace("_", " ").title()
            val_str = str(value.get("value", "--"))
            unit_str = str(value.get("unit", ""))
            rows.append([
                Paragraph(disp_name, styles["CellBold"]),
                Paragraph(val_str, styles["CellNormal"]),
                Paragraph(unit_str, styles["CellNormal"]),
            ])
    return rows


def _inr_rows(inr, scan, styles):
    rating = inr.get("rating_display") or (f"{inr.get('rating_stars')}/5" if inr.get("rating_stars") else inr.get("rating", "N/A"))
    category = inr.get("category", scan.get("product", {}).get("category", "solid"))

    rows = [
        [Paragraph("Metric", styles["HeaderCell"]), Paragraph("Evaluation Result", styles["HeaderCell"])],
        [
            Paragraph("Product Rating", styles["CellBold"]),
            Paragraph(f"<b><font size=11 color='#198D55'>{_text(rating)}</font></b> &nbsp; (FSSAI INR Draft Framework)", styles["CellNormal"]),
        ],
        [Paragraph("Classification", styles["CellBold"]), Paragraph(f"{category.title()} Product", styles["CellNormal"])],
        [Paragraph("INR Assessment Status", styles["CellBold"]), Paragraph(_text(inr.get("status", "Calculated")).replace("_", " ").title(), styles["CellNormal"])],
        [Paragraph("Nutritional Risk Points (Negative)", styles["CellBold"]), Paragraph(_format_dict_points(inr.get("negative_points", {})), styles["CellNormal"])],
        [Paragraph("Nutritional Bonus Points (Positive)", styles["CellBold"]), Paragraph(_format_dict_points(inr.get("positive_points", {})), styles["CellNormal"])],
        [Paragraph("Missing Values Treatment", styles["CellBold"]), Paragraph("Treated as zero" if inr.get("missing_fields_treated_as_zero") or inr.get("missing_values_treated_as_zero") else "All mandatory values present", styles["CellNormal"])],
        [Paragraph("Regulatory Basis", styles["CellBold"]), Paragraph(_text(inr.get("basis", "FSSAI 2022 draft INR framework; Category solid; per 100g/100ml")), styles["CellNormal"])],
    ]
    return rows


def _quality_rows(scan, styles):
    ocr = scan.get("ocr", {})
    proc = scan.get("processing", {})
    conf = f"{ocr.get('confidence', '--')}%" if ocr.get('confidence') is not None else "N/A"
    proc_time = f"{proc.get('processing_time_ms', '--')} ms" if proc.get('processing_time_ms') else "N/A"

    rows = [
        [Paragraph("Metric", styles["HeaderCell"]), Paragraph("Result", styles["HeaderCell"])],
        [Paragraph("OCR Confidence", styles["CellBold"]), Paragraph(conf, styles["CellNormal"])],
        [Paragraph("Engine Processing Time", styles["CellBold"]), Paragraph(proc_time, styles["CellNormal"])],
        [Paragraph("Scan ID", styles["CellBold"]), Paragraph(_text(scan.get("scan_id", "")), styles["CellNormal"])],
    ]
    return rows


def create_report_pdf(scan, image_bytes):
    output = BytesIO()
    # Usable printable width = 210 - 28 = 182 mm
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = _get_styles()
    fssai = scan.get("fssai", {})
    inr = scan.get("inr", {})
    ocr = scan.get("ocr", {})

    story = []

    # Header with Logo if available
    logo_path = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
    if not logo_path.exists():
        logo_path = Path("/Users/jitesh/Desktop/food_label_scanner/flutter_app/assets/images/logo.png")

    if logo_path.exists():
        try:
            logo_img = Image(str(logo_path), width=58 * mm, height=23.5 * mm)
            story.append(logo_img)
            story.append(Spacer(1, 4))
        except Exception:
            pass

    story.extend([
        Paragraph("Food Label Audit & Compliance Report", styles["DocTitle"]),
        Paragraph(f"Scan ID: {_text(scan.get('scan_id'))} &nbsp;|&nbsp; Uploaded: {_text(scan.get('uploaded_at'))}", styles["DocSubtitle"]),
        Spacer(1, 6),
    ])

    if image_bytes:
        try:
            image = Image(BytesIO(image_bytes))
            image._restrictSize(182 * mm, 68 * mm)
            story.extend([image, Spacer(1, 6)])
        except Exception:
            pass

    # 1. Product information (col widths: 50 mm, 132 mm -> sum 182 mm)
    story.append(Paragraph("Product Information", styles["Heading"]))
    story.append(_table(_value_rows(scan.get("product", {}), styles), [50 * mm, 132 * mm]))
    story.append(Spacer(1, 5))

    # 2. Ingredients
    story.append(Paragraph("Detected Ingredients", styles["Heading"]))
    ingredients = scan.get("ingredients", [])
    if ingredients:
        story.append(Paragraph(_text(", ".join(ingredients)), styles["CellNormal"]))
    else:
        story.append(Paragraph("Not detected by OCR. Verify against packaging.", styles["Disclaimer"]))
    story.append(Spacer(1, 5))

    # 3. Nutrition table (col widths: 92 mm, 45 mm, 45 mm -> sum 182 mm)
    story.append(Paragraph("Nutritional Information & Minerals", styles["Heading"]))
    story.append(_table(_nutrition_rows(scan, styles), [92 * mm, 45 * mm, 45 * mm]))
    story.append(Spacer(1, 3))
    story.append(Paragraph("Note: Only items extracted by OCR are listed above. Missing values require comparison with original label.", styles["Disclaimer"]))
    story.append(Spacer(1, 5))

    # 4. FSSAI Label Compliance (col widths: 34 mm, 68 mm, 80 mm -> sum 182 mm)
    story.append(Paragraph("FSSAI Regulatory Compliance Review", styles["Heading"]))
    overall_status = fssai.get("overall_status", "REVIEW_REQUIRED")
    status_label = "Verified / No Gaps Detected" if overall_status != "REVIEW_REQUIRED" else "Review Recommended"
    story.append(Paragraph(f"<b>Overall Status:</b> {_text(status_label)}", styles["CellNormal"]))
    story.append(Spacer(1, 4))
    story.append(_table(_fssai_rows(fssai, styles), [34 * mm, 68 * mm, 80 * mm]))
    story.append(Spacer(1, 5))

    # 5. INR Rating (col widths: 62 mm, 120 mm -> sum 182 mm)
    story.append(Paragraph("Indian Nutrition Rating (INR) Assessment", styles["Heading"]))
    story.append(_table(_inr_rows(inr, scan, styles), [62 * mm, 120 * mm]))
    story.append(Spacer(1, 5))

    # 6. OCR Quality (col widths: 62 mm, 120 mm -> sum 182 mm)
    story.append(Paragraph("OCR Processing & Quality", styles["Heading"]))
    story.append(_table(_quality_rows(scan, styles), [62 * mm, 120 * mm]))
    story.append(Spacer(1, 5))

    audit = fssai.get("compliance_audit", {})
    if audit:
        story.append(Paragraph("Audit Notes", styles["Heading"]))
        story.append(Paragraph(_text(audit.get("basis", "Offline FSSAI rules-based review.")), styles["CellNormal"]))
        story.append(Spacer(1, 3))
        story.append(Paragraph("Visual markers: Veg/Non-Veg green/brown symbols and regulatory FSSAI logos require physical label inspection as OCR only validates text representations.", styles["Disclaimer"]))

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.6, color=BORDER_COLOR, spaceAfter=8))
    story.append(Paragraph("<b>Disclaimer:</b> This document is an automated OCR-assisted preliminary audit generated by LabelLens based on FSSAI draft guidelines. It does not constitute legal, clinical, or statutory certification advice. Absence of detection does not indicate a legal non-compliance.", styles["Disclaimer"]))

    document.build(story)
    return output.getvalue()
