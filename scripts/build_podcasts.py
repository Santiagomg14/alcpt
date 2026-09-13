#!/usr/bin/env python3
"""
Genera los podcasts del cuaderno: guiones + MP3 con voces neuronales (edge-tts).

Dos series:
  * vocab     — todo el diccionario numerado, en episodios de ≤10 minutos. Cada
                palabra se oye en inglés, luego su significado en español, y otra
                vez en inglés para repetirla.
  * lecturas  — una lectura condensada por episodio (data/readings.json): resumen
                en inglés, glosario bilingüe y la pregunta de comprobación.

Solo se renderizan los episodios nuevos o cuyo guion cambió (se compara un hash),
así que correrlo tras agregar una palabra tarda segundos, no minutos.

Uso
---
    python scripts/build_podcasts.py             # guiones + audio que falte
    python scripts/build_podcasts.py --dry-run   # solo guiones y estimación, sin red
    python scripts/build_podcasts.py --force     # re-renderiza todo

Lee:     data/vocabulary.json, data/readings.json
Escribe: data/podcasts.json, docs/audio/*.mp3

Si edge-tts no está instalado, el script avisa y termina sin error para no
bloquear la regeneración del resto de documentos.
"""

import argparse
import asyncio
import hashlib
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
AUDIO = ROOT / "docs" / "audio"
PODCASTS = DATA / "podcasts.json"

VOICES = {"en": "en-US-AndrewNeural", "es": "es-CO-SalomeNeural"}
RATE = {"en": "-5%", "es": "-5%"}
MAX_SECONDS = 600            # tope pedido: 10 minutos
# El último episodio de vocabulario va creciendo con cada palabra nueva. Volver a
# renderizarlo cada vez metía un MP3 de ~1,4 MB en el historial de git por cada
# palabra (vocab-07 ya llevaba 5 versiones). Se rehace solo cuando ha crecido lo
# suficiente, o cuando ya está completo. `--force` lo rehace igualmente.
MIN_PALABRAS_NUEVAS = 10
TARGET_SECONDS = 540         # margen para que la estimación no se pase
WPM = {"en": 158, "es": 150}  # medido con estas voces y este rate
SEG_OVERHEAD = 1.4            # silencio inicial/final que trae cada segmento de edge-tts (medido)

# Trama MP3 de silencio: MPEG-2 Layer III, 24 kHz, 48 kbps, mono = 144 bytes, 24 ms.
# Es el mismo formato que entrega edge-tts, así que se puede intercalar sin recodificar.
SILENT_FRAME = bytes.fromhex("fff364c0") + bytes(140)
FRAME_SECONDS = 576 / 24000

TOPIC_EN = {"tech": "technology and computing", "math": "mathematics",
            "humanities": "the humanities", "social": "the social sciences",
            "science": "the natural sciences"}


# --- guiones ----------------------------------------------------------------------
def seg(voice, text, pause=0.0):
    return {"v": voice, "t": " ".join(str(text).split()), "p": pause}


def estimate(segments):
    total = 0.0
    for s in segments:
        total += len(s["t"].split()) / WPM[s["v"]] * 60 + SEG_OVERHEAD + s["p"]
    return total


def short_meaning(es, limit=110):
    """Primeras acepciones de la traducción, para que el episodio no se alargue."""
    parts = [p.strip() for p in es.split(";") if p.strip()]
    out = parts[0] if parts else es
    for p in parts[1:]:
        if len(out) + len(p) + 2 > limit:
            break
        out += "; " + p
    return out


def word_segments(e):
    return [
        seg("en", f"{e['n']}. {e['en']}.", 0.5),
        seg("es", short_meaning(e["es"]) + ".", 0.4),
        seg("en", f"{e['en']}.", 1.1),
    ]


def vocab_episodes(vocab):
    words = sorted((e for s in vocab["sections"] for e in s["entries"]), key=lambda e: e["n"])
    section_of = {e["n"]: s["title"] for s in vocab["sections"] for e in s["entries"]}

    # Reparto en bloques que quepan en TARGET_SECONDS según la estimación.
    blocks, cur, cur_t = [], [], 0.0
    for e in words:
        t = estimate(word_segments(e))
        if cur and cur_t + t > TARGET_SECONDS - 40:   # 40 s para intro y cierre
            blocks.append(cur)
            cur, cur_t = [], 0.0
        cur.append(e)
        cur_t += t
    if cur:
        blocks.append(cur)

    episodes = []
    for i, block in enumerate(blocks, 1):
        first, last = block[0]["n"], block[-1]["n"]
        sections = []
        for e in block:
            st = section_of[e["n"]]
            if st not in sections:
                sections.append(st)
        segs = [seg("en", f"ALCPT Notebook. Vocabulary, episode {i}: words {first} to {last}. "
                          "Listen to each word, then its meaning in Spanish, and repeat the word "
                          "out loud before the next one.", 1.2)]
        for e in block:
            segs += word_segments(e)
        segs.append(seg("en", f"End of episode {i}. Words {first} to {last}. "
                              "Play it again tomorrow: repetition is what makes them stick.", 0.5))
        episodes.append({
            "id": f"vocab-{i:02d}",
            "series": "vocab",
            "title": f"Palabras {first}–{last}",
            "subtitle": " · ".join(re.sub(r"^[A-Z]\. |Vocabulario extraído del? ", "", s) for s in sections),
            "words": [first, last],
            "count": len(block),
            "script": segs,
        })
    return episodes


