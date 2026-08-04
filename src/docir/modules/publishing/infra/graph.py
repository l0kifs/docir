"""The graph page — the corpus drawn as a constellation map, one ring per type.

Shneiderman's mantra, applied literally: overview first, zoom and filter, then
details on demand. Every document is on screen at once, but never as a physics
hairball — nodes sit in per-type rings at **deterministic** positions, so the
same corpus always draws the same map, which is what makes it something two
people can point at in a review. A force simulation redraws differently every
load; nobody can learn a picture that will not hold still.

The page is an application, not a document: full-viewport SVG, pan/zoom, a
pinned detail card. It shares the site's colour tokens (``theme.CSS_TOKENS``)
so it reads as the same site as the index and the pages — only the type/kind
palettes below are its own, because the map is where colour carries category.

Several details in the script are the survivors of real defects found in a
browser; their comments travel with them. The load-bearing ones: filtered-out
nodes are unreachable as well as invisible; emphasis never overrides a filter;
edge trims retreat past the selection halo only while it is shown; a click
never focuses a node (browsers disagree on whether click-focus draws a ring);
and unknown types/kinds get spare hues rather than vanishing into grey or
masquerading as ``relates_to``.
"""

from __future__ import annotations

import html
import json

from docir.modules.publishing.domain.site import Site, graph_payload
from docir.modules.publishing.infra.theme import CSS_TOKENS, FAVICON

#: Colour per document type — the categorical dimension. Types outside this
#: map get spare hues, assigned deterministically in the script; the palette
#: stays curated because these hues are tuned to hold up in both themes.
_PALETTE = {
    "decision": "#2f6feb",
    "issue": "#d1742f",
    "architecture": "#7048c4",
    "reference": "#2a8c72",
    "runbook": "#b3406e",
    "release_note": "#5c6470",
}

_GRAPH_CSS = """\
/* Edges need their own tone. `--line` is a 1px divider colour: on the dark
   background it made most edges effectively invisible until something
   highlighted them. */
:root{--edge:#c9cdd4;--edge-hi:#666}
@media(prefers-color-scheme:dark){:root{--edge:#3a4250;--edge-hi:#9aa0aa}}
*{box-sizing:border-box}
/* [hidden] must survive author display rules — see the site stylesheet. */
[hidden]{display:none!important}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);overflow:hidden;
font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.hd{display:flex;align-items:center;gap:.75rem;padding:.6rem 1rem;
border-bottom:1px solid var(--line);flex-wrap:wrap}
.back{font-weight:600}
.hd .tag{font-size:.72rem;color:var(--muted);border:1px solid var(--line);
border-radius:99px;padding:.05rem .5rem}
.srch{padding:.4rem .7rem;border:1px solid var(--line);border-radius:.45rem;
background:var(--bg);color:var(--fg);font-size:.85rem;min-width:13rem}
.chip{display:inline-flex;align-items:center;gap:.35rem;padding:.15rem .55rem;
border-radius:99px;border:1px solid var(--line);font-size:.75rem;color:var(--muted);
white-space:nowrap;background:var(--bg)}
.chip[aria-pressed="true"]{border-color:currentColor;background:var(--panel)}
.dot{width:.55rem;height:.55rem;border-radius:99px;flex:none}
.muted{color:var(--muted)}
.k{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}
.wrap{display:flex;flex-direction:column;height:100%}
.main{flex:1;position:relative;overflow:hidden}
svg{width:100%;height:100%;display:block;touch-action:none}
.stage-svg{cursor:grab}.stage-svg.grabbing{cursor:grabbing}
.node{cursor:pointer}
/* A node at 7% opacity was still the hit target: hoverable, clickable, and
   invisible. Filtered out has to mean out of reach as well as out of sight. */
.dim{pointer-events:none}
.node circle{transition:opacity .12s,stroke-width .12s}
.lbl{font-size:9px;fill:var(--muted);pointer-events:none;
paint-order:stroke;stroke:var(--bg);stroke-width:3px;stroke-linejoin:round}
.hubLbl{font-size:11px;font-weight:650;fill:var(--fg);pointer-events:auto;cursor:pointer}
/* Every node carries its name, but only the hovered (or pinned) one shows it:
   a hundred permanent labels is a wall of text, zero makes every dot a
   guessing game. */
.nmLbl{display:none}
.node.named .nmLbl{display:block}
/* Selection and keyboard focus mark the dot itself. The default focus outline
   boxed the whole group — node plus its floating label — drawing a huge frame
   around mostly empty space. The halo is the same affordance at the point the
   eye is actually on. */
.node:focus,.node:focus-visible{outline:none}
.halo{fill:none;stroke:var(--accent);stroke-width:2;opacity:0;transition:opacity .12s}
.node.sel .halo,.node:focus-visible .halo{opacity:1}
.edge{fill:none;transition:opacity .12s,stroke .12s}
.ring{fill:none;stroke:var(--line);stroke-dasharray:3 5}
.ringLbl{font-size:11px;font-weight:650;letter-spacing:.06em;text-transform:uppercase}
.dim{opacity:.07}
/* The legends float over the canvas instead of sitting in the header: ten
   chips forced the header onto two or three rows, while the map's top-left
   corner is empty at every zoom the layout produces. Collapsible for small
   screens, where the corner is not free. */
.legendbox{position:absolute;left:1rem;top:1rem;background:var(--panel);
border:1px solid var(--line);border-radius:.6rem;box-shadow:0 1px 3px rgba(0,0,0,.12);
padding:.45rem .6rem;max-height:calc(100% - 2rem);overflow:auto}
.lgHead{display:block;font-size:.7rem;color:var(--muted);text-transform:uppercase;
letter-spacing:.07em;padding:.1rem .15rem}
.lgHead::after{content:" \\25be"}
.legendbox.closed .lgHead::after{content:" \\25b8"}
.legendbox.closed .lgBody{display:none}
.lgGroup{display:flex;flex-direction:column;gap:.3rem;align-items:flex-start;margin:.3rem 0}
.lgSplit{border:0;border-top:1px solid var(--line);margin:.4rem 0}
.card{position:absolute;right:1rem;top:1rem;width:20rem;max-width:calc(100% - 2rem);
background:var(--panel);border:1px solid var(--line);border-radius:.6rem;
box-shadow:0 1px 3px rgba(0,0,0,.12);padding:.9rem 1rem;
max-height:calc(100% - 2rem);overflow:auto}
.card h2{margin:.15rem 0 .3rem;font-size:.95rem;line-height:1.35}
/* The link lists drop the browser bullet for a type-coloured dot, so the card
   speaks the same colour vocabulary as the map it describes. */
.card ul{margin:.3rem 0 0;padding-left:.1rem;list-style:none}
.card li{margin:.15rem 0;font-size:.82rem}
.card .dot{display:inline-block;margin-right:.4rem;vertical-align:-.05em}
.card .open{display:inline-block;margin:.4rem 0 0;font-weight:600;font-size:.85rem}
.card .close{position:absolute;top:.5rem;right:.6rem;color:var(--muted);font-size:1.1rem}
.hint{position:absolute;left:1rem;bottom:1rem;font-size:.75rem;color:var(--muted);
background:var(--bg);border:1px solid var(--line);border-radius:.4rem;padding:.3rem .6rem}
.hint kbd{border:1px solid var(--line);border-radius:.25rem;padding:0 .25rem;
font:inherit;font-size:.7rem;margin:0 .05rem}
@media(max-width:44rem){.card{position:static;width:auto;margin:.75rem;max-height:16rem}}
"""

