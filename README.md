# Vocabulario en inglés + ALCPT

Proyecto de estudio de Brayhan (nivel B2): diccionario acumulativo inglés–español y banco de
preguntas del ALCPT documentadas en profundidad.

## Instalación

```bash
pip install -r requirements.txt
```

Requiere Python 3.9 o superior.

## Uso con Claude Code

1. Abre una terminal en esta carpeta y ejecuta `claude`.
2. Claude Code leerá `CLAUDE.md` automáticamente y seguirá las reglas del proyecto.
3. Para procesar un examen nuevo: copia las capturas en `inbox/` y pídele
   *"procesa las imágenes del inbox, son del Form XX"*.
4. Para agregar palabras sueltas: solo escríbelas en el chat.
5. Para regenerar el PDF: *"regenera el PDF"* o `python scripts/build_pdf.py`.

Ventaja de trabajar aquí: Claude Code lee las imágenes desde el disco, así que no hay límite de
20 imágenes por mensaje.

## Comandos

```bash
python scripts/add_word.py "palabra" "traducción"   # agregar vocabulario
python scripts/build_pdf.py                          # generar el PDF
python scripts/build_pdf.py --out output/v2.pdf      # PDF con otro nombre
python scripts/build_html.py                         # versión web espejo del PDF
python scripts/build_artifact.py                     # cuaderno con buscador y audio
python scripts/build_artifact.py --standalone --out docs/index.html   # GitHub Pages
python bot/alcpt_bot.py                              # bot de Telegram
```

## Bot de Telegram

Mándale una palabra o una captura del examen y actualiza los JSON, regenera todo y hace push.
Funciona en cualquier equipo donde clones el repo:

```bash
pip install -r bot/requirements.txt
cp .env.example .env          # pon el token del bot
python bot/capture_id.py      # manda /start y captura tu ID
python bot/install_service.py # queda corriendo solo, arranca con el equipo
```

Detalles en [`bot/README.md`](bot/README.md).

## Audio

Las dos páginas web traen un botón de bocina en cada palabra y en cada pregunta. Usa la voz
del propio dispositivo (`speechSynthesis`), así que no consume datos ni requiere ninguna clave.
En las preguntas lee el enunciado y todas las opciones, como en la parte auditiva del examen.

## Archivos que importan

| Archivo | Qué contiene |
|---|---|
| `data/vocabulary.json` | Todas las palabras con su número y traducción |
| `data/forms.json` | Preguntas, opciones, respuestas y explicaciones |
| `data/phrasal_verbs.json` | Phrasal verbs de los formularios 50–87, agrupados por partícula |
| `CLAUDE.md` | Las reglas del flujo de trabajo |
| `output/*.pdf` | Documento consolidado, párrafos justificados |
| `output/ALCPT_Vocabulario_y_Examenes.html` | Espejo del PDF en versión web |
| `output/cuaderno_alcpt.html` | Cuaderno con buscador y audio |
| `docs/index.html` | Lo mismo, publicado en GitHub Pages |
| `bot/alcpt_bot.py` | Bot de Telegram que alimenta el diccionario |

Los tres JSON de `data/` son la única fuente de verdad: el PDF y las páginas siempre se
regeneran a partir de ellos.
