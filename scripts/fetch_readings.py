#!/usr/bin/env python3
"""
Trae lecturas de ThoughtCo o de Wikipedia y las condensa al nivel B2 para la
pestaña «Lecturas».

Flujo
-----
  1. --discover  lista artículos de una o varias secciones (no escribe nada).
  2. --add       descarga cada artículo, extrae el texto limpio y lo guarda en
                 inbox/readings/<id>.txt (fuera del repo); en data/readings.json
                 queda la entrada con sus metadatos y `summary: null` (pendiente).
  3. --condense  pasa cada pendiente por Claude Code (`claude -p`, igual que el
                 bot) y guarda resumen B2, puntos clave, glosario y 4 preguntas
                 de comprensión estilo ALCPT (idea principal, detalle, vocabulario
                 en contexto e inferencia).
  4. --more-questions  completa hasta 4 preguntas en las lecturas antiguas, que
                 tenían una sola; parte del resumen ya guardado (barato).

Wikipedia (desde el 29 sep): ThoughtCo bloquea la IP del servidor, y Brayhan pidió
temas que ThoughtCo no cubre (C, C++, máquinas de estado, AOCS). Se lee con la API
pública (texto plano), el id es «wiki-<pageid>» y la lectura cita la fuente y la
licencia (CC BY-SA 4.0).

Uso
---
    python scripts/fetch_readings.py --discover computer-science math --max 15
    python scripts/fetch_readings.py --add https://www.thoughtco.com/...-4172097 [URL...]
    python scripts/fetch_readings.py --add https://en.wikipedia.org/wiki/C%2B%2B --topic tech
    python scripts/fetch_readings.py --more-questions
    python scripts/fetch_readings.py --add-from-section philosophy --max 2
    python scripts/fetch_readings.py --condense
    python scripts/fetch_readings.py --list

Secciones admitidas: ver SECTIONS. El resumen se escribe en inglés (práctica de
lectura) y el glosario inglés→español, como el resto del cuaderno.
"""

import argparse
import html as htmllib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Faltan dependencias. Instala con: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW_DIR = ROOT / "inbox" / "readings"        # texto original: fuera del repo
READINGS = DATA / "readings.json"

BASE = "https://www.thoughtco.com/"
HEADERS = {
    # Sin cabeceras de navegador el sitio responde 402.
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# alias -> (slug de la sección, tema por defecto)
SECTIONS = {
    "computer-science": ("computer-science-4133486", "tech"),
    "math": ("math-4133545", "math"),
    "arithmetic": ("arithmetic-4133542", "math"),
    "pre-algebra": ("pre-algebra-and-algebra-4133541", "math"),
    "geometry": ("geometry-4133540", "math"),
    "statistics": ("statistics-4133539", "math"),
    "humanities": ("humanities-4133358", "humanities"),
    "history": ("history-and-culture-4133356", "humanities"),
    "geography": ("geography-4133035", "humanities"),
    "philosophy": ("philosophy-4133025", "humanities"),
    "literature": ("literature-4133251", "humanities"),
    "issues": ("issues-4133022", "humanities"),
    "social-sciences": ("social-sciences-4133522", "social"),
    "science": ("science-4132464", "science"),
    "animals": ("animals-and-nature-4133421", "science"),
}

TOPICS = {
    "tech": {"title": "Tecnología y computación", "en": "Technology and computing"},
    "aero": {"title": "Ingeniería aeroespacial", "en": "Aerospace engineering"},
    "culture": {"title": "Cultura general", "en": "General culture"},
    "math": {"title": "Matemáticas", "en": "Mathematics"},
    "humanities": {"title": "Humanidades", "en": "Humanities"},
    "social": {"title": "Ciencias sociales", "en": "Social sciences"},
    "science": {"title": "Ciencias naturales", "en": "Natural sciences"},
}

# La miga de pan del artículo manda sobre la sección desde la que se descubrió.
CRUMB_TOPIC = {
    "Computer Science": "tech", "Math": "math", "Social Sciences": "social",
    "Science": "science", "Animals & Nature": "science", "Humanities": "humanities",
}

MAX_WORDS_TO_CLAUDE = 4500


# --- utilidades -----------------------------------------------------------------
def load():
    if READINGS.exists():
        return json.loads(READINGS.read_text(encoding="utf-8"))
    return {
        "meta": {
            "source": "ThoughtCo (thoughtco.com)",
            "intro": ("Artículos de divulgación condensados al nivel B2: se leen en inglés, con "
                      "glosario en español y una pregunta de comprobación al final."),
            "last_updated": None,
        },
        "topics": [{"id": k, "title": v["title"]} for k, v in TOPICS.items()],
        "items": [],
    }


def save(db):
    db["meta"]["last_updated"] = date.today().isoformat()
    db["meta"]["total"] = len(db["items"])
    READINGS.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def article_id(url):
    m = re.search(r"-(\d{5,9})/?$", url.strip())
    return m.group(1) if m else None


BLOQUEADO = (
    "ThoughtCo bloquea las peticiones desde este equipo (HTTP {code}); no es cosa de "
    "las cabeceras: rechaza hasta la portada, así que el bloqueo es por dirección IP. "
    "Comprobado el 13 sep 2026 en el servidor. Las lecturas hay que traerlas desde el "
    "portátil (misma orden: python scripts/fetch_readings.py …) y subirlas al repo; "
    "todo lo demás del bot sí funciona aquí."
)


def get(url, tries=3):
    last = ""
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=40)
            if r.status_code == 200:
                return r.text
            if r.status_code in (402, 403, 451):
                raise RuntimeError(BLOQUEADO.format(code=r.status_code))
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {last}")


