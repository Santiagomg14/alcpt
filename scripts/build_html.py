#!/usr/bin/env python3
"""
Genera la versión web (HTML autocontenido) con el mismo contenido del PDF.

Uso:
    python scripts/build_html.py
    python scripts/build_html.py --out output/mi_nombre.html

Escribe: output/ALCPT_Vocabulario_y_Examenes.html
El orden es el mismo del PDF: vocabulario completo y después ALCPT por formulario.
Los párrafos van justificados, igual que en el PDF y en Word.
"""

import argparse
import json
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

CSS = """
:root{
  --ink:#1d1a1b; --grey:#6d6469; --accent:#8c2f39; --accent-soft:#fbf1f2;
  --rule:#e6dde0; --bg:#fdfbfb; --card:#ffffff; --ok:#1f7a3d; --ok-soft:#eef7f1;
  --soft:#fbf6f7;
}
@media (prefers-color-scheme: dark){
  :root{
    --ink:#ece7e8; --grey:#a79ea3; --accent:#e08a94; --accent-soft:#2a1c1f;
    --rule:#3a3134; --bg:#161314; --card:#1e1a1c; --ok:#6cc38b; --ok-soft:#18261d;
    --soft:#221d1f;
  }
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.65 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
}
.wrap{max-width:900px; margin:0 auto; padding:0 20px 90px}

header.cover{
  text-align:center; padding:70px 20px 46px; border-bottom:1px solid var(--rule); margin-bottom:34px;
}
header.cover h1{font-size:2.5rem; line-height:1.15; color:var(--accent); margin:0 0 12px; letter-spacing:-.01em}
header.cover p.sub{color:var(--grey); font-size:1.02rem; margin:0 auto; max-width:34em}
dl.meta{
  display:grid; grid-template-columns:max-content 1fr; gap:6px 20px;
  max-width:460px; margin:30px auto 0; text-align:left; font-size:.93rem;
}
dl.meta dt{color:var(--accent); font-weight:700}
dl.meta dd{margin:0; color:var(--ink)}

nav.toc{
  position:sticky; top:0; z-index:5; background:var(--bg);
  border-bottom:1px solid var(--rule); padding:10px 0; margin-bottom:26px;
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif; font-size:.83rem;
}
nav.toc .inner{max-width:900px; margin:0 auto; padding:0 20px; display:flex; flex-wrap:wrap; gap:6px}
nav.toc a{
  color:var(--grey); text-decoration:none; padding:3px 9px; border-radius:999px;
  border:1px solid var(--rule); white-space:nowrap;
}
nav.toc a:hover{color:var(--accent); border-color:var(--accent)}

h2.part{
  font-size:1.6rem; color:var(--accent); margin:52px 0 6px; padding-bottom:8px;
  border-bottom:2px solid var(--accent);
}
h3.sect{font-size:1.18rem; margin:38px 0 10px; color:var(--ink)}
h3.sect .count{color:var(--grey); font-weight:400; font-size:.85rem; margin-left:8px}
p.lead{text-align:justify; hyphens:auto; color:var(--grey); margin:8px 0 4px}
p.note{color:var(--grey); font-size:.9rem; text-align:justify; hyphens:auto}

table.vocab{width:100%; border-collapse:collapse; margin:10px 0 6px; font-size:.95rem}
table.vocab td{border-bottom:1px solid var(--rule); padding:7px 8px; vertical-align:top; text-align:justify; hyphens:auto}
table.vocab tr:nth-child(even){background:var(--soft)}
table.vocab td.n{color:var(--accent); font-weight:700; width:3.2em; text-align:right; padding-right:12px}
table.vocab td.en{font-weight:700; width:30%}

.pending{background:var(--accent-soft); border:1px solid var(--rule); border-radius:10px; padding:4px 16px 12px}

article.q{
  background:var(--card); border:1px solid var(--rule); border-left:3px solid var(--accent);
  border-radius:8px; padding:14px 18px; margin:14px 0;
}
article.q .stem{font-weight:700; text-align:justify; hyphens:auto; margin:0 0 10px}
article.q .stem .num{color:var(--accent); margin-right:6px}
ul.opts{list-style:none; margin:0 0 10px; padding:0; font-size:.95rem}
ul.opts li{padding:3px 0 3px 20px; position:relative; text-align:justify; hyphens:auto}
ul.opts li::before{content:"–"; position:absolute; left:4px; color:var(--grey)}
ul.opts li.ok{color:var(--ok); font-weight:700; background:var(--ok-soft); border-radius:5px}
ul.opts li.ok::before{content:"✓"; color:var(--ok)}
ul.opts li.ok .tag{font-size:.72rem; letter-spacing:.06em; margin-left:8px; font-weight:700}
p.answer{font-size:.93rem; margin:0 0 10px; color:var(--ok); text-align:justify; hyphens:auto}
p.expl{font-size:.93rem; margin:0; color:var(--ink); text-align:justify; hyphens:auto}
p.expl b{color:var(--accent)}

footer{margin-top:60px; padding-top:18px; border-top:1px solid var(--rule); color:var(--grey);
  font-size:.85rem; text-align:center; font-family:system-ui,sans-serif}
@media print{
  nav.toc{display:none} body{background:#fff}
  article.q{break-inside:avoid} header.cover{page-break-after:always}
}
"""


def slug(text):
    return "".join(ch if ch.isalnum() else "-" for ch in str(text).lower()).strip("-")


