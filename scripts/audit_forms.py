#!/usr/bin/env python3
"""Auditoría de data/forms.json: qué preguntas están completas, cuáles esperan
otra pantalla y cuáles tienen síntomas de error de OCR o de parser.

Uso:
    python scripts/audit_forms.py              # resumen por formulario
    python scripts/audit_forms.py --form 65    # detalle de un formulario
    python scripts/audit_forms.py --json       # para el bot y para pruebas
    python scripts/audit_forms.py --strict     # sale con 1 si hay síntomas de error

Clasificación de cada pregunta:
    completa    enunciado, ≥2 opciones sin marcadores, correcta ∈ opciones, explicación
    pendiente   le falta la pantalla de pregunta o la de explicación (marcadores
                «(Question stem…», «(Options screen…», «(Explanation screen…»,
                «(Not shown…»); se completa sola cuando llegue esa captura
    sospechosa  síntomas que no se arreglan con otra captura: correcta que no está
                entre las opciones, más de 4 opciones, opción con palabras que no
                existen, enunciado pegado, explicación cortada
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FORMS = REPO / "data" / "forms.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))

PLACEHOLDER = re.compile(r"^\((Question stem|Options screen|Explanation screen|Not shown|unreadable)")


def looks_garbage(text):
    try:
        from parse_capture import looks_garbage as lg
        return lg(text)
    except Exception:  # noqa: BLE001
        return False


def classify(q):
    pending, suspicious = [], []
    opts = q.get("options", [])
    real_opts = [o for o in opts if not PLACEHOLDER.match(o)]
    if PLACEHOLDER.match(q.get("question", "")):
        pending.append("falta pantalla de pregunta (enunciado)")
    if any(PLACEHOLDER.match(o) for o in opts):
        pending.append("falta pantalla de pregunta (opciones)")
    if PLACEHOLDER.match(q.get("explanation", "")) or q.get("correct", "").startswith("(Not shown"):
        pending.append("falta pantalla de explicación")
    if q.get("correct") and not PLACEHOLDER.match(q["correct"]) and q["correct"] not in opts:
        suspicious.append("la correcta no está entre las opciones")
    if len(real_opts) > 4:
        suspicious.append(f"{len(real_opts)} opciones")
    for o in real_opts:
        if looks_garbage(o):
            suspicious.append(f"opción ilegible: «{o}»")
    if re.search(r"[a-z]{16,}", q.get("question", "")):
        suspicious.append("enunciado con palabras pegadas")
    e = q.get("explanation", "")
    if e and not PLACEHOLDER.match(e) and not re.search(r"[.!?\"”)]$", e.strip()):
        suspicious.append("explicación sin cierre (¿truncada?)")
    if suspicious:
        return "sospechosa", pending + suspicious
    if pending:
        return "pendiente", pending
    return "completa", []


def audit(forms_path=FORMS):
    data = json.loads(Path(forms_path).read_text(encoding="utf-8"))
    report = {"forms": {}, "totals": {"completa": 0, "pendiente": 0, "sospechosa": 0}}
    for f in data["forms"]:
        entry = {"completa": 0, "pendiente": 0, "sospechosa": 0, "items": []}
        for q in f["questions"]:
            state, notes = classify(q)
            entry[state] += 1
            report["totals"][state] += 1
            if notes:
                entry["items"].append({"n": q.get("n"), "state": state, "notes": notes})
        report["forms"][str(f["form"])] = entry
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--form", help="detalle de un formulario")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="código 1 si hay sospechosas")
    args = ap.parse_args()
    rep = audit()
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        t = rep["totals"]
        print(f"Preguntas: {sum(t.values())} · completas {t['completa']} · "
              f"pendientes {t['pendiente']} · sospechosas {t['sospechosa']}")
        for form, e in rep["forms"].items():
            if args.form and form != args.form:
                continue
            print(f"  Form {form:<26} {e['completa']:>3} completas  {e['pendiente']:>3} pendientes  "
                  f"{e['sospechosa']:>3} sospechosas")
            if args.form or e["sospechosa"]:
                for it in e["items"]:
                    if args.form or it["state"] == "sospechosa":
                        print(f"      #{it['n']:<4} {it['state']:10} {'; '.join(it['notes'])}")
    return 1 if args.strict and rep["totals"]["sospechosa"] else 0


if __name__ == "__main__":
    sys.exit(main())
