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
# Donde vive docs/ publicado; el fragmento para Artifact toma los MP3 de aquí.
PAGES_URL = "https://santiagomg14.github.io/alcpt/"

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

/* ---------- phrasal verbs ---------- */
.pv{
  background:var(--surface); border:1px solid var(--rule); border-radius:11px;
  padding:14px 16px; margin:11px 0; box-shadow:var(--shadow);
}
.pv .top{display:flex; align-items:baseline; gap:9px; flex-wrap:wrap}
.pv .vb{
  font-family:Newsreader,Georgia,serif; font-weight:600; font-size:1.15rem;
  color:var(--accent-ink); letter-spacing:-.01em;
}
.pv .sep{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.62rem;
  letter-spacing:.1em; text-transform:uppercase; color:var(--muted);
  border:1px solid var(--rule); border-radius:999px; padding:2px 8px; white-space:nowrap;
}
.pv .top .say{margin-left:auto}
.pv .mean{margin:6px 0 0; font-weight:500}
.pv .trap{
  margin:8px 0 0; font-size:.9rem; color:var(--muted);
  border-left:2px solid var(--accent); padding-left:11px;
}
.pv .ex{
  margin:9px 0 0; padding:8px 11px; background:var(--raised);
  border:1px solid var(--rule-soft); border-radius:7px;
  display:flex; gap:9px; align-items:flex-start;
}
.pv .ex q{font-style:italic; flex:1}
.pv .ex q::before{content:"C"} .pv .ex q::after{content:"D"}
.pv .src{
  display:block; margin-top:4px; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.66rem; letter-spacing:.08em; text-transform:uppercase; color:var(--faint);
}
.subpart{
  font-family:Newsreader,Georgia,serif; font-weight:600; font-size:1.35rem;
  margin:30px 0 2px; letter-spacing:-.01em;
}
.sense{
  margin:0 0 4px; color:var(--muted); font-size:.93rem;
  border-left:2px solid var(--rule); padding-left:11px;
}
.keys{margin:10px 0 0; padding:0 0 0 18px; color:var(--muted); font-size:.93rem}
.keys li{margin:4px 0}

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

/* ---------- pestañas ---------- */
.tabs{
  position:sticky; top:0; z-index:30; background:var(--paper);
  display:flex; gap:2px; margin:0; padding:0; border-bottom:1px solid var(--rule);
  overflow-x:auto; scrollbar-width:none;
}
.tabs::-webkit-scrollbar{display:none}
.tab{
  flex:0 0 auto; font:inherit; font-weight:600; font-size:.95rem; color:var(--muted);
  background:transparent; border:0; border-bottom:2px solid transparent;
  padding:12px 14px 10px; margin-bottom:-1px; cursor:pointer; white-space:nowrap;
}
.tab:hover{color:var(--accent-ink)}
.tab[aria-selected="true"]{color:var(--accent-ink); border-bottom-color:var(--accent)}
.tab:focus-visible{outline:2px solid var(--accent); outline-offset:-2px; border-radius:6px}
.tab .cnt{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.68rem; font-weight:500;
  color:var(--faint); margin-left:6px; font-variant-numeric:tabular-nums;
}
.panel[hidden]{display:none}

