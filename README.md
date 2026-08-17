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
python scripts/build_html.py                         # generar la versión web
```

## Archivos que importan

| Archivo | Qué contiene |
|---|---|
| `data/vocabulary.json` | Todas las palabras con su número y traducción |
| `data/forms.json` | Preguntas, opciones, respuestas y explicaciones |
| `CLAUDE.md` | Las reglas del flujo de trabajo |
| `output/*.pdf` | Documento consolidado, párrafos justificados |
| `output/*.html` | Misma información en versión web (se abre en el navegador) |

Los dos JSON son la única fuente de verdad: el PDF siempre se regenera a partir de ellos.
