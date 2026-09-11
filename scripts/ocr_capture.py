#!/usr/bin/env python3
"""Convierte una captura del ALCPT en texto plano con OCR local (RapidOCR).

Existe para que el bot NO le pase la imagen a Claude Code: una captura cuesta
más de mil tokens de entrada y el texto que contiene, unos doscientos. Claude
recibe el texto ya extraído y solo tiene que estructurarlo.

Uso:
    python scripts/ocr_capture.py inbox/tg_xxx.jpg            # imprime el texto
    python scripts/ocr_capture.py inbox/tg_xxx.jpg --json     # texto + calidad
    python scripts/ocr_capture.py inbox/tg_xxx.jpg --out inbox/tg_xxx.txt

Salida en --json:
    {"text": "...", "lines": N, "confidence": 0.93, "usable": true}

`usable` es false cuando el OCR no encontró texto o la confianza media es
baja; en ese caso el bot cae al camino antiguo (Claude lee la imagen).

Códigos de salida: 0 = texto usable · 2 = texto no usable · 1 = error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

MIN_CONFIDENCE = 0.80   # media de confianza por debajo de la cual no fiarse
MIN_LINES = 3           # una captura del examen tiene enunciado + opciones
TARGET_WIDTH = 1400     # ancho al que se escala antes del OCR (más = más lento)


def prepare(path: Path):
    """Escala de grises, contraste automático y ancho fijo: el OCR rinde mejor y
    parejo en capturas de celular de cualquier resolución.

    Devuelve (imagen_preparada, factor): multiplicando una coordenada del OCR
    por `factor` se vuelve a la imagen original (el parser lo usa para mirar
    el color de cada opción)."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img, cutoff=1)
    factor = 1.0
    if img.width != TARGET_WIDTH:
        ratio = TARGET_WIDTH / img.width
        factor = 1 / ratio
        img = img.resize((TARGET_WIDTH, max(1, round(img.height * ratio))),
                         Image.LANCZOS)
    return img, factor


def group_lines(items, y_tol=0.6):
    """RapidOCR devuelve fragmentos con su caja; aquí se juntan los que comparten
    renglón (misma altura ± tolerancia) y se ordenan de izquierda a derecha.

    `y_tol` es la fracción de la altura del fragmento que se admite como
    desviación para considerarlo del mismo renglón."""
    frags = []
    for box, text, conf in items:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        frags.append({"x": min(xs), "y": (min(ys) + max(ys)) / 2,
                      "h": max(ys) - min(ys), "text": text.strip(), "conf": float(conf)})
    frags.sort(key=lambda f: (f["y"], f["x"]))
    rows = []
    for f in frags:
        if rows and abs(rows[-1]["y"] - f["y"]) <= y_tol * max(rows[-1]["h"], f["h"]):
            rows[-1]["frags"].append(f)
            rows[-1]["y"] = (rows[-1]["y"] + f["y"]) / 2
        else:
            rows.append({"y": f["y"], "h": f["h"], "frags": [f]})
    lines = []
    for r in rows:
        r["frags"].sort(key=lambda f: f["x"])
        lines.append(" ".join(f["text"] for f in r["frags"] if f["text"]))
    return lines, frags


def ocr(path: Path) -> dict:
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    img, factor = prepare(path)
    engine = RapidOCR()
    result, _elapsed = engine(np.asarray(img))
    if not result:
        return {"text": "", "lines": 0, "confidence": 0.0, "usable": False,
                "rows": [], "scale": factor}
    lines, frags = group_lines(result)
    conf = sum(f["conf"] for f in frags) / len(frags)
    text = "\n".join(l for l in lines if l)
    usable = len(lines) >= MIN_LINES and conf >= MIN_CONFIDENCE
    # `rows`: cada renglón con su posición (coordenadas de la imagen preparada)
    rows = []
    for line, frag in zip(lines, _row_geometry(frags)):
        if line:
            rows.append({"text": line, **frag})
    return {"text": text, "lines": len(lines), "confidence": round(conf, 3),
            "usable": usable, "rows": rows, "scale": factor}


def _row_geometry(frags, y_tol=0.6):
    """Misma agrupación que group_lines, pero devuelve la geometría del renglón."""
    frags = sorted(frags, key=lambda f: (f["y"], f["x"]))
    rows = []
    for f in frags:
        if rows and abs(rows[-1]["y"] - f["y"]) <= y_tol * max(rows[-1]["h"], f["h"]):
            r = rows[-1]
            r["y"] = (r["y"] + f["y"]) / 2
            r["h"] = max(r["h"], f["h"])
            r["x"] = min(r["x"], f["x"])
        else:
            rows.append({"x": f["x"], "y": f["y"], "h": f["h"]})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image", type=Path)
    ap.add_argument("--json", action="store_true", help="salida JSON con calidad")
    ap.add_argument("--out", type=Path, help="guardar el texto en este archivo")
    args = ap.parse_args()

    if not args.image.exists():
        print(f"No existe: {args.image}", file=sys.stderr)
        return 1
    try:
        res = ocr(args.image)
    except Exception as exc:  # noqa: BLE001 - el bot solo necesita saber que falló
        print(f"OCR falló: {exc}", file=sys.stderr)
        return 1

    if args.out:
        args.out.write_text(res["text"], encoding="utf-8")
    if args.json:
        print(json.dumps({k: v for k, v in res.items() if k not in ("rows", "scale")},
                         ensure_ascii=False))
    else:
        print(res["text"])
    return 0 if res["usable"] else 2


if __name__ == "__main__":
    sys.exit(main())
