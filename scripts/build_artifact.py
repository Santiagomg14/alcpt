#!/usr/bin/env python3
"""
Genera la versión consultable desde el celular (Artifact / página web con buscador).

A diferencia de build_html.py, que reproduce el PDF tal cual, esta versión es una
herramienta de consulta: buscador en vivo sobre el vocabulario y las preguntas.

Uso:
    python scripts/build_artifact.py
Escribe: output/cuaderno_alcpt.html
"""

import argparse
import json
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

FONTS = ("https://fonts.googleapis.com/css2?"
         "family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600"
         "&family=Public+Sans:wght@400;500;600;700"
         "&family=IBM+Plex+Mono:wght@400;500;600&display=swap")

CSS = """
:root{
  --paper:#faf7f7; --surface:#ffffff; --raised:#fffdfd;
  --ink:#1f1a1b; --muted:#6e6165; --faint:#9b8d91;
  --rule:#e7dcde; --rule-soft:#f1e9ea;
  --accent:#8c2f39; --accent-ink:#8c2f39; --accent-wash:#fbf1f2;
  --ok:#1f7a3d; --ok-wash:#eef7f1; --ok-rule:#cfe6d8;
  --on-accent:#ffffff;
  --shadow:0 1px 2px rgba(31,26,27,.05), 0 8px 24px -16px rgba(31,26,27,.28);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#171315; --surface:#201a1c; --raised:#251e21;
    --ink:#ede6e7; --muted:#a8999d; --faint:#7e7075;
    --rule:#3a3134; --rule-soft:#2c2427;
    --accent:#e08a94; --accent-ink:#efb3ba; --accent-wash:#2c1c1f;
    --ok:#6cc38b; --ok-wash:#17261c; --ok-rule:#2d4a38;
    --on-accent:#201a1c;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -16px rgba(0,0,0,.7);
  }
}
:root[data-theme="dark"]{
  --paper:#171315; --surface:#201a1c; --raised:#251e21;
  --ink:#ede6e7; --muted:#a8999d; --faint:#7e7075;
  --rule:#3a3134; --rule-soft:#2c2427;
  --accent:#e08a94; --accent-ink:#efb3ba; --accent-wash:#2c1c1f;
  --ok:#6cc38b; --ok-wash:#17261c; --ok-rule:#2d4a38;
  --on-accent:#201a1c;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -16px rgba(0,0,0,.7);
}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:16px; line-height:1.6;
}
.shell{max-width:860px; margin:0 auto; padding:0 18px 96px}

/* ---------- cabecera ---------- */
.masthead{padding:52px 0 26px; border-bottom:1px solid var(--rule)}
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.7rem;
  letter-spacing:.16em; text-transform:uppercase; color:var(--accent-ink); margin:0 0 12px;
}
h1{
  font-family:Newsreader,Georgia,"Times New Roman",serif; font-weight:500;
  font-size:clamp(2rem,6vw,2.9rem); line-height:1.08; letter-spacing:-.015em;
  margin:0 0 14px; text-wrap:balance;
}
.standfirst{margin:0; color:var(--muted); max-width:52ch; font-size:1.02rem}
.stats{
  display:flex; flex-wrap:wrap; gap:10px 30px; margin:24px 0 0; padding:0; list-style:none;
}
.stats div{display:flex; flex-direction:column; gap:2px}
.stats .fig{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-weight:600;
  font-size:1.28rem; font-variant-numeric:tabular-nums; color:var(--ink);
}
.stats .cap{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.66rem;
  letter-spacing:.13em; text-transform:uppercase; color:var(--faint);
}

/* ---------- barra de búsqueda ---------- */
.toolbar{
  position:sticky; top:0; z-index:20; background:var(--paper);
  padding:12px 0 10px; border-bottom:1px solid var(--rule);
  margin-bottom:8px;
}
.field{position:relative; display:block}
.field svg{
  position:absolute; left:13px; top:50%; transform:translateY(-50%);
  width:17px; height:17px; stroke:var(--faint); fill:none; stroke-width:2; pointer-events:none;
}
#q{
  width:100%; padding:11px 40px 11px 39px; font:inherit; font-size:1rem;
  color:var(--ink); background:var(--surface);
  border:1px solid var(--rule); border-radius:9px; outline:none;
}
#q::placeholder{color:var(--faint)}
#q:focus-visible{border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-wash)}
#clear{
  position:absolute; right:7px; top:50%; transform:translateY(-50%);
  border:0; background:transparent; color:var(--faint); cursor:pointer;
  font-size:1.35rem; line-height:1; padding:4px 8px; border-radius:6px; display:none;
}
#clear:hover{color:var(--accent)}
#clear:focus-visible{outline:2px solid var(--accent); outline-offset:1px}
.filters{display:flex; gap:7px; margin-top:10px; overflow-x:auto; scrollbar-width:none; padding-bottom:2px}
.filters::-webkit-scrollbar{display:none}
.chip{
  flex:0 0 auto; font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.72rem;
  letter-spacing:.06em; text-transform:uppercase; color:var(--muted);
  background:var(--surface); border:1px solid var(--rule); border-radius:999px;
  padding:5px 12px; cursor:pointer;
}
.chip:hover{border-color:var(--accent); color:var(--accent-ink)}
.chip:focus-visible{outline:2px solid var(--accent); outline-offset:1px}
.chip[aria-pressed="true"]{
  background:var(--accent); border-color:var(--accent); color:var(--on-accent);
}
.tally{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.72rem;
  color:var(--faint); margin-top:9px; font-variant-numeric:tabular-nums;
  display:flex; justify-content:space-between; align-items:center; gap:12px;
}
.tally button{
  border:0; background:transparent; color:var(--accent-ink); cursor:pointer;
  font:inherit; text-decoration:underline; text-underline-offset:3px; padding:2px 0;
}
.tally button:focus-visible{outline:2px solid var(--accent); outline-offset:2px}

/* ---------- secciones ---------- */
.part{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.7rem;
  letter-spacing:.16em; text-transform:uppercase; color:var(--accent-ink);
  margin:44px 0 4px; padding-top:22px; border-top:2px solid var(--accent);
}
.part-note{color:var(--muted); margin:0 0 6px; font-size:.94rem; max-width:60ch}
.group{margin-top:26px}
.group > summary{
  list-style:none; cursor:pointer; display:flex; align-items:baseline; gap:10px;
  padding:9px 0; border-bottom:1px solid var(--rule);
}
.group > summary::-webkit-details-marker{display:none}
.group > summary::before{
  content:"›"; font-size:1.15rem; line-height:1; color:var(--faint);
  transition:transform .18s ease; display:inline-block;
}
.group[open] > summary::before{transform:rotate(90deg)}
.group > summary:focus-visible{outline:2px solid var(--accent); outline-offset:3px; border-radius:4px}
.group h2{
  font-family:Newsreader,Georgia,serif; font-weight:600; font-size:1.24rem;
  margin:0; flex:1; letter-spacing:-.01em;
}
.group .n{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.72rem;
  color:var(--faint); font-variant-numeric:tabular-nums; white-space:nowrap;
}

/* ---------- botón de audio ---------- */
.say{
  flex:0 0 auto; width:30px; height:30px; padding:0; cursor:pointer;
  display:inline-flex; align-items:center; justify-content:center;
  background:var(--surface); border:1px solid var(--rule); border-radius:8px;
  color:var(--muted); transition:color .15s ease, border-color .15s ease;
}
.say svg{width:15px; height:15px; fill:currentColor; pointer-events:none}
.say .stop{display:none}
.say:hover{color:var(--accent-ink); border-color:var(--accent)}
.say:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.say[aria-pressed="true"]{color:var(--accent-ink); border-color:var(--accent); background:var(--accent-wash)}
.say[aria-pressed="true"] .play{display:none}
.say[aria-pressed="true"] .stop{display:block}
.say[hidden]{display:none}

/* ---------- vocabulario ---------- */
.terms{margin:0; padding:2px 0 0}
.term{
  display:grid; grid-template-columns:3.1rem 1fr auto; gap:2px 14px;
  padding:11px 0; border-bottom:1px solid var(--rule-soft); align-items:start;
}
.term .idx{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.78rem;
  color:var(--faint); font-variant-numeric:tabular-nums; text-align:right;
  padding-top:.22rem; grid-row:1 / span 2;
}
.term .en{font-weight:700; color:var(--ink)}
.term .es{color:var(--muted); font-size:.95rem}
.term .say{grid-column:3; grid-row:1 / span 2; align-self:center}

/* ---------- preguntas ---------- */
.card{
  background:var(--surface); border:1px solid var(--rule); border-radius:11px;
  padding:15px 17px; margin:12px 0; box-shadow:var(--shadow);
}
.card .stem{margin:0 0 11px; font-weight:600; display:flex; gap:10px; align-items:flex-start}
.card .stem .say{margin-left:auto; margin-top:-2px}
.card .stem .idx{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.76rem;
  color:var(--accent-ink); font-variant-numeric:tabular-nums; flex:0 0 auto;
}
.opts{list-style:none; margin:0 0 11px; padding:0; display:flex; flex-direction:column; gap:4px}
.opts li{
  padding:6px 11px 6px 30px; position:relative; border-radius:7px;
  font-size:.95rem; color:var(--muted); background:var(--raised);
  border:1px solid transparent;
}
.opts li::before{
  content:"○"; position:absolute; left:10px; top:6px; color:var(--faint); font-size:.85rem;
}
.opts li.ok{
  color:var(--ok); font-weight:600; background:var(--ok-wash); border-color:var(--ok-rule);
}
.opts li.ok::before{content:"●"; color:var(--ok)}
.answer{
  margin:0 0 11px; font-size:.9rem; color:var(--ok);
  background:var(--ok-wash); border:1px dashed var(--ok-rule);
  border-radius:7px; padding:7px 11px;
}
.expl{margin:0; font-size:.92rem; color:var(--ink); text-align:justify; hyphens:auto}
.expl b{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.7rem;
  letter-spacing:.12em; text-transform:uppercase; color:var(--accent-ink);
  display:block; margin-bottom:3px; font-weight:600;
}

.empty{
  display:none; text-align:center; color:var(--muted); padding:56px 20px;
  border:1px dashed var(--rule); border-radius:12px; margin-top:26px;
}
.empty strong{display:block; font-family:Newsreader,Georgia,serif; font-size:1.2rem; color:var(--ink); margin-bottom:5px}
mark{background:var(--accent-wash); color:var(--accent-ink); border-radius:3px; padding:0 1px}

footer{
  margin-top:52px; padding-top:18px; border-top:1px solid var(--rule);
  color:var(--faint); font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.7rem;
  letter-spacing:.06em; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;
}
.hidden{display:none !important}
@media (prefers-reduced-motion: reduce){*{transition:none !important; animation:none !important}}
@media (max-width:560px){
  .masthead{padding-top:34px}
  .term{grid-template-columns:2.5rem 1fr; gap:2px 10px}
  .stats{gap:10px 22px}
}
"""

