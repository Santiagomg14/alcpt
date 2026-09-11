# Handoff — Vocabulario en inglés + ALCPT (Brayhan)

**Última actualización:** 11 sep 2026 (03:14, bot en server)

## 1. El objetivo

Construir un diccionario acumulativo inglés→español para Brayhan (nivel B2) y
documentar en profundidad las preguntas del ALCPT, a partir de capturas de los
formularios. Todo se publica en un PDF, una web espejo y un cuaderno con buscador
y audio que él consulta desde el celular (GitHub Pages).

Desde el 9 sep 2026 el cuaderno tiene además dos pestañas nuevas:
**Lecturas** (artículos de ThoughtCo condensados a nivel B2, en temas ajenos a su
experticia: tecnología, matemáticas, humanidades y ciencias sociales) y
**Podcasts** (audios de ≤10 min: todo el vocabulario en orden y una lectura por
episodio).

## 2. El estado actual del proyecto

- **334 palabras confirmadas**, sin bloques `pending_` abiertos, y
  **293 preguntas** documentadas. Estas cifras, las de lecturas y episodios de
  abajo y la fecha de arriba **las actualiza el bot solo** en cada commit
  (`update_handoff()`); el resto del handoff sigue siendo manual. Verifícalo con:
  `python -c "import json;v=json.load(open('data/vocabulary.json'));print(sum(len(s['entries']) for s in v['sections']))"`
- **14 lecturas** condensadas en `data/readings.json` (3 tech, 3 math, 2 social,
  6 humanities: filosofía, asuntos públicos, geografía, historia).
- **21 episodios de podcast** en `data/podcasts.json` + `docs/audio/*.mp3`:
  7 de vocabulario (8:00–8:49 cada uno, el último 3:57 tras sumar «Basement») y
  14 de lecturas (4:53–6:05). ~48 MB de MP3 en `docs/audio/`, 132 min en total.
- **Bot de Telegram CORRIENDO en el servidor Linux** (`server`, Ubuntu 24.04),
  en `/home/citae/Pictures/programas/alcpt`, como unidad systemd de usuario
  `alcpt-bot`. `bot/active_host.json` registra `server (Linux)` como dueño.
  El 10 sep se actualizó el servidor (pull + `pip install -r requirements.txt`
  + restart): **ya corre el código con lecturas y podcasts**. Falta probarlo
  mandándole un enlace de ThoughtCo por Telegram.

## 3. Los archivos en los que trabajas

- `data/vocabulary.json`, `data/forms.json`, `data/phrasal_verbs.json`,
  `data/idioms.json` — fuentes únicas de verdad del cuaderno.
- `data/readings.json` — lecturas (metadatos + resumen, key_points, glossary,
  question). El texto original vive en `inbox/readings/<id>.txt`, fuera del repo.
- `data/podcasts.json` — guiones, hash, duración y bytes de cada episodio.
- `scripts/fetch_readings.py` — descubre/descarga/condensa artículos de ThoughtCo.
- `scripts/build_podcasts.py` — guiones + MP3 con edge-tts, solo lo que cambió.
- `scripts/build_artifact.py` — ahora genera las tres pestañas.
- `bot/alcpt_bot.py` — acepta enlaces de thoughtco.com y `/lecturas`; `rebuild()`
  corre `build_podcasts.py` antes del cuaderno. Las fotos van a `handle_image()`
  → `scripts/parse_capture.py` (local); `handle_image_claude()` es el camino viejo.
- `scripts/ocr_capture.py` — OCR con RapidOCR (escala de grises, 1400 px de
  ancho, agrupa fragmentos por renglón, devuelve texto + geometría + confianza).
- `scripts/parse_capture.py` — reglas sobre el OCR: `Form NN`, `Question N`,
  opciones `A.`/`b)`/sin letra, bloque `Explanation`; correcta por saturación
  verde de la franja de cada opción; `wordsegment` despega palabras; escribe en
  `forms.json` (dedupe por form+n, completa las «Not shown» si llega la de repaso).

## 4. Qué has cambiado

Sesión del 9 sep 2026 (este equipo, tras la migración del bot al servidor):

- Nuevo `scripts/fetch_readings.py`. ThoughtCo devuelve 402 sin cabeceras de
  navegador; con User-Agent de Chrome responde 200. El cuerpo se extrae de los
  bloques `.mntl-sc-block` (headings + html); imágenes y anuncios se omiten. La
  condensación usa `claude -p` leyendo el artículo por stdin y devolviendo JSON;
  quita `CLAUDECODE` del entorno para poder correr anidado.
- Nuevo `scripts/build_podcasts.py`. Voces `en-US-AndrewNeural` / `es-CO-SalomeNeural`
  a rate −5 %. Pausas como tramas MP3 de silencio (MPEG-2 L3, 24 kHz, 48 kbps,
  mono, 144 bytes = 24 ms) intercaladas; no hace falta ffmpeg. Duración medida
  con mutagen. Estimador: 158 wpm + 1,4 s de sobrecarga por segmento (medido).
