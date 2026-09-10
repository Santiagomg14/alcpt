# Handoff — Vocabulario en inglés + ALCPT (Brayhan)

**Última actualización:** 10 sep 2026

## 1. El objetivo

Construir un diccionario acumulativo inglés→español para Brayhan (nivel B2) y
documentar en profundidad las preguntas del ALCPT, a partir de capturas de los
formularios. Todo se publica en un PDF, una web espejo y un cuaderno con buscador
y audio que él consulta desde el celular (GitHub Pages).

## 2. El estado actual del proyecto

- **333 palabras confirmadas**, sin bloques `pending_` abiertos, y
  **266 preguntas** documentadas. Contado el 10 sep 2026 sobre los JSON; los
  handoffs anteriores arrastraban 331 y 233, cifras previas a las capturas que
  se procesaron en agosto. Verifícalo siempre con `counts()` del bot o con:
  `.venv/bin/python -c "import json;v=json.load(open('data/vocabulary.json'));print(sum(len(s['entries']) for s in v['sections']))"`
- Documentos regenerados el 10 sep 2026, al día con `data/`.
- **Bot de Telegram CORRIENDO en el servidor Linux** (`server`, Ubuntu 24.04),
  en `/home/citae/Pictures/programas/alcpt`, desde el 10 sep 2026 02:39 UTC.
  Migrado desde `LAPTOP-H4O9EDGC`, que lo había liberado el 9 sep.
  `bot/active_host.json` registra `server (Linux)` como dueño.
- Repositorio limpio, sincronizado con `main`.

## 3. Los archivos en los que trabajas

- `data/vocabulary.json`, `data/forms.json`, `data/phrasal_verbs.json`,
  `data/idioms.json` — fuentes únicas de verdad.
- `scripts/build_pdf.py`, `build_html.py`, `build_artifact.py` — generan
  `output/` y `docs/index.html`.
- `bot/alcpt_bot.py` e `bot/install_service.py` — el bot y su instalador de servicio.
- `inbox/` — capturas nuevas (fuera del repo, en `.gitignore`).

## 4. Qué has cambiado

Sesión del 10 sep 2026. Se activó el bot en el servidor Linux y se corrigió un
bug que la primera prueba dejó a la vista:

- `git pull --ff-only` para traer `39bca08` y `a7ebf8a` (liberación del bot en
  Windows), con el visto bueno del usuario.
- `.venv/bin/python bot/capture_id.py` → completó `ALLOWED_USER_IDS` en `.env`
  con el ID capturado al recibir `/start`. `.env` sigue fuera del repo.
- `.venv/bin/python bot/install_service.py --force` → creó la unidad de usuario
  `~/.config/systemd/user/alcpt-bot.service`, la habilitó y activó el lingering.
  Generó el commit automático `a9ae156` tomando el bot para `server (Linux)`.
- Se usó `--force` porque el instalador pregunta por `input()` y aquí no hay
  terminal interactiva; era seguro: `active_host.json` estaba en `host: null`.
- `6d5a396` — **arreglo en `bot/alcpt_bot.py`**: `finish()` ya no regenera ni
  commitea cuando `data/` no cambió. Nuevo helper `data_changed()`, y `/rebuild`
  pasa `force=True` porque ahí regenerar sin cambios sí es lo pedido.
- `f2ddf71` — corrección del conteo en este handoff (ver §2).

## 5. Qué has intentado

Verificaciones hechas en el servidor antes y después de instalar:

- Dependencias del `.venv`: `requests` 2.34.2, `reportlab` 5.0.1, `pypdf` 6.18.0.
- `CLAUDE_BIN=/home/citae/.local/bin/claude` → Claude Code 2.1.267.
- `getMe` de Telegram → responde `@alcpt_english_bot`.
- `install_service.py --status` → `active (running)`, PID 1253467, tomado por
  `server (Linux)`. `loginctl show-user citae -p Linger` → `Linger=yes`.
- `bot/bot.log` → «conectado como @alcpt_english_bot», sin 409 (nadie más lee
  el token).
- Con un entorno mínimo (`env -i HOME=… PATH=/usr/bin:/bin`), imitando el que
  systemd le da al servicio: SSH a GitHub autentica, `git push --dry-run` pasa y
  `claude -p` responde. O sea, el servicio puede traducir y hacer push por sí solo.
- **Prueba real desde el celular**: se le mandó «Scuttlebutt». El bot la recibió,
  llamó a Claude Code, que detectó que ya estaba en el diccionario y no la
  duplicó; después regeneró documentos y subió `6123ac6`. El circuito funciona
  de punta a punta.
- `data_changed()` probado en los cuatro casos: repo limpio, archivo nuevo en
  `data/`, JSON modificado y repo restaurado. Acierta en todos.

## 6. Qué ha fallado

- **Commits que mentían** (arreglado en `6d5a396`). La primera prueba dejó
  `6123ac6`, titulado «Vocabulario: agrega «Scuttlebutt»», cuyo único contenido
  real era la fecha de generación en `output/`: la palabra ya existía y Claude
  Code, correctamente, no editó nada, pero `finish()` regeneraba igual y el
  rebuild siempre cambia esa fecha, así que `git_sync()` nunca veía un commit
  vacío. Ese commit queda en el historial; los siguientes ya no pasarán.
- Fricción menor: `install_service.py` asume la opción segura (NO) cuando no hay
  TTY, lo que obliga a `--force` desde un guion o desde Claude Code.

## 7. Qué planeas hacer después

- **Falta probar el camino de las imágenes**: mandarle una captura del examen al
  bot. Es lo único del flujo que no se ha ejercitado en este equipo, y pasa por
  la descarga de archivos de Telegram y por `inbox/`.
- Verificar el arreglo de `6d5a396` en caliente: mandarle una palabra repetida y
  comprobar que responde «no cambió nada en data/» y no aparece ningún commit.
- Seguir procesando capturas nuevas que Brayhan mande por Telegram.
- Completar las 21 preguntas registradas con la nota
  `(Not shown — captured during the test…)` si vuelve a hacer esos formularios y
  captura la pantalla de repaso.

## 8. Cualquier cosa relevante

- **Telegram admite un solo lector por token.** Si el bot se instala en otra
  máquina, hay que desinstalarlo aquí primero (`.venv/bin/python
  bot/install_service.py --uninstall`); `bot/active_host.json` lleva el registro
  de quién lo tiene tomado.
- **En el servidor hay que invocar los scripts con `.venv/bin/python`**, no con
  `python`: las dependencias están en el entorno virtual del repo. La unidad de
  systemd ya apunta al intérprete del `.venv`.
- Comandos útiles en este equipo: `systemctl --user status alcpt-bot`,
  `systemctl --user restart alcpt-bot`, `journalctl --user -u alcpt-bot -f`.
- El servicio corre sin consola: todo lo que pase se ve en `bot/bot.log`
  (el token va enmascarado).
- El lingering está activo, así que el bot sobrevive al cierre de sesión y
  arranca solo al encender el equipo.
- El bot ya regenera los cuatro documentos y hace commit + push por su cuenta.
  Si se editan los JSON a mano, hay que correr los cuatro scripts, incluido
  `build_artifact.py --standalone --out docs/index.html`.
