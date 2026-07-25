"""
render_pdf.py — BundleModel -> PDF bytes (engine/, no I/O).

The PDF is the AUTHORITATIVE artifact: locked, portable, what goes to council, the AG, or
an external auditor. Walks the same model as render_docx, so the two never diverge.

reportlab is imported LAZILY, inside render(), so importing this module — and therefore
the entire FastAPI app whose route chain reaches here — never hard-fails when reportlab is
absent. A missing renderer degrades to a clean "install reportlab" error at generation
time instead of taking down app import. (That import-time coupling is exactly what broke
the local test gate before reportlab was installed.)
"""
from __future__ import annotations

from typing import Any, Dict, List


def render(model: Dict[str, Any]) -> bytes:
    """BundleModel -> PDF bytes. Requires reportlab (see requirements.txt)."""
    try:
        import io
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                        TableStyle, HRFlowable, PageBreak, ListFlowable, ListItem)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "PDF rendering requires the 'reportlab' package (see requirements.txt). "
            "Install it with: pip install reportlab") from exc

    NAVY = colors.HexColor("#1565C0")
    SLATE = colors.HexColor("#37474F")
    GREY = colors.HexColor("#6B7280")
    DARK = colors.HexColor("#0E1116")
    LINE = colors.HexColor("#D5DCE3")
    LGREY = colors.HexColor("#EEF2F6")

    ss = getSampleStyleSheet()

    def S(name, **kw):
        kw.setdefault("parent", ss["Normal"])
        return ParagraphStyle(name, **kw)

    BODY = S("body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=SLATE)
    H1 = S("h1", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=NAVY, spaceBefore=10, spaceAfter=5)
    H2 = S("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=DARK, spaceBefore=7, spaceAfter=2)
    SMALL = S("small", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=GREY)
    LEAD = S("lead", fontName="Helvetica-Bold", fontSize=11, leading=14.5, textColor=SLATE)
    TCELL = S("tcell", fontName="Helvetica", fontSize=8.3, leading=10.5, textColor=SLATE)
    THEAD = S("thead", fontName="Helvetica-Bold", fontSize=8.3, leading=10.5, textColor=colors.white)
    COVER_T = S("cover_t", fontName="Helvetica-Bold", fontSize=25, leading=29, textColor=NAVY, alignment=TA_CENTER)
    COVER_C = S("cover_c", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=SLATE, alignment=TA_CENTER)
    COVER_S = S("cover_s", fontName="Helvetica", fontSize=11, leading=15, textColor=SLATE, alignment=TA_CENTER)
    CTRL = S("ctrl", fontName="Helvetica", fontSize=7.5, leading=10, textColor=GREY, alignment=TA_CENTER)

    def kv_table(facts, width):
        data = [[Paragraph(f["label"], S("kl", parent=TCELL, fontName="Helvetica-Bold", textColor=DARK)),
                 Paragraph(str(f["value"]), TCELL)] for f in facts]
        t = Table(data, colWidths=[width * 0.38, width * 0.62])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        return t

    def grid(headers, rows, width, ratios=None):
        ratios = ratios or [1.0 / len(headers)] * len(headers)
        cw = [width * r for r in ratios]
        data = [[Paragraph(h, THEAD) for h in headers]]
        for row in rows:
            data.append([Paragraph(str(c), TCELL) for c in row])
        t = Table(data, colWidths=cw, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5),
                 ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
        for ri in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, ri), (-1, ri), LGREY))
        t.setStyle(TableStyle(style))
        return t

    def bullets(items):
        return ListFlowable([ListItem(Paragraph(t, BODY), leftIndent=10, value="•") for t in items],
                            bulletType="bullet", bulletColor=NAVY, leftIndent=8)

    meta = model["meta"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title=meta.get("preset_title", "TRAIGA Report"))
    W = doc.width
    story: List[Any] = []

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(0.85 * inch, 0.45 * inch, f"CONFIDENTIAL  |  {meta.get('city','')}  |  {meta.get('doc_id','')}")
        canvas.drawRightString(letter[0] - 0.85 * inch, 0.45 * inch, f"Page {d.page}")
        canvas.restoreState()

    for sec in model["sections"]:
        k = sec["kind"]
        if k == "cover":
            story += [Spacer(1, 1.6 * inch), Paragraph(sec["title"], COVER_T), Spacer(1, 10),
                      Paragraph(sec.get("subtitle", ""), COVER_S), Spacer(1, 26),
                      Paragraph(sec.get("city", ""), COVER_C), Spacer(1, 40),
                      Paragraph(f"Prepared for: {sec.get('audience','')}", COVER_S), Spacer(1, 1.4 * inch),
                      HRFlowable(width="60%", thickness=0.7, color=LINE), Spacer(1, 6),
                      Paragraph(f"Document ID {meta['doc_id']} &nbsp;·&nbsp; Generated {meta['generated_utc']}<br/>"
                                f"Tool release {meta['tool_release']} &nbsp;·&nbsp; Content SHA-256 {meta['content_sha256']}", CTRL),
                      PageBreak()]
        elif k == "provenance_summary":
            story += [Paragraph(sec["title"], H1), Paragraph(sec["headline"], LEAD), Spacer(1, 8)]
            rows = [[r["source"], str(r["count"]), "Discovered" if r["discovered"] else "Declared"] for r in sec["rows"]]
            if rows:
                story.append(grid(["Source", "Count", "Origin"], rows, W, [0.6, 0.15, 0.25]))
        elif k == "exec_status":
            story += [Paragraph(sec["title"], H1), kv_table(sec["facts"], W), Spacer(1, 8),
                      Paragraph(sec["background"], BODY), Spacer(1, 6), Paragraph(sec["notice"], SMALL)]
        elif k == "asset_inventory":
            story += [Paragraph(sec["title"], H1), Paragraph(sec["intro"], BODY), Spacer(1, 6)]
            rows = sec.get("rows", [])
            if rows:
                story.append(grid(["Vendor / System", "Type", "Source", "Conf.", "Status"],
                                  [[r["vendor"], r["type"], r["source"], r["confidence"], r["status"]] for r in rows],
                                  W, [0.26, 0.16, 0.30, 0.10, 0.18]))
            else:
                story.append(Paragraph(sec.get("empty", "None."), BODY))
        elif k == "compliance_detail":
            story += [Paragraph(sec["title"], H1), kv_table(sec["facts"], W), Spacer(1, 6), Paragraph(sec["note"], SMALL)]
        elif k == "violations":
            story.append(Paragraph(sec["title"], H1))
            items = sec.get("items", [])
            if not items:
                story.append(Paragraph(sec.get("empty", "None."), BODY))
            else:
                story.append(Paragraph(sec["intro"], BODY))
                for i, v in enumerate(items, start=1):
                    story.append(Paragraph(f"Finding {i}: {v['rule_id']} — {v['citation']}", H2))
                    facts = [{"label": "Severity", "value": v["severity"]}, {"label": "Status", "value": v["status"]},
                             {"label": "First observed", "value": v["first_observed"]},
                             {"label": "Cure deadline", "value": v["cure_deadline"]}]
                    if v.get("days_remaining") is not None:
                        facts.append({"label": "Days remaining", "value": str(v["days_remaining"])})
                    if v.get("remediation"):
                        facts.append({"label": "Remediation", "value": v["remediation"]})
                    story.append(kv_table(facts, W))
                    story.append(Spacer(1, 6))
        elif k == "recommendations":
            story += [Paragraph(sec["title"], H1), bullets(sec["items"])]
        elif k == "statutory_reference":
            story.append(Paragraph(sec["title"], H1))
            story.append(kv_table([{"label": it["citation"], "value": it["text"]} for it in sec["items"]], W))
        elif k == "methodology":
            story.append(Paragraph(sec["title"], H1))
            for para in sec["paragraphs"]:
                story += [Paragraph(para, BODY), Spacer(1, 4)]
        elif k == "attestation":
            story += [Paragraph(sec["title"], H1), Paragraph(sec["statement"], BODY), Spacer(1, 16)]
            for field in sec["fields"]:
                story += [Paragraph(f"<b>{field}:</b> ______________________________________", BODY), Spacer(1, 12)]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