JS = """
(function(){
  var q = document.getElementById('q'),
      clear = document.getElementById('clear'),
      empty = document.getElementById('empty'),
      tally = document.getElementById('tally'),
      chips = Array.prototype.slice.call(document.querySelectorAll('.chip')),
      items = Array.prototype.slice.call(document.querySelectorAll('[data-s]')),
      groups = Array.prototype.slice.call(document.querySelectorAll('.group')),
      parts = Array.prototype.slice.call(document.querySelectorAll('[data-part]')),
      scope = 'all',
      TOTAL_LABEL = tally.textContent;

  function norm(s){
    return s.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
  }

  function apply(){
    var term = norm(q.value.trim()), shown = 0;
    clear.style.display = q.value ? 'block' : 'none';

    items.forEach(function(el){
      var okScope = scope === 'all' || el.dataset.kind === scope;
      var okTerm  = !term || el.dataset.s.indexOf(term) !== -1;
      var show = okScope && okTerm;
      el.classList.toggle('hidden', !show);
      if(show) shown++;
    });

    groups.forEach(function(g){
      var live = g.querySelectorAll('[data-s]:not(.hidden)').length;
      g.classList.toggle('hidden', live === 0);
      g.querySelector('.n').textContent = live + (g.dataset.kind === 'voc' ? ' palabras' : ' preguntas');
      if(term && live > 0) g.open = true;
    });

    parts.forEach(function(p){
      var live = p.parentNode.querySelectorAll('.group[data-part-of="'+p.dataset.part+'"]:not(.hidden)').length;
      p.classList.toggle('hidden', live === 0);
    });

    empty.style.display = shown === 0 ? 'block' : 'none';
    tally.textContent = term || scope !== 'all'
      ? shown + ' resultado' + (shown === 1 ? '' : 's')
      : TOTAL_LABEL;
  }

  q.addEventListener('input', apply);
  clear.addEventListener('click', function(){ q.value=''; q.focus(); apply(); });
  q.addEventListener('keydown', function(e){ if(e.key === 'Escape'){ q.value=''; apply(); } });

  chips.forEach(function(c){
    c.addEventListener('click', function(){
      scope = c.dataset.scope;
      chips.forEach(function(o){ o.setAttribute('aria-pressed', String(o === c)); });
      apply();
    });
  });


  /* ---- voz: lee en inglés con la voz del propio dispositivo ---- */
  var synth = window.speechSynthesis,
      says = Array.prototype.slice.call(document.querySelectorAll('.say')),
      voice = null, active = null;

  if(!synth || typeof SpeechSynthesisUtterance === 'undefined'){
    says.forEach(function(b){ b.hidden = true; });
  } else {
    var pickVoice = function(){
      var vs = synth.getVoices().filter(function(v){ return /^en(-|_|$)/i.test(v.lang); });
      if(!vs.length) return;
      voice = vs.filter(function(v){ return /^en-US/i.test(v.lang); })[0] || vs[0];
    };
    pickVoice();
    if(typeof synth.onvoiceschanged !== 'undefined') synth.onvoiceschanged = pickVoice;

    var release = function(){
      if(active){ active.setAttribute('aria-pressed','false'); active = null; }
    };

    says.forEach(function(btn){
      btn.addEventListener('click', function(){
        var wasActive = active === btn;
        synth.cancel();
        release();
        if(wasActive) return;

        var u = new SpeechSynthesisUtterance(btn.dataset.say);
        u.lang = voice ? voice.lang : 'en-US';
        if(voice) u.voice = voice;
        u.rate = 0.95;
        u.onend = release;
        u.onerror = release;
        active = btn;
        btn.setAttribute('aria-pressed','true');
        synth.speak(u);
      });
    });

    window.addEventListener('pagehide', function(){ synth.cancel(); release(); });
    document.addEventListener('visibilitychange', function(){
      if(document.hidden){ synth.cancel(); release(); }
    });
  }

  document.getElementById('expand').addEventListener('click', function(){
    var anyClosed = groups.some(function(g){ return !g.open; });
    groups.forEach(function(g){ g.open = anyClosed; });
    this.textContent = anyClosed ? 'Contraer todo' : 'Expandir todo';
  });
})();
"""


