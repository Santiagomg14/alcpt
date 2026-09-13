#!/usr/bin/env python3
"""Procesa una carpeta entera de capturas: formularios ALCPT y listas de
vocabulario, en un solo proceso y sin IA.

Frente a llamar a parse_capture.py una vez por imagen, aquí el motor de OCR se
carga una sola vez (unos 2 s) y luego cada captura cuesta ~1,3 s en vez de ~3,5.
Para 500 imágenes son ~11 minutos en lugar de ~30.

Además lleva un registro de lo ya visto (`bot/processed.json`, sha256 del
archivo → qué se hizo con él): reenviar la misma captura no la vuelve a leer.
Con 500 fotos de las que muchas ya se procesaron, esto ahorra la mayor parte
del trabajo.

Uso:
    python scripts/process_batch.py inbox/lote1
    python scripts/process_batch.py inbox/lote1 --progress   # una línea JSON por imagen
    python scripts/process_batch.py inbox/lote1 --dry-run    # no escribe data/
    python scripts/process_batch.py inbox/lote1 --force      # ignora el registro

Salida final (JSON): totales por tipo y las capturas que no se pudieron leer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
REGISTRY = REPO / "bot" / "processed.json"
EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_registry() -> dict:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_registry(reg: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def process_one(path: Path, dry_run: bool = False) -> dict:
    """Una captura: primero como formulario, si no como lista de vocabulario."""
    from ocr_capture import ocr, TARGET_WIDTH
    import parse_capture as pc
    import parse_vocab_capture as pv

    res = ocr(path)
    path.with_suffix(".txt").write_text(res["text"], encoding="utf-8")
    if not res["usable"]:
        return {"kind": "ilegible",
                "detail": f"OCR poco fiable (confianza {res['confidence']:.2f})"}

    q, missing = pc.parse_rows(res["rows"], TARGET_WIDTH)
    if missing == ["número de pregunta"] and pc.resolve_missing_number(q):
        missing = []
    if not missing:
        pc.finish_fields(q, path, res["scale"])
        if dry_run:
            return {"kind": "form", "detail": f"Form {q['form']} #{q['n']} ({q['screen']})"}
        return {"kind": "form", "detail": pc.save(q)}

    pairs, why = pv.extract_pairs(res)
    if not why:
        if dry_run:
            return {"kind": "vocab", "detail": f"{len(pairs)} pares", "pairs": pairs}
        added, skipped = pv.save(pairs)
        return {"kind": "vocab", "detail": f"{len(added)} nuevas, {len(skipped)} repetidas",
                "added": [e["n"] for e in added]}
    return {"kind": "nada", "detail": "; ".join(missing)}


def run(folder: Path, progress=None, dry_run=False, force=False, stop=None) -> dict:
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in EXTS)
    reg = load_registry()
    totals = {"form": 0, "vocab": 0, "nada": 0, "ilegible": 0, "repetida": 0, "error": 0}
    problems = []
    t0 = time.time()
    for i, path in enumerate(files, 1):
        if stop and stop():
            break
        try:
            h = file_hash(path)
            if not force and h in reg:
                totals["repetida"] += 1
                out = {"kind": "repetida", "detail": reg[h]}
            else:
                out = process_one(path, dry_run)
                totals[out["kind"]] = totals.get(out["kind"], 0) + 1
                if not dry_run:
                    reg[h] = out["detail"][:120]
                if out["kind"] in ("nada", "ilegible"):
                    problems.append({"file": path.name, "why": out["detail"]})
        except Exception as exc:                       # una captura mala no para el lote
            totals["error"] += 1
            out = {"kind": "error", "detail": f"{type(exc).__name__}: {exc}"[:160]}
            problems.append({"file": path.name, "why": out["detail"]})
        if progress:
            progress({"i": i, "total": len(files), "file": path.name, **out})
        if not dry_run and i % 25 == 0:
            save_registry(reg)                          # por si se corta a mitad
    if not dry_run:
        save_registry(reg)
    return {"files": len(files), "seconds": round(time.time() - t0, 1),
            "totals": totals, "problems": problems[:40]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--progress", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="reprocesa aunque ya se hubiera visto")
    args = ap.parse_args()
    if not args.folder.is_dir():
        print(f"No es una carpeta: {args.folder}", file=sys.stderr)
        return 1
    rep = run(args.folder, dry_run=args.dry_run, force=args.force,
              progress=(lambda p: print(json.dumps(p, ensure_ascii=False), flush=True))
              if args.progress else None)
    print(json.dumps({"ok": True, **rep}, ensure_ascii=False))
    t = rep["totals"]
    print(f"\n{rep['files']} archivos en {rep['seconds']} s · "
          f"{t['form']} preguntas · {t['vocab']} listas · {t['repetida']} repetidas · "
          f"{t['nada'] + t['ilegible'] + t['error']} sin procesar", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