# --- descubrimiento -------------------------------------------------------------
def discover(alias, known_ids):
    slug, _topic = SECTIONS[alias]
    soup = BeautifulSoup(get(BASE + slug), "html.parser")
    out, seen = [], set()
    for card in soup.select("a.card[href]"):
        href = card["href"].split("?")[0]
        title = card.select_one(".card__title-text")
        aid = article_id(href)
        if not aid or not title or aid in seen or aid in known_ids:
            continue
        seen.add(aid)
        out.append({"id": aid, "url": href, "title": title.get_text(" ", strip=True)})
    return out


# --- extracción del artículo ----------------------------------------------------
def parse_article(html, url):
    soup = BeautifulSoup(html, "html.parser")
    canonical = soup.find("link", rel="canonical")
    canonical = canonical["href"] if canonical else url

    ld = {}
    for sc in soup.select('script[type*="ld+json"]'):
        try:
            d = json.loads(sc.get_text())
        except ValueError:
            continue
        for it in d if isinstance(d, list) else [d]:
            types = it.get("@type", [])
            types = types if isinstance(types, list) else [types]
            if "Article" in types or "NewsArticle" in types:
                ld = it
                break
        if ld:
            break

    h1 = soup.find("h1")
    title = ld.get("headline") or (h1.get_text(" ", strip=True) if h1 else None)
    title = htmllib.unescape(title or "").strip()
    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = htmllib.unescape(ld.get("description") or (desc_tag["content"] if desc_tag else ""))
    authors = ld.get("author") or []
    authors = authors if isinstance(authors, list) else [authors]
    author = ", ".join(a.get("name", "") for a in authors if isinstance(a, dict)) or None
    crumbs = [a.get_text(" ", strip=True)
              for a in soup.select('[class*="breadcrumb"] a')]

    body = soup.select_one(".article-content") or soup.select_one("article")
    if body is None:
        raise RuntimeError("No encuentro el cuerpo del artículo (¿cambió el HTML?)")
    parts = []
    for block in body.select(".mntl-sc-block"):
        cls = " ".join(block.get("class", []))
        if "mntl-sc-block-heading" in cls:
            parts.append("## " + block.get_text(" ", strip=True))
        elif "mntl-sc-block-html" in cls:
            els = block.find_all(["p", "li", "h3", "h4"])
            if els:
                for el in els:
                    t = el.get_text(" ", strip=True)
                    if t:
                        parts.append(("- " if el.name == "li" else "") + t)
            else:
                t = block.get_text(" ", strip=True)
                if t:
                    parts.append(t)
        # imágenes, anuncios, vídeos y avisos se omiten
    if not parts:  # estructura alterna: párrafos sueltos
        parts = [p.get_text(" ", strip=True) for p in body.find_all("p")]
    text = "\n\n".join(parts)
    if len(text.split()) < 120:
        raise RuntimeError("El texto extraído es demasiado corto; no parece un artículo")

    topic = None
    for c in crumbs:
        if c in CRUMB_TOPIC:
            topic = CRUMB_TOPIC[c]
            break
    return {
        "id": article_id(canonical) or article_id(url),
        "url": canonical,
        "title": title,
        "description": description,
        "author": author,
        "published": (ld.get("datePublished") or "")[:10] or None,
        "modified": (ld.get("dateModified") or "")[:10] or None,
        "path": crumbs,
        "topic": topic,
        "original_words": len(text.split()),
    }, text


