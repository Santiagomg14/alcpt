# Proyecto: Vocabulario en inglés + ALCPT (Brayhan)

Este repositorio continúa un proyecto de estudio que empezó en Claude.ai. Se movió a Claude Code
para poder procesar muchas imágenes de exámenes sin topar límites de subida.

## Contexto del estudiante

- Nombre: Brayhan.
- Nivel de inglés: **B2**. Esto es crítico: NO se agregan palabras de alta frecuencia que ya conoce.
- Objetivo: construir un diccionario acumulativo y documentar en profundidad las preguntas del
  ALCPT (American Language Course Placement Test).

## Reglas de trabajo (no negociables)

### 1. Palabras sueltas
Cuando Brayhan escriba una palabra o expresión, se agrega **directamente** a
`data/vocabulary.json`, en la sección `personal`, con:
- `en`: la palabra o expresión (si la escribió con error ortográfico, se corrige y se menciona).
- `es`: traducción, matices y acepciones separadas por punto y coma.
- Numeración `n` consecutiva, continuando la última usada.

### 2. Imágenes de formularios ALCPT
1. Leer las capturas de la carpeta `inbox/` (o la ruta que indique).
2. Extraer las preguntas: número, enunciado completo, todas las opciones, respuesta correcta y la
   explicación. Guardar en `data/forms.json` bajo el `form` correspondiente.
3. **Antes de tocar el vocabulario**: proponer una lista de palabras candidatas "extrañas" o poco
   frecuentes y **preguntarle a Brayhan cuáles descartar**. Guardarlas provisionalmente en
   `pending_<form>` dentro de `vocabulary.json`.
4. Solo cuando él confirme, mover las aprobadas a una sección nueva
   (`form87`, `form90`, etc.) con numeración consecutiva, y borrar el bloque `pending_`.

Criterio de filtrado: descartar vocabulario básico o intermedio bajo (heavy, storm, fence, piece,
gloves, whisper, etc.). Conservar términos militares, idioms, jerga, phrasal verbs no obvios y
palabras técnicas (scuttlebutt, chaplain, disrepair, dud, rule of thumb, expenditure, terrestrial…).

### 3. Idioma de cada parte
- **Vocabulario**: inglés → español (traducción y notas en español).
- **Sección ALCPT**: **TODO en inglés**, sin excepción: enunciado, opciones, respuesta correcta y
  explicación. Es intencional, funciona como práctica de lectura a nivel de examen.

### 4. Orden de presentación
Cuando se muestre el estado del proyecto (en chat o en PDF), el orden es siempre:
1. Vocabulario completo (todas las entradas desde el número 1).
2. Phrasal verbs, agrupados por partícula.
3. Idioms y expresiones militares, agrupados por uso.
4. Sección ALCPT agrupada por formulario, con pregunta / opciones / respuesta / explicación.
5. Lecturas (Parte V), agrupadas por tema. Van al final para no alterar el orden
   de las cuatro primeras partes, que es el que Brayhan estudia.

### 5. Phrasal verbs
`data/phrasal_verbs.json` explica los phrasal verbs que **aparecen de verdad** en los
formularios documentados. No se inventan ni se traen de listas genéricas: cada entrada
cita la frase textual del examen y el formulario donde salió.

Se agrupan **por partícula** (UP, OFF·AWAY, OUT, OVER, DOWN·BACK, otras) porque cada una
carga un sentido bastante estable, y entender eso rinde más que memorizar casos sueltos.
Cada entrada lleva: significado en español, si es separable o no, la trampa típica para
un hispanohablante, la frase del examen y su origen.

Explicación en español; los ejemplos, textuales en inglés.

### 6. Idioms y expresiones militares
`data/idioms.json` tiene dos secciones con el mismo formato que los phrasal verbs:

- **Idioms**, agrupados por lo que expresan (tiempo y urgencia, cantidad y dificultad,
  cómo es una persona, estados y modo).
- **Léxico militar**, agrupado por ámbito (mando y rutina, operaciones y combate,
  mantenimiento y equipo, información y vida en la base).

