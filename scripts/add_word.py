#!/usr/bin/env python3
"""
Agrega una palabra al diccionario manteniendo la numeración consecutiva.

Uso:
    python scripts/add_word.py "windscreen" "parabrisas (británico/australiano)"
    python scripts/add_word.py "dud" "algo que falla" --section form87
"""

import argparse
import json
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "vocabulary.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("en", help="palabra o expresión en inglés")
    ap.add_argument("es", help="traducción y notas en español")
    ap.add_argument("--section", default="personal",
                    help="id de la sección destino (por defecto: personal)")
    args = ap.parse_args()

    d = json.loads(DATA.read_text(encoding="utf-8"))

    highest = 0
    for s in d["sections"]:
        for e in s["entries"]:
            highest = max(highest, e["n"])

    target = next((s for s in d["sections"] if s["id"] == args.section), None)
    if target is None:
        target = {"id": args.section, "title": f"Sección {args.section}",
                  "subtitle": None, "entries": []}
        d["sections"].append(target)

    duplicates = [e["en"] for s in d["sections"] for e in s["entries"]
                  if e["en"].lower() == args.en.lower()]
    if duplicates:
        print(f"AVISO: '{args.en}' ya existe en el listado. Se agrega de todos modos.")

    target["entries"].append({"n": highest + 1, "en": args.en, "es": args.es})
    d["meta"]["total_confirmed"] = sum(len(s["entries"]) for s in d["sections"])
    d["meta"]["last_updated"] = date.today().isoformat()

    DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{highest + 1}. {args.en} — {args.es}")
    print(f"Total: {d['meta']['total_confirmed']} palabras")


if __name__ == "__main__":
    main()