def readings_topic_title(readings, topic_id):
    for t in readings.get("topics", []):
        if t["id"] == topic_id:
            return t["title"]
    return ""


def reading_episodes(readings):
    episodes = []
    items = [it for it in readings.get("items", []) if it.get("summary")]
    for it in items:
        topic = TOPIC_EN.get(it.get("topic"), "general knowledge")
        segs = [seg("en", f"ALCPT Notebook. Readings. {it['title']}. "
                          f"A ThoughtCo article on {topic}, condensed for level B2.", 1.2)]
        for p in it["summary"]:
            segs.append(seg("en", p, 0.9))
        if it.get("key_points"):
            segs.append(seg("en", "Key points.", 0.6))
            for k in it["key_points"]:
                segs.append(seg("en", k, 0.6))
        if it.get("glossary"):
            segs.append(seg("en", "Key vocabulary. Listen and repeat.", 0.8))
            for g in it["glossary"]:
                segs.append(seg("en", g["en"] + ".", 0.4))
                segs.append(seg("es", short_meaning(g["es"]) + ".", 0.4))
                segs.append(seg("en", g["en"] + ".", 0.9))
        q = it.get("question")
        if q:
            letters = "ABCD"
            opts = " ".join(f"{letters[i]}. {o}." for i, o in enumerate(q["options"][:4]))
            segs.append(seg("en", "Comprehension check. " + q["stem"], 0.6))
            segs.append(seg("en", opts, 2.5))
            idx = q["options"].index(q["answer"]) if q["answer"] in q["options"] else -1
            ans = f"{letters[idx]}. " if 0 <= idx < 4 else ""
            segs.append(seg("en", f"The answer is {ans}{q['answer']}.", 0.8))
        segs.append(seg("en", "End of this reading. The full text and the glossary are in the "
                              "Lecturas tab of the notebook.", 0.5))
        episodes.append({
            "id": f"lectura-{it['id']}",
            "series": "lecturas",
            "title": it["title"],
            "subtitle": readings_topic_title(readings, it.get("topic")),
            "reading": it["id"],
            "topic": it.get("topic"),
            "script": segs,
        })
    return episodes