/* ---------- lecturas ---------- */
.reading{
  background:var(--surface); border:1px solid var(--rule); border-radius:11px;
  padding:16px 18px; margin:12px 0; box-shadow:var(--shadow);
}
.reading:target{border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-wash)}
.rmeta{
  display:flex; flex-wrap:wrap; gap:4px 8px; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.66rem; letter-spacing:.08em; text-transform:uppercase; color:var(--faint);
}
.rmeta .rtopic{color:var(--accent-ink)}
.rtitle{
  font-family:Newsreader,Georgia,serif; font-weight:600; font-size:1.3rem; line-height:1.2;
  letter-spacing:-.01em; margin:6px 0; text-wrap:balance;
}
.rdesc{margin:0; color:var(--muted); font-size:.95rem}
.ractions{display:flex; flex-wrap:wrap; gap:8px; margin-top:12px}
.btn{
  display:inline-flex; align-items:center; gap:7px; font:inherit; font-size:.86rem; font-weight:600;
  color:var(--accent-ink); background:var(--accent-wash); border:1px solid transparent;
  border-radius:999px; padding:7px 14px; cursor:pointer; text-decoration:none;
}
.btn:hover{border-color:var(--accent)}
.btn:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.btn.ghost{background:transparent; border-color:var(--rule); color:var(--muted)}
.btn.ghost:hover{color:var(--accent-ink); border-color:var(--accent)}
.btn svg{width:14px; height:14px; fill:currentColor}
.rbody{margin-top:14px; border-top:1px solid var(--rule-soft); padding-top:4px}
.rbody > summary{
  list-style:none; cursor:pointer; padding:8px 0; font-weight:600; color:var(--accent-ink);
  display:flex; align-items:center; gap:8px;
}
.rbody > summary::-webkit-details-marker{display:none}
.rbody > summary::before{
  content:"›"; font-size:1.15rem; line-height:1; color:var(--faint);
  transition:transform .18s ease; display:inline-block;
}
.rbody[open] > summary::before{transform:rotate(90deg)}
.rbody > summary:focus-visible{outline:2px solid var(--accent); outline-offset:3px; border-radius:4px}
.rtext{margin-top:6px}
.rtext p{margin:0 0 12px; text-align:justify; hyphens:auto; font-size:1rem; line-height:1.68}
.rh{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.7rem; letter-spacing:.12em;
  text-transform:uppercase; color:var(--accent-ink); margin:18px 0 6px; font-weight:600;
}
.rpoints{margin:0; padding-left:20px; font-size:.95rem}
.rpoints li{margin:4px 0}
.reading .term{grid-template-columns:1fr auto}
.reading .term .idx{display:none}
.qstem{margin:0 0 8px; font-weight:600}
.quiz{list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:5px}
.quiz button{
  width:100%; text-align:left; font:inherit; font-size:.95rem; color:var(--muted);
  background:var(--raised); border:1px solid transparent; border-radius:7px;
  padding:7px 11px 7px 30px; position:relative; cursor:pointer;
}
.quiz button::before{
  content:"○"; position:absolute; left:10px; top:7px; color:var(--faint); font-size:.85rem;
}
.quiz button:hover{border-color:var(--rule)}
.quiz button:focus-visible{outline:2px solid var(--accent); outline-offset:1px}
.quiz .ok button{color:var(--ok); font-weight:600; background:var(--ok-wash); border-color:var(--ok-rule)}
.quiz .ok button::before{content:"●"; color:var(--ok)}
.quiz .bad button{color:var(--accent-ink); background:var(--accent-wash); text-decoration:line-through}
.quiz .bad button::before{content:"×"; color:var(--accent-ink)}
.quiz.done button{cursor:default}
.pending{
  font-size:.9rem; color:var(--muted); background:var(--raised); border:1px dashed var(--rule);
  border-radius:7px; padding:8px 11px; margin-top:12px;
}

