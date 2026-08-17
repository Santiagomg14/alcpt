# Bot de Telegram

Alimenta el diccionario desde el celular: le mandas una palabra o una captura del
examen y él actualiza los JSON, regenera el PDF y las páginas web, y hace push.

No tiene ninguna ruta fija: se orienta desde su propia ubicación dentro del repo,
así que **funciona en cualquier equipo donde clones el repositorio**. Lo único que
cambia entre equipos es el archivo `.env`.

## Qué entiende

| Le mandas | Qué hace |
|---|---|
| `scuttlebutt` | Traduce con Claude Code y la agrega a `personal` |
| `scuttlebutt = rumor, chisme` | La agrega tal cual, sin usar IA |
| Una captura del examen | Extrae número, enunciado, opciones, respuesta y explicación |
| `/estado` | Cuántas palabras y preguntas hay |
| `/rebuild` | Regenera PDF y páginas web |

Si la palabra ya existe, o si la pregunta ya está documentada en ese formulario,
avisa y **no duplica** nada.

## Instalación en un equipo nuevo

```bash
git clone <URL-DEL-REPO>
cd alcpt

pip install -r requirements.txt          # reportlab, pypdf
pip install -r bot/requirements.txt      # requests

cp .env.example .env                     # en Windows: copy .env.example .env
```

Completa `.env` con:

1. **`TELEGRAM_TOKEN`** — habla con [@BotFather](https://t.me/BotFather), `/newbot`,
   y copia el token que te entrega.
2. **`ALLOWED_USER_IDS`** — tu ID numérico de Telegram, que te dice
   [@userinfobot](https://t.me/userinfobot). Sin esto cualquiera que encuentre el
   bot podría escribir en tu diccionario.

Necesitas además, en ese mismo equipo:

- **Claude Code** instalado y con sesión iniciada (`claude` en el PATH). Es lo que
  traduce las palabras y lee las capturas. Si no está en el PATH, pon la ruta en
  `CLAUDE_BIN`.
- **Credenciales de git** para poder hacer push (`gh auth login`, una llave SSH o
  un token en la URL del remoto). Si prefieres que solo haga commits locales,
  pon `GIT_PUSH=0`.

Luego:

```bash
python bot/alcpt_bot.py
```

## Dejarlo siempre encendido

**Linux (systemd)** — crea `/etc/systemd/system/alcpt-bot.service`:

```ini
[Unit]
Description=Bot ALCPT
After=network-online.target

[Service]
WorkingDirectory=/ruta/al/alcpt
ExecStart=/usr/bin/python3 /ruta/al/alcpt/bot/alcpt_bot.py
Restart=always
RestartSec=10
User=TU_USUARIO

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now alcpt-bot
journalctl -u alcpt-bot -f      # ver el registro
```

**Windows** — Programador de tareas: nueva tarea, «Al iniciar sesión», acción
`pythonw.exe` con argumento `C:\ruta\al\alcpt\bot\alcpt_bot.py`. Marca «Ejecutar
tanto si el usuario inició sesión como si no».

## Cómo funciona por dentro

El bot **no** le da acceso a la terminal a Claude Code. Lo invoca con
`--allowed-tools Read Edit Write Glob Grep`, de modo que solo puede leer y editar
archivos del repositorio. Los pasos con efectos —regenerar documentos, `git commit`,
`git push`— los ejecuta el propio bot, de forma determinista.

Las capturas se guardan en `inbox/`, que está en `.gitignore`: no viajan al
repositorio, solo la información ya extraída en los JSON.