# --- Wikipedia ---------------------------------------------------------------------
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_SKIP = {"See also", "References", "Notes", "Further reading", "External links",
             "Bibliography", "Sources", "Citations", "Footnotes", "Gallery"}


def is_wikipedia(url):
    return bool(re.match(r"https?://en\.(m\.)?wikipedia\.org/wiki/", url.strip()))


def fetch_wikipedia(url):
    """Texto plano de un artículo de Wikipedia en inglés, sin referencias."""
    from urllib.parse import unquote
    title = unquote(url.strip().split("/wiki/", 1)[1].split("#")[0]).replace("_", " ")
    params = {"action": "query", "prop": "extracts|info|description",
              "explaintext": 1, "inprop": "url", "redirects": 1,
              "titles": title, "format": "json", "formatversion": 2}
    for attempt in range(5):
        r = requests.get(WIKI_API, timeout=40, params=params,
                         headers={"User-Agent": "ALCPT-notebook/1.0 (study notes)"})
        if r.status_code != 429:          # 429: Wikipedia pide bajar el ritmo
            break
        time.sleep(int(r.headers.get("Retry-After", "0") or 0) or 15 * (attempt + 1))
    r.raise_for_status()
    page = r.json()["query"]["pages"][0]
    if page.get("missing"):
        raise RuntimeError(f"Wikipedia no tiene el artículo «{title}»")
    parts, skip = [], False
    for line in page["extract"].splitlines():
        m = re.match(r"^(=+)\s*(.*?)\s*=+$", line)
        if m:
            skip = m.group(2) in WIKI_SKIP if len(m.group(1)) == 2 else skip
            if not skip:
                parts.append("## " + m.group(2))
            continue
        if not skip and line.strip():
            parts.append(line.strip())
    text = "\n\n".join(parts)
    meta = {
        "id": f"wiki-{page['pageid']}",
        "url": page.get("canonicalurl") or url,
        "title": page["title"],
        "description": page.get("description", ""),
        "author": "Wikipedia contributors",
        "published": None,
        "modified": (page.get("touched") or "")[:10] or None,
        "path": ["Wikipedia", "CC BY-SA 4.0"],
        "source": "Wikipedia",
        "license": "CC BY-SA 4.0",
        "topic": None,
        "original_words": len(text.split()),
    }
    return meta, text


