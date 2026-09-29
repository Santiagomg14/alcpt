#!/usr/bin/env python3
"""
Datos que solo usa el podcast de vocabulario: traducción corta y frase de ejemplo.

Para cada palabra del diccionario guarda en data/podcast_vocab.json:
  * es       — como mucho 3 traducciones, las más relevantes, para que la voz en
               español no lea la definición entera (Basement o Stack tienen párrafos);
  * example  — una frase de ejemplo en inglés, natural y de nivel B2.

Lo escrito (vocabulary.json, PDF, web) no cambia: esto es solo para el audio.

Solo pide a Claude lo que falta o lo que cambió (se compara la palabra y su
traducción), de a 40 palabras por llamada y sin herramientas, así que tras
agregar una palabra cuesta unos cientos de tokens. Sin Claude a mano, el podcast
recorta la traducción por su cuenta y omite la frase: nunca bloquea el rebuild.

Uso
---
    python scripts/podcast_extras.py            # completa lo que falte
    python scripts/podcast_extras.py --dry-run  # dice cuántas faltan, sin llamar a Claude
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXTRAS = DATA / "podcast_vocab.json"
BATCH = 40
MODEL = os.environ.get("PODCAST_MODEL", "claude-haiku-4-5-20251001")

PROMPT = """Preparo un podcast de vocabulario para un hispanohablante de nivel B2 que estudia
para el ALCPT (inglés militar de la Fuerza Aérea). Para cada entrada te doy el número,
la palabra en inglés y su definición completa en español.

Devuelve SOLO un objeto JSON, sin texto alrededor ni bloque de código, con esta forma:
{{"<n>": {{"es": "...", "example": "..."}}, ...}}

- "es": entre 1 y 3 traducciones al español, las más relevantes y habituales para ese
  sentido, separadas por coma. Sin explicaciones, paréntesis, ejemplos ni notas
  gramaticales. Si la entrada aclara un sentido concreto (militar, técnico), prioriza
  ese. Máximo 3 términos.
- "example": una frase de ejemplo en inglés, natural, de 6 a 14 palabras, que use la
  palabra o expresión exactamente con el sentido de la definición. Si viene bien, que
  sea de contexto militar o cotidiano de una base.

Entradas:
{items}
"""


def fingerprint(e):
    return hashlib.sha1(f"{e['en']}|{e['es']}".encode("utf-8")).hexdigest()[:10]


def load_words():
    vocab = json.loads((DATA / "vocabulary.json").read_text(encoding="utf-8"))
    return sorted((e for s in vocab["sections"] for e in s["entries"]), key=lambda e: e["n"])


def load_extras():
    if EXTRAS.exists():
        return json.loads(EXTRAS.read_text(encoding="utf-8"))
    return {}


def missing(words, extras):
    return [e for e in words
            if extras.get(str(e["n"]), {}).get("fp") != fingerprint(e)]


def find_claude():
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    for name in ("claude", "claude.cmd", "claude.exe"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def ask(claude, batch):
    items = "\n".join(f"{e['n']}. {e['en']} — {e['es']}" for e in batch)
    cmd = [claude, "-p", PROMPT.format(items=items), "--allowed-tools", "", "--model", MODEL]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env,
                         timeout=600, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout or "sin salida").strip()[-300:])
    m = re.search(r"\{.*\}", res.stdout, re.S)
    if not m:
        raise RuntimeError("Claude no devolvió JSON")
    return json.loads(m.group(0))


def clean_es(text):
    """Refuerza el tope de 3 términos aunque el modelo se pase."""
    parts = [p.strip(" .") for p in re.split(r"[,;/]", text) if p.strip(" .")]
    return ", ".join(parts[:3])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    words, extras = load_words(), load_extras()
    todo = missing(words, extras)
    # quita lo de palabras que ya no existen
    alive = {str(e["n"]) for e in words}
    removed = [k for k in extras if k not in alive]
    for k in removed:
        del extras[k]
    print(f"podcast_extras: {len(todo)} palabras sin traducción corta o frase de ejemplo")
    if args.dry_run or not todo:
        if removed:
            EXTRAS.write_text(json.dumps(extras, ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8")
        return 0
    claude = find_claude()
    if not claude:
        print("podcast_extras: no encuentro Claude Code; el podcast recortará por su cuenta")
        return 0
    done = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            out = ask(claude, batch)
        except (RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            print(f"podcast_extras: el lote {i // BATCH + 1} falló ({exc}); sigo con el resto")
            continue
        for e in batch:
            got = out.get(str(e["n"])) or {}
            es, ex = clean_es(str(got.get("es", ""))), " ".join(str(got.get("example", "")).split())
            if es and ex:
                extras[str(e["n"])] = {"en": e["en"], "es": es, "example": ex,
                                       "fp": fingerprint(e)}
                done += 1
        # se guarda tras cada lote: si algo corta, no se pierde lo hecho
        EXTRAS.write_text(json.dumps(dict(sorted(extras.items(), key=lambda kv: int(kv[0]))),
                                     ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"podcast_extras: {min(i + BATCH, len(todo))}/{len(todo)}")
    print(f"podcast_extras: {done} completadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
