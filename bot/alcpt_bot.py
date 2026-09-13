#!/usr/bin/env python3
"""
Bot de Telegram que alimenta el diccionario ALCPT.

Qué hace
--------
  * Le mandas una palabra  ->  la traduce y la agrega a data/vocabulary.json
  * Le mandas "palabra = traduccion"  ->  la agrega tal cual, sin usar IA
  * Le mandas una captura del examen  ->  extrae la pregunta y la agrega a data/forms.json
  * Después de cada cambio: regenera PDF y páginas web, hace commit y push
    (y refresca fecha y conteos en handoff.md antes del commit)

Portabilidad
------------
No hay ninguna ruta fija: todo se resuelve desde la posición de este archivo dentro
del repositorio, así que funciona en cualquier equipo donde se clone (Windows, Linux
o macOS). Lo único que cambia por equipo es el archivo .env.

Uso
---
    pip install -r bot/requirements.txt
    cp .env.example .env      # y completa los valores
    python bot/alcpt_bot.py
"""

import json
import os
import platform
import re
import shutil
import signal
import zipfile
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Falta la dependencia 'requests'. Instala con: pip install -r bot/requirements.txt")

# --- rutas, todas relativas al repositorio -------------------------------------
REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
INBOX = REPO / "inbox"
SCRIPTS = REPO / "scripts"
STATE = Path(__file__).resolve().parent / "state.json"

API = "https://api.telegram.org/bot{token}/{method}"
FILE_API = "https://api.telegram.org/file/bot{token}/{path}"