Aquí van las expresiones fijas que NO son phrasal verbs (take place, run short of,
tell time…) y el vocabulario de servicio que el examen da por sabido (sick call,
cover, dud, scuttlebutt…). Muchas ya están en el diccionario numerado: aquí se repiten
a propósito, agrupadas por uso y con la frase textual del examen.

Regla para no duplicar: si lleva partícula y funciona como verbo, va en
`phrasal_verbs.json`; si no, va aquí.

### 7. Formato de documentos
Preferencia fija de Brayhan: **en Word y PDF, los párrafos siempre van justificados.**
El script `scripts/build_pdf.py` ya aplica `TA_JUSTIFY` en todos los estilos de texto corrido.

### 8. Lecturas (pestaña «Lecturas» del cuaderno)
`data/readings.json` guarda artículos de divulgación de **ThoughtCo** condensados al nivel
B2. Temas elegidos por Brayhan: **tecnología y computación, matemáticas, humanidades y
ciencias sociales** (nada de ciencias naturales salvo que él lo pida). Son temas ajenos a su
experticia a propósito.

- Se traen con `scripts/fetch_readings.py` (`--discover`, `--add URL`, `--add-from-section`,
  `--condense`). El texto original queda en `inbox/readings/` (fuera del repo); al JSON solo
  van metadatos + el condensado.
- La condensación la hace Claude Code (`claude -p`, como el bot): **resumen en inglés** de
  250–350 palabras, `key_points`, `glossary` inglés→español (solo términos B2+) y una
  `question` de comprensión estilo ALCPT con 4 opciones.
- Las palabras del glosario **no** se pasan automáticamente al diccionario numerado; si
  Brayhan quiere alguna, la pide y entra por la regla 1.
- Desde el 13 sep 2026 salen también en el PDF y en la web espejo (Parte V), además
  de en la pestaña «Lecturas» del cuaderno.
- **ThoughtCo bloquea la IP del servidor (HTTP 402), también la portada**: las
  lecturas hay que traerlas desde el portátil y subirlas. El bot lo dice con ese
  mensaje en vez de fallar en seco.
- El bot también las trae: un enlace de thoughtco.com, o `/lecturas <sección> <n>`.

### 10. Capturas por Telegram: procesamiento local
Desde el 11 sep 2026 el bot NO le pasa las capturas a Claude Code. La cadena es
`scripts/ocr_capture.py` (RapidOCR, en el servidor) → `scripts/parse_capture.py`
(reglas: formulario, número, enunciado, opciones; respuesta correcta por el color de
la opción resaltada; explicación transcrita tal cual) → `data/forms.json` sin duplicar.
Cero tokens y ~3 s por captura. Si el parser no puede, el bot avisa con el texto OCR
y deja `inbox/<captura>.txt`; solo con `CAPTURE_FALLBACK=claude` en `.env` recurre a
Claude Code. La regla 2 (filtrar vocabulario y preguntar a Brayhan) sigue igual: el
parser no toca `vocabulary.json`.

La app tiene dos pantallas por ítem (pregunta con la correcta en verde; explicación
con «Correct Answer», «Explanation» e «Incorrect Answers»). Se funden en la misma
entrada; lo que falta queda con un marcador «(… not captured yet.)» y `/pendientes`
lo lista. El texto pasa por corrector ortográfico (corpus de wordsegment) y los
enunciados de audio se puntúan («…the order. What did he do?»).

**Listas de vocabulario en captura** (TikTok, apuntes: inglés a la izquierda, español a
la derecha): si la imagen no es del formulario, `scripts/parse_vocab_capture.py` separa
las dos columnas por el hueco horizontal, filtra la interfaz de la app y agrega las
entradas a `personal` con numeración consecutiva y `"ocr": true`. Después el bot le
pide a Claude, **solo con texto** (sin herramientas ni imagen, unos cientos de tokens),
el campo `es` con tildes repuestas y matices B2, y quita la marca. `VOCAB_POLISH=0`
lo desactiva. Las capturas HEIC del iPhone se abren con `pillow-heif`.

