#!/usr/bin/env python3
"""
Bot de Telegram que alimenta el diccionario ALCPT.

Qué hace
--------
  * Le mandas una palabra  ->  la traduce y la agrega a data/vocabulary.json
  * Le mandas "palabra = traduccion"  ->  la agrega tal cual, sin usar IA
  * Le mandas una captura del examen  ->  extrae la pregunta y la agrega a data/forms.json
  * Después de cada cambio: regenera PDF y páginas web, hace commit y push

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
import shutil
import subprocess
import sys
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
    for k in ("TELEGRAM_TOKEN", "ALLOWED_USER_IDS", "CLAUDE_BIN", "GIT_PUSH", "CLAUDE_MODEL"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


CFG = load_env()
TOKEN = CFG.get("TELEGRAM_TOKEN", "")
ALLOWED = {int(x) for x in CFG.get("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x}
GIT_PUSH = CFG.get("GIT_PUSH", "1") not in ("0", "false", "no")
CLAUDE_MODEL = CFG.get("CLAUDE_MODEL", "")


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
def ask_claude(prompt, timeout=900):
    """Ejecuta Claude Code sin interacción, dentro del repo, con permiso solo para editar."""
    if not CLAUDE:
        return False, ("No encuentro el ejecutable de Claude Code en este equipo. "
                       "Instálalo o define CLAUDE_BIN en el .env.")
    cmd = [CLAUDE, "-p", prompt,
           "--permission-mode", "acceptEdits",
           "--allowed-tools", "Read", "Edit", "Write", "Glob", "Grep"]
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


def finish(chat_id, summary, commit_msg):
    """Regenera documentos, sincroniza con git y avisa el resultado."""
    errors = rebuild()
    problem = git_sync(commit_msg)
    words, questions = counts()
    lines = [summary, "", f"Diccionario: {words} palabras · {questions} preguntas"]
    if errors:
        lines += ["", "Los documentos no se regeneraron del todo:"] + errors
    if problem:
        lines += ["", problem]
    elif GIT_PUSH and not errors:
        lines += ["", "Cambios subidos al repositorio."]
    send(chat_id, "\n".join(lines))


# --- manejadores ---------------------------------------------------------------
HELP = (
    "Diccionario ALCPT\n\n"
    "Mándame:\n"
    "• una palabra o expresión en inglés → la traduzco y la agrego\n"
    "• palabra = traducción → la agrego tal cual, sin IA\n"
    "• una captura del examen → extraigo la pregunta completa\n\n"
    "Comandos:\n"
    "/estado – cuántas palabras y preguntas hay\n"
    "/rebuild – regenerar PDF y páginas web\n"
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


def handle_image(chat_id, path):
    rel = path.relative_to(REPO).as_posix()
    send(chat_id, "Captura recibida, leyéndola…")
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


def handle_update(u):
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

    if text.startswith("/"):
        cmd = text.split()[0].split("@")[0]
        if cmd in ("/start", "/help"):
            send(chat_id, HELP)
        elif cmd == "/estado":
            words, questions = counts()
            send(chat_id, f"{words} palabras · {questions} preguntas documentadas.")
        elif cmd == "/rebuild":
            send(chat_id, "Regenerando…")
            finish(chat_id, "Documentos regenerados.", "Regenera PDF y páginas web")
        else:
            send(chat_id, "No conozco ese comando. Usa /help")
        return

    photo = msg.get("photo")
    doc = msg.get("document")
    if photo:
        path = download_file(photo[-1]["file_id"], INBOX)   # la mayor resolución
        handle_image(chat_id, path)
        return
    if doc and str(doc.get("mime_type", "")).startswith("image/"):
        path = download_file(doc["file_id"], INBOX)
        handle_image(chat_id, path)
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