def add(db, url, topic_hint=None, quiet=False):
    if is_wikipedia(url):
        meta, text = fetch_wikipedia(url)
        if any(it["id"] == meta["id"] for it in db["items"]):
            if not quiet:
                print(f"  ya estaba: {meta['id']}")
            return None
        meta["topic"] = topic_hint or "culture"
        meta["fetched"] = date.today().isoformat()
        meta["summary"] = None
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DIR / f"{meta['id']}.txt").write_text(
            f"# {meta['title']}\n{meta['url']}\n\n{text}", encoding="utf-8")
        db["items"].append(meta)
        if not quiet:
            print(f"  + {meta['id']} [{meta['topic']}] {meta['title']} ({meta['original_words']} palabras)")
        return meta
    aid = article_id(url)
    if not aid:
        raise RuntimeError(f"La URL no parece de ThoughtCo (falta el id numérico): {url}")
    if any(it["id"] == aid for it in db["items"]):
        if not quiet:
            print(f"  ya estaba: {aid}")
        return None
    meta, text = parse_article(get(url), url)
    if any(it["id"] == meta["id"] for it in db["items"]):
        if not quiet:
            print(f"  ya estaba (canónico): {meta['id']}")
        return None
    meta["topic"] = meta["topic"] or topic_hint or "humanities"
    meta["fetched"] = date.today().isoformat()
    meta["summary"] = None
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / f"{meta['id']}.txt").write_text(
        f"# {meta['title']}\n{meta['url']}\n\n{text}", encoding="utf-8")
    db["items"].append(meta)
    if not quiet:
        print(f"  + {meta['id']} [{meta['topic']}] {meta['title']} ({meta['original_words']} palabras)")
    return meta


# --- condensación con Claude Code -----------------------------------------------
def read_env():
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("CLAUDE_BIN", "CLAUDE_MODEL"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def find_claude(env):
    if env.get("CLAUDE_BIN"):
        return env["CLAUDE_BIN"]
    for name in ("claude", "claude.cmd", "claude.exe"):
        f = shutil.which(name)
        if f:
            return f
    return None


PROMPT = """Eres el editor de un cuaderno de inglés para Brayhan, estudiante hispanohablante de nivel B2 (inglés militar, se prepara para el ALCPT). Te paso por la entrada estándar un artículo de {source} titulado «{title}». Condénsalo para que él lo lea en inglés. Si es un tema técnico (programación, control de satélites, máquinas de estado), explica cómo funciona de verdad, con los conceptos clave y un ejemplo concreto, sin perder rigor.

Devuelve ÚNICAMENTE un objeto JSON válido, sin texto antes ni después, sin bloques de código, con estas claves:

"summary": lista de 3 a 5 párrafos EN INGLÉS, entre 250 y 350 palabras en total. Nivel B2: oraciones claras y directas, sin simplificar los términos técnicos importantes (se conservan y se explican con naturalidad). Fiel al original; nada de opiniones propias ni de información que no esté en el texto.
"key_points": lista de 3 a 5 frases cortas EN INGLÉS con lo que hay que recordar.
"glossary": lista de 6 a 10 objetos {{"en": ..., "es": ...}} con palabras o expresiones que APARECEN en tu resumen y que un estudiante B2 probablemente no conoce. Nada básico ni intermedio bajo (no: important, people, history, problem, build). Sí: términos técnicos, idioms, phrasal verbs no obvios, palabras cultas. En "es": traducción y matiz, separados por punto y coma, en español.
"questions": lista de 4 objetos {{"stem": ..., "options": [4 opciones], "answer": ...}}: preguntas de comprensión EN INGLÉS al estilo del ALCPT sobre el contenido del resumen, en este orden: 1) idea principal, 2) un detalle concreto, 3) el significado de una palabra o expresión del resumen en su contexto, 4) una inferencia razonable. Opciones plausibles y de longitud parecida; "answer" es el texto exacto de la opción correcta.
"""

QUESTIONS_PROMPT = """Eres el editor de un cuaderno de inglés para Brayhan, estudiante hispanohablante de nivel B2 que se prepara para el ALCPT. Te paso por la entrada estándar el resumen en inglés de una lectura titulada «{title}» y la pregunta de comprensión que ya tiene.

Devuelve ÚNICAMENTE un objeto JSON válido, sin texto antes ni después, con la clave "questions": lista de {n} objetos {{"stem": ..., "options": [4 opciones], "answer": ...}}, preguntas NUEVAS EN INGLÉS al estilo del ALCPT que no repitan la existente, sobre: {kinds}. Solo sobre lo que dice el resumen. Opciones plausibles y de longitud parecida; "answer" es el texto exacto de la opción correcta.
"""


def check_questions(qs, n):
    if not isinstance(qs, list) or len(qs) < n:
        raise RuntimeError(f"Esperaba {n} preguntas y llegaron {len(qs) if isinstance(qs, list) else 0}")
    out = []
    for q in qs[:n]:
        if q.get("answer") not in q.get("options", []) or len(q.get("options", [])) != 4:
            raise RuntimeError("Una pregunta no trae 4 opciones o su respuesta no está entre ellas")
        out.append({"stem": q["stem"], "options": q["options"], "answer": q["answer"]})
    return out


def run_claude(prompt, text, env, claude):
    cmd = [claude, "-p", prompt, "--output-format", "text", "--allowed-tools", ""]
    if env.get("CLAUDE_MODEL"):
        cmd += ["--model", env["CLAUDE_MODEL"]]
    sub_env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    for attempt in (1, 2, 3):   # a veces el JSON sale mal formado: se pide otra vez
        res = subprocess.run(cmd, input=text, cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=900, env=sub_env)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout).strip()[-800:])
        out = res.stdout.strip()
        start, end = out.find("{"), out.rfind("}")
        try:
            if start < 0 or end < 0:
                raise ValueError("Claude no devolvió JSON:\n" + out[:500])
            return json.loads(out[start:end + 1])
        except ValueError as exc:
            if attempt == 3:
                raise RuntimeError(f"JSON inválido tras 3 intentos: {exc}")


