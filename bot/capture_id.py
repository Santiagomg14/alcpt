#!/usr/bin/env python3
"""
Espera el primer mensaje que le llegue al bot y guarda ese ID en ALLOWED_USER_IDS.

Se usa una sola vez, al configurar el bot en un equipo nuevo:

    python bot/capture_id.py

Manda /start al bot desde tu Telegram y el script completa el .env solo.
No dejes esto corriendo a la vez que el bot: Telegram solo permite un lector
de mensajes por token.
"""

import re
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / ".env"
WAIT_SECONDS = 600


def token():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("TELEGRAM_TOKEN="):
            return line.split("=", 1)[1].strip()
    sys.exit("No encuentro TELEGRAM_TOKEN en .env")


def save(user_id):
    text = ENV.read_text(encoding="utf-8")
    if re.search(r"^ALLOWED_USER_IDS=.*$", text, flags=re.M):
        text = re.sub(r"^ALLOWED_USER_IDS=.*$", f"ALLOWED_USER_IDS={user_id}",
                      text, flags=re.M)
    else:
        text += f"\nALLOWED_USER_IDS={user_id}\n"
    ENV.write_text(text, encoding="utf-8")


def main():
    tk = token()
    base = f"https://api.telegram.org/bot{tk}"
    print("Esperando tu mensaje… mándale /start al bot.", flush=True)
    deadline = time.time() + WAIT_SECONDS
    offset = 0

    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/getUpdates",
                             params={"offset": offset, "timeout": 30}, timeout=45)
            r.raise_for_status()
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message") or {}
                who = msg.get("from") or {}
                if not who.get("id"):
                    continue
                save(who["id"])
                nombre = " ".join(filter(None, [who.get("first_name"), who.get("last_name")]))
                print(f"ID capturado: {who['id']} ({nombre} @{who.get('username', 's/u')})")
                requests.post(f"{base}/sendMessage", json={
                    "chat_id": who["id"],
                    "text": "Listo, quedaste autorizado. Ya puedes mandarme palabras y capturas.",
                }, timeout=20)
                return 0
        except requests.exceptions.RequestException as exc:
            print(f"red: {exc!r}", flush=True)
            time.sleep(5)

    print("Se agotó la espera sin recibir mensajes.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