- `scripts/build_artifact.py`: pestañas Cuaderno / Lecturas / Podcasts con
  `role=tablist`, hash en la URL (`#lecturas`, `#ep-vocab-01`, `#lectura-<id>`),
  última pestaña recordada en localStorage, filtro por tema, quiz de una sola
  respuesta, un solo `<audio>` sonando a la vez y saltos lectura↔episodio.
  Nuevo `--audio-base` (el fragmento para Artifact toma los MP3 de GitHub Pages).
- `bot/alcpt_bot.py`: `handle_reading_url`, `handle_readings_cmd`, `/lecturas`,
  `/estado` con lecturas, paso «podcasts» en `rebuild()`.
- `requirements.txt`: + requests, beautifulsoup4, edge-tts, mutagen.
- `CLAUDE.md` (reglas 8 y 9, estructura, comandos), `README.md`, `bot/README.md`.
- Primer lote: 14 artículos registrados y condensados; 21 MP3 generados.
- `build_podcasts.py` escribe `podcasts.json` tras cada episodio y tiene `--adopt`
  (reconoce MP3 ya generados sin registro): hizo falta porque Windows mató dos
  veces el render en segundo plano por falta de memoria.

Sesión del 10 sep 2026 (servidor `server`, Claude Code):

- Sincronización con el remoto. El servidor iba 1 commit adelante («Basement»,
  hecho por el bot) y 2 atrás (lecturas y podcasts del portátil). Se hizo
  `git rebase origin/main`; los únicos conflictos fueron los archivos generados
  (`docs/index.html`, `output/*`): se tomó la versión remota y se regeneró todo
  con los cinco scripts. `build_podcasts.py` re-renderizó solo `vocab-07`
  (237 s). Commit `774482d` pusheado.
- Instalados `edge-tts` y `mutagen` en el `.venv` del servidor.
- Reiniciado el servicio `alcpt-bot`; conectó bien a las 17:01 UTC.
- Nuevo `update_handoff()` en `bot/alcpt_bot.py`, llamado en `finish()` entre
  `rebuild()` y `git_sync()`. Reescribe con regex la línea «Última actualización»
  y los números en negrita del §2 (`**N palabras confirmadas**`, `**N preguntas**`,
  `**N lecturas**`, `**N episodios de podcast**`). Si una frase cambia de forma,
  esa sustitución simplemente no aplica; no rompe el bot. Probado sobre una copia
  con cifras falsas: las cuatro se corrigieron. **No cambiar esas frases del §2
  sin ajustar los patrones.**

Sesión del 11 sep 2026 (servidor `server`):

- **Capturas sin Claude Code.** Petición de Brayhan para ahorrar tokens. No hay
  `sudo` en el servidor (Tesseract descartado); `rapidocr-onnxruntime` va por pip
  con sus modelos. Probado con 3 capturas sintéticas (repaso con verde, examen sin
  respuesta, imagen ajena) y luego **con 9 capturas reales del Form 65** que mandó
  Brayhan: las 9 fallaron con el parser inicial (diseño supuesto ≠ app real) y se
  reescribió. La app tiene dos pantallas por ítem: la de pregunta (enunciado
  «NN. …», opciones con círculo, la correcta en texto verde) y la de explicación
  («Answer: NN)», «Correct Answer "…"», Explanation, Incorrect Answers). El parser
  detecta cuál es, y `save()` funde ambas en la misma entrada (cada campo se
  completa si falta). Resultado: 7 preguntas nuevas del Form 65 (56, 66, 86, 92,
  95, 98, 100), la 92 fundida de dos capturas, la 96 ya existía.
  Trucos que hicieron falta: restituir «________» por el hueco entre fragmentos
  OCR del mismo renglón; «10» + «0.» = 100; «56. 56 Phyllis» (número repetido);
  «Incorrect Answers» se evalúa antes que «Correct Answer»; verde por fracción de
  píxeles (g > r+35 y g > b+35) en la franja de cada opción; `wordsegment` solo
  parte tokens de 8+ letras cuando todas las partes son palabras reales y no hay
  guion delante (los sufijos «-oraneity» se respetan).
- `CAPTURE_FALLBACK` en `.env` (`off` por defecto, `claude` para el camino viejo).
- Diagramas de arquitectura (actual vs propuesta) publicados como artifact:
  https://claude.ai/code/artifact/e7308c13-eb52-40b0-b92f-ad0c430fdc88

## 5. Qué has intentado

- Secciones de ThoughtCo verificadas (200 con cabeceras): computer-science,
  math, statistics, geometry, humanities, history, geography, philosophy,
  issues, social-sciences. El slug de la URL no importa, solo el id numérico.
- Calibración edge-tts: 171 palabras EN → 64,8 s (158 wpm). Un episodio de 78
  palabras dio 755 s reales frente a 513 s estimados → se añadió la sobrecarga
  de 1,4 s por segmento y quedaron ~50 palabras por episodio (~480 s reales).