def more_questions(entry, env, claude, total=4):
    """Completa hasta `total` preguntas a partir del resumen ya guardado."""
    have = entry.get("questions") or ([entry["question"]] if entry.get("question") else [])
    need = total - len(have)
    if need <= 0:
        return False
    kinds = ["idea principal", "un detalle concreto",
             "el significado de una palabra o expresión en su contexto",
             "una inferencia razonable"][-need:]
    text = "\n\n".join(entry["summary"]) + "\n\nPregunta existente: " + \
        json.dumps(have, ensure_ascii=False)
    data = run_claude(QUESTIONS_PROMPT.format(title=entry["title"], n=need,
                                              kinds="; ".join(kinds)), text, env, claude)
    entry["questions"] = have + check_questions(data.get("questions"), need)
    entry.pop("question", None)
    return True


def condense(entry, env, claude):
    raw = RAW_DIR / f"{entry['id']}.txt"
    if not raw.exists():
        if is_wikipedia(entry["url"]):
            _meta, text = fetch_wikipedia(entry["url"])
        else:
            _meta, text = parse_article(get(entry["url"]), entry["url"])
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        raw.write_text(f"# {entry['title']}\n{entry['url']}\n\n{text}", encoding="utf-8")
    text = raw.read_text(encoding="utf-8")
    words = text.split()
    if len(words) > MAX_WORDS_TO_CLAUDE:
        text = " ".join(words[:MAX_WORDS_TO_CLAUDE]) + "\n\n[…texto recortado…]"

    source = "Wikipedia" if entry.get("source") == "Wikipedia" else "divulgación de ThoughtCo"
    data = run_claude(PROMPT.format(title=entry["title"], source=source), text, env, claude)
    for k in ("summary", "key_points", "glossary", "questions"):
        if k not in data:
            raise RuntimeError(f"Falta la clave «{k}» en la respuesta")
    if isinstance(data["summary"], str):
        data["summary"] = [p for p in data["summary"].split("\n") if p.strip()]

    entry["summary"] = data["summary"]
    entry["key_points"] = data["key_points"]
    entry["glossary"] = [{"en": g["en"].strip(), "es": g["es"].strip()} for g in data["glossary"]]
    entry["questions"] = check_questions(data["questions"], 4)
    entry.pop("question", None)
    entry["summary_words"] = sum(len(p.split()) for p in data["summary"])
    entry["condensed"] = date.today().isoformat()


