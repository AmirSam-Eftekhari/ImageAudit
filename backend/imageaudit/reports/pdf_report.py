"""PDF report built with ReportLab (Platypus)."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..core.models import AuditResult

SEV_COLORS = {"critical": "#dc2626", "high": "#ea580c", "medium": "#ca8a04", "low": "#2563eb", "info": "#64748b"}
_REPLACE = {"≈": "~", "≡": "==", "→": "->", "×": "x", "≤": "<=", "≥": ">=", "—": "-", "–": "-",
            "↔": "<->", "…": "...", "•": "*", "\u00a0": " "}


def _t(text: object) -> str:
    s = str(text)
    for k, v in _REPLACE.items():
        s = s.replace(k, v)
    return escape(s.encode("cp1252", "replace").decode("cp1252"))


def _table(rows, widths=None, header=True) -> Table:
    tbl = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    tbl.setStyle(TableStyle(style))
    return tbl


def pdf_report(result: AuditResult) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"ImageAudit report - {result.dataset.name}",
                            author="ImageAudit")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], alignment=0, fontSize=20, textColor=colors.HexColor("#0f172a"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, spaceBefore=12, textColor=colors.HexColor("#0e7490"))
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11.5)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, textColor=colors.HexColor("#475569"), leading=10)
    d, stats, h = result.dataset, result.statistics, result.health
    t = stats["totals"]
    S: list = [Paragraph(_t(f"ImageAudit report: {d.name}"), h1),
               Paragraph(_t(f"Format {d.format} | mode {result.mode} | scanned {result.created_at} | "
                            f"{result.duration_s}s | ImageAudit v{result.version}"), small),
               Paragraph(_t(d.root), small), Spacer(1, 6)]

    S.append(Paragraph("Dataset overview", h2))
    S.append(_table([["Images", "Valid", "Invalid", "Annotations", "Annotated images", "Classes used/declared"],
                     [t["images_total"], t["images_valid"], t["images_invalid"], t["annotations_total"],
                      t["annotated_images"], f"{t['classes_used']}/{t['classes_declared']}"]]))
    S.append(Spacer(1, 4))
    S.append(_table([["Split", "Images", "Valid", "Annotations", "Missing labels", "Empty labels"]] +
                    [[s["split"], s["images"], s["valid"], s["annotations"], s["missing_labels"], s["empty_labels"]]
                     for s in stats["splits"]]))

    S.append(Paragraph(_t(f"Health score: {h['overall'] if h['overall'] is not None else 'n/a'}  (grade {h['grade'] or 'n/a'})"), h2))
    rows = [["Component", "Measured", "Score", "Weight"]]
    for c in h["components"]:
        m = "n/a" if c["metric"] is None else (f"{c['metric']}x" if c["key"] == "class_balance" else f"{c['metric'] * 100:.2f}%")
        rows.append([_t(c["label"]), m, "n/a" if not c["applicable"] else c["score"], f"{c['effective_weight'] * 100:.0f}%"])
    S.append(_table(rows, [70 * mm, 30 * mm, 25 * mm, 25 * mm]))
    S.append(Paragraph("overall = weighted mean of applicable components; each score = 100 x (1 - min(1, rate / zero_at)).", small))

    S.append(Paragraph(f"Findings ({len(result.findings)})", h2))
    frows = [["Severity", "Category", "Finding", "Affected"]]
    for f in result.findings:
        frows.append([Paragraph(f'<font color="{SEV_COLORS[f.severity]}"><b>{f.severity.upper()}</b></font>', body),
                      Paragraph(_t(f.category), body), Paragraph(_t(f.title), body), f.affected_count])
    S.append(_table(frows, [22 * mm, 30 * mm, 100 * mm, 20 * mm]))
    S.append(Spacer(1, 6))
    for f in result.findings[:25]:
        S.append(Paragraph(f'<font color="{SEV_COLORS[f.severity]}"><b>[{f.severity.upper()}]</b></font> <b>{_t(f.title)}</b>', body))
        S.append(Paragraph(_t(f.description), body))
        S.append(Paragraph("<b>Action:</b> " + _t(f.recommendation), small))
        for e in f.examples[:3]:
            S.append(Paragraph(_t(f"e.g. {e.get('path', '')} ({e.get('split', '')}) {e.get('detail', '')}")[:260], small))
        S.append(Spacer(1, 4))

    S.append(Paragraph("Class distribution", h2))
    classes = stats["classes"][:15]
    if classes:
        drawing = Drawing(170 * mm, max(40, 14 * len(classes) + 20))
        chart = HorizontalBarChart()
        chart.x, chart.y, chart.width, chart.height = 40 * mm, 8, 110 * mm, max(20, 14 * len(classes))
        chart.data = [[c["count"] for c in reversed(classes)]]
        chart.categoryAxis.categoryNames = [_t(c["name"])[:20] for c in reversed(classes)]
        chart.categoryAxis.labels.fontSize = 7
        chart.valueAxis.labels.fontSize = 7
        chart.valueAxis.valueMin = 0
        chart.bars[0].fillColor = colors.HexColor("#0891b2")
        drawing.add(chart)
        S.append(drawing)
    bal = stats["class_balance"]
    S.append(Paragraph(_t(f"Imbalance ratio {bal['imbalance_ratio']} | evenness {bal['evenness']} | unused: "
                          f"{', '.join(bal['unused_classes']) or 'none'}"), small))

    S.append(Paragraph("Image and quality statistics", h2))
    q = stats["quality"]
    S.append(_table([["Flag", "Images"]] + [[k.replace("_", " "), v] for k, v in q["flag_counts"].items()], [60 * mm, 30 * mm]))
    res = stats["resolution"]["top"][:8]
    S.append(Spacer(1, 4))
    S.append(_table([["Resolution", "Images"]] + [[r["label"], r["count"]] for r in res], [60 * mm, 30 * mm]))
    S.append(Paragraph(_t(f"Blur threshold {result.config['quality']['blur_threshold']} (Laplacian variance; heuristic, dataset-dependent)."), small))

    S.append(Paragraph("Duplicate and leakage analysis", h2))
    ds = stats["duplicates"]
    S.append(Paragraph(_t(f"{ds['groups']} duplicate groups: {ds['exact_groups']} exact, {ds['perceptual_groups']} perceptual; "
                          f"{ds['within_split_groups']} within a split, {ds['cross_split_groups']} across splits."), body))
    lk = result.leakage
    if lk["pairs"]:
        S.append(_table([["Splits", "Exact groups", "Near-dup groups", "Images"]] +
                        [[f"{p['a']} <-> {p['b']}", p["exact_groups"], p["perceptual_groups"], f"{p['images_a']} + {p['images_b']}"]
                         for p in lk["pairs"]]))
    else:
        S.append(Paragraph("No cross-split duplicates detected." if lk["applicable"] else "Single split: leakage not applicable.", body))
    S.append(Paragraph(_t(lk["note"]), small))
    doc.build(S)
    return buf.getvalue()