- Concatenar MP3 de las dos voces + tramas de silencio: mutagen lo lee bien y
  la duración cuadra.
- `git pull --rebase` desde Claude Code en el servidor queda bloqueado por el
  clasificador de permisos; `git fetch` + `git rebase origin/main` sí pasa.
- `claude -p` anidado desde una sesión de Claude Code funciona si se quita
  `CLAUDECODE` del entorno (8 s para una respuesta trivial; 20–60 s por artículo).
- Página validada: Node `--check` del JS sin errores y etiquetas HTML balanceadas.
  No se pudo abrir en Chrome desde aquí (extensión desconectada).

## 6. Qué ha fallado

- Heredocs largos en la shell de Claude Code fallan («unexpected EOF»); los
  scripts grandes se escribieron con la herramienta de archivos.
- edge-tts 7.x no emite `WordBoundary` por defecto, por eso la duración se mide
  con mutagen y no con los offsets del stream.
- La primera estimación de duración se quedó corta un 47 % (ver §5).

## 7. Qué planeas hacer después

- Seguir calibrando el parser con más capturas reales (ya va 9/9 del Form 65).
  Pendiente conocido: en la pantalla de explicación el bloque «Incorrect Answers»
  puede venir cortado por el scroll (la última frase queda truncada); y el
  enunciado de la #66 salió sin signos («what did Tom do … he got kind of riled»).
  Si una captura falla, el texto OCR queda en `inbox/<captura>.txt` para depurar
  con `python scripts/parse_capture.py inbox/x.jpg --dry-run`.
- Probar el bot actualizado mandándole un enlace de ThoughtCo y `/lecturas`.
  Revisar que `inbox/readings/` se cree solo en el servidor (está en `.gitignore`).
- Mandarle a Brayhan el enlace de GitHub Pages con `#podcasts` y pedirle
  feedback: ¿ritmo de las voces?, ¿palabras por episodio?, ¿temas?
- Si quiere más lecturas: `python scripts/fetch_readings.py --discover <sección>`
  y elegir; o `/lecturas <sección> <n>` desde Telegram.
- Completar las 21 preguntas con la nota `(Not shown — captured during the test…)`
  si vuelve a hacer esos formularios y captura la pantalla de repaso.
- Pendiente de decidir: ¿las lecturas van también al PDF y a la web espejo?
  Hoy solo están en el cuaderno (pestaña Lecturas).

## 8. Cualquier cosa relevante

- **Al empezar sesión en el servidor, hacer `git fetch` primero**: el bot
  commitea y pushea solo, así que el portátil y el servidor divergen con
  facilidad. Si hay conflicto, siempre está en los generados: resolver con la
  versión que sea y regenerar (PDF → espejo → podcasts → cuaderno → Pages).
- **Artifact de Claude «Cuaderno ALCPT»** (https://claude.ai/code/artifact/95b9749a-55b5-4292-831d-121fb6dd2aed):
  se publica desde `output/cuaderno_alcpt.html`, actualizado el 10 sep (versión 5,
  con pestañas Lecturas y Podcasts). **Limitación:** el visor de artifacts bloquea
  por CSP los MP3 que vienen de GitHub Pages, así que en el artifact la pestaña
  Podcasts muestra los reproductores pero no suena; embeberlos como data: URI no
  cabe (48 MB frente a un tope de 16 MB). El audio de podcasts funciona en
  GitHub Pages (`docs/index.html`). Resuelto el 11 sep: el fragmento lleva un
  aviso con enlace a Pages al inicio de la pestaña y, si un `<audio>` falla al
  cargar, el JS lo cambia por un enlace al episodio en Pages (`data-pages`).
- **Telegram admite un solo lector por token.** Si el bot se instala en otra
  máquina, hay que desinstalarlo primero donde esté (`install_service.py
  --uninstall`); `bot/active_host.json` lleva el registro de quién lo tiene tomado.
- **En el servidor hay que invocar los scripts con `.venv/bin/python`**, no con
  `python`: las dependencias están en el entorno virtual del repo.
- Comandos útiles allá: `systemctl --user status alcpt-bot`,
  `systemctl --user restart alcpt-bot`, `journalctl --user -u alcpt-bot -f`.
  El servicio corre sin consola: todo queda en `bot/bot.log` (token enmascarado).
- Orden de regeneración: PDF → espejo → **podcasts** → cuaderno → Pages. El bot
  ya lo hace así; si se edita a mano, no olvidar `build_podcasts.py` antes de
  `build_artifact.py`.
- `build_podcasts.py` sin edge-tts instalado avisa y sale con 0 (actualiza
  guiones, no audio), para no bloquear al bot.
- GitHub Pages sirve `docs/`; los MP3 pesan ~3 MB cada uno. Si el repo crece
  demasiado, la alternativa es mover `docs/audio/` a Releases o a otro hosting y
  cambiar `--audio-base`.
