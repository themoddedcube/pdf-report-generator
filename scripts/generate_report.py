#!/usr/bin/env python3
"""PDF report generator — ReportLab Platypus engine."""

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    FrameBreak,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.pagesizes import letter

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# ---------------------------------------------------------------------------
# Default style (professional navy + gold corporate palette)
# ---------------------------------------------------------------------------
DEFAULT_PRIMARY   = (26,  54,  93)   # deep navy
DEFAULT_ACCENT    = (201, 160,  48)   # gold
DEFAULT_HIGHLIGHT = (235, 243, 252)   # light blue tint

THEMES = {
    "default":   {"primary": DEFAULT_PRIMARY,   "accent": DEFAULT_ACCENT,    "highlight": DEFAULT_HIGHLIGHT},
    "navy":      {"primary": (10,  36,  99),     "accent": (255, 195,   0),   "highlight": (230, 240, 255)},
    "charcoal":  {"primary": (45,  45,  45),     "accent": (220,  80,  40),   "highlight": (245, 245, 245)},
    "forest":    {"primary": (20,  83,  45),     "accent": (180, 140,  20),   "highlight": (230, 247, 236)},
    "burgundy":  {"primary": (100,  0,  30),     "accent": (200, 160,  80),   "highlight": (250, 235, 240)},
}


def rgb(t):
    return colors.Color(t[0]/255, t[1]/255, t[2]/255)


# ---------------------------------------------------------------------------
# Page callbacks
# ---------------------------------------------------------------------------

class ReportCanvas:
    """Mixin-style: stores doc-level data for onPage callbacks."""
    pass


def make_body_page(canvas, doc):
    meta   = doc.report_meta
    theme  = doc.report_theme
    pw, ph = doc.pagesize

    primary   = rgb(theme["primary"])
    accent    = rgb(theme["accent"])
    rule_gray = colors.Color(0.75, 0.75, 0.75)

    # Header rule
    canvas.saveState()
    canvas.setStrokeColor(primary)
    canvas.setLineWidth(1.5)
    canvas.line(0.6*inch, ph - 0.5*inch, pw - 0.6*inch, ph - 0.5*inch)

    # Header text
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(primary)
    canvas.drawString(0.6*inch, ph - 0.42*inch, meta.get("company", ""))

    classification = meta.get("classification", "")
    if classification:
        canvas.setFillColor(accent)
        canvas.drawRightString(pw - 0.6*inch, ph - 0.42*inch, classification)

    # Footer rule
    canvas.setStrokeColor(rule_gray)
    canvas.setLineWidth(0.75)
    canvas.line(0.6*inch, 0.5*inch, pw - 0.6*inch, 0.5*inch)

    # Footer text
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.Color(0.4, 0.4, 0.4))

    doc_id = meta.get("document_id", "")
    doc_date = meta.get("date", str(date.today()))
    left_footer = f"{doc_id}  |  {doc_date}" if doc_id else doc_date
    canvas.drawString(0.6*inch, 0.32*inch, left_footer)

    title = meta.get("title", "")
    canvas.drawCentredString(pw / 2, 0.32*inch, title[:60])

    canvas.drawRightString(pw - 0.6*inch, 0.32*inch, f"Page {doc.page}")
    canvas.restoreState()