def script_hash(ep):
    payload = json.dumps({"s": ep["script"], "v": VOICES, "r": RATE},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


# --- audio ------------------------------------------------------------------------
def silence(seconds):
    return SILENT_FRAME * max(0, round(seconds / FRAME_SECONDS))


async def tts(text, voice, rate, tries=3):
    import edge_tts
    last = None
    for i in range(tries):
        try:
            buf = bytearray()
            async for ch in edge_tts.Communicate(text, voice, rate=rate).stream():
                if ch["type"] == "audio":
                    buf += ch["data"]
            if buf:
                return bytes(buf)
            last = "respuesta vacía"
        except Exception as e:  # red, límite del servicio…
            last = e
        await asyncio.sleep(2 * (i + 1))
    raise RuntimeError(f"edge-tts falló: {last}")


async def render(ep, out_path):
    sem = asyncio.Semaphore(4)

    async def one(s):
        async with sem:
            return await tts(s["t"], VOICES[s["v"]], RATE[s["v"]])

    chunks = await asyncio.gather(*(one(s) for s in ep["script"]))
    data = bytearray(silence(0.4))
    for s, audio in zip(ep["script"], chunks):
        data += audio
        data += silence(s["p"])
    data += silence(0.6)
    out_path.write_bytes(bytes(data))


def mp3_seconds(path):
    try:
        from mutagen.mp3 import MP3
        return round(MP3(str(path)).info.length, 1)
    except Exception:
        # 48 kbps constantes: bytes * 8 / 48000
        return round(path.stat().st_size * 8 / 48000, 1)


# --- principal --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="solo guiones, sin generar audio")
    ap.add_argument("--force", action="store_true", help="re-renderiza todos los episodios")
    ap.add_argument("--only", help="solo el episodio con este id (p. ej. vocab-03)")
    ap.add_argument("--adopt", action="store_true",
                    help="da por buenos los MP3 que ya existan sin registro (tras un render "
                         "interrumpido); úsalo solo si el guion no cambió desde que se generaron")
    args = ap.parse_args()

    vocab = json.loads((DATA / "vocabulary.json").read_text(encoding="utf-8"))
    readings = {"items": [], "topics": []}
    if (DATA / "readings.json").exists():
        readings = json.loads((DATA / "readings.json").read_text(encoding="utf-8"))
    previous = {}
    if PODCASTS.exists():
        previous = {e["id"]: e for e in
                    json.loads(PODCASTS.read_text(encoding="utf-8"))["episodes"]}

    episodes = vocab_episodes(vocab) + reading_episodes(readings)
    for ep in episodes:
        ep["hash"] = script_hash(ep)
        ep["file"] = f"audio/{ep['id']}.mp3"
        ep["estimate"] = round(estimate(ep["script"]))

    have_tts = True
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        have_tts = False
        print("AVISO: edge-tts no está instalado (pip install -r requirements.txt); "
              "se actualizan los guiones pero no el audio.")

    AUDIO.mkdir(parents=True, exist_ok=True)
    todo = []
    for ep in episodes:
        path = AUDIO / f"{ep['id']}.mp3"
        prev = previous.get(ep["id"])
        fresh = prev and prev.get("hash") == ep["hash"] and path.exists() and prev.get("seconds")
        # Episodio de vocabulario aún incompleto: esperar a juntar unas cuantas
        # palabras antes de rehacerlo, para no llenar el historial de MP3.
        if (not fresh and prev and path.exists() and prev.get("seconds")
                and ep["series"] == "vocab" and not args.force
                and ep["estimate"] < MAX_SECONDS
                and (ep.get("count", 0) - (prev.get("count") or 0)) < MIN_PALABRAS_NUEVAS):
            nuevas = ep.get("count", 0) - (prev.get("count") or 0)
            print(f"  {ep['id']}: {nuevas} palabra(s) nueva(s), "
                  f"espero a {MIN_PALABRAS_NUEVAS} para rehacerlo (--force lo fuerza)")
            ep["count"] = prev.get("count", ep.get("count"))
            ep["words"] = prev.get("words", ep.get("words"))
            ep["hash"] = prev.get("hash")
            fresh = True
        if fresh and not args.force:
            ep["seconds"], ep["bytes"], ep["built"] = prev["seconds"], prev["bytes"], prev["built"]
        elif args.adopt and path.exists() and not args.force:
            ep["seconds"] = mp3_seconds(path)
            ep["bytes"] = path.stat().st_size
            ep["built"] = date.fromtimestamp(path.stat().st_mtime).isoformat()
            print(f"  adoptado {ep['id']}: {ep['seconds']:.0f}s")
        elif args.only and ep["id"] != args.only:
            if prev:
                ep.update({k: prev.get(k) for k in ("seconds", "bytes", "built")})
        else:
            todo.append(ep)

    print(f"{len(episodes)} episodios · {len(todo)} por renderizar")
    if not args.dry_run and have_tts:
        for ep in todo:
            path = AUDIO / f"{ep['id']}.mp3"
            print(f"  renderizando {ep['id']} ({len(ep['script'])} segmentos, "
                  f"~{ep['estimate']}s)…", end=" ", flush=True)
            try:
                asyncio.run(render(ep, path))
            except Exception as e:
                print(f"ERROR: {e}")
                continue
            ep["seconds"] = mp3_seconds(path)
            ep["bytes"] = path.stat().st_size
            ep["built"] = date.today().isoformat()
            flag = "  ¡SUPERA 10 MIN!" if ep["seconds"] > MAX_SECONDS else ""
            print(f"{ep['seconds']:.0f}s, {ep['bytes'] / 1024:.0f} KB{flag}")
            write_index(episodes)
    else:
        for ep in todo:
            print(f"  pendiente {ep['id']}: ~{ep['estimate']}s, {len(ep['script'])} segmentos")

    # Limpia MP3 huérfanos (episodios que ya no existen, p. ej. al re-bloquear el vocabulario)
    valid = {f"{ep['id']}.mp3" for ep in episodes}
    for f in AUDIO.glob("*.mp3"):
        if f.name not in valid:
            f.unlink()
            print(f"  borrado huérfano {f.name}")

    write_index(episodes)
    total = sum(e.get("seconds") or 0 for e in episodes)
    print(f"OK -> {PODCASTS}  ({total / 60:.0f} min de audio en total)")


def write_index(episodes):
    """Escribe data/podcasts.json. Se llama tras cada episodio para no perder nada si
    el proceso se interrumpe a mitad de camino."""
    out = {
        "meta": {
            "intro": ("Audios de diez minutos como máximo para estudiar sin pantalla. La serie de "
                      "vocabulario recorre todo el diccionario en orden; la de lecturas condensa "
                      "artículos de ThoughtCo sobre temas fuera de la rutina militar."),
            "voices": VOICES, "rate": RATE, "max_seconds": MAX_SECONDS,
            "last_updated": date.today().isoformat(),
            "total": len(episodes),
        },
        "series": [
            {"id": "vocab", "title": "Vocabulario en audio",
             "note": ("Cada palabra se escucha en inglés, después su significado en español y de "
                      "nuevo en inglés. Los episodios siguen la numeración del diccionario.")},
            {"id": "lecturas", "title": "Lecturas condensadas",
             "note": ("Resumen en inglés de un artículo, sus palabras clave con traducción y una "
                      "pregunta de comprobación al final.")},
        ],
        "episodes": episodes,
    }
    PODCASTS.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
