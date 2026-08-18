#!/usr/bin/env python3
"""
Genera el PDF consolidado del proyecto de vocabulario + ALCPT.

Uso:
    python scripts/build_pdf.py
    python scripts/build_pdf.py --out output/mi_nombre.pdf

Lee:  data/vocabulary.json, data/phrasal_verbs.json, data/idioms.json y data/forms.json
Escribe: output/ALCPT_Vocabulario_y_Examenes.pdf

Preferencia fija del usuario: TODOS los párrafos van justificados.
"""

import argparse
import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

INK = colors.HexColor("#1b1b1b")
ACCENT = colors.HexColor("#8c2f39")
SOFT = colors.HexColor("#f4e6e8")
GREY = colors.HexColor("#5d5d5d")
RULE = colors.HexColor("#d8c3c6")


def esc(text):
    """Escapa caracteres reservados del mini-XML de ReportLab."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_styles():
    ss = getSampleStyleSheet()
    s = {}

    s["cover_title"] = ParagraphStyle(
        "cover_title", parent=ss["Title"], fontName="Times-Bold",
        fontSize=30, leading=36, textColor=ACCENT, alignment=TA_CENTER,
        spaceAfter=6,
    )
    s["cover_sub"] = ParagraphStyle(
        "cover_sub", parent=ss["Normal"], fontName="Times-Italic",
        fontSize=14, leading=20, textColor=GREY, alignment=TA_CENTER,
    )
    s["cover_meta"] = ParagraphStyle(
        "cover_meta", parent=ss["Normal"], fontName="Helvetica",
        fontSize=10, leading=16, textColor=GREY, alignment=TA_CENTER,
    )
    s["h1"] = ParagraphStyle(
        "h1", parent=ss["Heading1"], fontName="Times-Bold",
        fontSize=20, leading=24, textColor=ACCENT,
        spaceBefore=0, spaceAfter=10,
    )
    s["h2"] = ParagraphStyle(
        "h2", parent=ss["Heading2"], fontName="Times-Bold",
        fontSize=14, leading=18, textColor=INK,
        spaceBefore=14, spaceAfter=6,
    )
    s["h3"] = ParagraphStyle(
        "h3", parent=ss["Heading3"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=14, textColor=ACCENT,
        spaceBefore=10, spaceAfter=3,
    )
    # Justificado: preferencia fija.
    s["body"] = ParagraphStyle(
        "body", parent=ss["Normal"], fontName="Times-Roman",
        fontSize=10.5, leading=15, textColor=INK,
        alignment=TA_JUSTIFY, spaceAfter=6,
    )
    s["note"] = ParagraphStyle(
        "note", parent=s["body"], fontName="Times-Italic",
        fontSize=9.5, leading=13.5, textColor=GREY,
    )
    s["vocab"] = ParagraphStyle(
        "vocab", parent=s["body"], fontSize=10, leading=14,
        spaceAfter=0, alignment=TA_JUSTIFY,
    )
    s["opt"] = ParagraphStyle(
        "opt", parent=s["body"], fontSize=10, leading=13.5,
        leftIndent=14, spaceAfter=1, alignment=TA_JUSTIFY,
    )
    s["expl"] = ParagraphStyle(
        "expl", parent=s["body"], fontSize=10, leading=14.5,
        leftIndent=0, spaceBefore=4, spaceAfter=2, alignment=TA_JUSTIFY,
    )
    s["qstem"] = ParagraphStyle(
        "qstem", parent=s["body"], fontName="Times-Bold",
        fontSize=10.5, leading=14.5, spaceBefore=10, spaceAfter=3,
        alignment=TA_JUSTIFY,
    )
    s["pv_verb"] = ParagraphStyle(
        "pv_verb", parent=s["body"], fontName="Times-Bold", fontSize=11.5,
        leading=15, textColor=ACCENT, spaceBefore=9, spaceAfter=1,
        alignment=TA_JUSTIFY,
    )
    s["pv_mean"] = ParagraphStyle(
        "pv_mean", parent=s["body"], fontSize=10, leading=13.5,
        spaceAfter=1, alignment=TA_JUSTIFY,
    )
    s["pv_trap"] = ParagraphStyle(
        "pv_trap", parent=s["body"], fontSize=9.5, leading=13, textColor=GREY,
        leftIndent=12, spaceAfter=1, alignment=TA_JUSTIFY,
    )
    s["pv_ex"] = ParagraphStyle(
        "pv_ex", parent=s["body"], fontName="Times-Italic", fontSize=9.5,
        leading=13, leftIndent=12, spaceAfter=5, alignment=TA_JUSTIFY,
    )
    return s


def page_furniture(canvas, doc):
    if doc.page == 1:  # la portada va limpia
        return
    canvas.saveState()
    w, h = letter
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(2.2 * cm, 1.5 * cm, "Vocabulario en inglés y ALCPT · Brayhan")
    canvas.drawRightString(w - 2.2 * cm, 1.5 * cm, f"Página {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(2.2 * cm, 1.9 * cm, w - 2.2 * cm, 1.9 * cm)
    canvas.restoreState()


def cover(story, s, vocab, forms, pv, idioms):
    total = vocab["meta"]["total_confirmed"]
    form_ids = ", ".join(str(f["form"]) for f in forms["forms"])
    total_q = sum(len(f["questions"]) for f in forms["forms"])
    total_pv = sum(len(g["entries"]) for g in pv["groups"])
    total_id = sum(len(g["entries"]) for sec in idioms["sections"] for g in sec["groups"])
    story.append(Spacer(1, 4.5 * cm))
    story.append(Paragraph("Vocabulario en inglés<br/>y exámenes ALCPT", s["cover_title"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Listado acumulado con traducciones al español y banco de preguntas resueltas", s["cover_sub"]))
    story.append(Spacer(1, 2.2 * cm))

    rows = [
        ["Estudiante", vocab["meta"]["owner"]],
        ["Nivel de referencia", vocab["meta"]["level"]],
        ["Palabras confirmadas", str(total)],
        ["Formularios documentados", form_ids],
        ["Phrasal verbs explicados", str(total_pv)],
        ["Idioms y términos militares", str(total_id)],
        ["Preguntas documentadas", str(total_q)],
        ["Actualizado", date.today().isoformat()],
    ]
    t = Table(rows, colWidths=[6 * cm, 7 * cm], hAlign="CENTER")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), ACCENT),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(PageBreak())


def vocabulary_part(story, s, vocab):
    story.append(Paragraph("Parte I · Vocabulario completo", s["h1"]))
    story.append(Paragraph(
        "Listado acumulado de todas las palabras y expresiones registradas hasta la fecha, con su "
        "traducción y matices de uso en español. Las secciones respetan el origen de cada término: "
        "primero las palabras aportadas directamente y después las extraídas de cada formulario del ALCPT.",
        s["body"]))

    for section in vocab["sections"]:
        story.append(Paragraph(esc(section["title"]), s["h2"]))
        if section.get("subtitle"):
            story.append(Paragraph(esc(section["subtitle"]), s["note"]))

        rows = []
        for e in section["entries"]:
            num = Paragraph(f'<font color="#8c2f39"><b>{e["n"]}</b></font>', s["vocab"])
            word = Paragraph(f'<b>{esc(e["en"])}</b>', s["vocab"])
            meaning = Paragraph(esc(e["es"]), s["vocab"])
            rows.append([num, word, meaning])

        t = Table(rows, colWidths=[1.1 * cm, 5.1 * cm, 10.3 * cm], repeatRows=0)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#fbf6f7")]),
        ]))
        story.append(t)

    # cualquier bloque pending_* que siga esperando el filtrado de Brayhan
    for key in sorted(k for k in vocab if k.startswith("pending_")):
        pend = vocab[key]
        if not pend.get("candidates"):
            continue
        origen = key[len("pending_"):]
        story.append(Paragraph(
            f"Apéndice · Candidatos pendientes de filtrado ({esc(origen)})", s["h2"]))
        story.append(Paragraph(esc(pend["note"]), s["note"]))
        rows = []
        for e in pend["candidates"]:
            rows.append([
                Paragraph(f'<b>{esc(e["en"])}</b>', s["vocab"]),
                Paragraph(esc(e["es"]), s["vocab"]),
            ])
        t = Table(rows, colWidths=[5.6 * cm, 10.9 * cm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
            ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ]))
        story.append(t)

    story.append(PageBreak())


def _entry(story, s, e):
    """Una expresión: título, etiqueta, significado, trampa, ejemplo y origen."""
    expr = e.get("expr") or e.get("verb")
    tag = e.get("tag") or e.get("sep") or ""
    block = []
    cabeza = esc(expr)
    if tag:
        cabeza += f'  <font size="7" color="#5d5d5d">[{esc(tag).upper()}]</font>'
    block.append(Paragraph(cabeza, s["pv_verb"]))
    block.append(Paragraph(esc(e["es"]), s["pv_mean"]))
    if e.get("trap"):
        block.append(Paragraph(esc(e["trap"]), s["pv_trap"]))
    block.append(Paragraph(
        f'&#8220;{esc(e["example"])}&#8221;  '
        f'<font size="7" color="#5d5d5d">{esc(e["source"])}</font>', s["pv_ex"]))
    story.append(KeepTogether(block))


def _keys(story, s, meta):
    for k in meta["keys"]:
        story.append(Paragraph(f"&#8226; {esc(k)}", s["note"]))


def phrasal_part(story, s, pv):
    story.append(Paragraph("Parte II · Phrasal verbs de los formularios 50 a 87", s["h1"]))
    story.append(Paragraph(esc(pv["meta"]["intro"]), s["body"]))
    _keys(story, s, pv["meta"])
    for g in pv["groups"]:
        story.append(Paragraph(esc(g["particle"]), s["h2"]))
        story.append(Paragraph(esc(g["sense"]), s["note"]))
        for e in g["entries"]:
            _entry(story, s, e)
    story.append(PageBreak())


def idioms_part(story, s, idioms):
    story.append(Paragraph("Parte III · Idioms y expresiones militares", s["h1"]))
    story.append(Paragraph(esc(idioms["meta"]["intro"]), s["body"]))
    _keys(story, s, idioms["meta"])
    for sec in idioms["sections"]:
        story.append(Paragraph(esc(sec["title"]), s["h1"]))
        story.append(Paragraph(esc(sec["note"]), s["note"]))
        for g in sec["groups"]:
            story.append(Paragraph(esc(g["theme"]), s["h2"]))
            story.append(Paragraph(esc(g["sense"]), s["note"]))
            for e in g["entries"]:
                _entry(story, s, e)
    story.append(PageBreak())


def forms_part(story, s, forms):
    story.append(Paragraph("Parte IV · Preguntas ALCPT resueltas", s["h1"]))
    story.append(Paragraph(
        "Each item below reproduces the question, all answer options, the correct answer and a detailed "
        "explanation. This part is written entirely in English on purpose, so that reviewing it doubles "
        "as reading practice at test level.",
        s["body"]))

    for form in forms["forms"]:
        story.append(Paragraph(f'Form {esc(form["form"])}', s["h2"]))
        for q in form["questions"]:
            block = []
            label = f'{q["n"]}.' if q.get("n") else "—"
            block.append(Paragraph(f'{label} {esc(q["question"])}', s["qstem"]))
            for opt in q["options"]:
                if opt == q["correct"]:
                    block.append(Paragraph(
                        f'&#8211; <b><font color="#1f7a3d">{esc(opt)}</font></b>  '
                        f'<font size="8" color="#1f7a3d">[CORRECT]</font>', s["opt"]))
                else:
                    block.append(Paragraph(f'&#8211; {esc(opt)}', s["opt"]))
            if q["correct"] not in q["options"]:
                # respuesta no visible en la captura: se deja explícita igualmente
                block.append(Paragraph(
                    f'<b>Correct answer.</b> {esc(q["correct"])}', s["opt"]))
            block.append(Paragraph(
                f'<b>Explanation.</b> {esc(q["explanation"])}', s["expl"]))
            story.append(KeepTogether(block))
        story.append(Spacer(1, 0.3 * cm))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUTPUT / "ALCPT_Vocabulario_y_Examenes.pdf"))
    args = ap.parse_args()

    vocab = json.loads((DATA / "vocabulary.json").read_text(encoding="utf-8"))
    forms = json.loads((DATA / "forms.json").read_text(encoding="utf-8"))
    pv = json.loads((DATA / "phrasal_verbs.json").read_text(encoding="utf-8"))
    idioms = json.loads((DATA / "idioms.json").read_text(encoding="utf-8"))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = BaseDocTemplate(
        str(out_path), pagesize=letter,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.0 * cm, bottomMargin=2.4 * cm,
        title="Vocabulario en inglés y exámenes ALCPT",
        author="Brayhan", subject="Vocabulario B2 + ALCPT",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[frame], onPage=page_furniture),
    ])

    s = build_styles()
    story = []
    cover(story, s, vocab, forms, pv, idioms)
    vocabulary_part(story, s, vocab)
    phrasal_part(story, s, pv)
    idioms_part(story, s, idioms)
    forms_part(story, s, forms)

    doc.build(story)
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