def make_cover_page(canvas, doc):
    meta  = doc.report_meta
    theme = doc.report_theme
    pw, ph = doc.pagesize

    primary   = rgb(theme["primary"])
    accent    = rgb(theme["accent"])
    highlight = rgb(theme["highlight"])

    # Full-bleed primary color top band (~40% of page)
    canvas.saveState()
    canvas.setFillColor(primary)
    canvas.rect(0, ph * 0.58, pw, ph * 0.42, fill=1, stroke=0)

    # Accent stripe
    canvas.setFillColor(accent)
    canvas.rect(0, ph * 0.555, pw, ph * 0.025, fill=1, stroke=0)

    # Title on band
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 26)
    title = meta.get("title", "Report")
    canvas.drawCentredString(pw / 2, ph * 0.72, title)

    subtitle = meta.get("subtitle", "")
    if subtitle:
        canvas.setFont("Helvetica", 14)
        canvas.setFillColor(colors.Color(0.85, 0.85, 0.85))
        canvas.drawCentredString(pw / 2, ph * 0.67, subtitle)

    # Metadata block on white area
    canvas.setFillColor(primary)
    canvas.setFont("Helvetica-Bold", 10)
    y = ph * 0.50

    fields = [
        ("Author",     meta.get("author", "")),
        ("Company",    meta.get("company", "")),
        ("Department", meta.get("department", "")),
        ("Date",       meta.get("date", str(date.today()))),
        ("Document",   meta.get("document_id", "")),
    ]
    for label, value in fields:
        if value:
            canvas.setFont("Helvetica-Bold", 9)
            canvas.setFillColor(primary)
            canvas.drawString(0.8*inch, y, f"{label}:")
            canvas.setFont("Helvetica", 9)
            canvas.setFillColor(colors.Color(0.2, 0.2, 0.2))
            canvas.drawString(2.2*inch, y, str(value))
            y -= 0.22*inch

    # Classification badge
    classification = meta.get("classification", "")
    if classification:
        badge_colors = {
            "CONFIDENTIAL": (colors.Color(0.7, 0, 0), colors.white),
            "INTERNAL":     (colors.Color(0.8, 0.5, 0), colors.white),
            "PUBLIC":       (colors.Color(0, 0.5, 0.1), colors.white),
        }
        bg, fg = badge_colors.get(classification.upper(), (primary, colors.white))
        bw, bh = 1.4*inch, 0.25*inch
        bx = pw - 0.8*inch - bw
        by = ph * 0.50
        canvas.setFillColor(bg)
        canvas.roundRect(bx, by, bw, bh, 4, fill=1, stroke=0)
        canvas.setFillColor(fg)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawCentredString(bx + bw/2, by + 0.07*inch, classification.upper())

    # Logo area placeholder
    logo_path = meta.get("logo_path", "")
    if logo_path and os.path.isfile(logo_path):
        try:
            img = ImageReader(logo_path)
            iw, ih = img.getSize()
            scale = min(1.2*inch / iw, 0.6*inch / ih)
            canvas.drawImage(logo_path, pw - 0.8*inch - iw*scale, ph*0.76,
                             width=iw*scale, height=ih*scale, mask="auto")
        except Exception:
            pass

    # Bottom bar
    canvas.setFillColor(highlight)
    canvas.rect(0, 0, pw, 0.6*inch, fill=1, stroke=0)
    canvas.setFillColor(primary)
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(pw/2, 0.22*inch, "Generated by pdf-report-generator")
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def build_styles(theme):
    primary   = rgb(theme["primary"])
    accent    = rgb(theme["accent"])
    highlight = rgb(theme["highlight"])
    dark_gray = colors.Color(0.15, 0.15, 0.15)

    s = {}
    s["ReportBody"] = ParagraphStyle(
        "ReportBody", fontName="Helvetica", fontSize=10,
        leading=15, textColor=dark_gray,
        spaceAfter=6, spaceBefore=0,
    )
    s["SectionHeading"] = ParagraphStyle(
        "SectionHeading", fontName="Helvetica-Bold", fontSize=14,
        leading=18, textColor=primary,
        spaceBefore=18, spaceAfter=6,
    )
    s["SubsectionHeading"] = ParagraphStyle(
        "SubsectionHeading", fontName="Helvetica-Bold", fontSize=11,
        leading=15, textColor=primary,
        spaceBefore=12, spaceAfter=4,
    )
    s["ExecSummary"] = ParagraphStyle(
        "ExecSummary", fontName="Helvetica", fontSize=10,
        leading=15, textColor=dark_gray,
        leftIndent=12, rightIndent=12,
        spaceBefore=4, spaceAfter=4,
    )
    s["ExecSummaryTitle"] = ParagraphStyle(
        "ExecSummaryTitle", fontName="Helvetica-Bold", fontSize=11,
        leading=15, textColor=primary,
        spaceBefore=0, spaceAfter=6,
    )
    s["Caption"] = ParagraphStyle(
        "Caption", fontName="Helvetica-Oblique", fontSize=8,
        leading=12, textColor=colors.Color(0.4, 0.4, 0.4),
        alignment=TA_CENTER, spaceAfter=10,
    )
    s["TableHeader"] = ParagraphStyle(
        "TableHeader", fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.white, leading=12,
    )
    s["TableCell"] = ParagraphStyle(
        "TableCell", fontName="Helvetica", fontSize=9,
        textColor=dark_gray, leading=12,
    )
    s["TOCEntry0"] = ParagraphStyle(
        "TOCEntry0", fontName="Helvetica-Bold", fontSize=10,
        textColor=primary, leading=14, leftIndent=0, spaceAfter=2,
    )
    s["TOCEntry1"] = ParagraphStyle(
        "TOCEntry1", fontName="Helvetica", fontSize=9,
        textColor=dark_gray, leading=13, leftIndent=18, spaceAfter=1,
    )
    return s, primary, accent, highlight