### 11. Lotes grandes (cientos de capturas)
Telegram admite 30 imágenes por tanda y el bot solo puede descargar archivos de
hasta 20 MB, así que para lotes grandes hay dos caminos, ambos por Telegram:

**OJO con los dos enlaces de iCloud.** El del botón «Compartir» de Fotos
(`share.icloud.com/photos/…`, que redirige a `icloud.com/photos/#…`) va por
CloudKit y exige iniciar sesión con la cuenta de Apple: **no se puede leer** y el
bot responde con las instrucciones para crear el otro. El de «álbum compartido»
(`icloud.com/sharedalbum/#B0X…`) es público y ese sí funciona.

- **Álbum compartido de iCloud** (el bueno, sin límite): en el iPhone, Fotos →
  seleccionar → Compartir → «Añadir a álbum compartido» → en el álbum, «Personas»
  → «Sitio web público» → copiar enlace. Se le manda al bot tal cual, o con
  `/lote <enlace>`. `scripts/fetch_icloud_album.py` habla con la API pública
  (`webstream` y `webasseturls`) y baja la copia de mayor resolución de cada foto.
- **ZIP**: como documento por Telegram (hasta 20 MB) o `/lote <enlace directo al zip>`.

En el servidor, el OCR va con `OCR_THREADS=4` (variable de entorno): con los 24
hilos por defecto ONNX reserva gigabytes y el sistema mata el lote, porque la
máquina es compartida. Con 4 son 0,5 GB y además va más rápido (2,6 s por captura).

Las fotos se guardan en `capturas/album_<token>/`, **dentro del repositorio**: son el
respaldo de Brayhan (borra las del iPhone) y permiten reprocesarlas si el lector
mejora. El nombre de cada foto es su checksum en iCloud, así que **reenviar el mismo
enlace solo baja y procesa lo nuevo**. El texto OCR (`*.txt`) no se versiona: es
derivado y se regenera.

El procesado corre en un hilo aparte: el bot sigue atendiendo mensajes, avisa cada
25 imágenes y admite `/lote estado` y `/lote cancelar`. Al final, un solo commit.
`scripts/process_batch.py` carga el motor de OCR una vez (~3,3 s por captura en vez
de ~3,5 arrancando de cero) y lleva `bot/processed.json` (sha256 → resultado) para
no releer una imagen ya vista. Cada captura se prueba primero como formulario y,
si no lo es, como lista de vocabulario.

**Ráfagas**: el bot no regenera ni commitea por captura. Anota cada cambio y, tras
`FLUSH_DELAY` segundos (30) sin novedades, regenera una vez, un commit «Lote: …» y
un push. `/rebuild` cierra el lote de inmediato. Al parar el servicio (SIGTERM)
también se cierra.

**Verificación**: `python scripts/audit_forms.py` (0 sospechosas es el objetivo) y
`python scripts/check_captures.py` (compara el parser con las 93 capturas reales;
`--update` tras revisar cambios a mano).

### 9. Podcasts (pestaña «Podcasts»)
`data/podcasts.json` + `docs/audio/*.mp3`, generados por `scripts/build_podcasts.py` con
**edge-tts** (voces `en-US-AndrewNeural` y `es-CO-SalomeNeural`, sin clave ni costo).

- **Tope fijo: 10 minutos por episodio** (`MAX_SECONDS = 600`). Dos series:
  `vocab` (todo el diccionario en orden: palabra en inglés → significado en español →
  palabra otra vez) y `lecturas` (una por artículo: resumen, glosario y pregunta).
- Solo se re-renderiza lo que cambió (hash del guion). Agregar una lectura crea un
  episodio nuevo. El último episodio de vocabulario, que va creciendo, **espera a
  juntar 10 palabras** antes de rehacerse (`MIN_PALABRAS_NUEVAS`): rehacerlo por cada
  palabra metía un MP3 de ~1,4 MB en el historial de git cada vez. `--force` lo
  rehace igualmente.
- Las pausas se insertan como tramas MP3 de silencio del mismo formato que edge-tts; no se
  necesita ffmpeg.

