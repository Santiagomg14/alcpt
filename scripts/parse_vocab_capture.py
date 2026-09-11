#!/usr/bin/env python3
"""Captura de una lista de vocabulario (TikTok, Instagram, apuntes: término en
inglés a la izquierda y significado en español a la derecha) → entradas en
data/vocabulary.json, sección `personal`, numeración consecutiva. Sin IA.

    ┌──────────────┬──────────────────────┐
    │ Pull up      │ Llegar / Aparecer    │   ← una fila = una entrada
    │ Pull out     │ Retirarse / Sacar    │
    │ Pull through │ Salir adelante       │
    └──────────────┴──────────────────────┘

Cómo decide que la captura es de este tipo: no hay encabezado «Form NN» ni
«End Review», y al menos tres filas tienen dos bloques de texto separados por
un hueco horizontal claro, con inglés a la izquierda y español a la derecha.

El OCR pierde las tildes («dificil», «atras») y a veces una letra («Legar»).
Aquí se guarda lo leído tal cual, marcado con `"ocr": true`; el bot le pide
después a Claude Code (solo texto, sin imagen) que reponga tildes y añada
matices, como hace con las palabras sueltas. Sin Claude, la entrada queda como
la leyó el OCR, que ya es útil.

Uso:
    python scripts/parse_vocab_capture.py inbox/x.jpg --dry-run
    python scripts/parse_vocab_capture.py inbox/x.jpg --json

Salida --json: {"ok": true, "added": [{"n": 335, "en": "Pull up", "es": "…"}],
                "skipped": [{"en": "Back down", "why": "ya estaba (n 29)"}]}
Códigos de salida: 0 = agregadas (o todas repetidas) · 2 = no es una lista · 1 = error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_capture import ocr  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
VOCAB = REPO / "data" / "vocabulary.json"

RE_FORM = re.compile(r"\bform\s*\d{2,3}\b|end\s*review|correct\s*answer", re.I)
RE_STATUS = re.compile(r"\b\d{1,2}:\d{2}\b")
RE_UI = re.compile(r"^(seguir|follow|agrega\s*un\s*comentario|add\s*a\s*comment|gif|m[aá]s|"
                   r"audio\s*original|compartir|share|guardar)$", re.I)
RE_NUMBERS = re.compile(r"\b\d[\d.,]*\s*[kKmM]?\b")
ES_HINTS = re.compile(r"[áéíóúñ¿¡]|\b(el|la|los|las|de|del|para|con|algo|alguien|un|una|se|"
                      r"ar|er|ir)\b|(ar|er|ir|arse|erse|irse)\b", re.I)
EN_HINTS = re.compile(r"\b(up|out|off|on|in|down|over|away|back|through|into|to|the|a|for|"
                      r"with|get|go|take|put|pull|come|make|give|look|turn|run|bring)\b", re.I)


def is_form_capture(rows) -> bool:
    return any(RE_FORM.search(r["text"]) for r in rows)


def split_row(frags, row_h):
    """Divide los fragmentos de una fila en columna izquierda y derecha por el
    hueco horizontal más grande (si es claro: > 1 altura de texto)."""
    frags = sorted(frags, key=lambda f: f["x"])
    best_i, best_gap = None, 0
    for i in range(1, len(frags)):
        gap = frags[i]["x"] - frags[i - 1]["x2"]
        if gap > best_gap:
            best_i, best_gap = i, gap
    if best_i is None or best_gap < 1.0 * row_h:
        return None
    left = " ".join(f["text"] for f in frags[:best_i])
    right = " ".join(f["text"] for f in frags[best_i:])
    return left.strip(), right.strip()


def clean_es(s: str) -> str:
    s = RE_NUMBERS.sub("", s)                 # «Orillar el carro 2,077»
    s = re.sub(r"\s*/\s*", " / ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -–·|")
    return s


def clean_en(s: str) -> str:
    s = RE_NUMBERS.sub("", s).strip(" -–·|")
    return s[:1].upper() + s[1:] if s else s


def extract_pairs(res):
    """Devuelve (pares, motivo). Cada par: {"en", "es"}."""
    rows = res["rows"]
    if is_form_capture(rows):
        return [], "es una captura del formulario ALCPT"
    frags = res["frags"]
    # agrupar fragmentos por fila igual que ocr_capture (misma tolerancia)
    frags = sorted(frags, key=lambda f: (f["y"], f["x"]))
    groups = []
    for f in frags:
        if groups and abs(groups[-1]["y"] - f["y"]) <= 0.6 * max(groups[-1]["h"], f["h"]):
            groups[-1]["frags"].append(f)
            groups[-1]["y"] = (groups[-1]["y"] + f["y"]) / 2
            groups[-1]["h"] = max(groups[-1]["h"], f["h"])
        else:
            groups.append({"y": f["y"], "h": f["h"], "frags": [f]})
    pairs = []
    height = res.get("height", 0)
    for g in groups:
        text = " ".join(f["text"] for f in g["frags"])
        if RE_STATUS.search(text) or RE_UI.match(text.strip()):
            continue
        if height and g["y"] > 0.85 * height:
            continue                              # zona de botones y comentarios de la app
        sp = split_row(g["frags"], g["h"])
        if not sp:
            continue
        en, es = clean_en(sp[0]), clean_es(sp[1])
        if not en or not es or len(en) > 40:
            continue
        if RE_UI.match(en.replace(" ", "")) or RE_UI.match(es.replace(" ", "")) \
                or RE_UI.match(es) or re.search(r"\byeah\b|@|#", en, re.I):
            continue                              # «English Yeah = Seguir», «… = GIF»
        if not EN_HINTS.search(en) and not re.fullmatch(r"[A-Za-z' -]+", en):
            continue
        if not ES_HINTS.search(es) and EN_HINTS.search(es):
            continue                              # las dos columnas en inglés: otra cosa
        pairs.append({"en": en, "es": es})
    if len(pairs) < 3:
        return pairs, f"solo se reconocieron {len(pairs)} pares término/significado (mínimo 3)"
    return pairs, ""


def save(pairs):
    d = json.loads(VOCAB.read_text(encoding="utf-8"))
    highest = max((e["n"] for s in d["sections"] for e in s["entries"]), default=0)
    existing = {e["en"].strip().lower(): e["n"] for s in d["sections"] for e in s["entries"]}
    target = next(s for s in d["sections"] if s["id"] == "personal")
    added, skipped = [], []
    for p in pairs:
        key = p["en"].strip().lower()
        if key in existing:
            skipped.append({"en": p["en"], "why": f"ya estaba (n {existing[key]})"})
            continue
        highest += 1
        entry = {"n": highest, "en": p["en"], "es": p["es"], "ocr": True}
        target["entries"].append(entry)
        existing[key] = highest
        added.append(entry)
    if added:
        d["meta"]["last_updated"] = date.today().isoformat()
        d["meta"]["total_confirmed"] = sum(len(s["entries"]) for s in d["sections"])
        VOCAB.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.image.exists():
        print(f"No existe: {args.image}", file=sys.stderr)
        return 1
    res = ocr(args.image)
    if not res["usable"]:
        out = {"ok": False, "reason": f"OCR poco fiable (confianza {res['confidence']:.2f})"}
        print(json.dumps(out, ensure_ascii=False) if args.json else out["reason"])
        return 2
    pairs, why = extract_pairs(res)
    if why:
        out = {"ok": False, "reason": why, "pairs": pairs}
        print(json.dumps(out, ensure_ascii=False) if args.json else why)
        return 2
    if args.dry_run:
        out = {"ok": True, "pairs": pairs, "dry_run": True}
        print(json.dumps(out, ensure_ascii=False, indent=1) if args.json else
              "\n".join(f"{p['en']} = {p['es']}" for p in pairs))
        return 0
    added, skipped = save(pairs)
    out = {"ok": True, "added": added, "skipped": skipped}
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        for e in added:
            print(f"{e['n']}. {e['en']} = {e['es']}")
        for s in skipped:
            print(f"   (omitida) {s['en']}: {s['why']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