_GRAPH_JS = """\
const DATA=__DATA__, COLOR=__COLOR__;

// Relation kinds get their own visual vocabulary: a node's colour says what it
// is, an edge's colour says what the link means. `relates_to` stays neutral
// because it is the bulk of most corpora — colouring the background noise
// would drown the edges that carry signal.
const KIND={
  relates_to:{c:'var(--edge)', w:1.2, dash:'',      lbl:'relates to'},
  refines:   {c:'#2a8c72',     w:1.8, dash:'',      lbl:'refines'},
  implements:{c:'#2f6feb',     w:1.8, dash:'',      lbl:'implements'},
  depends_on:{c:'#8a6d1f',     w:1.8, dash:'5 3',   lbl:'depends on'},
  supersedes:{c:'#b3406e',     w:2.2, dash:'',      lbl:'supersedes'},
  contradicts:{c:'#d1442f',    w:2.2, dash:'2 3',   lbl:'contradicts'},
};
const kindOf=k=>KIND[k]||KIND.relates_to;
// Kinds actually present, so the legend describes this corpus rather than the
// schema's full vocabulary.
const kinds=[...new Set(DATA.edges.map(e=>e.k))]
  .sort((a,b)=>(a==='relates_to')-(b==='relates_to')||a.localeCompare(b));
// A kind the map does not know must not masquerade as `relates_to` — the one
// style tuned to disappear into the background — and its legend chip would
// take the fallback's label too, so two chips both read "relates to". An
// unknown kind gets the next spare hue, signal weight, and its own name.
// Deterministic: `kinds` is sorted before assignment.
const KIND_SPARE=['#3a7d99','#8a55c4','#6b8f1f','#99553a'];
kinds.filter(k=>!(k in KIND)).forEach((k,i)=>KIND[k]={
  c:KIND_SPARE[i%KIND_SPARE.length], w:1.8, dash:'', lbl:k.replace(/_/g,' ')});
const activeKinds=new Set(kinds);

function legend(el, names, activeSet, onToggle){
  el.innerHTML='';
  for(const t of names){
    const b=document.createElement('button');
    b.className='chip'; b.setAttribute('aria-pressed', activeSet.has(t));
    b.innerHTML=`<span class="dot" style="background:${COLOR[t]||'#888'}"></span>${t}`;
    b.onclick=()=>{activeSet.has(t)?activeSet.delete(t):activeSet.add(t);
      b.setAttribute('aria-pressed',activeSet.has(t)); onToggle();};
    el.appendChild(b);
  }
}

const svg=document.getElementById('svg'), card=document.getElementById('card');
const byId=Object.fromEntries(DATA.nodes.map(n=>[n.id,n]));
const nbr={}; for(const n of DATA.nodes) nbr[n.id]=new Set();
for(const e of DATA.edges){ nbr[e.s].add(e.t); nbr[e.t].add(e.s); }

// Deterministic cluster layout. One ring per type, radius set by how many
// documents it holds, hubs pulled toward the centre of their own ring so the
// eye lands on them first. No physics: the same corpus always draws the same
// map, which is what makes it something two people can discuss.
const types=[...new Set(DATA.nodes.map(n=>n.ty))]
  .sort((a,b)=>DATA.nodes.filter(n=>n.ty===b).length
              -DATA.nodes.filter(n=>n.ty===a).length);
// A type outside the hand-tuned palette takes the next spare hue instead of
// the shared grey fallback — two unknown types must stay tellable apart.
// Writing into COLOR up front means every consumer (nodes, rings, legend
// chips, card dots) picks the hue up without knowing spares exist.
// Deterministic: `types` is sorted before assignment.
const TYPE_SPARE=['#0f8a9c','#7a8f1f','#a04a9c','#7a5230'];
types.filter(t=>!(t in COLOR)).forEach((t,i)=>COLOR[t]=TYPE_SPARE[i%TYPE_SPARE.length]);
const active=new Set(types);
// Closed work is hidden by default: a graph is readable at 20-50 nodes and a
// hairball past 200, and on a mature corpus most documents are finished work.
// "How much of this is done" stays legible from the holes. The site receives
// no schema, so inactive statuses are recognised by name — the union of the
// bundled profiles' inactive statuses. An unknown status counts as open,
// which errs on the visible side.
let showClosed=false;
const CLOSED=new Set(['resolved','superseded','rejected','deprecated','closed']);
const open=n=>!CLOSED.has(n.st)&&!n.ar;

const W=1800,H=1150;
// The centre goes to the type the graph actually revolves around — most total
// edge endpoints, not most documents: weight counts both ends of every edge.
const weight=t=>DATA.edges.filter(e=>byId[e.s].ty===t||byId[e.t].ty===t).length;
const hub=[...types].sort((a,b)=>weight(b)-weight(a))[0];
// An empty corpus has no hub: [hub, ...] would be [undefined] and the layout
// would draw one ghost ring labelled "undefined". No types, no rings.
const order=types.length?[hub,...types.filter(t=>t!==hub)]:[];
const radiusOf=t=>Math.max(95,Math.sqrt(DATA.nodes.filter(n=>n.ty===t).length)*44);
const centreR=radiusOf(hub);

const rings=[]; let angle=-Math.PI/2;
order.forEach((t,i)=>{
  const members=DATA.nodes.filter(n=>n.ty===t).sort((a,b)=>b.deg-a.deg);
  const rr=radiusOf(t);
  // Orbit from the geometry, not a constant: a satellite sits outside the
  // centre ring plus its own radius plus a gap, so however lopsided the
  // corpus is, no cluster can reach the centre one. Satellite-to-satellite
  // clearance is NOT guaranteed by this: it holds while the spokes are far
  // apart and only one satellite is large. Two big rings on adjacent spokes
  // would need angular spacing derived from their radii.
  const orbit=i===0?0:centreR+rr+130;
  const cx=W/2+Math.cos(angle)*orbit, cy=H/2+Math.sin(angle)*orbit;
  if(i>0) angle+=Math.PI*2/Math.max(1,order.length-1);
  rings.push({t,cx,cy,rr,n:members.length});
  members.forEach((m,j)=>{
    // Golden-angle spiral: even coverage, no two nodes at the same spot, and
    // high-degree nodes land near the middle because they are placed first.
    const k=(j+0.5)/members.length, a=j*2.39996;
    m.x=cx+Math.cos(a)*rr*Math.sqrt(k); m.y=cy+Math.sin(a)*rr*Math.sqrt(k);
  });
});
function norm(x,y){const d=Math.hypot(x,y)||1;return {x:x/d,y:y/d}}
const maxDeg=Math.max(1,...DATA.nodes.map(n=>n.deg));
const rad=n=>4+10*Math.sqrt(n.deg/maxDeg);

// Fit the initial view to what the layout actually produced rather than to
// the nominal canvas: orbits are derived from cluster sizes, so the extent
// depends on the corpus and a fixed viewBox leaves part of the map off-screen.
const pad=90;
const ext=rings.reduce((a,r)=>({
  x0:Math.min(a.x0,r.cx-r.rr-pad), y0:Math.min(a.y0,r.cy-r.rr-pad-40),
  x1:Math.max(a.x1,r.cx+r.rr+pad), y1:Math.max(a.y1,r.cy+r.rr+pad)}),
  {x0:1e9,y0:1e9,x1:-1e9,y1:-1e9});
const HOME=rings.length?{x:ext.x0,y:ext.y0,w:ext.x1-ext.x0,h:ext.y1-ext.y0}
                       :{x:0,y:0,w:W,h:H};
let vb={...HOME};
// What is *pinned*, as opposed to what the cursor happens to be over. Hover
// wiping the highlight belonging to the open card made the graph and the card
// disagree about what was selected.
let selected=null;

// One visibility predicate, shared by draw() and show(). The card's links can
// point at documents the filters hide, and show() needs the same answer
// draw() used — a private reimplementation of "visible" is how they drift.
const vis=n=>{
  const q=(document.getElementById('q').value||'').toLowerCase().trim();
  return active.has(n.ty)&&(showClosed||open(n))
    &&(!q||(n.id+' '+n.t+' '+n.tg.join(' ')+' '+n.st).toLowerCase().includes(q));
};

// Geometry for one edge, with an independent clearance at each end. At rest
// the line hugs the dot; a pinned or keyboard-focused node grows a halo (ring
// at r+3.5 with a 2-unit stroke), and the edge must retreat past r+4.5 — at
// that end only, and only while the halo is there. retrim() swaps the gaps.
const GAP=1.5, HALO_GAP=5.5;
function edgeD(e, gs, gt){
  const a=byId[e.s], b=byId[e.t], K=kindOf(e.k);
  // A quadratic curve rather than a straight line: parallel edges between the
  // same clusters would otherwise stack into one thick unreadable band.
  const mx=(a.x+b.x)/2, my=(a.y+b.y)/2, dx=b.x-a.x, dy=b.y-a.y;
  const cx=mx-dy*0.12, cy=my+dx*0.12;
  // Trim both ends to the node edge. Drawn centre-to-centre the arrowhead
  // sits *under* the target node and the direction is invisible — the one
  // thing the arrow exists to show. The tangents of a quadratic are
  // 2(c-a) at the start and 2(b-c) at the end, so the direction is exact.
  const t0=norm(cx-a.x, cy-a.y), t1=norm(b.x-cx, b.y-cy);
  // The marker anchors at its notch apex (refX 2.4), so the head lies wholly
  // ahead of the path's endpoint — the tip sits (9.6-2.4)/10 * markerWidth
  // stroke widths beyond it.
  const tip=K.w*4.6*0.72+gt;
  const sx=a.x+t0.x*(rad(a)+gs), sy=a.y+t0.y*(rad(a)+gs);
  const ex=b.x-t1.x*(rad(b)+tip), ey=b.y-t1.y*(rad(b)+tip);
  return `M${sx} ${sy}Q${cx} ${cy} ${ex} ${ey}`;
}
const edgeByKey={}; for(const e of DATA.edges) edgeByKey[e.s+'|'+e.t]=e;

function draw(){
  const shown=DATA.nodes.filter(vis).length;
  document.getElementById('shown').textContent=shown+' of '+DATA.nodes.length;
  // One marker, not one per kind. `context-stroke` makes the head take its
  // line's stroke colour — including the inline colour set when a
  // neighbourhood is emphasised, which a per-kind fill could not follow.
  // `markerUnits="strokeWidth"` keeps the head proportional to its line, so a
  // `supersedes` arrow reads heavier than a `relates_to` one. The shape is a
  // slim concave-backed dart; refX is the notch apex, so the head *begins*
  // where the line ends — anchored nearer the tip, the shaft ran on under
  // the head and its butt end showed wherever the dart narrowed past it.
  const parts=[`<defs><marker id="ar" viewBox="0 0 10 10" refX="2.4" refY="5"
      markerWidth="4.6" markerHeight="4.6" orient="auto" markerUnits="strokeWidth">
      <path d="M0 1.6L9.6 5L0 8.4L2.4 5z" fill="context-stroke"/></marker></defs>
      <g class="rings">`];
  for(const r of rings){
    parts.push(`<circle class="ring" cx="${r.cx}" cy="${r.cy}" r="${r.rr+26}"/>`);
    parts.push(`<text class="ringLbl" x="${r.cx}" y="${r.cy-r.rr-36}"
      text-anchor="middle" fill="${COLOR[r.t]||'#888'}">${r.t}
      <tspan class="muted">${r.n}</tspan></text>`);
  }
  parts.push('</g><g class="edges">');
  for(const e of DATA.edges){
    const a=byId[e.s],b=byId[e.t]; if(!a||!b) continue;
    const on=vis(a)&&vis(b)&&activeKinds.has(e.k);
    const K=kindOf(e.k);
    parts.push(`<path class="edge${on?'':' dim'}" data-s="${e.s}" data-t="${e.t}"
      data-k="${e.k}" data-halo="" d="${edgeD(e,GAP,GAP)}"
      stroke="${K.c}" stroke-width="${K.w}"${K.dash?` stroke-dasharray="${K.dash}"`:''}
      marker-end="url(#ar)"/>`);
  }
  parts.push('</g><g class="nodes">');
  for(const n of DATA.nodes){
    const on=vis(n), r=rad(n);
    parts.push(`<g class="node${on?'':' dim'}" data-id="${n.id}"
      tabindex="${on?0:-1}" role="button" aria-label="${esc(n.t)}">
      <circle cx="${n.x}" cy="${n.y}" r="${r}"
      fill="${COLOR[n.ty]||'#888'}" fill-opacity="${open(n)?.9:.35}"
      stroke="${COLOR[n.ty]||'#888'}" stroke-width="1.5"/>` +
      `<circle class="halo" cx="${n.x}" cy="${n.y}" r="${r+3.5}"/>` +
      `<text class="lbl ${n.deg>=8?'hubLbl':'nmLbl'}" x="${n.x}" y="${n.y-r-5}"
      text-anchor="middle">${esc(n.t)}</text></g>`);
  }
  parts.push('</g>');
  svg.innerHTML=parts.join('');
  applyView();
  // Re-pin after a redraw. Filtering rebuilds the DOM, which would drop the
  // highlight while leaving the card open; and if the pinned document is now
  // filtered out, the card describing it has to go too.
  if(selected){
    if(!svg.querySelector(`.node[data-id="${selected}"]:not(.dim)`)){
      selected=null; card.hidden=true; setHash(null); highlight(null);
    } else highlight(selected);
  }
  for(const g of svg.querySelectorAll('.node')){
    // Suppress mouse focus at the source. Browsers disagree on whether a
    // click matches :focus-visible, and any that says yes frames the whole
    // group — dot plus floating label — in a focus rectangle. Cancelling
    // pointerdown stops the click from focusing at all; Tab still focuses
    // and shows the halo.
    g.onpointerdown=ev=>ev.preventDefault();
    g.onmouseenter=()=>highlight(g.dataset.id);
    g.onmouseleave=()=>highlight(selected);
    g.onfocus=()=>{highlight(g.dataset.id);reveal(g.dataset.id)};
    g.onblur=()=>highlight(selected);
    g.onclick=()=>{ if(!suppressClick) show(g.dataset.id); };
    g.onkeydown=ev=>{if(ev.key==='Enter'||ev.key===' '){
      ev.preventDefault();show(g.dataset.id);}};
  }
}
// `"` is escaped alongside `<>&` because titles land in attribute position
// (aria-label), where an unescaped quote ends the attribute and the rest of
// the title parses as junk attributes.
const ESC={'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'};
function esc(s){return String(s).replace(/[<>&"]/g,c=>ESC[c])}

// Re-trim the edges around whichever nodes currently wear a halo: the pinned
// one and the keyboard-focused one. Hover changes nothing here, so the loop
// is a cheap no-op on every plain mouse pass. data-halo caches each path's
// current state so only genuine transitions rewrite geometry.
function retrim(){
  const has=new Set(); if(selected) has.add(selected);
  const f=document.activeElement&&document.activeElement.closest
    ?document.activeElement.closest('.node'):null;
  if(f) has.add(f.dataset.id);
  for(const p of svg.querySelectorAll('.edge')){
    const state=(has.has(p.dataset.s)?'s':'')+(has.has(p.dataset.t)?'t':'');
    if(p.dataset.halo===state) continue;
    p.dataset.halo=state;
    const e=edgeByKey[p.dataset.s+'|'+p.dataset.t];
    p.setAttribute('d', edgeD(e, state.includes('s')?HALO_GAP:GAP,
                                 state.includes('t')?HALO_GAP:GAP));
  }
}
// Hover lifts the neighbourhood out instead of asking the eye to trace one
// line across a hundred others — the single most effective anti-hairball
// interaction.
function highlight(id){
  retrim();
  const keep=id?new Set([id,...nbr[id]]):null;
  // Exactly one name at a time: the hovered (or pinned) document's. Hover is
  // the only way to learn a non-hub node's title without opening the card.
  for(const g of svg.querySelectorAll('.node.named')) g.classList.remove('named');
  if(id){ const g=svg.querySelector(`.node[data-id="${id}"]`);
    if(g&&!g.classList.contains('dim')) g.classList.add('named'); }
  // Filtered-out elements stay filtered out. `keep` is built from the full
  // edge list, so a hub's neighbourhood includes hidden documents — and
  // inline emphasis on a `.dim` edge would override the filter's opacity,
  // drawing bright arrows into blank space where a hidden neighbour sits.
  for(const g of svg.querySelectorAll('.node')){
    // The halo tracks `selected`, not the hover: re-derived on every repaint
    // of emphasis so hovering elsewhere cannot steal the pinned ring.
    g.classList.toggle('sel', g.dataset.id===selected);
    if(g.classList.contains('dim')){ g.style.opacity=''; continue; }
    g.style.opacity=!keep||keep.has(g.dataset.id)?'':'0.12';
  }
  for(const p of svg.querySelectorAll('.edge')){
    if(p.classList.contains('dim')){
      p.style.opacity=p.style.stroke=''; continue; }
    const hit=!keep||(keep.has(p.dataset.s)&&keep.has(p.dataset.t));
    // Emphasise by opacity contrast alone, never by recolouring or widening:
    // the stroke colour carries the relation kind, and widening the stroke
    // also scaled the arrowhead (markerUnits is strokeWidth) into the nodes
    // exactly when someone was looking at them.
    p.style.opacity=hit?(keep?'1':''):'0.05';
    // `relates_to` is drawn in the divider colour so the bulk stays quiet in
    // the background — which also makes them nearly invisible when they are
    // the thing being looked at. Emphasis promotes it to the muted
    // foreground and leaves every other kind on its own hue.
    p.style.stroke=(keep&&hit&&p.dataset.k==='relates_to')?'var(--edge-hi)':'';
  }
}
// The pin lives in the URL fragment: a document page links here as
// graph.html#<id>, and once pinned the address stays shareable and
// reload-stable. replaceState, not assignment — pinning while exploring must
// not grow a history entry per click.
function setHash(id){
  history.replaceState(null,'', id?'#'+id:location.pathname+location.search);
}
function show(id){
  const n=byId[id]; if(!n) return;
  // A card link may target a hidden document. Pinning it while it stayed
  // hidden left the card and the map describing different selections — the
  // exact disagreement `selected` exists to prevent (draw() closes the card
  // in the mirror case). Details on demand wins: relax whichever filter
  // hides the target, and rebuild the type legend to reflect the new state.
  if(!vis(n)){
    if(!active.has(n.ty)) active.add(n.ty);
    if(!showClosed&&!open(n)){ showClosed=true;
      document.getElementById('closed').setAttribute('aria-pressed',true); }
    const q=document.getElementById('q');
    if(q.value&&!vis(n)) q.value='';
    legend(document.getElementById('legend'), types, active, draw);
    draw();
  }
  selected=id;
  setHash(id);
  const out=DATA.edges.filter(e=>e.s===id), inc=DATA.edges.filter(e=>e.t===id);
  const li=(e,dir)=>{const m=byId[dir==='out'?e.t:e.s];
    return `<li><span class="dot" style="background:${COLOR[m.ty]||'#888'}"></span>`+
      `<a href="#" data-go="${m.id}">${esc(m.t)}</a> `+
      `<span class="k">${e.k}</span></li>`;};
  card.hidden=false;
  card.innerHTML=`<button class="close" aria-label="Close">&#215;</button>
    <div class="k">${n.ty} &#183; ${n.st} &#183; ${n.up}</div><h2>${esc(n.t)}</h2>
    <p class="muted" style="font-size:.83rem;margin:.2rem 0 .5rem">${esc(n.d)}</p>
    <div style="display:flex;gap:.3rem;flex-wrap:wrap">`+
    n.tg.map(t=>`<span class="chip">#${esc(t)}</span>`).join('')+`</div>
    <a class="open" href="${n.id}.html">open document &#8594;</a>`+
    (out.length?`<div class="k" style="margin-top:.7rem">links to ${out.length}</div>`+
      `<ul>${out.map(e=>li(e,'out')).join('')}</ul>`:'')+
    (inc.length?`<div class="k" style="margin-top:.7rem">linked from ${inc.length}</div>`+
      `<ul>${inc.map(e=>li(e,'in')).join('')}</ul>`:'');
  card.querySelector('.close').onclick=()=>{
    card.hidden=true;selected=null;setHash(null);highlight(null)};
  for(const a of card.querySelectorAll('[data-go]'))
    a.onclick=ev=>{ev.preventDefault();show(a.dataset.go);reveal(a.dataset.go)};
  highlight(id);
}
// -- view: pan and zoom ----------------------------------------------------
//
// The viewBox aspect ratio must match the element's, or SVG letterboxes the
// content and a pixel on screen is not the pixel the arithmetic assumed —
// zoom then drifts away from the cursor, compounding per wheel tick. `fit`
// keeps the two aspects equal; after that the conversion below is exact and
// every interaction built on it is correct by construction.
function fit(box){
  const r=svg.getBoundingClientRect(), aspect=r.width/Math.max(1,r.height);
  let {x,y,w,h}=box;
  if(w/h < aspect){ const nw=h*aspect; x-=(nw-w)/2; w=nw; }
  else            { const nh=w/aspect; y-=(nh-h)/2; h=nh; }
  return {x,y,w,h};
}
// How far outside the content the view may sit. Some slack is useful;
// unbounded panning is not — the graph could be dragged entirely off-screen,
// leaving a blank canvas whose only cure was a reset button the user had no
// reason to suspect they needed.
const SLACK=0.65;
function clamp(v){
  const w=Math.min(v.w,HOME.w*3), h=w*(v.h/v.w);
  const mx=w*SLACK, my=h*SLACK;
  return {
    x:Math.min(Math.max(v.x, HOME.x-mx), HOME.x+HOME.w-w+mx),
    y:Math.min(Math.max(v.y, HOME.y-my), HOME.y+HOME.h-h+my),
    w, h,
  };
}
function applyView(){ svg.setAttribute('viewBox',`${vb.x} ${vb.y} ${vb.w} ${vb.h}`); }
function setView(v){ vb=clamp(fit(v)); applyView(); }
function toGraph(cx,cy){
  const r=svg.getBoundingClientRect();
  return {x:vb.x+(cx-r.left)/r.width*vb.w, y:vb.y+(cy-r.top)/r.height*vb.h};
}
const MIN_W=200, MAX_W=()=>HOME.w*2.4;
function zoomAt(cx,cy,factor){
  const g=toGraph(cx,cy);
  const w=Math.min(MAX_W(),Math.max(MIN_W,vb.w*factor)), h=w*(vb.h/vb.w);
  const r=svg.getBoundingClientRect();
  // Keep the graph point under the cursor under the cursor. With the aspects
  // matched this holds exactly, at any position in the viewport.
  setView({x:g.x-(cx-r.left)/r.width*w, y:g.y-(cy-r.top)/r.height*h, w, h});
}
// -- pointer ---------------------------------------------------------------
//
// A drag that begins on a node used to pan *and* open that node, because the
// click fires on release regardless. The fix is a movement threshold: below
// it the gesture was a click, above it the click is suppressed.
const CLICK_SLOP=5;
let drag=null, suppressClick=false;
const pointers=new Map();

svg.addEventListener('pointerdown',e=>{
  pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(pointers.size>1){ drag=null; return; }        // a second finger means pinch
  drag={x:e.clientX,y:e.clientY,vb:{...vb},moved:0};
  suppressClick=false;
  svg.classList.add('grabbing');
});

svg.addEventListener('pointermove',e=>{
  // A release nothing heard: below the drag threshold there is no capture,
  // so a pointerup over the header — or with the button let go outside the
  // window — never reaches a listener, and the stale drag made bare hover
  // pan the view. A move with no buttons down after a pointerdown IS that
  // release.
  if(drag&&e.buttons===0){ endPointer(e); return; }
  if(pointers.has(e.pointerId)) pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(pointers.size===2){ pinch(); return; }
  if(!drag) return;
  const dx=e.clientX-drag.x, dy=e.clientY-drag.y;
  drag.moved=Math.max(drag.moved,Math.hypot(dx,dy));
  if(drag.moved>CLICK_SLOP && !suppressClick){
    suppressClick=true;
    // Capture only once this is genuinely a drag. Capturing on pointerdown
    // retargets the whole gesture to the <svg>, and the click derived from
    // it then lands on the canvas rather than the node — so every click on
    // a document did nothing at all.
    try{ svg.setPointerCapture(e.pointerId); }catch{}
  }
  const r=svg.getBoundingClientRect();
  setView({x:drag.vb.x-dx*(drag.vb.w/r.width), y:drag.vb.y-dy*(drag.vb.h/r.height),
           w:drag.vb.w, h:drag.vb.h});
});

function endPointer(e){
  pointers.delete(e.pointerId);
  if(pointers.size<2) lastPinch=0;
  if(pointers.size===0){ drag=null; svg.classList.remove('grabbing');
    // Release the suppression after the click event has had its turn.
    setTimeout(()=>{suppressClick=false},0); }
}
// On the window, not the <svg>: an uncaptured release over the header or the
// card belongs to that element, and the <svg> would wait for a pointerup
// that already happened. endPointer is idempotent, so extra deliveries are
// safe.
addEventListener('pointerup',endPointer);
addEventListener('pointercancel',endPointer);
// Without this a pointer lost outside the window leaves the view stuck in a
// drag.
svg.addEventListener('lostpointercapture',endPointer);

let lastPinch=0;
function pinch(){
  const [a,b]=[...pointers.values()];
  const dist=Math.hypot(a.x-b.x,a.y-b.y);
  if(lastPinch) zoomAt((a.x+b.x)/2,(a.y+b.y)/2,lastPinch/dist);
  lastPinch=dist;
}

svg.addEventListener('wheel',e=>{e.preventDefault();
  zoomAt(e.clientX,e.clientY,e.deltaY>0?1.12:0.89);
},{passive:false});

// Keyboard equivalents, because zoom and pan were mouse-only and the nodes
// are focusable — you could tab to a document you had no way to bring into
// view.
addEventListener('keydown',e=>{
  // Defensive: the event target is not always an Element (a key delivered to
  // the document or the window has no `matches`), and an exception here
  // kills every shortcut silently.
  const t=e.target;
  if(t && typeof t.matches==='function'
      && t.matches('input,textarea,[contenteditable]')) return;
  if(e.metaKey||e.ctrlKey||e.altKey) return;
  const r=svg.getBoundingClientRect(), mid=[r.left+r.width/2,r.top+r.height/2];
  const step=vb.w*0.12;
  const moves={ArrowLeft:[-step,0],ArrowRight:[step,0],
               ArrowUp:[0,-step],ArrowDown:[0,step]};
  if(moves[e.key]){ e.preventDefault();
    setView({...vb,x:vb.x+moves[e.key][0],y:vb.y+moves[e.key][1]}); }
  else if(e.key==='+'||e.key==='='){ e.preventDefault(); zoomAt(...mid,0.8); }
  else if(e.key==='-'){ e.preventDefault(); zoomAt(...mid,1.25); }
  else if(e.key==='0'){ e.preventDefault(); setView({...HOME}); }
  else if(e.key==='Escape'){ card.hidden=true; selected=null; setHash(null);
    highlight(null); }
});

// Bring a document into view without yanking the zoom level around: only
// move if it is actually off-screen, and keep the current scale.
function reveal(id){
  const n=byId[id]; if(!n) return;
  const p=vb.w*0.12;
  let {x,y,w,h}=vb;
  if(n.x<x+p) x=n.x-p; else if(n.x>x+w-p) x=n.x-w+p;
  if(n.y<y+p) y=n.y-p; else if(n.y>y+h-p) y=n.y-h+p;
  setView({x,y,w,h});
}

// The fitted view depends on the element's aspect ratio, so it has to be
// recomputed when that changes or the letterboxing comes straight back.
let resizeTimer;
addEventListener('resize',()=>{clearTimeout(resizeTimer);
  resizeTimer=setTimeout(()=>setView(vb),80)});

document.getElementById('q').addEventListener('input',draw);
document.getElementById('closed').onclick=e=>{showClosed=!showClosed;
  e.currentTarget.setAttribute('aria-pressed',showClosed);draw()};
document.getElementById('home').onclick=()=>setView({...HOME});
document.getElementById('lgToggle').onclick=e=>{
  const box=document.getElementById('legendbox');
  box.classList.toggle('closed');
  e.currentTarget.setAttribute('aria-expanded',
    String(!box.classList.contains('closed')));
};
legend(document.getElementById('legend'), types, active, draw);
// The relation legend doubles as a filter, like the type one. Its swatch is a
// line with an arrowhead rather than a dot, so the legend looks like the
// thing it describes.
(function relationLegend(){
  const el=document.getElementById('klegend'); el.innerHTML='';
  for(const k of kinds){
    const K=kindOf(k);
    const b=document.createElement('button');
    b.className='chip'; b.setAttribute('aria-pressed',true);
    b.title=`relation: ${k}`;
    b.innerHTML=`<svg width="22" height="8" aria-hidden="true"><path d="M1 4H14.6"
      stroke="${K.c}" stroke-width="${Math.max(1.4,K.w)}"`+
      `${K.dash?` stroke-dasharray="${K.dash}"`:''}/>
      <path d="M13 1.4L20 4L13 6.6L14.6 4z" fill="${K.c}"/></svg>${K.lbl}`;
    b.onclick=()=>{activeKinds.has(k)?activeKinds.delete(k):activeKinds.add(k);
      b.setAttribute('aria-pressed',activeKinds.has(k)); draw();};
    el.appendChild(b);
  }
})();
setView({...HOME});
draw();
// Deep link: a document page's "view in graph" arrives as graph.html#<id>.
// show() pins it and relaxes whatever filter hides it, so the link works for
// a closed document too. An unknown fragment is ignored — an old link to a
// deleted document lands on the plain overview rather than an error.
const target=decodeURIComponent(location.hash.slice(1));
if(target&&byId[target]) show(target);
// A fragment change with no page load — a hand-edited hash, a link followed
// while already on the graph — must behave like arriving fresh. setHash uses
// replaceState, which never fires this event, so pinning cannot loop.
addEventListener('hashchange',()=>{
  const id=decodeURIComponent(location.hash.slice(1));
  if(id&&byId[id]) show(id);
});
"""