## Estructura

```
alcpt/
├── CLAUDE.md              <- este archivo
├── README.md              <- cómo usarlo
├── requirements.txt
├── data/
│   ├── vocabulary.json    <- fuente única del diccionario
│   ├── forms.json         <- fuente única de las preguntas
│   ├── phrasal_verbs.json <- phrasal verbs de los formularios, por partícula
│   ├── idioms.json        <- idioms y léxico militar, por uso
│   ├── readings.json      <- lecturas de ThoughtCo condensadas (pestaña Lecturas)
│   └── podcasts.json      <- guiones y metadatos de los episodios (pestaña Podcasts)
├── scripts/
│   ├── build_pdf.py       <- genera el PDF consolidado
│   ├── build_html.py      <- versión web espejo del PDF
│   ├── build_artifact.py  <- cuaderno con pestañas Cuaderno / Lecturas / Podcasts
│   ├── build_podcasts.py  <- guiones + MP3 con edge-tts (≤10 min por episodio)
│   ├── fetch_readings.py  <- trae y condensa artículos de ThoughtCo
│   ├── ocr_capture.py     <- OCR local de una captura (RapidOCR, sin red)
│   ├── parse_capture.py   <- captura → pregunta en forms.json, sin Claude Code
│   ├── parse_vocab_capture.py <- lista término=significado (TikTok) → vocabulary.json
│   ├── fetch_icloud_album.py  <- baja un álbum compartido de iCloud entero
│   ├── process_batch.py   <- procesa una carpeta de capturas (motor OCR cacheado)
│   ├── audit_forms.py     <- completas / pendientes / sospechosas en forms.json
│   ├── check_captures.py  <- regresión del parser contra tests/captures_expected.json
│   └── add_word.py        <- agrega palabras por línea de comandos
├── bot/
│   ├── alcpt_bot.py       <- bot de Telegram (portátil, sin rutas fijas)
│   └── README.md          <- cómo dejarlo corriendo en cualquier equipo
├── capturas/              <- imágenes de origen, SÍ versionadas (respaldo de Brayhan)
│   └── album_<token>/     <- una carpeta por álbum de iCloud; reenviar el enlace es incremental
├── inbox/                 <- capturas sueltas de Telegram y texto de lecturas (fuera del repo)
├── docs/                  <- index.html + audio/*.mp3 publicados en GitHub Pages
└── output/                <- PDF y páginas generadas
```

## Al cambiar los datos

Cualquier cambio en `data/*.json` obliga a regenerar los documentos. El orden importa:
los podcasts van antes del cuaderno, porque el cuaderno lee `podcasts.json`.

```bash
python scripts/build_pdf.py
python scripts/build_html.py
python scripts/build_podcasts.py        # solo re-renderiza los episodios que cambiaron
python scripts/build_artifact.py
python scripts/build_artifact.py --standalone --out docs/index.html
```

El bot ya hace esto solo. Si editas a mano, no olvides `docs/index.html`: es lo que
ve Brayhan desde el celular.

## Comandos habituales

```bash
# Agregar una palabra
python scripts/add_word.py "windscreen" "parabrisas (británico/australiano)"

# Regenerar el PDF
python scripts/build_pdf.py

# Regenerar la versión web
python scripts/build_html.py

# Lecturas: ver candidatos, agregar, condensar
python scripts/fetch_readings.py --discover math philosophy --max 10
python scripts/fetch_readings.py --add https://www.thoughtco.com/...-4172097
python scripts/fetch_readings.py --condense

# Podcasts (MP3 en docs/audio)
python scripts/build_podcasts.py            # lo que falte
python scripts/build_podcasts.py --dry-run  # solo guiones y estimación

# Ver cuántas entradas hay
python -c "import json;d=json.load(open('data/vocabulary.json'));print(sum(len(s['entries']) for s in d['sections']))"
```

## Estado (9 sep 2026)

- **333 palabras y 266 preguntas** según los JSON (las cifras de abajo son del 17 ago; el
  conteo vivo se hace con el comando de arriba). **14 lecturas** y **21 podcasts**.
