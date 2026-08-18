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
git clone https://github.com/Santiagomg14/alcpt.git
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

Para el ID no hace falta buscarlo a mano:

```bash
python bot/capture_id.py     # manda /start al bot y lo escribe solo en .env
```

Luego, para dejarlo permanente:

```bash
python bot/install_service.py
```

O para probarlo en primer plano antes: `python bot/alcpt_bot.py`

## Dejarlo siempre encendido

Un solo comando, igual en cualquier sistema:

```bash
python bot/install_service.py              # instalar y arrancar
python bot/install_service.py --status     # ¿está vivo?
python bot/install_service.py --restart    # reiniciar
python bot/install_service.py --uninstall  # quitar
```

El instalador detecta el sistema y usa el mecanismo nativo, **sin pedir permisos
de administrador**:

| Sistema | Qué crea | Arranca |
|---|---|---|
| Windows | Tarea programada «ALCPT Bot» (cmdlets de PowerShell) | al iniciar sesión |
| Linux | Unidad de usuario de systemd `alcpt-bot` + lingering | al arrancar el equipo |
| macOS | LaunchAgent `com.brayhan.alcptbot` | al iniciar sesión |

Antes de instalar comprueba lo que falta en ese equipo (`.env`, `requests`, Claude
Code, git) y lo dice en vez de fallar a medias.

En Windows arranca con `pythonw.exe` para que no quede una consola abierta; por eso
el bot escribe todo en `bot/bot.log`, que es donde hay que mirar si algo va mal.
El token nunca aparece ahí: se enmascara antes de escribir.

### Una sola máquina a la vez

Telegram admite **un solo lector por token**: si el bot corre en dos equipos, se
pelean los mensajes y se pierden. Como todas las máquinas comparten el repositorio,
se usa `bot/active_host.json` —versionado— para saber cuál lo tiene tomado.

Al instalar, el script hace `git pull`, mira ese archivo y **pregunta**:

```
Este equipo: PORTATIL-SALA (Linux)
El bot está tomado por otra máquina: LAPTOP-H4O9EDGC (Windows)
  desde 2026-08-17T19:04:09  (C:\...\alcpt)

¿Esta será la máquina definitiva donde va a correr el sistema? [s/N]
```

- Si respondes **no**, no instala nada y te recuerda cómo probarlo en primer plano.
- Si respondes **sí** y otra máquina lo tiene tomado, te dice exactamente qué
  ejecutar allá (`--uninstall`) y no continúa hasta que confirmes que lo hiciste.
- Al terminar, este equipo queda registrado como el dueño y se sube el cambio.

`--uninstall` libera el registro, dejando el bot disponible para otra máquina.
`--status` dice qué equipo lo tiene tomado y avisa si no es este.
`--force` se salta las preguntas, para guiones automáticos.

Si de todas formas quedaran dos corriendo, el bot lo detecta en caliente: Telegram
devuelve 409 y queda un aviso claro en `bot/bot.log`.

## Cómo funciona por dentro

El bot **no** le da acceso a la terminal a Claude Code. Lo invoca con
`--allowed-tools Read Edit Write Glob Grep`, de modo que solo puede leer y editar
archivos del repositorio. Los pasos con efectos —regenerar documentos, `git commit`,
`git push`— los ejecuta el propio bot, de forma determinista.

Las capturas se guardan en `inbox/`, que está en `.gitignore`: no viajan al
repositorio, solo la información ya extraída en los JSON.