# ---------------------------------------------------------------------------
# Chart rendering
# ---------------------------------------------------------------------------

def render_chart(chart_spec, theme, tmp_dir):
    if not HAS_MATPLOTLIB:
        return None
    primary   = tuple(c/255 for c in theme["primary"])
    accent    = tuple(c/255 for c in theme["accent"])
    highlight = tuple(c/255 for c in theme["highlight"])

    palettes = [primary, accent, (0.3, 0.6, 0.8), (0.8, 0.4, 0.1), (0.2, 0.7, 0.4)]

    chart_type = chart_spec.get("type", "bar")
    title      = chart_spec.get("title", "")
    labels     = chart_spec.get("labels", [])
    datasets   = chart_spec.get("datasets", [])

    fig, ax = plt.subplots(figsize=(6, 3.2))
    fig.patch.set_facecolor("white")
    ax.set_facecolor((0.98, 0.98, 0.98))

    if chart_type in ("bar", "horizontal_bar"):
        x = range(len(labels))
        bar_w = 0.8 / max(len(datasets), 1)
        for i, ds in enumerate(datasets):
            offset = (i - len(datasets)/2 + 0.5) * bar_w
            vals = ds.get("values", [])
            clr = palettes[i % len(palettes)]
            if chart_type == "bar":
                ax.bar([xi + offset for xi in x], vals, width=bar_w*0.9,
                       label=ds.get("label", ""), color=clr)
            else:
                ax.barh([xi + offset for xi in x], vals, height=bar_w*0.9,
                        label=ds.get("label", ""), color=clr)
        if chart_type == "bar":
            ax.set_xticks(list(x))
            ax.set_xticklabels(labels, fontsize=8)
        else:
            ax.set_yticks(list(x))
            ax.set_yticklabels(labels, fontsize=8)

    elif chart_type == "line":
        for i, ds in enumerate(datasets):
            clr = palettes[i % len(palettes)]
            ax.plot(labels, ds.get("values", []), marker="o", linewidth=2,
                    color=clr, label=ds.get("label", ""))

    elif chart_type == "pie":
        vals = datasets[0].get("values", []) if datasets else []
        ax.pie(vals, labels=labels, colors=palettes[:len(vals)],
               autopct="%1.1f%%", startangle=90, textprops={"fontsize": 8})
        ax.axis("equal")

    if chart_type != "pie":
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(labelsize=8)

    if any(ds.get("label") for ds in datasets):
        ax.legend(fontsize=8, framealpha=0.8)

    ax.set_title(title, fontsize=10, fontweight="bold", color=primary, pad=8)
    plt.tight_layout(pad=0.8)

    path = os.path.join(tmp_dir, f"chart_{abs(hash(title))}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Table builder
# ---------------------------------------------------------------------------

def build_table(tbl_spec, styles, theme, pw):
    primary   = rgb(theme["primary"])
    accent    = rgb(theme["accent"])
    alt_row   = rgb(theme["highlight"])

    headers = tbl_spec.get("headers", [])
    rows    = tbl_spec.get("rows", [])

    header_cells = [Paragraph(str(h), styles["TableHeader"]) for h in headers]
    data = [header_cells]
    for row in rows:
        data.append([Paragraph(str(c), styles["TableCell"]) for c in row])

    col_count = max(len(headers), 1)
    avail     = pw - 1.2*inch
    col_w     = avail / col_count

    ts = TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  primary),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  9),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0),(-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",(0, 0), (-1, -1), 7),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.Color(0.7, 0.7, 0.7)),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
    ])
    for i in range(1, len(data)):
        if i % 2 == 0:
            ts.add("BACKGROUND", (0, i), (-1, i), alt_row)

    return Table(data, colWidths=[col_w]*col_count, style=ts, repeatRows=1)