- **331 palabras confirmadas** al 17 ago (numeración 1–331, sin bloques `pending_` abiertos).
  Secciones: A. Mis palabras (48) · B. Form 62 (72) · C. Form 50 (76) · D. Form 63 (8) ·
  E. Form 69 (12) · F. Form 70 (22) · G. Form 71 (1) · H. Form 73 (27) · I. Form 75 (12) ·
  J. Form 82 (15) · K. Form 87 (36) · L. Technical & Action Verbs (2).
- **233 preguntas** documentadas en 11 secciones:

  | Sección | Preguntas | Sección | Preguntas |
  |---|---|---|---|
  | Form 50 | 21 | Form 73 | 36 |
  | Form 62 | 30 | Form 75 | 10 |
  | Form 63 | 19 | Form 82 | 25 |
  | Form 69 | 25 | Form 87 | 36 |
  | Form 70 | 27 | Technical & Action Verbs | 2 |
  | Form 71 | 2 | | |

- No hay nada pendiente de filtrado: Brayhan aprobó los 135 candidatos (30 del Form 87 más
  105 de los formularios nuevos) y ya están numerados del 197 al 331.

### Nota sobre las capturas
Muchas capturas se tomaron **durante** el examen (no en la pantalla de repaso): muestran las
opciones pero no la respuesta correcta ni la explicación. Esas 21 preguntas quedan registradas con
la nota `(Not shown — captured during the test…)` en el campo `correct`. Si Brayhan vuelve a hacer
el formulario y captura la pantalla de repaso, se completan.

## Protocolo de trabajo (handoff + Git)

Aplica a todo el que trabaje en este repositorio, use Claude Code o no. El trabajo se
reparte entre varias máquinas y varios desarrolladores, así que la continuidad y la
coordinación son parte del trabajo, no un extra.

### Handoff

1. **Al iniciar cualquier sesión**: leer `handoff.md` COMPLETO antes de tocar código.
   Contiene el objetivo, el estado real y el punto exacto donde quedó la sesión
   anterior. Continuar desde ahí; no re-descubrir el proyecto desde cero.
2. **Si `handoff.md` todavía no existe**, crearlo en cuanto empiece trabajo real, con
   las 8 secciones de abajo, y hacerle commit + push.
3. **Antes de cerrar la sesión** (cuando el usuario se despida, diga que va a cerrar, o
   pida «actualiza el handoff»): actualizarlo con lo ocurrido manteniendo sus 8
   secciones, actualizar la fecha de «Última actualización», y hacer commit + push para
   que el otro equipo siempre lo reciba.
4. Si se termina un bloque de trabajo significativo a mitad de sesión, actualizar el
   handoff también — no esperar al cierre.

Las 8 secciones fijas de `handoff.md`:

1. El objetivo
2. El estado actual del proyecto
3. Los archivos en los que trabajas
4. Qué has cambiado
5. Qué has intentado
6. Qué ha fallado
7. Qué planeas hacer después
8. Cualquier cosa relevante

### Git y GitHub

- **Commit + push de todo cambio**, sin esperar a que el usuario lo pida cada vez.
- En **lotes grandes**: presentar primero un resumen y esperar el visto bueno del
  usuario antes del push.
- Trabajar sobre la rama que ya use el repo. No crear ramas nuevas salvo que se pida.
- **Cambios remotos: avisar y PREGUNTAR antes de hacer `pull`.** Nunca traer cambios de
  otros desarrolladores sin confirmación, porque puede pisar trabajo local en curso.
  Conviene un `git fetch` al empezar para saber si hay novedades.
- Mensajes de commit en español, explicando el porqué del cambio.
- **Nunca versionar `.env` ni credenciales**, ni ponerlas en archivos de ejemplo,
  instaladores o scripts. Revisar `.gitignore` antes del primer push.
- No reescribir historia ya publicada (`push --force`, `reset --hard` sobre lo subido)
  sin pedirlo explícitamente: hay otras personas trabajando sobre el mismo remoto.