def build(vocab, forms):
    out = []
    a = out.append
    total_words = sum(len(s["entries"]) for s in vocab["sections"])
    total_q = sum(len(f["questions"]) for f in forms["forms"])
    form_ids = ", ".join(str(f["form"]) for f in forms["forms"])

    a("<!doctype html><html lang='es'><head><meta charset='utf-8'>")
    a("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    a("<title>Vocabulario en inglés y exámenes ALCPT</title>")
    a(f"<style>{CSS}</style></head><body>")

    a("<header class='cover'>")
    a("<h1>Vocabulario en inglés<br>y exámenes ALCPT</h1>")
    a("<p class='sub'>Listado acumulado con traducciones al español y banco de preguntas resueltas</p>")
    a("<dl class='meta'>")
    for k, v in [
        ("Estudiante", vocab["meta"]["owner"]),
        ("Nivel de referencia", vocab["meta"]["level"]),
        ("Palabras confirmadas", str(total_words)),
        ("Formularios documentados", form_ids),
        ("Preguntas documentadas", str(total_q)),
        ("Actualizado", date.today().isoformat()),
    ]:
        a(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>")
    a("</dl></header>")

    # navegación
    a("<nav class='toc'><div class='inner'>")
    a("<a href='#vocabulario'>Vocabulario</a>")
    for s in vocab["sections"]:
        a(f"<a href='#voc-{slug(s['id'])}'>{escape(s['title'])}</a>")
    a("<a href='#alcpt'>ALCPT</a>")
    for f in forms["forms"]:
        label = str(f["form"])
        label = label if not label.isdigit() else f"Form {label}"
        a(f"<a href='#form-{slug(f['form'])}'>{escape(label)}</a>")
    a("</div></nav>")

    a("<div class='wrap'>")

    # ---- Parte I: vocabulario
    a("<h2 class='part' id='vocabulario'>Parte I · Vocabulario completo</h2>")
    a("<p class='lead'>Listado acumulado de todas las palabras y expresiones registradas hasta la fecha, "
      "con su traducción y matices de uso en español. Las secciones respetan el origen de cada término: "
      "primero las palabras aportadas directamente y después las extraídas de cada formulario del ALCPT.</p>")

    for s in vocab["sections"]:
        a(f"<h3 class='sect' id='voc-{slug(s['id'])}'>{escape(s['title'])}"
          f"<span class='count'>{len(s['entries'])} entradas</span></h3>")
        if s.get("subtitle"):
            a(f"<p class='note'>{escape(s['subtitle'])}</p>")
        a("<table class='vocab'>")
        for e in s["entries"]:
            a(f"<tr><td class='n'>{e['n']}</td><td class='en'>{escape(e['en'])}</td>"
              f"<td>{escape(e['es'])}</td></tr>")
        a("</table>")

    # cualquier bloque pending_* que siga esperando el filtrado de Brayhan
    for key in sorted(k for k in vocab if k.startswith("pending_")):
        pend = vocab[key]
        if not pend.get("candidates"):
            continue
        origen = key[len("pending_"):]
        a("<div class='pending'>")
        a(f"<h3 class='sect'>Apéndice · Candidatos pendientes de filtrado ({escape(origen)})"
          f"<span class='count'>{len(pend['candidates'])} candidatos</span></h3>")
        a(f"<p class='note'>{escape(pend['note'])}</p>")
        a("<table class='vocab'>")
        for e in pend["candidates"]:
            a(f"<tr><td class='en'>{escape(e['en'])}</td><td>{escape(e['es'])}</td></tr>")
        a("</table></div>")

    # ---- Parte II: ALCPT
    a("<h2 class='part' id='alcpt'>Parte II · Preguntas ALCPT resueltas</h2>")
    a("<p class='lead'>Each item below reproduces the question, all answer options, the correct answer and a "
      "detailed explanation. This part is written entirely in English on purpose, so that reviewing it "
      "doubles as reading practice at test level.</p>")

    for f in forms["forms"]:
        label = str(f["form"])
        label = label if not label.isdigit() else f"Form {label}"
        a(f"<h3 class='sect' id='form-{slug(f['form'])}'>{escape(label)}"
          f"<span class='count'>{len(f['questions'])} questions</span></h3>")
        for q in f["questions"]:
            a("<article class='q'>")
            num = f"{q['n']}." if q.get("n") else "—"
            a(f"<p class='stem'><span class='num'>{escape(num)}</span>{escape(q['question'])}</p>")
            a("<ul class='opts'>")
            for opt in q["options"]:
                if opt == q["correct"]:
                    a(f"<li class='ok'>{escape(opt)}<span class='tag'>CORRECT</span></li>")
                else:
                    a(f"<li>{escape(opt)}</li>")
            a("</ul>")
            if q["correct"] not in q["options"]:
                a(f"<p class='answer'><b>Correct answer.</b> {escape(q['correct'])}</p>")
            a(f"<p class='expl'><b>Explanation.</b> {escape(q['explanation'])}</p>")
            a("</article>")

    a(f"<footer>{total_words} palabras · {total_q} preguntas · generado el {date.today().isoformat()}</footer>")
    a("</div></body></html>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUTPUT / "ALCPT_Vocabulario_y_Examenes.html"))
    args = ap.parse_args()

    vocab = json.loads((DATA / "vocabulary.json").read_text(encoding="utf-8"))
    forms = json.loads((DATA / "forms.json").read_text(encoding="utf-8"))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build(vocab, forms), encoding="utf-8")
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
