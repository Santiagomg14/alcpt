# Handoff — Vocabulario en inglés + ALCPT (Brayhan)

**Última actualización:** 9 sep 2026

## 1. El objetivo

Construir un diccionario acumulativo inglés→español para Brayhan (nivel B2) y
documentar en profundidad las preguntas del ALCPT, a partir de capturas de los
formularios. Todo se publica en un PDF, una web espejo y un cuaderno con buscador
y audio que él consulta desde el celular (GitHub Pages).

## 2. El estado actual del proyecto

- **331 palabras confirmadas** (1–331), sin bloques `pending_` abiertos.
- **233 preguntas** documentadas en 11 secciones (Forms 50, 62, 63, 69, 70, 71,
  73, 75, 82, 87 y Technical & Action Verbs).
- Documentos regenerados el 18 ago 2026 22:14, posteriores al último cambio de
  `data/` — están al día.
- **Bot de Telegram DETENIDO en este equipo** (`LAPTOP-H4O9EDGC`) desde el
  9 sep 2026: se desinstaló la tarea programada «ALCPT Bot» para migrarlo a un
  servidor. `bot/active_host.json` marca `host: null` (nadie lo tiene tomado).
  **Hasta que se instale en el servidor, el bot no atiende mensajes.**
- Repositorio limpio, sincronizado con `main`.

## 3. Los archivos en los que trabajas

- `data/vocabulary.json`, `data/forms.json`, `data/phrasal_verbs.json`,
  `data/idioms.json` — fuentes únicas de verdad.
- `scripts/build_pdf.py`, `build_html.py`, `build_artifact.py` — generan
  `output/` y `docs/index.html`.
- `bot/alcpt_bot.py` e `bot/install_service.py` — el bot y su instalador de servicio.
- `inbox/` — capturas nuevas (fuera del repo, en `.gitignore`).

## 4. Qué has cambiado

Sesión del 9 sep 2026: sin cambios en código ni datos. Se retiró el bot de este
equipo (`python bot/install_service.py --uninstall`), lo que generó el commit
automático `39bca08` liberando `bot/active_host.json`. Se actualizó este handoff.

## 5. Qué has intentado

- 9 sep 2026: `--status` antes → «Running» en LAPTOP-H4O9EDGC; `--uninstall` →
  «Servicio retirado. Bot liberado»; `--status` después → «No instalado», tomado
  por nadie. No quedó ningún `pythonw.exe` corriendo.
- Sesión anterior (19 ago): se verificó bot vivo, `getMe` respondía
  `@alcpt_english_bot` y los documentos de `output/` y `docs/` estaban al día.

## 6. Qué ha fallado

Nada bloqueante. En `bot/bot.log` aparecen cortes de red esporádicos contra
`api.telegram.org` (el último el 19 ago a las 08:07), pero el bot reintenta solo
cada 15 s y se recupera; no requieren intervención.

## 7. Qué planeas hacer después

- **Instalar el bot en el servidor**: clonar el repo, crear `.env` con el token
  (nunca versionarlo), `pip install -r requirements.txt` y seguir `bot/README.md`
  (`python bot/install_service.py --install` o el equivalente Linux). El
  instalador debe registrar el nuevo host en `bot/active_host.json`.
- Verificar desde el servidor con `--status` y un mensaje de prueba a Telegram.
- Seguir procesando capturas nuevas que Brayhan mande por Telegram.
- Completar las 21 preguntas registradas con la nota
  `(Not shown — captured during the test…)` si vuelve a hacer esos formularios y
  captura la pantalla de repaso.

## 8. Cualquier cosa relevante

- **Telegram admite un solo lector por token.** Si el bot se instala en otra
  máquina, hay que desinstalarlo aquí primero (`python bot/install_service.py
  --uninstall`); `bot/active_host.json` lleva el registro de quién lo tiene tomado.
- El bot arranca con `pythonw.exe`, sin consola: todo lo que pase se ve en
  `bot/bot.log` (el token va enmascarado).
- El bot ya regenera los cuatro documentos y hace commit + push por su cuenta.
  Si se editan los JSON a mano, hay que correr los cuatro scripts, incluido
  `build_artifact.py --standalone --out docs/index.html`.
