# Handoff — Vocabulario en inglés + ALCPT (Brayhan)

**Última actualización:** 19 ago 2026

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
- **Bot de Telegram corriendo** en este equipo (`LAPTOP-H4O9EDGC`), instalado como
  tarea programada «ALCPT Bot», que arranca sola al iniciar sesión de Windows.
- Repositorio limpio, sincronizado con `main` (`c596fe3`).

## 3. Los archivos en los que trabajas

- `data/vocabulary.json`, `data/forms.json`, `data/phrasal_verbs.json`,
  `data/idioms.json` — fuentes únicas de verdad.
- `scripts/build_pdf.py`, `build_html.py`, `build_artifact.py` — generan
  `output/` y `docs/index.html`.
- `bot/alcpt_bot.py` e `bot/install_service.py` — el bot y su instalador de servicio.
- `inbox/` — capturas nuevas (fuera del repo, en `.gitignore`).

## 4. Qué has cambiado

En esta sesión no se tocó ni el código ni los datos: solo se verificó que los
servicios estuvieran arriba y se creó este `handoff.md`, que faltaba.

## 5. Qué has intentado

- `python bot/install_service.py --status` → tarea «ALCPT Bot» en **Running**,
  registrada a nombre de este mismo equipo en `bot/active_host.json`.
- Se confirmó el proceso vivo (`pythonw.exe … bot/alcpt_bot.py`, PID 11608).
- Llamada a `getMe` de la API de Telegram → responde `@alcpt_english_bot`.
- Se compararon fechas de `data/` contra `output/` y `docs/`: los documentos son
  posteriores, no hay nada por regenerar.

## 6. Qué ha fallado

Nada bloqueante. En `bot/bot.log` aparecen cortes de red esporádicos contra
`api.telegram.org` (el último el 19 ago a las 08:07), pero el bot reintenta solo
cada 15 s y se recupera; no requieren intervención.

## 7. Qué planeas hacer después

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