# --- CLI ------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--discover", nargs="+", metavar="SECCION",
                    help="lista artículos nuevos de estas secciones: " + ", ".join(SECTIONS))
    ap.add_argument("--add", nargs="+", metavar="URL", help="descarga y registra estos artículos")
    ap.add_argument("--add-from-section", nargs="+", metavar="SECCION",
                    help="descarga los primeros artículos nuevos de estas secciones")
    ap.add_argument("--max", type=int, default=10, help="tope por sección (descubrir / agregar)")
    ap.add_argument("--condense", action="store_true",
                    help="condensa las lecturas pendientes con Claude Code")
    ap.add_argument("--list", action="store_true", help="muestra las lecturas registradas")
    ap.add_argument("--topic", choices=list(TOPICS), help="tema para --add (Wikipedia no lo trae)")
    ap.add_argument("--more-questions", action="store_true",
                    help="completa hasta 4 preguntas en las lecturas que tienen menos")
    args = ap.parse_args()

    db = load()
    known = {it["id"] for it in db["items"]}
    changed = False

    if args.discover:
        for alias in args.discover:
            if alias not in SECTIONS:
                sys.exit(f"Sección desconocida: {alias}. Opciones: {', '.join(SECTIONS)}")
            found = discover(alias, known)[: args.max]
            print(f"\n## {alias} ({len(found)} nuevos)")
            for f in found:
                print(f"  {f['url']}\n      {f['title']}")

    if args.add:
        for url in args.add:
            try:
                if add(db, url, topic_hint=args.topic):
                    changed = True
            except Exception as e:  # seguimos con las demás
                print(f"  x {url}: {e}")
            time.sleep(1.5)

    if args.add_from_section:
        for alias in args.add_from_section:
            if alias not in SECTIONS:
                sys.exit(f"Sección desconocida: {alias}")
            _slug, topic = SECTIONS[alias]
            for f in discover(alias, known)[: args.max]:
                try:
                    if add(db, f["url"], topic_hint=topic):
                        changed = True
                        known.add(f["id"])
                except Exception as e:
                    print(f"  x {f['url']}: {e}")
                time.sleep(1.5)

    for t_id, t in TOPICS.items():                # temas nuevos (aero, culture…)
        if not any(x["id"] == t_id for x in db["topics"]):
            db["topics"].append({"id": t_id, "title": t["title"]})
            changed = True
    if changed:
        save(db)

    if args.more_questions:
        env = read_env()
        claude = find_claude(env)
        if not claude:
            sys.exit("No encuentro Claude Code. Instálalo o define CLAUDE_BIN en .env")
        for it in [i for i in db["items"] if i.get("summary")]:
            try:
                if more_questions(it, env, claude):
                    save(db)
                    print(f"  ok {it['id']} {it['title']}: {len(it['questions'])} preguntas")
            except Exception as e:
                print(f"  x  {it['id']} {it['title']}: {e}")

    if args.condense:
        env = read_env()
        claude = find_claude(env)
        if not claude:
            sys.exit("No encuentro Claude Code. Instálalo o define CLAUDE_BIN en .env")
        pending = [it for it in db["items"] if not it.get("summary")]
        print(f"\nCondensando {len(pending)} lecturas con Claude Code…")
        for it in pending:
            t0 = time.time()
            try:
                condense(it, env, claude)
                save(db)  # guardar tras cada una: si algo falla, no se pierde lo hecho
                print(f"  ok {it['id']} {it['title']} "
                      f"({it['summary_words']} palabras, {time.time() - t0:.0f}s)")
            except Exception as e:
                print(f"  x  {it['id']} {it['title']}: {e}")

    if args.list or not any([args.discover, args.add, args.add_from_section, args.condense,
                             args.more_questions]):
        print(f"{len(db['items'])} lecturas registradas")
        for it in db["items"]:
            state = "ok" if it.get("summary") else "PENDIENTE"
            print(f"  [{state:9}] {it['id']} [{it['topic']}] {it['title']}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        # Errores esperables (el sitio nos bloquea): mensaje limpio, sin traza,
        # para que el bot lo pueda enseñar tal cual por Telegram.
        sys.exit(str(exc))