_SHELL = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Graph &#8212; __TITLE__</title>
__FAVICON__
<style>__TOKENS____CSS__</style>
</head><body>
<div class="wrap">
  <header class="hd">
    <a class="back" href="index.html">&#8592; __TITLE__</a>
    <span class="tag">graph</span>
    <input class="srch" id="q" type="search" placeholder="Search titles, tags, ids&#8230;"
           aria-label="Search documents">
    <button class="chip" id="closed" aria-pressed="false">show closed</button>
    <span class="muted" id="shown" style="font-size:.78rem"></span>
  </header>
  <div class="main">
    <!-- role=group, not img: img makes the whole subtree presentational, which
         would strip the focusable role=button nodes from the accessibility
         tree. -->
    <svg id="svg" class="stage-svg" role="group" aria-label="Document graph"></svg>
    <div class="legendbox" id="legendbox">
      <button class="lgHead" id="lgToggle" aria-expanded="true">legend</button>
      <div class="lgBody">
        <span id="legend" class="lgGroup"></span>
        <hr class="lgSplit">
        <span id="klegend" class="lgGroup"></span>
      </div>
    </div>
    <div class="hint">Scroll or pinch to zoom &#183; drag to pan &#183; click to pin
      &#183; <kbd>+</kbd><kbd>-</kbd><kbd>0</kbd> <kbd>esc</kbd>
      &#183; <button id="home" style="color:var(--accent)">reset view</button></div>
    <div class="card" id="card" hidden></div>
  </div>
</div>
<script>__JS__</script></body></html>
"""


def render_graph_page(site: Site, *, title: str) -> str:
    """Render the constellation page for a resolved site."""
    data = json.dumps(graph_payload(site), separators=(",", ":"), ensure_ascii=False)
    color = json.dumps(_PALETTE, separators=(",", ":"))
    script = _GRAPH_JS.replace("__DATA__", _script_safe(data)).replace("__COLOR__", color)
    return (
        _SHELL.replace("__TITLE__", html.escape(title))
        .replace("__FAVICON__", FAVICON)
        .replace("__TOKENS__", CSS_TOKENS)
        .replace("__CSS__", _GRAPH_CSS)
        .replace("__JS__", script)
    )


def _script_safe(payload: str) -> str:
    """Make a JSON payload safe to inline inside a ``<script>`` element.

    The HTML parser ends a script at the first ``</script`` it sees, *inside a
    string literal or not* — a document titled ``</script><img onerror=...>``
    would otherwise terminate the script and parse as markup. Escaping the
    slash is invisible to ``JSON.parse``/the JS engine and closes the hole.
    """
    return payload.replace("</", "<\\/")