# --- configuración -------------------------------------------------------------
def load_env():
    """Lee .env del repositorio sin depender de python-dotenv."""
    env = {}
    path = REPO / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    # las variables reales del sistema tienen prioridad sobre el archivo
    for k in ("TELEGRAM_TOKEN", "ALLOWED_USER_IDS", "CLAUDE_BIN", "GIT_PUSH", "CLAUDE_MODEL",
              "CAPTURE_FALLBACK", "FLUSH_DELAY", "VOCAB_POLISH"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


CFG = load_env()
TOKEN = CFG.get("TELEGRAM_TOKEN", "")
ALLOWED = {int(x) for x in CFG.get("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x}
GIT_PUSH = CFG.get("GIT_PUSH", "1") not in ("0", "false", "no")
CLAUDE_MODEL = CFG.get("CLAUDE_MODEL", "")
# Qué hacer cuando el procesador local no logra estructurar una captura:
#   "off"    (por defecto) avisa y deja el texto OCR en inbox/, sin gastar tokens
#   "claude" le pasa la imagen a Claude Code como antes
CAPTURE_FALLBACK = CFG.get("CAPTURE_FALLBACK", "off").strip().lower()


def find_claude():
    """Localiza el ejecutable de Claude Code en este equipo."""
    if CFG.get("CLAUDE_BIN"):
        return CFG["CLAUDE_BIN"]
    for name in ("claude", "claude.cmd", "claude.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


CLAUDE = find_claude()


LOG_FILE = Path(__file__).resolve().parent / "bot.log"


def redact(text):
    """Nunca dejar el token en el registro: los errores de red traen la URL completa."""
    text = str(text)
    return text.replace(TOKEN, "***") if TOKEN else text


def log(msg):
    """Escribe en consola y en bot/bot.log (como servicio no hay consola)."""
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {redact(msg)}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# --- Telegram ------------------------------------------------------------------
def api(method, **params):
    r = requests.post(API.format(token=TOKEN, method=method), json=params, timeout=70)
    r.raise_for_status()
    return r.json()


def send(chat_id, text, preview=False):
    for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]:
        api("sendMessage", chat_id=chat_id, text=chunk,
            disable_web_page_preview=not preview)


def download_file(file_id, dest_dir):
    info = api("getFile", file_id=file_id)["result"]
    remote = info["file_path"]
    suffix = Path(remote).suffix or ".jpg"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"tg_{datetime.now():%Y%m%d_%H%M%S}_{file_id[-8:]}{suffix}"
    with requests.get(FILE_API.format(token=TOKEN, path=remote), stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for block in r.iter_content(65536):
                fh.write(block)
    return dest


# --- Claude Code en modo no interactivo ----------------------------------------
def ask_claude(prompt, timeout=900, tools=True):
    """Ejecuta Claude Code sin interacción, dentro del repo, con permiso solo para
    editar. Con tools=False no puede tocar archivos: solo responde texto (barato,
    para pulir o traducir lo que el bot ya extrajo)."""
    if not CLAUDE:
        return False, ("No encuentro el ejecutable de Claude Code en este equipo. "
                       "Instálalo o define CLAUDE_BIN en el .env.")
    cmd = [CLAUDE, "-p", prompt]
    if tools:
        cmd += ["--permission-mode", "acceptEdits",
                "--allowed-tools", "Read", "Edit", "Write", "Glob", "Grep"]
    else:
        cmd += ["--allowed-tools", ""]
    if CLAUDE_MODEL:
        cmd += ["--model", CLAUDE_MODEL]
    try:
        res = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                             timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, "Claude Code tardó demasiado y se canceló."
    if res.returncode != 0:
        return False, (res.stderr or res.stdout or "error desconocido").strip()[-1500:]
    return True, (res.stdout or "").strip()


# --- construcción y git --------------------------------------------------------
def run(cmd, **kw):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def rebuild():
    """Regenera PDF, página espejo, cuaderno y la versión para GitHub Pages."""
    steps = [
        ("PDF", [sys.executable, str(SCRIPTS / "build_pdf.py")]),
        ("página espejo", [sys.executable, str(SCRIPTS / "build_html.py")]),
        # Antes del cuaderno: solo re-renderiza los episodios cuyo guion cambió
        # (p. ej. el último de vocabulario al agregar una palabra). Sin edge-tts
        # instalado avisa y sigue, no bloquea lo demás.
        ("podcasts", [sys.executable, str(SCRIPTS / "build_podcasts.py")]),
        ("cuaderno", [sys.executable, str(SCRIPTS / "build_artifact.py")]),
        ("GitHub Pages", [sys.executable, str(SCRIPTS / "build_artifact.py"),
                          "--standalone", "--out", "docs/index.html"]),
    ]
    errors = []
    for label, cmd in steps:
        res = run(cmd)
        if res.returncode != 0:
            errors.append(f"{label}: {(res.stderr or res.stdout).strip()[-400:]}")
    return errors


def git_sync(message):
    """Hace commit de los cambios y, si está habilitado, push."""
    if run(["git", "rev-parse", "--git-dir"]).returncode != 0:
        return "Este directorio no es un repositorio git."
    run(["git", "add", "-A"])
    if not run(["git", "diff", "--cached", "--quiet"]).returncode:
        return None  # no había nada que guardar
    body = f"{message}\n\nRegistrado por el bot de Telegram.\n"
    res = run(["git", "commit", "-m", body])
    if res.returncode != 0:
        return f"No se pudo hacer commit: {(res.stderr or res.stdout).strip()[-300:]}"
    if not GIT_PUSH:
        return None
    res = run(["git", "push"])
    if res.returncode != 0:
        return (f"Commit hecho, pero el push falló: {(res.stderr or res.stdout).strip()[-300:]}\n"
                "Revisa las credenciales de git en este equipo.")
    return None


def counts():
    vocab = json.loads((DATA / "vocabulary.json").read_text(encoding="utf-8"))
    forms = json.loads((DATA / "forms.json").read_text(encoding="utf-8"))
    return (sum(len(s["entries"]) for s in vocab["sections"]),
            sum(len(f["questions"]) for f in forms["forms"]))


MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


def update_handoff():
    """Refresca en handoff.md la fecha y los conteos que el bot deja obsoletos.

    El handoff lo redactan a mano las sesiones de trabajo; el bot no lo
    escribe. Pero cada palabra o lectura que registra deja vieja la cifra del
    §2 hasta la siguiente sesión, y quien lo lea al empezar se fía de un número
    equivocado. Aquí se corrige solo eso: la línea «Última actualización» y los
    números en negrita de la sección 2. Los patrones son tolerantes: si el
    archivo no existe o alguna frase cambió de forma, se salta esa parte.
    """
    path = REPO / "handoff.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    words, questions = counts()
    now = datetime.now()
    stamp = (f"{now.day} {MESES[now.month - 1]} {now.year} "
             f"({now:%H:%M}, bot en {platform.node()})")
    subs = [
        (r"^(\*\*Última actualización:\*\*).*$", lambda m: f"{m.group(1)} {stamp}"),
        (r"\*\*\d+ palabras confirmadas\*\*", lambda m: f"**{words} palabras confirmadas**"),
        (r"\*\*\d+ preguntas\*\*", lambda m: f"**{questions} preguntas**"),
    ]
    for name, key, label in (("readings.json", "items", "lecturas"),
                             ("podcasts.json", "episodes", "episodios de podcast")):
        try:
            n = len(json.loads((DATA / name).read_text(encoding="utf-8"))[key])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        subs.append((rf"\*\*\d+ {label}\*\*", lambda m, n=n, label=label: f"**{n} {label}**"))
    new = text
    for pattern, repl in subs:
        new = re.sub(pattern, repl, new, count=1, flags=re.M)
    if new != text:
        path.write_text(new, encoding="utf-8")
        log("handoff.md: fecha y conteos actualizados")


def pending_report():
    """Qué preguntas quedaron a medias porque solo llegó una de las dos pantallas."""
    forms = json.loads((DATA / "forms.json").read_text(encoding="utf-8"))
    need_q, need_e = [], []
    for f in forms["forms"]:
        for q in f["questions"]:
            tag = f"{f['form']}·{q.get('n')}"
            opts = q.get("options", [])
            # solo las que dejó a medias el procesador local (marcadores entre paréntesis);
            # las antiguas con menos de 4 opciones vienen de capturas recortadas y no
            # se van a completar solas
            if q.get("question", "").startswith("(Question stem") \
                    or any(o.startswith("(") for o in opts):
                need_q.append(tag)
            if q.get("explanation", "").startswith("(") or q.get("correct", "").startswith("(Not shown"):
                need_e.append(tag)
    if not need_q and not need_e:
        return "Nada pendiente: todas las preguntas tienen enunciado, opciones, respuesta y explicación."
    lines = []
    if need_q:
        lines += [f"Falta la pantalla de PREGUNTA (form·nº), {len(need_q)}:", "  " + ", ".join(need_q)]
    if need_e:
        lines += [f"Falta la pantalla de EXPLICACIÓN (form·nº), {len(need_e)}:", "  " + ", ".join(need_e)]
    return "\n".join(lines)


def data_changed():
    """¿Quedó algo nuevo en data/ respecto al último commit?

    Devuelve None cuando no se puede saber (esto no es un repo git): en ese
    caso el llamador regenera igual, que es lo seguro.
    """
    if run(["git", "rev-parse", "--git-dir"]).returncode != 0:
        return None
    res = run(["git", "status", "--porcelain", "--", "data"])
    if res.returncode != 0:
        return None
    return bool(res.stdout.strip())


# --- ráfagas: un solo rebuild + commit por lote ---------------------------------
# Brayhan manda las capturas de veinte en veinte. Regenerar y subir por cada una
# costaba ~10 s y un commit por captura. Ahora cada cambio se anota y, cuando
# pasan FLUSH_DELAY segundos sin novedades, se regenera y se sube una sola vez.
FLUSH_DELAY = int(CFG.get("FLUSH_DELAY", "30"))
WORK = threading.RLock()          # handlers y flush no se pisan
_batch = {"timer": None, "items": [], "chat": None, "force": False}


def finish(chat_id, summary, commit_msg, force=False):
    """Avisa el resultado ya y deja el rebuild + commit para el cierre del lote.

    Si el paso no tocó `data/` (la palabra ya estaba, la captura repetía una
    pregunta completa) no se anota nada: no hay nada que regenerar. `force` es
    para /rebuild, donde regenerar sin cambios sí es lo que se pidió.
    """
    if not force and data_changed() is False:
        log(f"sin cambios en data/: no se anota ({commit_msg})")
        send(chat_id, summary + "\n\n(Ya estaba así; no hay nada nuevo que subir.)")
        return
    send(chat_id, summary)
    with WORK:
        _batch["items"].append(commit_msg)
        _batch["chat"] = chat_id
        _batch["force"] = _batch["force"] or force
        if _batch["timer"]:
            _batch["timer"].cancel()
        if force:
            flush()
            return
        _batch["timer"] = threading.Timer(FLUSH_DELAY, flush)
        _batch["timer"].daemon = True
        _batch["timer"].start()
        log(f"lote: {len(_batch['items'])} cambio(s); cierre en {FLUSH_DELAY} s")


def flush():
    """Cierra el lote: regenera todo, actualiza el handoff, un commit, un push."""
    with WORK:
        items, chat_id = _batch["items"], _batch["chat"]
        _batch.update(timer=None, items=[], force=False)
        if not items or chat_id is None:
            return
        log(f"cerrando lote de {len(items)} cambio(s)")
        errors = rebuild()
        update_handoff()
        if len(items) == 1:
            msg = items[0]
        else:
            captures = sum(1 for i in items if i.startswith("ALCPT: procesa"))
            words = sum(1 for i in items if i.startswith("Vocabulario"))
            parts = []
            if captures:
                parts.append(f"{captures} captura{'s' if captures > 1 else ''}")
            if words:
                parts.append(f"{words} palabra{'s' if words > 1 else ''}")
            other = len(items) - captures - words
            if other:
                parts.append(f"{other} cambio{'s' if other > 1 else ''}")
            msg = "Lote: " + ", ".join(parts) + "\n\n" + "\n".join(f"- {i}" for i in items)
        problem = git_sync(msg)
        wc, qc = counts()
        lines = [f"Lote cerrado: {len(items)} cambio{'s' if len(items) > 1 else ''} regenerado{'s' if len(items) > 1 else ''}.",
                 f"Diccionario: {wc} palabras · {qc} preguntas"]
        if errors:
            lines += ["", "Los documentos no se regeneraron del todo:"] + errors
        if problem:
            lines += ["", problem]
        elif GIT_PUSH and not errors:
            lines += ["", "Cambios subidos al repositorio."]
        pend = pending_summary()
        if pend:
            lines += ["", pend]
        send(chat_id, "\n".join(lines))


def pending_summary():
    """Una línea con lo que quedó a medias en este lote (para no pedir /pendientes)."""
    try:
        forms = json.loads((DATA / "forms.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    q_need, e_need = 0, 0
    for f in forms["forms"]:
        for q in f["questions"]:
            if q.get("question", "").startswith("(Question stem") or any(o.startswith("(") for o in q.get("options", [])):
                q_need += 1
            if q.get("explanation", "").startswith("(") or q.get("correct", "").startswith("(Not shown"):
                e_need += 1
    if not q_need and not e_need:
        return ""
    return f"Pendientes: {q_need} sin pantalla de pregunta · {e_need} sin explicación (/pendientes)."


# --- manejadores ---------------------------------------------------------------
HELP = (
    "Diccionario ALCPT\n\n"
    "Mándame:\n"
    "• una palabra o expresión en inglés → la traduzco y la agrego\n"
    "• palabra = traducción → la agrego tal cual, sin IA\n"
    "• una captura del examen → la leo aquí mismo (sin IA) y la guardo\n"
    "• una captura con una lista término = significado (TikTok, apuntes) → la\n"
    "   agrego al vocabulario y Claude repone tildes y matices\n"
    "   manda las DOS pantallas de cada ítem: la de la pregunta (opciones con la\n"
    "   correcta en verde) y la de la explicación, desplazada arriba del todo\n\n"
    "Comandos:\n"
    "/estado – cuántas palabras y preguntas hay\n"
    "/pendientes – preguntas a las que les falta una pantalla (pregunta o explicación)\n"
    "/lote <enlace> – procesa un álbum de iCloud o un .zip entero (cientos de\n"
    "   capturas); /lote estado y /lote cancelar mientras corre\n"
    "/rebuild – regenerar PDF y páginas web\n"
    "/lecturas – traer lecturas nuevas de ThoughtCo (p. ej. /lecturas math 2)\n"
    "   secciones: computer-science, math, statistics, philosophy, history,\n"
    "   geography, issues, social-sciences, humanities\n"
    "• un enlace de álbum compartido de iCloud → me bajo todas las capturas y las\n"
    "   proceso una por una, sin límite de 30\n"
    "• un .zip con capturas (hasta 20 MB por Telegram, o /lote con un enlace directo)\n"
    "• un enlace de thoughtco.com → lo condenso y lo agrego a Lecturas\n"
    "/help – este mensaje"
)


def handle_word(chat_id, text):
    if "=" in text:
        en, es = (p.strip() for p in text.split("=", 1))
        if not en or not es:
            send(chat_id, "Formato: palabra = traducción")
            return
        res = run([sys.executable, str(SCRIPTS / "add_word.py"), en, es])
        if res.returncode != 0:
            send(chat_id, f"No pude agregarla:\n{(res.stderr or res.stdout).strip()[-500:]}")
            return
        finish(chat_id, res.stdout.strip(), f"Vocabulario: agrega «{en}»")
        return

    send(chat_id, f"Buscando «{text}»…")
    prompt = (
        f"Agrega la palabra o expresión «{text}» a data/vocabulary.json siguiendo "
        "las reglas de CLAUDE.md.\n"
        "- Va en la sección con id `personal`.\n"
        "- El campo `n` continúa la numeración global consecutiva.\n"
        "- `es` debe traer traducción, matices y acepciones separados por punto y coma, "
        "pensados para un estudiante de nivel B2.\n"
        "- Si viene con error ortográfico, corrígela y menciónalo.\n"
        "- Si ya existe en el diccionario, no la dupliques: dilo y no edites nada.\n"
        "- Actualiza meta.total_confirmed y meta.last_updated.\n"
        "- No toques data/forms.json.\n"
        "Responde con UNA sola línea: el número, la palabra y su traducción."
    )
    ok, out = ask_claude(prompt)
    if not ok:
        send(chat_id, f"No pude procesarla:\n{out}")
        return
    finish(chat_id, out or f"Agregada «{text}».", f"Vocabulario: agrega «{text}»")


PARSE_SCRIPT = SCRIPTS / "parse_capture.py"


def handle_image(chat_id, path):
    """Captura del ALCPT → pregunta en forms.json, todo en el servidor.

    OCR con RapidOCR y parser de reglas (scripts/parse_capture.py): la imagen
    no sale del equipo ni pasa por Claude Code. Si el parser no puede
    estructurarla, se avisa con el texto leído y, solo si CAPTURE_FALLBACK es
    "claude", se recurre al camino antiguo."""
    send(chat_id, "Captura recibida, leyéndola…")
    res = run([sys.executable, str(PARSE_SCRIPT), str(path), "--json"], timeout=300)
    out = {}
    try:
        out = json.loads(res.stdout.strip().splitlines()[-1]) if res.stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        out = {}
    if res.returncode == 0 and out.get("ok"):
        q = out.get("question", {})
        summary = out.get("message", "Captura procesada.")
        if q:
            summary += f"\n\n{q.get('question', '')}\n" + "\n".join(
                ("✓ " if o == q.get("correct") else "· ") + o for o in q.get("options", []))
        log(f"captura {path.name}: {out.get('message')} (OCR {out.get('confidence')})")
        finish(chat_id, summary, f"ALCPT: procesa {path.name} (OCR local)")
        return

    reason = out.get("reason") or (res.stderr or res.stdout or "error desconocido").strip()[-400:]
    text = (out.get("text") or "").strip()
    # ¿Es una lista de vocabulario (TikTok, apuntes) y no una pantalla del examen?
    if "formulario" in reason or "OCR poco fiable" not in reason:
        if handle_vocab_image(chat_id, path):
            return
    log(f"captura {path.name}: no estructurada: {reason}")
    if CAPTURE_FALLBACK == "claude":
        send(chat_id, f"El procesador local no pudo ({reason}). Se la paso a Claude Code…")
        handle_image_claude(chat_id, path)
        return
    lines = [f"No pude estructurar la captura: {reason}",
             f"El texto leído quedó en inbox/{path.with_suffix('.txt').name}."]
    if text:
        lines += ["", "Lo que leí:", text[:1200]]
    lines += ["", "Si es una captura válida del ALCPT, mándala de nuevo más nítida o "
                  "completa (encabezado con el formulario y todas las opciones)."]
    send(chat_id, "\n".join(lines))


# --- lotes grandes: álbum compartido de iCloud ---------------------------------
# Telegram deja mandar 30 imágenes por tanda y el bot solo puede bajar archivos de
# hasta 20 MB, así que 500 capturas por ahí no caben. Con el enlace de un álbum
# compartido el servidor va directo a iCloud y luego procesa la carpeta entera.
ICLOUD_SCRIPT = SCRIPTS / "fetch_icloud_album.py"
BATCH_SCRIPT = SCRIPTS / "process_batch.py"
# Álbum compartido (público, se puede leer): …/sharedalbum/#B0X…
RE_ICLOUD = re.compile(r"https?://(?:\w+\.)?icloud\.com/\S*", re.I)
# Enlace del botón «Compartir» de Fotos: share.icloud.com/photos/… o icloud.com/photos/#…
# Va por CloudKit y exige iniciar sesión con la cuenta de Apple, así que el bot no
# puede abrirlo. Se detecta solo para explicar cómo crear el que sí sirve.
RE_ICLOUD_PHOTOS = re.compile(r"https?://(?:\w+\.)?icloud\.com/photos/\S*", re.I)
RE_URL = re.compile(r"https?://\S+", re.I)
ALBUM_HOWTO = (
    "Ese enlace es del botón «Compartir» de Fotos y va por la cuenta de Apple: "
    "sin iniciar sesión no puedo abrirlo, y no voy a pedirte tu contraseña.\n\n"
    "Hazme uno de «álbum compartido», que es público y sí puedo leer:\n"
    "1. Fotos → selecciona las capturas → Compartir\n"
    "2. «Añadir a álbum compartido» → crea uno nuevo (p. ej. «ALCPT»)\n"
    "3. Abre ese álbum → pestaña «Personas»\n"
    "4. Activa «Sitio web público» → «Copiar enlace»\n\n"
    "El enlace bueno se ve así: https://www.icloud.com/sharedalbum/#B0X5…\n"
    "Mándamelo y proceso el álbum entero."
)
_job = {"thread": None, "cancel": False, "state": "", "chat": None}
# Las capturas de origen se guardan aquí y SÍ van al repositorio: son el respaldo
# de Brayhan y permiten reprocesarlas si el lector mejora. Una carpeta por álbum,
# con su token en el nombre, para que reenviar el mismo enlace sea incremental:
# el descargador nombra cada foto por su checksum y salta las que ya están.
CAPTURAS = REPO / "capturas"


def album_folder(url):
    """Carpeta estable para un álbum; la misma cada vez que llega ese enlace."""
    token = url.split("#", 1)[1] if "#" in url else url.rstrip("/").rsplit("/", 1)[-1]
    token = re.sub(r"[^A-Za-z0-9_-]", "", token)[:12] or "sin_token"
    return CAPTURAS / f"album_{token}"


def eta(n_images: int) -> str:
    """Tiempo aproximado: unos 3,3 s por captura nueva en este equipo."""
    minutes = round(n_images * 3.3 / 60)
    if minutes < 1:
        return "menos de un minuto"
    return f"un minuto" if minutes == 1 else f"unos {minutes} minutos"


def job_running() -> bool:
    th = _job["thread"]
    return bool(th and th.is_alive())


def handle_batch_url(chat_id, url):
    """Arranca la descarga y el procesado en segundo plano; el bot sigue atendiendo."""
    log(f"lote: petición para {url}")
    if job_running():
        send(chat_id, f"Ya hay un lote en marcha: {_job['state']}\n"
                      "Espera a que termine o manda /lote cancelar.")
        return
    _job.update(cancel=False, state="preparando", chat=chat_id)
    _job["thread"] = threading.Thread(target=_run_batch, args=(chat_id, url), daemon=True)
    _job["thread"].start()


def _run_batch(chat_id, url):
    es_album = bool(RE_ICLOUD.search(url))
    folder = album_folder(url) if es_album else CAPTURAS / f"zip_{datetime.now():%Y%m%d_%H%M%S}"
    try:
        if es_album:
            ya = len(list(folder.glob("*.jpg"))) if folder.exists() else 0
            send(chat_id, "Abriendo el álbum…" if not ya else
                 f"Abriendo el álbum (ya tengo {ya} fotos de la vez anterior; "
                 "solo bajo las nuevas)…")
            got = _download_album(chat_id, url, folder)
        else:
            send(chat_id, "Descargando el archivo…")
            got = _download_zip(chat_id, url, folder)
        if got is None or _job["cancel"]:
            return
        if got == 0:
            send(chat_id, "No había imágenes nuevas que procesar.")
            return
        _process_folder(chat_id, folder)
    except Exception as exc:                            # el lote no puede tumbar el bot
        log(f"lote: fallo inesperado: {exc!r}")
        send(chat_id, f"El lote se cortó por un error: {type(exc).__name__}: {exc}"[:600])
    finally:
        _job["state"] = ""


def _download_album(chat_id, url, folder):
    """Descarga con avance cada 50 fotos. Devuelve cuántas hay en la carpeta."""
    _job["state"] = "descargando"
    log(f"lote: abriendo álbum {url} → {folder.name}")
    cmd = [sys.executable, str(ICLOUD_SCRIPT), url, "--out", str(folder)]
    proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    last, summary = 0, {}
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("ok") is False:
            proc.wait()
            log(f"lote: álbum rechazado: {ev.get('reason')}")
            send(chat_id, f"No pude abrir el álbum: {ev.get('reason')}")
            return None
        if ev.get("ok") is True:
            summary = ev
        done = ev.get("done")
        if done and done - last >= 50:
            last = done
            send(chat_id, f"Descargadas {done} de {ev.get('total')}…")
        if _job["cancel"]:
            proc.terminate()
            send(chat_id, "Descarga cancelada.")
            return None
    proc.wait()
    if not summary:
        log(f"lote: descarga sin resumen (código {proc.returncode})")
        send(chat_id, "La descarga terminó sin resumen; revisa el enlace.")
        return None
    log(f"lote: descarga terminada {summary}")
    nuevas = summary.get("downloaded", 0)
    total = nuevas + summary.get("skipped", 0)
    if not nuevas:
        send(chat_id, f"El álbum no tiene fotos nuevas: las {total} ya estaban procesadas.")
        return 0
    send(chat_id, f"Descargadas {nuevas} fotos nuevas "
                  f"({summary.get('skipped', 0)} ya estaban, {summary.get('failed', 0)} fallaron).\n"
                  f"Ahora las proceso: {eta(nuevas)}.")
    return total


def _download_zip(chat_id, url, folder):
    """Enlace directo a un .zip (Drive, Dropbox, iCloud Drive, lo que sea) con las
    capturas dentro. Es el camino de respaldo si el álbum compartido no funciona."""
    _job["state"] = "descargando zip"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "lote.zip"
    try:
        with requests.get(url, stream=True, timeout=120,
                          headers={"User-Agent": "Mozilla/5.0"}) as r:
            r.raise_for_status()
            if r.headers.get("Content-Type", "").startswith(("text/html", "text/plain")):
                send(chat_id, "Ese enlace devuelve una página web, no un archivo. "
                              "Necesito el enlace de descarga directa del .zip "
                              "(o el de un álbum compartido de iCloud).")
                return None
            size = 0
            with open(dest, "wb") as fh:
                for block in r.iter_content(1 << 20):
                    if _job["cancel"]:
                        return None
                    fh.write(block)
                    size += len(block)
                    if size % (50 << 20) < (1 << 20):
                        send(chat_id, f"Descargados {size >> 20} MB…")
    except requests.RequestException as exc:
        send(chat_id, f"No pude descargar ese enlace: {exc}"[:400])
        return None
    with open(dest, "rb") as fh:
        if fh.read(2) != b"PK":                 # firma de todo archivo ZIP
            dest.unlink(missing_ok=True)
            send(chat_id, "Lo que llegó no es un ZIP. Comprueba que el enlace sea de "
                          "descarga directa, o mándame un álbum compartido de iCloud.")
            return None
    return _extract_zip(chat_id, dest, folder)


def _extract_zip(chat_id, zip_path, folder):
    """Saca las imágenes del ZIP a `folder`, ignorando carpetas y basura del sistema."""
    _job["state"] = "descomprimiendo"
    exts = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
    n = 0
    try:
        with zipfile.ZipFile(zip_path) as z:
            for info in z.infolist():
                name = Path(info.filename).name
                if info.is_dir() or name.startswith(".") or "__MACOSX" in info.filename:
                    continue
                if Path(name).suffix.lower() not in exts:
                    continue
                target = folder / f"z{n:04d}_{name}"
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                n += 1
    except zipfile.BadZipFile:
        send(chat_id, "Ese archivo no es un ZIP válido.")
        return None
    zip_path.unlink(missing_ok=True)
    if not n:
        send(chat_id, "El ZIP no traía imágenes.")
        return 0
    send(chat_id, f"{n} imágenes extraídas. Las proceso: {eta(n)}.")
    return n


def handle_zip_document(chat_id, path):
    """ZIP mandado por Telegram (máximo 20 MB, unas 40-60 capturas)."""
    if job_running():
        send(chat_id, f"Ya hay un lote en marcha: {_job['state']}.")
        return
    folder = CAPTURAS / f"zip_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True, exist_ok=True)
    def work():
        _job.update(cancel=False, state="descomprimiendo", chat=chat_id)
        try:
            if _extract_zip(chat_id, path, folder):
                _process_folder(chat_id, folder)
        except Exception as exc:
            log(f"zip: fallo inesperado: {exc!r}")
            send(chat_id, f"El ZIP se cortó por un error: {type(exc).__name__}: {exc}"[:400])
        finally:
            _job["state"] = ""
    _job["thread"] = threading.Thread(target=work, daemon=True)
    _job["thread"].start()


def _process_folder(chat_id, folder):
    """Lee la carpeta imagen por imagen mostrando avance; un solo commit al final."""
    _job["state"] = "procesando"
    log(f"lote: procesando {folder.name}")
    cmd = [sys.executable, str(BATCH_SCRIPT), str(folder), "--progress"]
    env = {**os.environ, "OCR_THREADS": os.environ.get("OCR_THREADS", "4"),
           "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "4")}
    proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", bufsize=1, env=env)
    summary, last = {}, 0
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("ok") is True:
            summary = ev
            continue
        i, total = ev.get("i", 0), ev.get("total", 0)
        _job["state"] = f"procesando {i}/{total}"
        if i - last >= 25:
            last = i
            send(chat_id, f"Procesadas {i} de {total}…")
        if _job["cancel"]:
            proc.terminate()
            break
    proc.wait()
    if _job["cancel"]:
        send(chat_id, f"Lote cancelado en {_job['state']}. Lo hecho hasta ahí queda guardado.")
    if not summary:
        send(chat_id, "El procesado terminó sin resumen. Revisa bot/bot.log.")
        return
    t = summary["totals"]
    secs = summary["seconds"]
    dur = f"{round(secs)} s" if secs < 90 else f"{round(secs / 60)} min"
    lines = [f"Lote terminado: {summary['files']} imágenes en {dur}.",
             f"· {t['form']} pantallas de formulario",
             f"· {t['vocab']} listas de vocabulario",
             f"· {t['repetida']} ya procesadas antes (saltadas)"]
    fallidas = t["nada"] + t["ilegible"] + t["error"]
    if fallidas:
        lines.append(f"· {fallidas} sin procesar")
        for p in summary.get("problems", [])[:8]:
            lines.append(f"   {p['file']}: {p['why'][:90]}")
    polished = polish_pending_vocab()
    if polished:
        lines.append(f"· {polished} entradas de vocabulario pulidas con Claude")
    log(f"lote terminado: {summary['files']} imágenes, {t}")
    finish(chat_id, "\n".join(lines),
           f"ALCPT: lote de {summary['files']} capturas ({t['form']} preguntas, "
           f"{t['vocab']} listas de vocabulario)")


def polish_pending_vocab(chunk=25):
    """Repone tildes y matices en todo lo que quedó marcado `ocr` (de a 25)."""
    if not (VOCAB_POLISH and CLAUDE):
        return 0
    d = json.loads((DATA / "vocabulary.json").read_text(encoding="utf-8"))
    pending = [e for s in d["sections"] for e in s["entries"] if e.get("ocr")]
    total = 0
    for i in range(0, len(pending), chunk):
        total += len(polish_entries(pending[i:i + chunk]))
    return total


VOCAB_SCRIPT = SCRIPTS / "parse_vocab_capture.py"
VOCAB_POLISH = CFG.get("VOCAB_POLISH", "1") not in ("0", "false", "no")


def handle_vocab_image(chat_id, path):
    """Lista término → significado (p. ej. phrasal verbs de TikTok). Se extrae en
    local y se agrega a `personal`; luego Claude, solo con texto, repone tildes
    y matices. Devuelve True si la captura era de este tipo."""
    res = run([sys.executable, str(VOCAB_SCRIPT), str(path), "--json"], timeout=300)
    try:
        out = json.loads(res.stdout.strip().splitlines()[-1]) if res.stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        out = {}
    if res.returncode != 0 or not out.get("ok"):
        return False
    added, skipped = out.get("added", []), out.get("skipped", [])
    lines = [f"Lista de vocabulario: {len(added)} entrada{'s' if len(added) != 1 else ''} nueva{'s' if len(added) != 1 else ''}."]
    lines += [f"{e['n']}. {e['en']} = {e['es']}" for e in added]
    lines += [f"(ya estaba) {s['en']}: {s['why']}" for s in skipped]
    log(f"captura {path.name}: vocabulario, {len(added)} nuevas, {len(skipped)} repetidas")
    if added and VOCAB_POLISH and CLAUDE:
        polished = polish_entries(added)
        if polished:
            lines.append("")
            lines.append("Pulidas por Claude (tildes y matices):")
            lines += [f"{e['n']}. {e['en']} = {e['es']}" for e in polished]
    if not added:
        send(chat_id, "\n".join(lines) + "\n\n(Ya estaban todas; no hay nada nuevo que subir.)")
        return True
    finish(chat_id, "\n".join(lines), f"Vocabulario: {len(added)} entradas desde captura {path.name}")
    return True


def polish_entries(entries):
    """Claude solo recibe texto: las parejas leídas por OCR. Devuelve JSON con la
    misma numeración y `es` corregido y enriquecido; el bot lo aplica. Sin
    herramientas ni lectura del diccionario: unos cientos de tokens."""
    listado = "\n".join(f"{e['n']}. {e['en']} = {e['es']}" for e in entries)
    prompt = (
        "Estas entradas salieron por OCR de una captura de vocabulario inglés→español "
        "(sin tildes y con alguna letra perdida). Para cada una devuelve el campo `es` "
        "corregido: repón tildes y letras («Legar» → «Llegar»), conserva el significado "
        "que traía la captura como primera acepción y añade, separados por punto y coma, "
        "otras acepciones y matices útiles para un estudiante de nivel B2 (registro, "
        "ejemplo breve en inglés entre paréntesis si ayuda). No cambies `en` salvo para "
        "corregir mayúsculas u ortografía evidente.\n\n"
        f"{listado}\n\n"
        "Responde SOLO con un JSON: una lista de objetos {\"n\": …, \"en\": …, \"es\": …}, "
        "sin texto antes ni después."
    )
    ok, out = ask_claude(prompt, timeout=300, tools=False)
    if not ok:
        log(f"pulido con Claude falló: {out[:200]}")
        return []
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        log("pulido con Claude: respuesta sin JSON")
        return []
    try:
        fixed = {int(x["n"]): x for x in json.loads(m.group(0))}
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        log(f"pulido con Claude: JSON inválido ({exc})")
        return []
    vocab_path = DATA / "vocabulary.json"
    d = json.loads(vocab_path.read_text(encoding="utf-8"))
    applied = []
    for s in d["sections"]:
        for e in s["entries"]:
            f = fixed.get(e["n"])
            if f and e.get("ocr") and f.get("es"):
                e["es"] = str(f["es"]).strip()
                if f.get("en"):
                    e["en"] = str(f["en"]).strip()
                e.pop("ocr", None)
                applied.append(e)
    if applied:
        vocab_path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return applied


def handle_image_claude(chat_id, path):
    """Camino antiguo: Claude Code abre la imagen (cuesta tokens)."""
    rel = path.relative_to(REPO).as_posix()
    prompt = (
        f"Procesa la captura del ALCPT que está en {rel}, siguiendo CLAUDE.md.\n"
        "- Identifica a qué formulario pertenece (lo dice el encabezado de la app).\n"
        "- Extrae número, enunciado completo, todas las opciones, la respuesta correcta "
        "y la explicación. TODO en inglés.\n"
        "- Agrégala a data/forms.json en el `form` que corresponda, creando la sección "
        "si no existe, y ordenando las preguntas por número.\n"
        "- IMPORTANTE: si esa pregunta ya está documentada en ese formulario, NO la "
        "dupliques; dilo y no edites nada.\n"
        "- Si la captura es de la pantalla del examen y no muestra la respuesta correcta, "
        "usa la nota «(Not shown — captured during the test, before the review screen.)» "
        "en `correct`, igual que las demás.\n"
        "- Si la imagen no es del ALCPT, dilo y no edites nada.\n"
        "- No toques data/vocabulary.json.\n"
        "- Actualiza meta.last_updated y meta.total_questions.\n"
        "Responde con UNA sola línea diciendo qué formulario y qué número agregaste."
    )
    ok, out = ask_claude(prompt)
    if not ok:
        send(chat_id, f"No pude leerla:\n{out}")
        return
    finish(chat_id, out or "Captura procesada.", f"ALCPT: procesa {path.name}")


THOUGHTCO_URL = re.compile(r"https?://(?:www\.)?thoughtco\.com/\S+", re.I)
READINGS_SCRIPT = SCRIPTS / "fetch_readings.py"


def readings_count():
    p = DATA / "readings.json"
    if not p.exists():
        return 0
    try:
        return len(json.loads(p.read_text(encoding="utf-8")).get("items", []))
    except (json.JSONDecodeError, OSError):
        return 0


def handle_reading_url(chat_id, urls):
    """Un enlace de ThoughtCo: descargar, condensar con Claude Code y publicar."""
    send(chat_id, f"Descargando {len(urls)} lectura{'s' if len(urls) != 1 else ''} de ThoughtCo…")
    res = run([sys.executable, str(READINGS_SCRIPT), "--add", *urls], timeout=300)
    if res.returncode != 0:
        send(chat_id, f"No pude descargarla:\n{(res.stderr or res.stdout).strip()[-600:]}")
        return
    added = res.stdout.strip()
    if "+ " not in added:
        send(chat_id, added or "Nada nuevo: esa lectura ya estaba registrada.")
        return
    send(chat_id, added + "\n\nCondensando con Claude Code (tarda un minuto)…")
    res = run([sys.executable, str(READINGS_SCRIPT), "--condense"], timeout=1200)
    if res.returncode != 0:
        send(chat_id, f"Descargada, pero no pude condensarla:\n{(res.stderr or res.stdout).strip()[-600:]}")
    finish(chat_id, (res.stdout or "Lectura condensada.").strip()[-1500:],
           f"Lecturas: agrega {len(urls)} artículo{'s' if len(urls) != 1 else ''} de ThoughtCo")


def handle_readings_cmd(chat_id, args):
    """/lecturas [sección] [n]: trae n artículos nuevos de esa sección y los condensa."""
    section, n = "computer-science", 1
    for tok in args:
        if tok.isdigit():
            n = max(1, min(int(tok), 5))
        else:
            section = tok.lower()
    send(chat_id, f"Buscando {n} lectura{'s' if n != 1 else ''} nueva{'s' if n != 1 else ''} en «{section}»…")
    res = run([sys.executable, str(READINGS_SCRIPT), "--add-from-section", section,
               "--max", str(n)], timeout=600)
    if res.returncode != 0:
        send(chat_id, f"No pude traerlas:\n{(res.stderr or res.stdout).strip()[-600:]}")
        return
    if "+ " not in res.stdout:
        send(chat_id, (res.stdout or "").strip() or "No encontré artículos nuevos en esa sección.")
        return
    send(chat_id, res.stdout.strip() + "\n\nCondensando con Claude Code…")
    res = run([sys.executable, str(READINGS_SCRIPT), "--condense"], timeout=1800)
    finish(chat_id, (res.stdout or "Lecturas condensadas.").strip()[-1500:],
           f"Lecturas: {n} artículo{'s' if n != 1 else ''} nuevo{'s' if n != 1 else ''} de {section}")


def handle_update(u):
    with WORK:
        _handle_update(u)


def _handle_update(u):
    msg = u.get("message") or u.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    user_id = msg.get("from", {}).get("id")

    if ALLOWED and user_id not in ALLOWED:
        log(f"ignorado usuario no autorizado {user_id}")
        send(chat_id, "Este bot es privado.")
        return

    text = (msg.get("text") or msg.get("caption") or "").strip()
    if text:
        log(f"mensaje: {text[:100]}")
    elif msg.get("photo"):
        log("mensaje: foto")
    elif msg.get("document"):
        log(f"mensaje: documento {msg['document'].get('file_name')} "
            f"({msg['document'].get('mime_type')})")

    if text.startswith("/"):
        cmd = text.split()[0].split("@")[0]
        if cmd in ("/start", "/help"):
            send(chat_id, HELP)
        elif cmd == "/estado":
            words, questions = counts()
            send(chat_id, f"{words} palabras · {questions} preguntas documentadas · "
                          f"{readings_count()} lecturas.")
        elif cmd == "/lote":
            arg = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if arg.lower() in ("cancelar", "cancel", "parar", "stop"):
                if job_running():
                    _job["cancel"] = True
                    send(chat_id, "Cancelando en cuanto termine la imagen en curso…")
                else:
                    send(chat_id, "No hay ningún lote en marcha.")
            elif not arg or arg.lower() in ("estado", "status"):
                send(chat_id, f"Lote en marcha: {_job['state']}." if job_running()
                     else "No hay ningún lote en marcha. Mándame el enlace de un álbum "
                          "compartido de iCloud y lo proceso entero.")
            elif RE_ICLOUD_PHOTOS.search(arg):
                send(chat_id, ALBUM_HOWTO)
            elif not RE_URL.match(arg):
                send(chat_id, "Eso no parece un enlace. Mándame el de un álbum "
                              "compartido de iCloud o el de un .zip con las capturas.")
            else:
                handle_batch_url(chat_id, arg)
        elif cmd == "/pendientes":
            send(chat_id, pending_report())
        elif cmd == "/lecturas":
            handle_readings_cmd(chat_id, text.split()[1:])
        elif cmd == "/rebuild":
            send(chat_id, "Regenerando…")
            finish(chat_id, "Documentos regenerados.", "Regenera PDF y páginas web",
                   force=True)
        else:
            send(chat_id, "No conozco ese comando. Usa /help")
        return

    photo = msg.get("photo")
    doc = msg.get("document")
    if photo:
        path = download_file(photo[-1]["file_id"], INBOX)   # la mayor resolución
        handle_image(chat_id, path)
        return
    if doc and (str(doc.get("mime_type", "")) in ("application/zip", "application/x-zip-compressed")
                or str(doc.get("file_name", "")).lower().endswith(".zip")):
        if doc.get("file_size", 0) > 20 * 1024 * 1024:
            send(chat_id, "Telegram no me deja bajar archivos de más de 20 MB. "
                          "Manda el ZIP en trozos más pequeños, o mejor el enlace de un "
                          "álbum compartido de iCloud, que no tiene ese límite.")
            return
        send(chat_id, "ZIP recibido, descomprimiendo…")
        handle_zip_document(chat_id, download_file(doc["file_id"], INBOX))
        return

    if doc and str(doc.get("mime_type", "")).startswith("image/"):
        path = download_file(doc["file_id"], INBOX)
        handle_image(chat_id, path)
        return

    # primero se descarta el enlace de Fotos (no se puede leer); cualquier otro
    # enlace de iCloud se intenta como álbum, y el descargador ya explica si no lo es
    if RE_ICLOUD_PHOTOS.search(text):
        send(chat_id, ALBUM_HOWTO)
        return

    m = RE_ICLOUD.search(text)
    if m:
        handle_batch_url(chat_id, m.group(0).rstrip(".,;)"))
        return

    urls = THOUGHTCO_URL.findall(text)
    if urls:
        handle_reading_url(chat_id, [u.rstrip(".,)") for u in urls])
        return

    if RE_URL.match(text.strip()):
        # una dirección web nunca es una palabra del diccionario
        send(chat_id, "No sé qué hacer con ese enlace. Acepto:\n"
                      "• álbum compartido de iCloud (…/sharedalbum/#B0X…)\n"
                      "• enlace directo a un .zip con capturas\n"
                      "• un artículo de thoughtco.com\n"
                      "Con /lote <enlace> lo proceso como lote.")
        return

    if text:
        handle_word(chat_id, text)
    else:
        send(chat_id, "Mándame una palabra o una captura del examen. /help para más.")


# --- bucle principal -----------------------------------------------------------
def load_offset():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8")).get("offset", 0)
        except (json.JSONDecodeError, OSError):
            return 0
    return 0


def save_offset(offset):
    STATE.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def main():
    if not TOKEN:
        sys.exit("Falta TELEGRAM_TOKEN. Copia .env.example a .env y complétalo.")
    if not ALLOWED:
        log("AVISO: ALLOWED_USER_IDS está vacío, cualquiera podrá escribirle al bot.")
    if not CLAUDE:
        log("AVISO: no encuentro Claude Code. Las palabras con '=' y las capturas "
            "se guardarán, pero no se podrán procesar automáticamente.")

    # systemd manda SIGTERM al parar: cerrar el lote antes de morir
    def _term(*_):
        log("SIGTERM: cerrando lote pendiente")
        flush()
        sys.exit(0)
    signal.signal(signal.SIGTERM, _term)

    me = api("getMe")["result"]
    log(f"conectado como @{me['username']} · repo {REPO}")
    offset = load_offset()
    conflicts = 0

    while True:
        try:
            res = requests.get(API.format(token=TOKEN, method="getUpdates"),
                               params={"offset": offset, "timeout": 50}, timeout=70)
            res.raise_for_status()
            conflicts = 0
            for u in res.json().get("result", []):
                offset = u["update_id"] + 1
                save_offset(offset)
                try:
                    handle_update(u)
                except Exception as exc:                     # un update malo no tumba el bot
                    log(f"error procesando update: {exc!r}")
        except requests.exceptions.RequestException as exc:
            # 409 = otro proceso esta leyendo este mismo bot. Telegram solo admite uno.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 409:
                conflicts += 1
                if conflicts in (3, 30):
                    log("CONFLICTO: otro equipo o proceso esta leyendo este bot. "
                        "Telegram solo admite un lector por token. Revisa con "
                        "'python bot/install_service.py --status' que maquina lo tiene "
                        "tomado y quita el servicio de la otra.")
            else:
                conflicts = 0
                log(f"red: {exc!r}; reintento en 15 s")
            time.sleep(15)
        except KeyboardInterrupt:
            log("detenido")
            flush()
            return


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        log(f"salida: {exc}")
        raise
    except Exception as exc:
        log(f"fallo inesperado: {exc!r}")
        raise