# ---------------------------------------------------------------------------
# Executive summary box
# ---------------------------------------------------------------------------

def build_exec_summary(text, styles, theme, pw):
    primary   = rgb(theme["primary"])
    highlight = rgb(theme["highlight"])
    accent    = rgb(theme["accent"])

    title_cell = Paragraph("Executive Summary", styles["ExecSummaryTitle"])
    body_cell  = Paragraph(text.replace("\n", "<br/>"), styles["ExecSummary"])

    ts = TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), highlight),
        ("LEFTPADDING",  (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ("LINEAFTER",    (0, 0), (0, -1),  3, primary),
        ("BOX",          (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.85)),
    ])
    avail = pw - 1.2*inch
    inner = [[title_cell], [body_cell]]
    return Table(inner, colWidths=[avail], style=ts)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_report(spec: dict, output_path: str):
    meta  = spec.get("metadata", {})
    theme = spec.get("theme", {})

    # Resolve theme
    t = dict(THEMES["default"])
    if "primary_color"   in theme: t["primary"]   = tuple(theme["primary_color"])
    if "accent_color"    in theme: t["accent"]     = tuple(theme["accent_color"])
    if "highlight_color" in theme: t["highlight"]  = tuple(theme["highlight_color"])

    # Page size
    page_size_key = meta.get("page_size", "letter").lower()
    pagesize = A4 if page_size_key == "a4" else LETTER
    pw, ph = pagesize

    # Styles
    styles, primary, accent, highlight = build_styles(t)

    # Doc setup
    doc = BaseDocTemplate(
        output_path,
        pagesize=pagesize,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.75*inch, bottomMargin=0.65*inch,
        title=meta.get("title", ""),
        author=meta.get("author", ""),
    )
    doc.report_meta  = meta
    doc.report_theme = t

    from reportlab.platypus import Frame

    cover_frame = Frame(0, 0, pw, ph, leftPadding=0, rightPadding=0,
                        topPadding=0, bottomPadding=0, id="cover")
    body_frame  = Frame(0.6*inch, 0.65*inch,
                        pw - 1.2*inch, ph - 1.4*inch,
                        leftPadding=0, rightPadding=0,
                        topPadding=0, bottomPadding=0, id="body")

    cover_tpl = PageTemplate(id="Cover", frames=[cover_frame], onPage=make_cover_page)
    body_tpl  = PageTemplate(id="Body",  frames=[body_frame],  onPage=make_body_page)
    doc.addPageTemplates([cover_tpl, body_tpl])

    story = []

    # ---- Cover ----
    story.append(NextPageTemplate("Body"))
    story.append(PageBreak())

    # ---- TOC ----
    toc = TableOfContents()
    toc.levelStyles = [styles["TOCEntry0"], styles["TOCEntry1"]]
    story.append(Paragraph("Table of Contents", styles["SectionHeading"]))
    story.append(Spacer(1, 6))
    story.append(toc)
    story.append(PageBreak())

    # ---- Exec Summary ----
    exec_text = spec.get("executive_summary", "")
    if exec_text:
        story.append(build_exec_summary(exec_text, styles, t, pw))
        story.append(Spacer(1, 18))

    # Build placement maps
    tables_by_section = {}
    for tbl in spec.get("tables", []):
        idx = tbl.get("after_section", 0)
        tables_by_section.setdefault(idx, []).append(tbl)

    charts_by_section = {}
    for cht in spec.get("charts", []):
        idx = cht.get("after_section", 0)
        charts_by_section.setdefault(idx, []).append(cht)

    images_by_section = {}
    for img in spec.get("images", []):
        idx = img.get("after_section", 0)
        images_by_section.setdefault(idx, []).append(img)

    tmp_dir = tempfile.mkdtemp()

    sections = spec.get("sections", [])
    for sec_idx, section in enumerate(sections):
        heading = section.get("heading", f"Section {sec_idx+1}")
        body    = section.get("body", "")

        # Numbered heading with rule
        num = sec_idx + 1
        h_para = Paragraph(f"{num}.  {heading}", styles["SectionHeading"])
        story.append(h_para)
        story.append(HRFlowable(width="100%", thickness=0.75,
                                color=rgb(t["accent"]), spaceAfter=6))

        for para_text in body.split("\n\n"):
            para_text = para_text.strip()
            if para_text:
                story.append(Paragraph(para_text, styles["ReportBody"]))

        for sub in section.get("subsections", []):
            story.append(Paragraph(sub.get("heading", ""), styles["SubsectionHeading"]))
            for para_text in sub.get("body", "").split("\n\n"):
                para_text = para_text.strip()
                if para_text:
                    story.append(Paragraph(para_text, styles["ReportBody"]))

        # Tables after this section
        for tbl_spec in tables_by_section.get(sec_idx, []):
            story.append(Spacer(1, 8))
            if tbl_spec.get("title"):
                story.append(Paragraph(tbl_spec["title"], styles["SubsectionHeading"]))
            story.append(build_table(tbl_spec, styles, t, pw))
            story.append(Spacer(1, 8))

        # Charts after this section
        for cht_spec in charts_by_section.get(sec_idx, []):
            chart_path = render_chart(cht_spec, t, tmp_dir)
            if chart_path:
                story.append(Spacer(1, 8))
                avail = pw - 1.2*inch
                img_w = min(avail, 5.5*inch)
                story.append(Image(chart_path, width=img_w, height=img_w*0.52))
                story.append(Paragraph(cht_spec.get("title", ""), styles["Caption"]))

        # Images after this section
        for img_spec in images_by_section.get(sec_idx, []):
            img_path = img_spec.get("path", "")
            if img_path and os.path.isfile(img_path):
                avail = pw - 1.2*inch
                w = min(img_spec.get("width_inches", 5.0)*inch, avail)
                story.append(Spacer(1, 8))
                story.append(Image(img_path, width=w))
                if img_spec.get("caption"):
                    story.append(Paragraph(img_spec["caption"], styles["Caption"]))

    # Multi-pass build for TOC
    doc.multiBuild(story)

    # Cleanup tmp
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate a PDF report from a JSON spec.")
    parser.add_argument("--spec",   help="Path to JSON spec file (omit to read from stdin)")
    parser.add_argument("--output", required=True, help="Output PDF path")
    args = parser.parse_args()

    if args.spec:
        with open(args.spec, "r", encoding="utf-8") as f:
            spec = json.load(f)
    else:
        spec = json.load(sys.stdin)

    build_report(spec, args.output)
    print(f"PDF written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
