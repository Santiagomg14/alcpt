#!/usr/bin/env python3
"""Regresión del parser de capturas contra capturas reales.

Las imágenes viven en inbox/ (fuera del repo); lo que se versiona es el
resultado esperado de cada una en tests/captures_expected.json. Si un cambio
en ocr_capture.py o parse_capture.py altera el formulario, el número, las
opciones o la correcta de alguna captura conocida, esto lo dice.

Uso:
    python scripts/check_captures.py            # compara con lo esperado
    python scripts/check_captures.py --update   # regenera lo esperado (tras revisar)
    python scripts/check_captures.py --only tg_20260911_0313

Solo se comparan los campos estructurales (screen, form, n, options, correct);
el texto libre (enunciado, explicación) se muestra pero no falla la prueba.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INBOX = REPO / "inbox"
EXPECTED = REPO / "tests" / "captures_expected.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def parse_one(path):
    from ocr_capture import ocr, TARGET_WIDTH
    import parse_capture as pc
    res = ocr(path)
    if not res["usable"]:
        return {"ok": False, "reason": "ocr"}
    q, missing = pc.parse_rows(res["rows"], TARGET_WIDTH)
    if missing:
        return {"ok": False, "reason": "; ".join(missing)}
    pc.finish_fields(q, path, res["scale"])
    return {"ok": True, "screen": q["screen"], "form": q["form"], "n": q["n"],
            "options": q["options"], "correct": q["correct"],
            "question": q["question"], "explanation": q["explanation"][:120]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    files = sorted(p for p in INBOX.glob("tg_*.jpg") if args.only in p.name)
    if not files:
        print("No hay capturas en inbox/ (este equipo no las tiene).")
        return 0
    expected = json.loads(EXPECTED.read_text(encoding="utf-8")) if EXPECTED.exists() else {}
    results, fails = {}, 0
    for f in files:
        got = parse_one(f)
        results[f.name] = got
        exp = expected.get(f.name)
        if args.update or exp is None:
            tag = "nuevo" if exp is None else "actualizado"
            print(f"  {tag:12} {f.name}: {got.get('screen','-')} F{got.get('form')} #{got.get('n')} "
                  f"{got.get('options')} ✓{str(got.get('correct'))[:25]}")
            continue
        keys = ("ok", "screen", "form", "n", "options", "correct")
        diff = {k: (exp.get(k), got.get(k)) for k in keys if exp.get(k) != got.get(k)}
        if diff:
            fails += 1
            print(f"  CAMBIÓ {f.name}:")
            for k, (a, b) in diff.items():
                print(f"      {k}: {a!r}  →  {b!r}")
    if args.update:
        EXPECTED.parent.mkdir(exist_ok=True)
        EXPECTED.write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"Guardado lo esperado para {len(results)} capturas en {EXPECTED.relative_to(REPO)}")
        return 0
    print(f"{len(files)} capturas · {fails} con cambios estructurales")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