/* ---------- podcasts ---------- */
.ep{
  background:var(--surface); border:1px solid var(--rule); border-radius:11px;
  padding:14px 16px; margin:11px 0; box-shadow:var(--shadow);
}
.ep:target{border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-wash)}
.ep-head{display:flex; gap:12px; align-items:flex-start}
.ep-idx{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.78rem; color:var(--accent-ink);
  font-variant-numeric:tabular-nums; padding-top:.3rem; flex:0 0 1.8rem;
}
.ep-title{
  font-family:Newsreader,Georgia,serif; font-weight:600; font-size:1.15rem; margin:0;
  letter-spacing:-.01em; line-height:1.25;
}
.ep-sub{margin:3px 0 0; color:var(--muted); font-size:.88rem}
.ep-sub .dur{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.74rem; color:var(--faint);
  font-variant-numeric:tabular-nums; white-space:nowrap;
}
.ep audio{display:block; width:100%; margin-top:12px; height:40px}
.ep-more{margin-top:10px}
.ep-more > summary{
  list-style:none; cursor:pointer; font-size:.86rem; color:var(--accent-ink); font-weight:600; padding:4px 0;
}
.ep-more > summary::-webkit-details-marker{display:none}
.ep-more > summary:focus-visible{outline:2px solid var(--accent); outline-offset:2px; border-radius:4px}
.ep-more .term{padding:7px 0}

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

  /* ---- pestañas: Cuaderno / Lecturas / Podcasts ---- */
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.tab')),
      panels = Array.prototype.slice.call(document.querySelectorAll('.panel')),
      tabbar = document.querySelector('.tabs'),
      toolbar = document.querySelector('.toolbar');

  function fitToolbar(){ if(tabbar && toolbar) toolbar.style.top = tabbar.offsetHeight + 'px'; }
  fitToolbar();
  window.addEventListener('resize', fitToolbar);

  function showTab(name, keepHash){
    if(!document.getElementById('panel-' + name)) name = 'cuaderno';
    tabs.forEach(function(t){
      var on = t.dataset.tab === name;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
    });
    panels.forEach(function(p){ p.hidden = p.id !== 'panel-' + name; });
    try{ localStorage.setItem('alcpt-tab', name); }catch(e){}
    if(!keepHash){
      try{ history.replaceState(null, '', name === 'cuaderno'
        ? location.pathname + location.search : '#' + name); }catch(e){}
    }
  }
  tabs.forEach(function(t){
    t.addEventListener('click', function(){ showTab(t.dataset.tab); window.scrollTo(0, 0); });
  });
  if(tabbar) tabbar.addEventListener('keydown', function(e){
    var i = tabs.indexOf(document.activeElement);
    if(i < 0 || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
    e.preventDefault();
    var j = (i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    tabs[j].focus(); showTab(tabs[j].dataset.tab);
  });

  function reveal(el){
    var p = el.closest('.panel');
    if(p) showTab(p.id.replace('panel-', ''), true);
    var d = el.querySelector('details.rbody');
    if(d) d.open = true;
    el.scrollIntoView({block:'start'});
  }
  function openFromHash(){
    var h = location.hash.replace('#', '');
    if(!h) return false;
    if(document.getElementById('panel-' + h)){ showTab(h, true); return true; }
    var el = document.getElementById(h);
    if(el && el.closest('.panel')){ reveal(el); return true; }
    return false;
  }
  if(!openFromHash()){
    var saved = null;
    try{ saved = localStorage.getItem('alcpt-tab'); }catch(e){}
    showTab(saved || 'cuaderno', true);
  }
  window.addEventListener('hashchange', openFromHash);

  /* ---- lecturas: filtro por tema y pregunta de comprobación ---- */
  var rchips = Array.prototype.slice.call(document.querySelectorAll('.rchip')),
      readings = Array.prototype.slice.call(document.querySelectorAll('.reading'));
  rchips.forEach(function(c){
    c.addEventListener('click', function(){
      var t = c.dataset.topic;
      rchips.forEach(function(o){ o.setAttribute('aria-pressed', String(o === c)); });
      readings.forEach(function(r){ r.classList.toggle('hidden', t !== 'all' && r.dataset.topic !== t); });
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll('.quiz'), function(q){
    q.addEventListener('click', function(e){
      var b = e.target.closest('button');
      if(!b || q.classList.contains('done')) return;
      q.classList.add('done');
      Array.prototype.forEach.call(q.querySelectorAll('li'), function(li){
        if(li.dataset.ok === '1') li.classList.add('ok');
        else if(li.contains(b)) li.classList.add('bad');
      });
    });
  });

  /* ---- podcasts: un solo audio a la vez; saltos entre lectura y episodio ---- */
  var audios = Array.prototype.slice.call(document.querySelectorAll('.ep audio'));
  audios.forEach(function(a){
    a.addEventListener('play', function(){
      audios.forEach(function(o){ if(o !== a) o.pause(); });
      if(synth){ synth.cancel(); }
      if(typeof release === 'function') release();
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-goto]'), function(b){
    b.addEventListener('click', function(){
      var el = document.getElementById(b.dataset.goto);
      if(!el) return;
      reveal(el);
      try{ history.replaceState(null, '', '#' + b.dataset.goto); }catch(e){}
      var a = el.querySelector('audio');
      if(a && b.dataset.play){ a.play().catch(function(){}); }
    });
  });

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


def mmss(seconds):
    seconds = int(round(seconds or 0))
    return f"{seconds // 60}:{seconds % 60:02d}"


PLAY_ICON = ('<svg viewBox="0 0 16 16" aria-hidden="true">'
             '<path d="M4.5 2.8v10.4a.6.6 0 0 0 .92.5l8-5.2a.6.6 0 0 0 0-1L5.42 2.3a.6.6 0 0 0-.92.5z"/></svg>')
LINK_ICON = ('<svg viewBox="0 0 16 16" aria-hidden="true">'
             '<path d="M9 2h5v5h-1.5V4.56L7.03 10.03 5.97 8.97 11.44 3.5H9V2z"/>'
             '<path d="M3 4h4v1.5H4.5v6h6V8H12v5H3V4z"/></svg>')


def build(vocab, forms, pv, idioms, readings, podcasts, audio_base):
    out = []
    a = out.append
    total_words = sum(len(s["entries"]) for s in vocab["sections"])
    total_q = sum(len(f["questions"]) for f in forms["forms"])
    total_pv = sum(len(g["entries"]) for g in pv["groups"])
    total_id = sum(len(g["entries"]) for sec in idioms["sections"] for g in sec["groups"])
    total_r = len(readings.get("items", []))
    episodes = podcasts.get("episodes", [])
    total_ep = len(episodes)
    ep_by_reading = {e["reading"]: e for e in episodes if e.get("reading")}
    words_by_n = {e["n"]: e for s in vocab["sections"] for e in s["entries"]}
    topic_title = {t["id"]: t["title"] for t in readings.get("topics", [])}

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
    for fig, cap in [(total_words, "palabras"), (total_pv, "phrasal verbs"),
                     (total_id, "idioms"), (total_q, "preguntas"),
                     (total_r, "lecturas"), (total_ep, "podcasts")]:
        a(f'<div><span class="fig">{escape(str(fig))}</span><span class="cap">{cap}</span></div>')
    a("</div></header>")

    # pestañas
    a('<nav class="tabs" role="tablist" aria-label="Secciones del cuaderno">')
    for tid, label, cnt, sel in [("cuaderno", "Cuaderno", total_words + total_q, "true"),
                                 ("lecturas", "Lecturas", total_r, "false"),
                                 ("podcasts", "Podcasts", total_ep, "false")]:
        a(f'<button class="tab" type="button" role="tab" id="tab-{tid}" data-tab="{tid}" '
          f'aria-selected="{sel}" aria-controls="panel-{tid}">{label}'
          f'<span class="cnt">{cnt}</span></button>')
    a("</nav>")

    # ===================== pestaña 1: cuaderno =====================
    a('<section class="panel" id="panel-cuaderno" role="tabpanel" aria-labelledby="tab-cuaderno">')

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
                                  ("pv", "Phrasal verbs", "false"), ("id", "Idioms", "false"),
                                  ("q", "Preguntas", "false")]:
        a(f'<button class="chip" type="button" data-scope="{scope}" aria-pressed="{pressed}">{label}</button>')
    a("</div>")
    a(f'<p class="tally"><span id="tally">{total_words} palabras · {total_pv} phrasal '
      f'verbs · {total_q} preguntas</span>'
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

    # ---- phrasal verbs e idioms comparten formato
    def entry_card(e, kind):
        """Una expresión: título, etiqueta, significado, trampa, ejemplo y origen."""
        expr = e.get("expr") or e.get("verb")
        tag = e.get("tag") or e.get("sep") or ""
        sk = key(" ".join([expr, e["es"], e["trap"], e["example"], e["source"]]))
        a(f'<article class="pv" data-s="{escape(sk, quote=True)}" data-kind="{kind}">')
        a('<div class="top">'
          f'<span class="vb">{escape(expr)}</span>'
          + (f'<span class="sep">{escape(tag)}</span>' if tag else "")
          + say_button(expr, f"Escuchar {expr}") + '</div>')
        a(f'<p class="mean">{escape(e["es"])}</p>')
        a(f'<p class="trap">{escape(e["trap"])}</p>')
        a('<div class="ex">'
          f'<q>{escape(e["example"])}</q>'
          + say_button(e["example"], f"Escuchar el ejemplo de {expr}") + '</div>')
        a(f'<span class="src">{escape(e["source"])}</span>')
        a("</article>")

    def group_block(g, kind, part, label):
        titulo = g.get("particle") or g.get("theme")
        a(f'<details class="group" data-kind="{kind}" data-part-of="{part}">')
        a(f'<summary><h2>{escape(titulo)}</h2>'
          f'<span class="n">{len(g["entries"])} {label}</span></summary>')
        a(f'<p class="sense">{escape(g["sense"])}</p>')
        for e in g["entries"]:
            entry_card(e, kind)
        a("</details>")

    def keys_list(meta):
        a('<ul class="keys">')
        for k in meta["keys"]:
            a(f"<li>{escape(k)}</li>")
        a("</ul>")

    # ---- phrasal verbs
    a('<p class="part" data-part="pv">Parte II · Phrasal verbs</p>')
    a(f'<p class="part-note">{escape(pv["meta"]["intro"])}</p>')
    keys_list(pv["meta"])
    for g in pv["groups"]:
        group_block(g, "pv", "pv", "phrasal verbs")

    # ---- idioms y léxico militar
    a('<p class="part" data-part="id">Parte III · Idioms y expresiones militares</p>')
    a(f'<p class="part-note">{escape(idioms["meta"]["intro"])}</p>')
    keys_list(idioms["meta"])
    for sec in idioms["sections"]:
        a(f'<h3 class="subpart">{escape(sec["title"])}</h3>')
        a(f'<p class="sense">{escape(sec["note"])}</p>')
        for g in sec["groups"]:
            group_block(g, "id", "id", "expresiones")

    # ---- preguntas
    a('<p class="part" data-part="q">Parte IV · Preguntas resueltas</p>')
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
    a("</section>")

    # ===================== pestaña 2: lecturas =====================
    a('<section class="panel" id="panel-lecturas" role="tabpanel" aria-labelledby="tab-lecturas" hidden>')
    a('<p class="part">Lecturas · ThoughtCo</p>')
    a(f'<p class="part-note">{escape(readings.get("meta", {}).get("intro", ""))} '
      "Son temas ajenos a la rutina militar a propósito: el examen mezcla registros, y leer "
      "fuera de lo conocido es lo que hace crecer el vocabulario.</p>")
    items = readings.get("items", [])
    if items:
        counts = {}
        for it in items:
            counts[it.get("topic")] = counts.get(it.get("topic"), 0) + 1
        a('<div class="filters" role="group" aria-label="Filtrar lecturas por tema" style="margin-top:14px">')
        a(f'<button class="chip rchip" type="button" data-topic="all" aria-pressed="true">Todas · {len(items)}</button>')
        for t in readings.get("topics", []):
            if counts.get(t["id"]):
                a(f'<button class="chip rchip" type="button" data-topic="{t["id"]}" aria-pressed="false">'
                  f'{escape(t["title"])} · {counts[t["id"]]}</button>')
        a("</div>")
    else:
        a('<p class="pending">Todavía no hay lecturas. Se agregan con '
          "<code>scripts/fetch_readings.py</code> o mandándole al bot un enlace de ThoughtCo.</p>")

    for it in items:
        rid = f'lectura-{it["id"]}'
        ep = ep_by_reading.get(it["id"])
        crumbs = [c for c in it.get("path", []) if c not in ("Science, Tech, Math", "Humanities")]
        a(f'<article class="reading" id="{rid}" data-topic="{escape(it.get("topic") or "")}">')
        a('<div class="rmeta">'
          f'<span class="rtopic">{escape(topic_title.get(it.get("topic"), it.get("topic") or ""))}</span>'
          + "".join(f"<span>· {escape(c)}</span>" for c in crumbs[:2])
          + (f'<span>· {it["summary_words"]} words · ~{max(1, round(it["summary_words"] / 130))} min</span>'
             if it.get("summary") else "")
          + "</div>")
        a(f'<h3 class="rtitle">{escape(it["title"])}</h3>')
        if it.get("description"):
            a(f'<p class="rdesc">{escape(it["description"])}</p>')
        a('<div class="ractions">')
        if ep and ep.get("seconds"):
            a(f'<button class="btn" type="button" data-goto="ep-{ep["id"]}" data-play="1">'
              f'{PLAY_ICON}Escuchar · {mmss(ep["seconds"])}</button>')
        a(f'<a class="btn ghost" href="{escape(it["url"], quote=True)}" target="_blank" '
          f'rel="noopener noreferrer">{LINK_ICON}Artículo original</a>')
        a("</div>")

        if not it.get("summary"):
            a('<p class="pending">Pendiente de condensar: corre '
              "<code>python scripts/fetch_readings.py --condense</code>.</p>")
            a("</article>")
            continue

        a('<details class="rbody"><summary>Leer el resumen</summary>')
        a('<div class="rtext">')
        for p in it["summary"]:
            a(f"<p>{escape(p)}</p>")
        a("</div>")
        if it.get("key_points"):
            a('<p class="rh">Key points</p><ul class="rpoints">')
            for k in it["key_points"]:
                a(f"<li>{escape(k)}</li>")
            a("</ul>")
        if it.get("glossary"):
            a('<p class="rh">Glosario</p><div class="terms">')
            for g in it["glossary"]:
                a('<div class="term">'
                  f'<span class="en">{escape(g["en"])}</span>'
                  f'<span class="es">{escape(g["es"])}</span>'
                  + say_button(g["en"], f'Escuchar {g["en"]}') + "</div>")
            a("</div>")
        q = it.get("question")
        if q:
            a('<p class="rh">Comprehension check</p>')
            a(f'<p class="qstem">{escape(q["stem"])}</p>')
            a('<ul class="quiz">')
            for opt in q["options"]:
                ok = ' data-ok="1"' if opt == q["answer"] else ""
                a(f'<li{ok}><button type="button">{escape(opt)}</button></li>')
            a("</ul>")
        a("</details></article>")
    a("</section>")

    # ===================== pestaña 3: podcasts =====================
    a('<section class="panel" id="panel-podcasts" role="tabpanel" aria-labelledby="tab-podcasts" hidden>')
    a('<p class="part">Podcasts</p>')
    a(f'<p class="part-note">{escape(podcasts.get("meta", {}).get("intro", ""))}</p>')
    if not episodes:
        a('<p class="pending">Todavía no hay episodios. Se generan con '
          "<code>python scripts/build_podcasts.py</code>.</p>")
    for serie in podcasts.get("series", []):
        eps = [e for e in episodes if e["series"] == serie["id"]]
        if not eps:
            continue
        total_s = sum(e.get("seconds") or 0 for e in eps)
        a(f'<h3 class="subpart">{escape(serie["title"])}</h3>')
        a(f'<p class="sense">{escape(serie["note"])} '
          f'{len(eps)} episodio{"s" if len(eps) != 1 else ""} · {mmss(total_s)} en total.</p>')
        for i, e in enumerate(eps, 1):
            a(f'<article class="ep" id="ep-{e["id"]}">')
            a('<div class="ep-head">'
              f'<span class="ep-idx">{i:02d}</span><div>'
              f'<h4 class="ep-title">{escape(e["title"])}</h4>'
              f'<p class="ep-sub">{escape(e.get("subtitle") or "")}'
              + (f' · {e["count"]} palabras' if e.get("count") else "")
              + (f' · <span class="dur">{mmss(e["seconds"])}</span>' if e.get("seconds") else "")
              + "</p></div></div>")
            if e.get("seconds"):
                a(f'<audio controls preload="none" src="{escape(audio_base + e["id"] + ".mp3", quote=True)}">'
                  "Tu navegador no reproduce audio MP3.</audio>")
            else:
                a('<p class="pending">Audio pendiente de generar.</p>')
            if e["series"] == "vocab" and e.get("words"):
                first, last = e["words"]
                a('<details class="ep-more"><summary>Palabras del episodio</summary><div class="terms">')
                for n in range(first, last + 1):
                    w = words_by_n.get(n)
                    if not w:
                        continue
                    a('<div class="term">'
                      f'<span class="idx">{n}</span>'
                      f'<span class="en">{escape(w["en"])}</span>'
                      f'<span class="es">{escape(w["es"])}</span>'
                      + say_button(w["en"], f'Escuchar {w["en"]}') + "</div>")
                a("</div></details>")
            elif e.get("reading"):
                a('<div class="ractions">'
                  f'<button class="btn ghost" type="button" data-goto="lectura-{e["reading"]}">'
                  "Leer el resumen y el glosario</button></div>")
            a("</article>")
    a("</section>")

    a(f'<footer><span>Brayhan · nivel B2</span>'
      f'<span>{total_words} palabras · {total_pv} phrasal verbs · '
      f'{total_id} idioms · {total_q} preguntas · {total_r} lecturas · {total_ep} podcasts</span></footer>')
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
    ap.add_argument("--audio-base", default=None,
                    help="prefijo de las URLs de los MP3 (por defecto: 'audio/' en la versión "
                         "standalone, y la URL de GitHub Pages en el fragmento)")
    args = ap.parse_args()

    def load(name, default):
        p = DATA / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

    vocab = load("vocabulary.json", None)
    forms = load("forms.json", None)
    pv = load("phrasal_verbs.json", None)
    idioms = load("idioms.json", None)
    readings = load("readings.json", {"meta": {}, "topics": [], "items": []})
    podcasts = load("podcasts.json", {"meta": {}, "series": [], "episodes": []})

    audio_base = args.audio_base
    if audio_base is None:
        audio_base = "audio/" if args.standalone else PAGES_URL + "audio/"

    html = build(vocab, forms, pv, idioms, readings, podcasts, audio_base)
    if args.standalone:
        html = wrap_standalone(html)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    main()