SPRITE = (
    '<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
    '<symbol id="ic-play" viewBox="0 0 16 16">'
    '<path d="M7.4 2.6 4.3 5.3H2a.8.8 0 0 0-.8.8v3.8a.8.8 0 0 0 .8.8h2.3l3.1 2.7'
    'a.6.6 0 0 0 1-.45V3.05a.6.6 0 0 0-1-.45z"/>'
    '<path d="M10.3 5.7a3.2 3.2 0 0 1 0 4.6" fill="none" stroke="currentColor" '
    'stroke-width="1.3" stroke-linecap="round"/>'
    '<path d="M12.3 3.9a6 6 0 0 1 0 8.2" fill="none" stroke="currentColor" '
    'stroke-width="1.3" stroke-linecap="round"/></symbol>'
    '<symbol id="ic-stop" viewBox="0 0 16 16">'
    '<rect x="3.5" y="3.5" width="9" height="9" rx="1.6"/></symbol></svg>'
)

SPEAKER = ('<svg class="play"><use href="#ic-play"/></svg>'
           '<svg class="stop"><use href="#ic-stop"/></svg>')


def say_button(text, label):
    """Botón que reproduce `text` en inglés con la voz del navegador."""
    return (f'<button class="say" type="button" aria-pressed="false" '
            f'data-say="{escape(text, quote=True)}" '
            f'aria-label="{escape(label, quote=True)}">{SPEAKER}</button>')


