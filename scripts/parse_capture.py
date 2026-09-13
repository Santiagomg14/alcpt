#!/usr/bin/env python3
"""Convierte una captura de la app del ALCPT en una pregunta de data/forms.json,
sin IA: OCR local (ocr_capture.py) → reglas → color → forms.json sin duplicar.

La app (modo revisión, fondo oscuro) tiene dos pantallas por ítem, y Brayhan
puede mandar una, la otra o las dos, en cualquier orden:

  Pantalla de pregunta          Pantalla de explicación
  ┌ Form 65 ───────────┐        ┌ Form 65 ───────────────────┐
  │ 92. Do you ___ if… │        │ 92. 92 Do you ___ if…      │  (caja de color)
  │  ○ want            │        │ Answer: 92)                │
  │  ○ wish            │        │ Correct Answer "mind"      │
  │  ○ like            │        │ Explanation:               │
  │  ◉ mind   (verde)  │        │  • …                       │
  │      End Review    │        │ Incorrect Answers:         │
  └────────────────────┘        │  • "want" is incorrect …   │
                                │  like  mind  (opciones que │
                                │  siguen debajo, cortadas)  │
                                └────────────────────────────┘

De la primera salen número, enunciado, opciones y la correcta (texto verde).
De la segunda salen número, enunciado, la correcta (entre comillas) y la
explicación. Las dos se funden en forms.json: cada campo se completa con lo
que aún falte. Si solo llega la de pregunta y no hay verde (pantalla del
examen, no de revisión), se registra con la nota «(Not shown — …)».

Uso:
    python scripts/parse_capture.py inbox/tg_xxx.jpg             # parsea y guarda
    python scripts/parse_capture.py inbox/tg_xxx.jpg --dry-run   # solo muestra
    python scripts/parse_capture.py inbox/tg_xxx.jpg --json

Códigos de salida: 0 = guardada o fundida · 2 = no se pudo estructurar · 1 = error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_capture import ocr, ocr_crop  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FORMS = REPO / "data" / "forms.json"
NOT_SHOWN = "(Not shown — captured during the test, before the review screen.)"
NOT_SHOWN_EXPL = ("Listening comprehension item. Only the answer choices were "
                  "captured, so the correct option and its explanation were not recorded.")
NO_EXPL_YET = "(Explanation screen not captured yet.)"
NO_OPTIONS_YET = "(Options screen not captured yet.)"
NO_STEM_YET = "(Question stem not captured yet — only the explanation screen was sent.)"
NO_ANSWER_YET = "(Correct answer not visible in this capture.)"
UNREADABLE = "(unreadable option — marked in red)"
PLACEHOLDERS = {NOT_SHOWN, NOT_SHOWN_EXPL, NO_EXPL_YET, NO_OPTIONS_YET, NO_STEM_YET,
                NO_ANSWER_YET, UNREADABLE, ""}

RE_FORM = re.compile(r"\b(?:form(?:ulario)?|alcpt)\s*#?\s*(\d{2,3})\b", re.I)
RE_STATUS = re.compile(r"\b\d{1,2}:\d{2}\b.*\b(?:4g|5g|lte|wifi|\d{1,3})\b", re.I)
RE_NOISE = re.compile(r"^\s*(?:end\s*review|cc|next|previous|submit|answer\s*:?\s*\d*\s*\)?)\s*$", re.I)
# «56. Phyllis…», «56. 56 Phyllis…», «54.54the…», «10 When…»; nunca «6:51»
RE_STEM_NUM = re.compile(r"^\s*(\d{1,3})(?:\s*[.)]\s*(?:\1(?=\s|[A-Za-z0-9]))?\s*|\s+(?=[A-Za-z]))(.*)$")
RE_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
RE_AD = re.compile(r"descargar|app\s*store|google\s*play|instalar|anuncio|kingshot|\bad\b"
                   r"|\bABRIR\b|\bINSTALAR\b|\bCOMPRAR\b|\$\s?\d", re.I)
# Contador de la pantalla del examen: «22:06  44%  44/100» → la pregunta es la 44
RE_PROGRESS = re.compile(r"\b(\d{1,3})\s*/\s*100\b")
MAX_OPTIONS = 4          # un ítem del ALCPT nunca tiene más de cuatro opciones
RE_ANSWER_N = re.compile(r"answer\s*:?\s*(\d{1,3})\s*\)", re.I)
RE_CORRECT = re.compile(r"^\s*correct\s*answer\s*[:\"“”']*\s*(.+?)[\"“”']*\s*$", re.I)
RE_EXPL = re.compile(r"^\s*explanation\s*:?\s*(.*)$", re.I)
RE_INCORRECT = re.compile(r"^\s*incorrect\s*answers?\s*:?\s*(.*)$", re.I)
RE_QUOTED_START = re.compile(r"^\s*[\"“”']\s*([^\"“”']+)\s*[\"“”']\s*is\s+incorrect", re.I)


# --- utilidades de texto -------------------------------------------------------
_SEG = None


def segment(tok: str) -> str:
    """Parte una palabra pegada por el OCR («belost» → «be lost») con wordsegment."""
    global _SEG
    try:
        import wordsegment as ws
    except ImportError:
        return tok
    if _SEG is None:
        ws.load()
        _SEG = ws
    parts = _SEG.segment(tok)
    return " ".join(parts) if parts else tok


def unglue(text: str) -> str:
    """Solo toca tokens alfabéticos de 8+ letras que no sean palabras conocidas,
    para no romper siglas, números ni palabras reales largas."""
    def fix(m):
        if m.group(1):            # «-oraneity»: sufijos y guiones se dejan en paz
            return m.group(0)
        tok = m.group(2)
        out = segment(tok)
        if _SEG is None or " " not in out:
            return tok
        parts = out.split()
        # solo si cada trozo es una palabra real de 2+ letras («the beverage»)
        if any((len(x) < 2 and x not in ("a", "i")) or x not in _SEG.UNIGRAMS for x in parts):
            return tok
        # «itwas» y «outof» existen en el corpus como rarezas: se parten si el token
        # entero es muchísimo menos frecuente que sus partes
        whole = _SEG.UNIGRAMS.get(tok.lower(), 0)
        if whole and whole > 0.001 * min(_SEG.UNIGRAMS[x] for x in parts):
            return tok
        return out[0].upper() + out[1:] if tok[0].isupper() else out
    return re.sub(r"(-?)([A-Za-z]{5,})", fix, text)


_KEEP = {"alcpt", "bx", "nco", "tv", "us", "usa", "ok", "mr", "mrs", "ms", "dr", "ur"}


def _edits1(w):
    letters = "abcdefghijklmnopqrstuvwxyz'"
    splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    yield from (a + b[1:] for a, b in splits if b)
    yield from (a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1)
    yield from (a + c + b[1:] for a, b in splits if b for c in letters)
    yield from (a + c + b for a, b in splits for c in letters)


def correct_word(w: str) -> str:
    """Corrector tipo Norvig con el corpus de wordsegment: solo toca palabras que
    no existen y tienen una vecina a una edición de distancia mucho más
    frecuente («warer» → «water», «Getltout» no, «Barousse» no)."""
    if _SEG is None:
        segment("a")
    low = w.lower()
    if len(low) < 3 or low in _SEG.UNIGRAMS or low in _KEEP or not low.isalpha():
        return w
    cands = {c for c in _edits1(low) if c in _SEG.UNIGRAMS}
    if not cands:
        return w
    best = max(cands, key=lambda c: _SEG.UNIGRAMS[c])
    if _SEG.UNIGRAMS[best] < 2e6:       # vecinas raras no son evidencia
        return w
    if w[:1].isupper():
        best = best[0].upper() + best[1:]
    return best


def spellfix(text: str) -> str:
    """Aplica correct_word palabra por palabra, respetando puntuación y guiones."""
    text = re.sub(r"(?<=[a-z]) o (?=[a-z])", " to ", text)   # «adjust o the» → «adjust to the»
    return re.sub(r"[A-Za-z']+", lambda m: correct_word(m.group(0)), text)


QUESTION_START = re.compile(r"^(what|who|whom|whose|where|when|why|how|which|do|does|did|is|are|"
                            r"was|were|can|could|will|would|should|have|has|had|may|might)\b", re.I)


def polish_stem(text: str) -> str:
    """Deja el enunciado como lo escribiría una persona: mayúscula inicial,
    «Mrs.» con punto, signo final («?» si empieza como pregunta). Los ítems de
    audio vienen en minúscula y sin puntuación porque la app muestra la
    transcripción tal cual."""
    s = text.strip()
    if not s or s.startswith("("):
        return s
    s = re.sub(r"\b(Mr|Mrs|Ms|Dr)\s", r"\1. ", s)
    s = s[0].upper() + s[1:]
    if re.search(r"[.?!_\"”]$", s):
        return s
    # Transcripciones de audio sin puntuación. Dos formas típicas:
    #   «Jack carried out the order what did he do»  → afirmación + pregunta
    #   «What did Tom do when the bill came he got kind of riled» → pregunta + respuesta
    words = s.split()
    m = re.search(r" (what|who|where|when|why|how|which) (?=\w)", s, re.I)
    if not QUESTION_START.match(s) and m and len(s[:m.start()].split()) >= 3:
        a, b = s[:m.start()].strip(), s[m.start():].strip()
        return f"{a}. {b[0].upper()}{b[1:]}?"
    if QUESTION_START.match(s):
        for m in re.finditer(r" (he|she|they|we|you|it|I'm|I've|I) (?=\w)", s):
            if len(s[:m.start()].split()) >= 5:
                a, b = s[:m.start()].strip(), s[m.start():].strip()
                return f"{a}? {b[0].upper()}{b[1:]}."
        return s + "?"
    return s + "."


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def match_option(text: str, options: list[str], fuzzy: bool = False) -> str | None:
    """Casa un texto con una opción aunque el OCR pegara palabras. `fuzzy` admite
    una letra de diferencia: solo para los nombres de las incorrectas, nunca
    para la correcta («slip» no puede acabar casando con «sit»)."""
    key = norm(text)
    for o in options:
        if norm(o) == key:
            return o
    for o in options:
        if key and (key in norm(o) or norm(o) in key):
            return o
    if not fuzzy:
        return None
    # «warer» ≈ «water»: el OCR de la opción en rojo suele fallar por una letra
    import difflib
    for o in options:
        if key and len(key) >= 4 and difflib.SequenceMatcher(None, key, norm(o)).ratio() >= 0.8:
            return o
    return None


# --- color: qué opción está en verde ------------------------------------------
def green_fraction(img, box) -> int:
    import numpy as np
    a = np.asarray(img.crop(box)).astype(int)
    if a.size == 0:
        return 0.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mask = (g > 90) & (g > r + 20) & (g > b + 20)
    return int(mask.sum())          # píxeles verdes: «six» en verde también cuenta


def red_fraction(img, box) -> int:
    import numpy as np
    a = np.asarray(img.crop(box)).astype(int)
    if a.size == 0:
        return 0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((r > 150) & (r > g + 60) & (r > b + 60)).sum())


def option_box(img, r, scale):
    w, h = img.size
    y1, y2 = int(r["y1"] * scale), int(r["y2"] * scale)
    half = max(6, int(r["h"] * scale * 0.8))
    x0 = max(0, int(r["x"] * scale) - int(w * 0.02))
    return (x0, max(0, y1 - half), min(w, x0 + int(w * 0.75)), min(h, y2 + half))


def reread_red_options(image_path: Path, q, scale):
    """La opción que Brayhan marcó mal sale en rojo cursiva y el OCR normal la
    destroza («Getltoutmramuir»). Se vuelve a leer ese recorte por el canal rojo
    y ampliado, que la deja legible."""
    img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    for i, r in enumerate(q["_option_rows"]):
        box = option_box(img, r, scale)
        if red_fraction(img, box) < 12:
            continue
        # la lectura original y dos relecturas; gana la de mayor confianza del OCR,
        # y si ninguna llega a 0.80 la opción se declara ilegible (la completa la
        # otra pantalla, donde aparece entre comillas en «Incorrect Answers»)
        candidates = [(q["options"][i], r.get("conf", 0.0))]
        for kw in ({"upscale": 4, "channel": "R"}, {"upscale": 4, "channel": None}):
            text, conf = ocr_crop(img, box, **kw)
            if text and len(text) >= 2:
                candidates.append((unglue(text), conf))
        best, conf = max(candidates, key=lambda c: c[1])
        q["options"][i] = best if conf >= 0.80 else UNREADABLE


def green_option(image_path: Path, option_rows, scale) -> int | None:
    """La correcta en la pantalla de pregunta va con el texto en verde; el resto
    en blanco. Se mide la fracción de píxeles verdes en la franja de cada opción."""
    if not option_rows:
        return None
    img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    w, h = img.size
    scores = []
    for r in option_rows:
        scores.append(green_fraction(img, option_box(img, r, scale)))
    best = max(range(len(scores)), key=lambda i: scores[i])
    others = [s for i, s in enumerate(scores) if i != best]
    if scores[best] >= 12 and scores[best] > 3 * (max(others) if others else 0) + 5:
        return best
    return None


def _span(r):
    """Rango vertical de una opción: empieza y termina en el mismo renglón hasta
    que se le pegue una continuación."""
    return {"x": r["x"], "y1": r["y"], "y2": r["y"], "h": r["h"], "conf": r.get("conf", 1.0)}


def looks_garbage(option: str) -> bool:
    """Basura de OCR («Getltoutmramuir», «Ba iii eai»), no vocabulario raro.
    El ALCPT pregunta palabras poco frecuentes («gesticulated», «razes»,
    «-oraneity»): una sola palabra pronunciable nunca se descarta."""
    if option.startswith(("(", "-")):
        return False
    words = re.findall(r"[A-Za-z']+", option)
    if not words:
        return True
    if len(words) == 1:
        w = words[0].lower().strip("'")
        if not re.search(r"[aeiouy]", w) or re.search(r"[^aeiouy]{5,}", w):
            return True
        # Solo el patrón de letras decide: el examen pregunta palabras rarísimas
        # («gesticulated», «razes») que no están en el corpus de frecuencias.
        return bool(re.search(r"(.)\1{2,}", w))     # «iii», «lll»: el OCR patinando
    return known_ratio(option) < 0.34


def known_ratio(text: str) -> float:
    """Fracción de palabras del texto que existen en el corpus: mide si el OCR
    devolvió inglés o basura («Getltoutmramuir»)."""
    if _SEG is None:
        segment("a")
    words = re.findall(r"[A-Za-z']+", text)
    if not words:
        return 0.0
    return sum(1 for w in words if w.lower().strip("'") in _SEG.UNIGRAMS) / len(words)


# --- de renglones OCR a campos ---------------------------------------------------
def parse_rows(rows, width):
    """Devuelve (pregunta, faltantes). Campos: form, n, question, options,
    correct, explanation, screen ('question' | 'explanation')."""
    form, n = None, None
    stem, options, expl, incorrect = [], [], [], []
    option_rows = []
    correct_text = None
    stage = "head"       # head → stem → options | answer → explanation → incorrect → tail
    # («options» también se alcanza directo desde el contador de la pantalla del examen)
    stem_x = None
    pending_digits = ""  # «10» en un renglón y «0.» en el siguiente = 100
    stem_x_locked = False  # tras la primera línea del enunciado ya no se corrige n
    prev_row = None

    for r in rows:
        line = r["text"].strip()
        if not line:
            continue
        prev = prev_row
        prev_row = r
        if stage == "head":
            if RE_PROGRESS.search(line):
                # «4/100» es la posición dentro del examen, no el número del ítem
                # (se comprobó: no coinciden). Solo sirve para saber que la captura
                # se tomó durante el examen, donde no se ve el enunciado.
                stage = "options"
                continue
            if (RE_STATUS.search(line) or RE_TIME.search(line)
                    or re.fullmatch(r"[\d:\s_]+", line)):
                continue
        if RE_NOISE.match(line):
            if RE_ANSWER_N.search(line) and n is None:
                n = int(RE_ANSWER_N.search(line).group(1))
            if re.match(r"^\s*end\s*review", line, re.I):
                break          # debajo solo hay botones y anuncios de la app
            continue
        if RE_AD.search(line) and stage != "explanation":
            break              # banner publicitario de la app, justo sobre End Review
        m = RE_FORM.search(line)
        if m and form is None:
            form = m.group(1)
            rest = RE_FORM.sub("", line).strip(" -:·|")
            if not rest:
                continue
            line = rest
        m = RE_ANSWER_N.search(line)
        if m:
            if n is None:
                n = int(m.group(1))
            stage = "answer"
            continue
        m = RE_INCORRECT.match(line)
        if m:
            stage = "incorrect"
            if m.group(1):
                incorrect.append(m.group(1))
            continue
        m = RE_CORRECT.match(line)
        if m:
            correct_text = m.group(1).strip(" \"“”':")
            stage = "answer"
            continue
        m = RE_EXPL.match(line)
        if m:
            stage = "explanation"
            if m.group(1):
                expl.append(m.group(1))
            continue

        if stage == "explanation":
            expl.append(line)
            continue
        if stage == "incorrect":
            # Debajo del bloque asoman las opciones que siguen (con su círculo, más a la
            # derecha que las viñetas). Si el renglón está pegado al anterior, es la
            # continuación de esa opción; si es el primero y empieza en minúscula, es la
            # cola de una opción cuya cabeza quedó tapada, y se descarta.
            if r["x"] > width * 0.2 and len(line.split()) <= 7 \
                    and not re.search(r"(,|\band\b|\bor\b|\bto\b)$", line) \
                    and (len(options) < MAX_OPTIONS or (
                        option_rows and r["y"] - option_rows[-1]["y2"]
                        < 1.8 * max(r["h"], option_rows[-1]["h"]))):
                if option_rows and r["y"] - option_rows[-1]["y2"] < 1.8 * max(r["h"], option_rows[-1]["h"]):
                    options[-1] = (options[-1] + " " + line).strip()
                    option_rows[-1]["y2"] = r["y"]
                    option_rows[-1]["conf"] = min(option_rows[-1]["conf"], r.get("conf", 1.0))
                elif not options and line[:1].islower():
                    pass
                else:
                    options.append(line)
                    option_rows.append(_span(r))
            else:
                incorrect.append(line)
            continue

        # --- pantalla de pregunta: enunciado y luego opciones ---
        if stage in ("head", "stem"):
            if n is None:
                m = RE_STEM_NUM.match(line)
                if m:
                    digits = pending_digits + m.group(1)
                    if re.fullmatch(r"\d{1,2}", line.split()[0]) and "." not in line.split()[0] \
                            and not m.group(2):
                        pending_digits = digits
                        continue
                    n = int(digits) if len(digits) <= 3 else int(m.group(1))
                    pending_digits = ""
                    stage = "stem"
                    stem_x = r["x"]
                    rest = re.sub(r"^(?:number|item|question|pregunta)\s*\d{1,3}\s*",
                                  "", m.group(2), flags=re.I)
                    if rest:
                        stem.append(rest)
                    continue
                if pending_digits and re.match(r"^\d\s*[.)]", line):
                    # «10» + «0. were vast…» → 100
                    m2 = re.match(r"^(\d)\s*[.)]\s*(.*)$", line)
                    n = int(pending_digits + m2.group(1))
                    pending_digits = ""
                    stage = "stem"
                    stem_x = r["x"] if stem_x is None else stem_x
                    if m2.group(2):
                        stem.append(m2.group(2))
                    continue
                if pending_digits:
                    # el número quedó en su renglón; esta línea ya es enunciado
                    n = int(pending_digits)
                    pending_digits = ""
                    stage = "stem"
                    stem_x = r["x"]
                    stem.append(line)
                    continue
            if stage == "stem" and n is not None and n < 100 and not stem_x_locked \
                    and re.match(r"^\d\s*[.)]\s", line):
                # la app parte «100.» en dos renglones: «10» arriba y «0.» abajo
                m2 = re.match(r"^(\d)\s*[.)]\s*(.*)$", line)
                n = int(f"{n}{m2.group(1)}")
                stem_x_locked = True
                if m2.group(2):
                    stem.append(m2.group(2))
                continue
            stem_x_locked = True
            gap = (r["y"] - prev["y"]) / max(r["h"], prev["h"]) if prev is not None else 0
            indent = r["x"] - stem_x if stem_x is not None else 0
            if stage == "stem" and (gap > 2.5 or (indent > width * 0.10 and gap > 1.8)):
                stage = "options"
            else:
                if stage == "head":
                    stage = "stem"
                    stem_x = r["x"]
                stem.append(line)
                continue
        if stage == "options":
            if len(options) >= MAX_OPTIONS and not (
                    option_rows and r["y"] - option_rows[-1]["y2"]
                    < 1.8 * max(r["h"], option_rows[-1]["h"])):
                continue          # lo que viene debajo de la cuarta opción es el anuncio
            if option_rows and r["y"] - option_rows[-1]["y2"] < 1.8 * max(r["h"], option_rows[-1]["h"]):
                options[-1] = (options[-1] + " " + line).strip()   # opción que ocupa 2 renglones
                option_rows[-1]["y2"] = r["y"]
                option_rows[-1]["conf"] = min(option_rows[-1]["conf"], r.get("conf", 1.0))
            else:
                options.append(line)
                option_rows.append(_span(r))
            continue
        if stage == "answer":
            if correct_text is not None:
                correct_text = (correct_text + " " + line).strip(" \"“”':")
            else:
                stem.append(line)

    screen = "explanation" if (correct_text or expl or incorrect) else "question"
    q = {
        "form": form,
        "n": n,
        "question": polish_stem(spellfix(unglue(" ".join(stem).strip()))),
        "options": [spellfix(unglue(o)) for o in options if o],
        "correct": spellfix(unglue(correct_text)) if correct_text else None,
        "explanation": spellfix(unglue(" ".join(expl).strip())),
        "incorrect": spellfix(unglue(" ".join(incorrect).strip())),
        "screen": screen,
        "_option_rows": option_rows,
    }
    missing = []
    if not form:
        missing.append("formulario (no se lee «Form NN» arriba)")
    if n is None:
        missing.append("número de pregunta")
    if screen == "question" and len(q["options"]) < 2:
        missing.append("opciones (se leyeron menos de 2)")
    if screen == "explanation" and not correct_text and not (expl or incorrect):
        missing.append("la línea «Correct Answer»")
    return q, missing


def finish_fields(q, image_path, scale):
    """Completa correct/explanation según la pantalla."""
    reread_red_options(image_path, q, scale)      # en las dos pantallas
    if q["screen"] == "question":
        idx = green_option(image_path, q["_option_rows"], scale)
        if idx is not None:
            q["correct"] = q["options"][idx]
            q["explanation"] = NO_EXPL_YET
        else:
            q["correct"] = NOT_SHOWN
            q["explanation"] = NOT_SHOWN_EXPL
    elif not q["correct"]:
        # explicación desplazada: la respuesta quedó fuera, pero el texto sirve
        q["correct"] = NO_ANSWER_YET
        if not q["options"]:
            q["options"] = [NO_OPTIONS_YET]
        extra = ""
        if len(q["question"]) > 120:        # no es enunciado: es explicación arrastrada
            extra = q["question"]
            q["question"] = ""
        q["explanation"] = trim_truncated(
            " ".join(x for x in (extra, q["explanation"], q["incorrect"]) if x).strip()) or NO_EXPL_YET
    else:
        c = q["correct"]
        if " " not in c and len(c) >= 5:
            c = segment(c)          # «belost» → «be lost», «softdrinks» → «soft drinks»
        # los nombres de las incorrectas salen entre comillas en su bloque
        names = [m.group(1).strip() for m in
                 (RE_QUOTED_START.match(s) for s in re.split(r"(?<=[.!?])\s+", q["incorrect"])) if m]
        q["options"] = [o for o, r in zip(q["options"], q["_option_rows"]) if r.get("conf", 1.0) >= 0.80] \
            + q["options"][len(q["_option_rows"]):]
        for name in names:
            hit = match_option(name, q["options"], fuzzy=True)
            if hit is None:
                q["options"].append(name)
            elif norm(hit) != norm(name) and known_ratio(hit) < known_ratio(name) + 0.01 \
                    and len(name) >= 4:
                q["options"][q["options"].index(hit)] = name   # «-"war er-» → «water»
        hit = match_option(c, q["options"])
        if hit is None:
            q["options"].insert(0, c)
        else:
            c = hit
        q["correct"] = c
        expl = q["explanation"]
        if q["incorrect"]:
            expl = (expl + " " + q["incorrect"]).strip()
        q["explanation"] = trim_truncated(expl) or NO_EXPL_YET
        if len(q["options"]) < 2:
            q["options"].append(NO_OPTIONS_YET)
    if not q["question"]:
        q["question"] = NO_STEM_YET
    q["options"] = [o for o in q["options"] if not looks_garbage(o)]
    q.pop("_option_rows", None)
    q.pop("incorrect", None)


def trim_truncated(text: str) -> str:
    """La pantalla de explicación se desplaza: la última frase suele quedar
    cortada («The correct structure»). Si el texto no acaba en puntuación, se
    quita ese último fragmento; con otra captura desplazada se recupera entero."""
    s = text.strip()
    if not s or re.search(r"[.!?\"”)]$", s):
        return s
    cut = max(s.rfind(". "), s.rfind("? "), s.rfind("! "))
    return s[:cut + 1] if cut > 40 else s


def merge_explanations(old: str, new: str) -> str:
    """Dos capturas desplazadas de la misma explicación: se unen por el trozo
    en que se solapan; si no se solapan, se concatenan."""
    if not old or old in PLACEHOLDERS:
        return new
    if not new or new in PLACEHOLDERS or new in old:
        return old
    if old in new:
        return new
    a, b = old.split(), new.split()
    for k in range(min(len(a), len(b), 12), 3, -1):
        if a[-k:] == b[:k]:
            return " ".join(a + b[k:])
    for k in range(min(len(a), len(b), 12), 3, -1):
        if b[-k:] == a[:k]:
            return " ".join(b + a[k:])
    return old + " " + new


def _resolve_by_wrong_answers(q) -> bool:
    """Sin «Correct Answer» visible, los nombres entrecomillados del bloque
    «Incorrect Answers» bastan si solo una pregunta del formulario los tiene todos."""
    names = [m.group(1).strip() for m in
             (RE_QUOTED_START.match(s) for s in re.split(r"(?<=[.!?])\s+", q.get("incorrect", ""))) if m]
    if len(names) < 2:
        return False
    try:
        data = json.loads(FORMS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    section = next((f for f in data["forms"] if str(f["form"]) == q["form"]), None)
    if not section:
        return False
    hits = [x for x in section["questions"]
            if all(match_option(nm, x.get("options", []), fuzzy=True) for nm in names)]
    if len(hits) != 1:
        return False
    q["n"] = hits[0]["n"]
    if q["n"] is None:
        q["_match"] = hits[0].get("correct")
    return True


def resolve_missing_number(q) -> bool:
    """Pantalla de explicación desplazada: «Answer: NN)» quedó fuera de la captura.
    Se busca en el formulario la única pregunta cuya correcta o alguna opción
    coincida exactamente con la que trae la captura. Si hay dudas, no se toca."""
    if q.get("n") is not None or not q.get("form"):
        return False
    if not q.get("correct") or q["correct"].startswith("("):
        return _resolve_by_wrong_answers(q)
    try:
        data = json.loads(FORMS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    section = next((f for f in data["forms"] if str(f["form"]) == q["form"]), None)
    if not section:
        return False
    import difflib
    key = norm(q["correct"])
    if len(key) < 4:                       # «six», «mad»: demasiado genéricos
        return False

    def parecido(a, b):
        return a == b or (len(a) >= 8 and len(b) >= 8
                          and difflib.SequenceMatcher(None, a, b).ratio() >= 0.85)

    # El OCR de la respuesta suele traer erratas («I he wind» por «The wind»),
    # así que se compara con tolerancia y se exige que encaje con una sola.
    hits = [x for x in section["questions"]
            if parecido(norm(x.get("correct", "")), key)
            or any(parecido(norm(o), key) for o in x.get("options", []))]
    if len(hits) != 1:
        return False
    q["n"] = hits[0]["n"]
    # Cuatro preguntas antiguas quedaron sin número («Item number not visible»);
    # para esas se guarda el texto de su respuesta como identificador.
    if q["n"] is None:
        q["_match"] = hits[0].get("correct")
    return True


# --- forms.json -----------------------------------------------------------------
def merge(existing: dict, new: dict) -> list[str]:
    """Rellena en `existing` lo que traiga `new` y falte. Devuelve qué cambió."""
    changed = []
    old_correct = existing.get("correct", "")
    coherente = (old_correct in PLACEHOLDERS
                 or match_option(old_correct, new["options"]) is not None)
    if len(new["options"]) > len([o for o in existing.get("options", []) if o not in PLACEHOLDERS]) \
            and new["screen"] == "question" and coherente:
        existing["options"] = new["options"][:MAX_OPTIONS]
        changed.append("opciones")
    elif new["screen"] == "explanation":
        opts = [o for o in existing.get("options", []) if o not in PLACEHOLDERS]
        for o in new["options"]:
            if o not in PLACEHOLDERS and not match_option(o, opts):
                opts.append(o)
        opts = opts[:MAX_OPTIONS]
        if UNREADABLE in existing.get("options", []):
            kept = existing["options"][:]
            extra = [o for o in opts if not match_option(o, [k for k in kept if k != UNREADABLE], fuzzy=True)]
            if extra:
                kept[kept.index(UNREADABLE)] = extra[0]
            opts = kept
        if opts != existing.get("options"):
            existing["options"] = opts
            changed.append("opciones")
    if existing.get("correct") not in PLACEHOLDERS and existing["correct"] not in existing.get("options", []):
        hit = match_option(existing["correct"], existing.get("options", []))
        if hit:
            existing["correct"] = hit
            changed.append("respuesta casada")
    if existing.get("correct") in PLACEHOLDERS and new["correct"] not in PLACEHOLDERS:
        hit = match_option(new["correct"], existing["options"]) or new["correct"]
        existing["correct"] = hit
        changed.append("respuesta")
    if new["explanation"] not in PLACEHOLDERS:
        merged = merge_explanations(existing.get("explanation", ""), new["explanation"])
        if merged != existing.get("explanation"):
            existing["explanation"] = merged
            changed.append("explicación")
    if (not existing.get("question") or existing["question"].startswith("(")) \
            and new["question"] and not new["question"].startswith("("):
        existing["question"] = new["question"]
        changed.append("enunciado")
    return changed


def save(q) -> str:
    data = json.loads(FORMS.read_text(encoding="utf-8"))
    section = next((f for f in data["forms"] if str(f["form"]) == q["form"]), None)
    if section is None:
        section = {"form": q["form"], "questions": []}
        data["forms"].append(section)
        data["forms"].sort(key=lambda f: (not str(f["form"]).isdigit(),
                                          int(f["form"]) if str(f["form"]).isdigit() else 0,
                                          str(f["form"])))
    entry = {k: q[k] for k in ("n", "question", "options", "correct", "explanation")}
    if q.get("_match"):
        existing = next((x for x in section["questions"]
                         if x.get("n") is None and x.get("correct") == q["_match"]), None)
    else:
        existing = next((x for x in section["questions"] if x.get("n") == q["n"]), None)
    if existing:
        changed = merge(existing, q)
        if not changed:
            return (f"Form {q['form']} "
                    f"{'#' + str(q['n']) if q['n'] is not None else '(sin número)'} "
                    "ya estaba completa; no se cambió nada.")
        status = "completada: " + ", ".join(changed)
    else:
        section["questions"].append(entry)
        section["questions"].sort(key=lambda x: (x.get("n") is None, x.get("n") or 0))
        status = "agregada desde la pantalla de " + ("pregunta" if q["screen"] == "question" else "explicación")
    label = f"#{q['n']}" if q["n"] is not None else "(sin número)"
    meta = data.setdefault("meta", {})
    meta["last_updated"] = date.today().isoformat()
    meta["total_questions"] = sum(len(f["questions"]) for f in data["forms"])
    docs = meta.setdefault("forms_documented", [])
    if q["form"] not in docs:
        docs.append(q["form"])
    FORMS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"Form {q['form']} {label} {status}."


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
    args.image.with_suffix(".txt").write_text(res["text"], encoding="utf-8")
    if not res["usable"]:
        out = {"ok": False, "reason": f"OCR poco fiable (confianza {res['confidence']:.2f}, "
                                      f"{res['lines']} renglones)", "text": res["text"]}
        print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
        return 2

    from ocr_capture import TARGET_WIDTH
    q, missing = parse_rows(res["rows"], TARGET_WIDTH)
    if missing == ["número de pregunta"] and resolve_missing_number(q):
        missing = []
    if missing:
        out = {"ok": False, "reason": "No pude estructurar la captura. Falta: " + "; ".join(missing),
               "text": res["text"], "partial": {k: v for k, v in q.items() if not k.startswith("_")}}
        print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
        return 2
    finish_fields(q, args.image, res["scale"])

    message = ("(dry-run, no se guardó) " + json.dumps(q, ensure_ascii=False)) if args.dry_run else save(q)
    out = {"ok": True, "message": message, "question": q, "confidence": res["confidence"]}
    print(json.dumps(out, ensure_ascii=False) if args.json else message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
