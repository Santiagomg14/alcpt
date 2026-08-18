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
│   └── idioms.json        <- idioms y léxico militar, por uso
├── scripts/
│   ├── build_pdf.py       <- genera el PDF consolidado
│   ├── build_html.py      <- versión web espejo del PDF
│   ├── build_artifact.py  <- cuaderno con buscador y audio (+ --standalone para Pages)
│   └── add_word.py        <- agrega palabras por línea de comandos
├── bot/
│   ├── alcpt_bot.py       <- bot de Telegram (portátil, sin rutas fijas)
│   └── README.md          <- cómo dejarlo corriendo en cualquier equipo
├── inbox/                 <- capturas nuevas del ALCPT (fuera del repo)
├── docs/                  <- index.html publicado en GitHub Pages
└── output/                <- PDF y páginas generadas
```

## Al cambiar los datos

Cualquier cambio en `data/*.json` obliga a regenerar los cuatro documentos:

```bash
python scripts/build_pdf.py
python scripts/build_html.py
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

# Ver cuántas entradas hay
python -c "import json;d=json.load(open('data/vocabulary.json'));print(sum(len(s['entries']) for s in d['sections']))"
```

## Estado (17 ago 2026)

- **331 palabras confirmadas** (numeración 1–331, sin bloques `pending_` abiertos).
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