def key(text):
    """Texto normalizado para la búsqueda (sin tildes, en minúscula)."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(text).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def build(vocab, forms):
    out = []
    a = out.append
    total_words = sum(len(s["entries"]) for s in vocab["sections"])
    total_q = sum(len(f["questions"]) for f in forms["forms"])

    a("<title>Cuaderno ALCPT</title>")
    a(f'<link rel="stylesheet" href="{FONTS}">')
    a(f"<style>{CSS}</style>")
    a(SPRITE)
    a('<div class="shell">')

    # cabecera
    a('<header class="masthead">')
    a('<p class="eyebrow">Inglés militar · Nivel B2</p>')
    a("<h1>Cuaderno ALCPT</h1>")
    a('<p class="standfirst">Diccionario acumulado y banco de preguntas resueltas del American '
      "Language Course Placement Test. Busca una palabra, un idiom o el enunciado de cualquier ítem.</p>")
    a('<div class="stats">')
    for fig, cap in [(total_words, "palabras"), (total_q, "preguntas"),
                     (len(forms["forms"]), "formularios"), (date.today().isoformat(), "actualizado")]:
        a(f'<div><span class="fig">{escape(str(fig))}</span><span class="cap">{cap}</span></div>')
    a("</div></header>")

    # buscador
    a('<div class="toolbar">')
    a('<label class="field" for="q">')
    a('<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/>'
      '<path d="M20 20l-3.5-3.5"/></svg>')
    a('<input id="q" type="search" autocomplete="off" spellcheck="false" '
      'placeholder="Buscar palabra, traducción, pregunta o explicación…">')
    a('<button id="clear" type="button" aria-label="Borrar búsqueda">&times;</button>')
    a("</label>")
    a('<div class="filters" role="group" aria-label="Filtrar por tipo">')
    for scope, label, pressed in [("all", "Todo", "true"), ("voc", "Vocabulario", "false"),
                                  ("q", "Preguntas", "false")]:
        a(f'<button class="chip" type="button" data-scope="{scope}" aria-pressed="{pressed}">{label}</button>')
    a("</div>")
    a(f'<p class="tally"><span id="tally">{total_words} palabras · {total_q} preguntas</span>'
      '<button id="expand" type="button">Contraer todo</button></p>')
    a("</div>")

    # ---- vocabulario
    a('<p class="part" data-part="voc">Parte I · Vocabulario</p>')
    a('<p class="part-note">Todas las entradas registradas hasta la fecha con su traducción y matices '
      "de uso. La numeración es acumulativa: se conserva aunque se agreguen formularios nuevos.</p>")
    for s in vocab["sections"]:
        a(f'<details class="group" data-kind="voc" data-part-of="voc" open>')
        a(f'<summary><h2>{escape(s["title"])}</h2>'
          f'<span class="n">{len(s["entries"])} palabras</span></summary>')
        a('<div class="terms">')
        for e in s["entries"]:
            sk = key(f'{e["en"]} {e["es"]}')
            a(f'<div class="term" data-s="{escape(sk, quote=True)}" data-kind="voc">'
              f'<span class="idx">{e["n"]}</span>'
              f'<span class="en">{escape(e["en"])}</span>'
              f'<span class="es">{escape(e["es"])}</span>'
              + say_button(e["en"], f'Escuchar {e["en"]}') + '</div>')
        a("</div></details>")

    for pkey in sorted(k for k in vocab if k.startswith("pending_")):
        pend = vocab[pkey]
        if not pend.get("candidates"):
            continue
        a('<details class="group" data-kind="voc" data-part-of="voc">')
        a(f'<summary><h2>Pendientes · {escape(pkey[len("pending_"):])}</h2>'
          f'<span class="n">{len(pend["candidates"])} palabras</span></summary>')
        a('<div class="terms">')
        for e in pend["candidates"]:
            sk = key(f'{e["en"]} {e["es"]}')
            a(f'<div class="term" data-s="{escape(sk, quote=True)}" data-kind="voc">'
              f'<span class="idx">—</span>'
              f'<span class="en">{escape(e["en"])}</span>'
              f'<span class="es">{escape(e["es"])}</span>'
              + say_button(e["en"], f'Escuchar {e["en"]}') + '</div>')
        a("</div></details>")

    # ---- preguntas
    a('<p class="part" data-part="q">Parte II · Preguntas resueltas</p>')
    a('<p class="part-note">Cada ítem reproduce el enunciado, todas las opciones, la respuesta correcta '
      "y la explicación. Esta parte va íntegramente en inglés a propósito: repasarla es también "
      "práctica de lectura al nivel del examen.</p>")
    for f in forms["forms"]:
        label = str(f["form"])
        label = label if not label.isdigit() else f"Form {label}"
        a('<details class="group" data-kind="q" data-part-of="q">')
        a(f'<summary><h2>{escape(label)}</h2>'
          f'<span class="n">{len(f["questions"])} preguntas</span></summary>')
        for qq in f["questions"]:
            sk = key(" ".join([qq["question"], " ".join(qq["options"]),
                               qq["correct"], qq["explanation"], label]))
            a(f'<article class="card" data-s="{escape(sk, quote=True)}" data-kind="q">')
            num = f'{qq["n"]}.' if qq.get("n") else "—"
            speech = qq["question"] + ". Options: " + "; ".join(qq["options"]) + "."
            a(f'<p class="stem"><span class="idx">{escape(num)}</span>'
              f'<span>{escape(qq["question"])}</span>'
              + say_button(speech, f'Escuchar la pregunta {num}') + '</p>')
            a('<ul class="opts">')
            for opt in qq["options"]:
                cls = ' class="ok"' if opt == qq["correct"] else ""
                a(f"<li{cls}>{escape(opt)}</li>")
            a("</ul>")
            if qq["correct"] not in qq["options"]:
                a(f'<p class="answer">{escape(qq["correct"])}</p>')
            a(f'<p class="expl"><b>Explanation</b>{escape(qq["explanation"])}</p>')
            a("</article>")
        a("</details>")

    a('<div class="empty" id="empty"><strong>Sin coincidencias</strong>'
      "Prueba con otra palabra, o revisa el filtro de arriba.</div>")
    a(f'<footer><span>Brayhan · nivel B2</span><span>{total_words} palabras · {total_q} preguntas</span></footer>')
    a("</div>")
    a(f"<script>{JS}</script>")
    return "\n".join(out)


SHELL = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="description" content="Diccionario acumulado y banco de preguntas resueltas del ALCPT.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><text y='14' font-size='14'>%F0%9F%93%96</text></svg>">
{head}
</head><body>
{body}
</body></html>
"""


def wrap_standalone(fragment):
    """Envuelve el fragmento del artifact en un documento HTML completo (GitHub Pages).

    El fragmento empieza con <title>, <link> y <style>; todo eso va al <head> y el
    resto al <body>. Se corta en el cierre de <style> porque el CSS lleva saltos de
    linea propios y no se puede partir por lineas.
    """
    cut = fragment.index("</style>") + len("</style>")
    return SHELL.format(head=fragment[:cut].strip(), body=fragment[cut:].strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUTPUT / "cuaderno_alcpt.html"))
    ap.add_argument("--standalone", action="store_true",
                    help="documento HTML completo (para GitHub Pages) en vez de fragmento")
    args = ap.parse_args()

    vocab = json.loads((DATA / "vocabulary.json").read_text(encoding="utf-8"))
    forms = json.loads((DATA / "forms.json").read_text(encoding="utf-8"))

    html = build(vocab, forms)
    if args.standalone:
        html = wrap_standalone(html)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
