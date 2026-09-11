#!/usr/bin/env python3
"""Convierte una captura del ALCPT en una pregunta de data/forms.json, sin IA.

Cadena completa y local: OCR (ocr_capture.py) → reglas de texto → color de la
opción resaltada → escritura en forms.json sin duplicar. No usa Claude Code ni
ninguna red. Si algo no cuadra (no se ve el formulario, no hay opciones), no
toca los datos: deja el texto OCR junto a la captura y explica qué faltó.

Uso:
    python scripts/parse_capture.py inbox/tg_xxx.jpg             # parsea y guarda
    python scripts/parse_capture.py inbox/tg_xxx.jpg --dry-run   # solo muestra
    python scripts/parse_capture.py inbox/tg_xxx.jpg --json      # resultado JSON

Códigos de salida: 0 = guardada (o ya existía) · 2 = no se pudo estructurar ·
1 = error.

Supuestos sobre la app del ALCPT (calibrar con capturas reales):
- El encabezado dice el formulario: «Form 87», «ALCPT 87», «Formulario 87».
- El número del ítem aparece como «Question 42», «Q42», «42.» o «42)».
- Las opciones van en renglones propios, con o sin letra («A.», «b)»).
- En la pantalla de repaso la opción correcta va resaltada en verde y debajo
  hay un bloque «Explanation».
- En la pantalla del examen no hay explicación ni resaltado: se registra con
  la nota «(Not shown — captured during the test, before the review screen.)»,
  igual que las 21 preguntas que ya están así.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_capture import ocr  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FORMS = REPO / "data" / "forms.json"
NOT_SHOWN = "(Not shown — captured during the test, before the review screen.)"
NOT_SHOWN_EXPL = ("Listening comprehension item. Only the answer choices were "
                  "captured, so the correct option and its explanation were not recorded.")

RE_FORM = re.compile(r"\b(?:form(?:ulario)?|alcpt)\s*#?\s*(\d{2,3})\b", re.I)
RE_QNUM = re.compile(r"\b(?:question|item|pregunta|q)\s*#?\s*(\d{1,3})\b", re.I)
RE_QNUM_LEAD = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*(.*)$")
RE_OPTION = re.compile(r"^\s*\(?([A-Da-d])\s*[.):]\s*(.*)$")
RE_EXPL = re.compile(r"^\s*explanation\s*[:.]?\s*(.*)$", re.I)
RE_CORRECT_LINE = re.compile(r"^\s*correct\s*(?:answer)?\s*[:.]?\s*(.*)$", re.I)
NOISE = re.compile(r"^\s*(?:\d{1,2}:\d{2}|[\d.]+\s*%|next|previous|submit|review|"
                   r"back|home|menu)\s*$", re.I)


# --- color: qué opción está resaltada ---------------------------------------
def highlighted_index(image_path: Path, option_rows, scale) -> int | None:
    """Índice de la opción cuya franja horizontal es la más saturada.

    Cada opción ocupa una tarjeta que va de borde a borde; se promedia el color
    de una franja a la altura de su texto (el texto es una fracción mínima de
    los píxeles). La correcta en la app va sobre verde: sobresale en saturación
    respecto a las otras, que van sobre blanco o gris. Si ninguna sobresale de
    verdad, se devuelve None y el llamador lo trata como «no resaltada»."""
    if len(option_rows) < 2:
        return None
    img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    w, h = img.size
    scores = []
    for r in option_rows:
        y = int(r["y"] * scale)
        half = max(4, int(r["h"] * scale * 0.5))
        box = (int(w * 0.05), max(0, y - half), int(w * 0.95), min(h, y + half))
        rm, gm, bm = ImageStat.Stat(img.crop(box)).mean
        sat = max(rm, gm, bm) - min(rm, gm, bm)
        greenish = gm - max(rm, bm)
        scores.append((sat, greenish))
    sats = sorted(s for s, _ in scores)
    best = max(range(len(scores)), key=lambda i: scores[i])
    best_sat, best_green = scores[best]
    others = sats[:-1]
    baseline = others[len(others) // 2] if others else 0
    # tiene que ser claramente más saturada que las demás y tirar a verde
    if best_sat >= 12 and best_sat >= baseline + 8 and best_green > 0:
        return best
    return None


# --- palabras pegadas ---------------------------------------------------------
_SEG_READY = False


def unglue(text: str) -> str:
    """El OCR a veces devuelve «Thesailorcansteer»: se parte con wordsegment
    (unigramas y bigramas de inglés) solo en tokens largos y puramente
    alfabéticos, para no tocar siglas, números ni palabras normales."""
    global _SEG_READY
    try:
        import wordsegment as ws
    except ImportError:
        return text
    if not _SEG_READY:
        ws.load()
        _SEG_READY = True

    def fix(m):
        tok = m.group(0)
        parts = ws.segment(tok)
        if len(parts) < 2:
            return tok
        out = " ".join(parts)
        if tok[0].isupper():
            out = out[0].upper() + out[1:]
        return out

    return re.sub(r"[A-Za-z]{13,}", fix, text)


# --- texto: de renglones OCR a campos -----------------------------------------
def parse_rows(rows):
    """Devuelve (pregunta, faltantes). `pregunta` es un dict con form, n,
    question, options, correct, explanation; `faltantes` lista lo que no se
    pudo determinar (vacía si todo cuadró)."""
    form = None
    n = None
    stem, options, expl = [], [], []
    option_rows = []
    correct_text = None
    stage = "head"   # head → stem → options → explanation

    for r in rows:
        line = r["text"].strip()
        if not line or NOISE.match(line):
            continue
        m = RE_FORM.search(line)
        if m and form is None:
            form = m.group(1)
        m = RE_QNUM.search(line)
        if m and n is None:
            n = int(m.group(1))
            # el resto del renglón puede ser el enunciado
            rest = RE_QNUM.sub("", RE_FORM.sub("", line))
            rest = re.sub(r"\balcpt\b", "", rest, flags=re.I).strip(" -:·|—")
            if rest and stage in ("head", "stem"):
                stem.append(rest)
                stage = "stem"
            continue
        if form is not None and stage == "head" and RE_FORM.search(line):
            continue   # renglón de encabezado sin más contenido

        m = RE_EXPL.match(line)
        if m:
            stage = "explanation"
            if m.group(1):
                expl.append(m.group(1))
            continue
        m = RE_CORRECT_LINE.match(line)
        if m and stage != "explanation":
            correct_text = m.group(1).strip()
            continue

        if stage == "explanation":
            expl.append(line)
            continue

        m = RE_OPTION.match(line)
        if m:
            stage = "options"
            options.append(m.group(2).strip())
            option_rows.append(r)
            continue
        m = RE_QNUM_LEAD.match(line)
        if m and n is None and stage in ("head", "stem"):
            n = int(m.group(1))
            if m.group(2):
                stem.append(m.group(2))
            stage = "stem"
            continue
        if stage == "options" and len(options) < 4:
            # renglón sin letra entre opciones: el OCR se comió el prefijo
            options.append(line)
            option_rows.append(r)
            continue
        if stage in ("head", "stem"):
            stage = "stem"
            stem.append(line)

    q = {
        "form": form,
        "n": n,
        "question": unglue(" ".join(stem).strip()),
        "options": [unglue(o) for o in options if o],
        "correct": correct_text,
        "explanation": unglue(" ".join(expl).strip()),
        "_option_rows": option_rows,
    }
    missing = []
    if not form:
        missing.append("formulario (no se lee «Form NN» en la captura)")
    if n is None:
        missing.append("número de pregunta")
    if len(q["options"]) < 2:
        missing.append("opciones (se leyeron menos de 2)")
    if not q["question"]:
        q["question"] = "(Listening item — the audio prompt is not visible in the screenshot.)"
    return q, missing


def resolve_correct(q, image_path, scale):
    """Fija `correct` y `explanation` según lo que muestre la captura."""
    if q["correct"]:
        # «Correct answer: B» o el texto de la opción
        c = q["correct"]
        m = re.fullmatch(r"\(?([A-Da-d])\)?\.?", c)
        if m:
            i = "ABCD".index(m.group(1).upper())
            if i < len(q["options"]):
                q["correct"] = q["options"][i]
        return
    idx = highlighted_index(image_path, q["_option_rows"], scale)
    if idx is not None and idx < len(q["options"]):
        q["correct"] = q["options"][idx]
        return
    # sin resaltado ni texto de respuesta: pantalla del examen
    q["correct"] = NOT_SHOWN
    if not q["explanation"]:
        q["explanation"] = NOT_SHOWN_EXPL


# --- forms.json --------------------------------------------------------------
def save(q) -> str:
    data = json.loads(FORMS.read_text(encoding="utf-8"))
    section = next((f for f in data["forms"] if str(f["form"]) == q["form"]), None)
    if section is None:
        section = {"form": q["form"], "questions": []}
        data["forms"].append(section)
        data["forms"].sort(key=lambda f: (not str(f["form"]).isdigit(),
                                          int(f["form"]) if str(f["form"]).isdigit() else 0,
                                          str(f["form"])))
    existing = next((x for x in section["questions"] if x.get("n") == q["n"]), None)
    entry = {k: q[k] for k in ("n", "question", "options", "correct", "explanation")}
    if existing:
        # ya estaba; si la nueva trae respuesta y la vieja no, se completa
        if existing.get("correct") == NOT_SHOWN and q["correct"] != NOT_SHOWN:
            existing.update(entry)
            status = "completada"
        else:
            return f"Form {q['form']} #{q['n']} ya estaba documentada; no se cambió nada."
    else:
        section["questions"].append(entry)
        section["questions"].sort(key=lambda x: (x.get("n") is None, x.get("n") or 0))
        status = "agregada"
    meta = data.setdefault("meta", {})
    meta["last_updated"] = date.today().isoformat()
    meta["total_questions"] = sum(len(f["questions"]) for f in data["forms"])
    docs = meta.setdefault("forms_documented", [])
    if q["form"] not in docs:
        docs.append(q["form"])
    FORMS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"Form {q['form']} #{q['n']} {status} ({'sin respuesta visible' if q['correct'] == NOT_SHOWN else 'con respuesta y explicación'})."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="no escribe forms.json")
    ap.add_argument("--json", action="store_true", help="imprime el resultado en JSON")
    args = ap.parse_args()
    if not args.image.exists():
        print(f"No existe: {args.image}", file=sys.stderr)
        return 1

    res = ocr(args.image)
    txt_path = args.image.with_suffix(".txt")
    txt_path.write_text(res["text"], encoding="utf-8")   # queda para revisar a mano
    if not res["usable"]:
        out = {"ok": False, "reason": f"OCR poco fiable (confianza {res['confidence']:.2f}, "
                                      f"{res['lines']} renglones)", "text": res["text"]}
        print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
        return 2

    q, missing = parse_rows(res["rows"])
    if missing:
        out = {"ok": False, "reason": "No pude estructurar la captura. Falta: " + "; ".join(missing),
               "text": res["text"], "partial": {k: v for k, v in q.items() if not k.startswith("_")}}
        print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
        return 2
    resolve_correct(q, args.image, res["scale"])
    q.pop("_option_rows", None)

    message = "(dry-run, no se guardó) " + json.dumps(q, ensure_ascii=False) if args.dry_run else save(q)
    out = {"ok": True, "message": message, "question": q, "confidence": res["confidence"]}
    print(json.dumps(out, ensure_ascii=False) if args.json else message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
