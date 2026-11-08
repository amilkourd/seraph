"""The page a judge opens from the dashboard to watch Devin build a Halo view: Silex's timeline, the view as Devin
writes it (fed with the state it was built from), the references and what Devin took from each, Devin's own steps,
the prompt. Polls /sessions/<id>/data every 1.5 s. French UI, big type, dark."""

PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Devin · vue Halo</title>
<style>
:root { --bg:#0b0b0c; --panel:#151517; --line:#2a2a2e; --ink:#f2f2f0; --dim:#a7a7a2; --ok:#5fd38d; --warn:#f5b83d;
        --bad:#ff5a4e; --blue:#6aa8ff; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:18px/1.45 ui-monospace, "SF Mono", Menlo, monospace; }
main { max-width:1500px; margin:0 auto; padding:24px 16px 48px; }
header { display:flex; flex-wrap:wrap; align-items:baseline; gap:12px 24px; margin-bottom:20px; }
h1 { font-size:28px; margin:0; font-weight:700; }
.purpose { font-size:20px; color:var(--dim); flex-basis:100%; }
.pill { font-size:18px; padding:4px 12px; border-radius:999px; border:1px solid var(--line); }
.pill.building { color:var(--warn); border-color:var(--warn); } .pill.ready { color:var(--ok); border-color:var(--ok); }
.pill.failed { color:var(--bad); border-color:var(--bad); }
.clock { font-size:40px; font-weight:700; margin-left:auto; font-variant-numeric:tabular-nums; }
.grid { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.1fr); gap:20px; }
@media (max-width:1000px) { .grid { grid-template-columns:1fr; } .clock { margin-left:0; } }
section { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; min-width:0; }
h2 { font-size:20px; margin:0 0 12px; }
ol { list-style:none; margin:0; padding:0; }
li { padding:6px 0; border-top:1px solid var(--line); display:flex; gap:12px; }
li:first-child { border-top:0; }
.t { color:var(--dim); min-width:4.5em; text-align:right; font-variant-numeric:tabular-nums; }
.tool { color:var(--blue); min-width:4.5em; }
.out { color:var(--dim); white-space:pre-wrap; word-break:break-word; }
.screen { position:relative; width:100%; aspect-ratio:874/402; background:#000; border-radius:8px; overflow:hidden; }
.screen iframe { position:absolute; left:0; top:0; width:874px; height:402px; border:0; transform-origin:0 0; }
.screen .empty { position:absolute; inset:0; display:grid; place-items:center; color:var(--dim); font-size:20px; }
.refs { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; }
.ref img { width:100%; border-radius:6px; background:#fff; display:block; aspect-ratio:16/10; object-fit:cover; }
.ref b { display:block; margin:6px 0 2px; }
.ref p { margin:0; }
details { margin-top:20px; } summary { cursor:pointer; font-size:20px; }
pre { white-space:pre-wrap; word-break:break-word; font-size:15px; color:var(--dim); max-height:60vh; overflow:auto; }
.errors li { color:var(--bad); }
.stack > section + section { margin-top:20px; }
</style>
</head>
<body>
<main>
  <header>
    <h1 id="title">Devin construit une vue Halo</h1>
    <span class="pill" id="status">…</span>
    <span class="clock" id="clock">0 s</span>
    <div class="purpose" id="purpose"></div>
  </header>
  <div class="grid">
    <div class="stack">
      <section><h2>Silex</h2><ol id="events"></ol></section>
      <section><h2>Ce que fait Devin</h2><ol id="trace"><li><span class="out">Ses actions s'affichent à la fin de chaque essai.</span></li></ol></section>
    </div>
    <div class="stack">
      <section><h2 id="screen-title">La vue</h2>
        <div class="screen" id="screen"><div class="empty" id="empty">Devin n'a pas encore écrit la vue</div></div>
      </section>
      <section id="err-box" hidden><h2>Refusé par Silex</h2><ol class="errors" id="errors"></ol></section>
      <section><h2>Ce que Devin a pris dans chaque image</h2><div class="refs" id="refs"></div></section>
    </div>
  </div>
  <details><summary>Le message envoyé à Devin</summary><pre id="prompt"></pre></details>
</main>
<script>
const qs = new URLSearchParams(location.search);
const base = location.pathname.replace(/\\/$/, '');
const dataUrl = base + '/data' + (qs.get('view') ? '?view=' + encodeURIComponent(qs.get('view')) : '');
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let frameSrc = '', state = null, stateUrl = '', t0 = null, done = null;

function fit() {
  const box = $('screen'), f = box.querySelector('iframe');
  if (f) f.style.transform = 'scale(' + (box.clientWidth / 874) + ')';
}
addEventListener('resize', fit);
function feed() {
  const f = $('screen').querySelector('iframe');
  if (f && state) f.contentWindow.postMessage({ type: 'seraph:state', state }, '*');
}
addEventListener('message', e => { if (e.data && e.data.type === 'seraph:ready') feed(); });

async function loadState(url) {
  if (!url || url === stateUrl) return;
  stateUrl = url;
  try { state = await (await fetch(url)).json(); feed(); } catch (e) { /* the view shows its empty frame */ }
}
function showFrame(src, title) {
  $('screen-title').textContent = title;
  if (!src || src === frameSrc) return;
  frameSrc = src;
  $('empty').hidden = true;
  const old = $('screen').querySelector('iframe'); if (old) old.remove();
  const f = document.createElement('iframe');
  f.src = src; f.onload = () => { fit(); feed(); };
  $('screen').appendChild(f); fit();
}

function tick() {
  if (t0 == null) return;
  const s = done != null ? done : (Date.now() - t0) / 1000;
  $('clock').textContent = Math.round(s) + ' s';
}
setInterval(tick, 250);

async function poll() {
  let d;
  try { d = await (await fetch(dataUrl, { cache: 'no-store' })).json(); } catch (e) { return; }
  const j = d.job || {};
  $('title').textContent = 'Devin construit ' + (j.view_id || 'une vue Halo');
  $('purpose').textContent = j.purpose_fr ? '« ' + j.purpose_fr + ' »' : '';
  const st = j.status === 'ready' ? 'ready' : j.status === 'failed' ? 'failed' : 'building';
  $('status').className = 'pill ' + st;
  $('status').textContent = { ready: 'servie', failed: 'refusée', building: j.late ? 'en retard' : 'en cours' }[st]
    + (j.attempt > 1 ? ' · essai ' + j.attempt : '');
  t0 = d.t0_ms; done = j.request_to_view_ms != null ? j.request_to_view_ms / 1000 : (st === 'failed' ? d.elapsed_s : null);
  tick();
  $('events').innerHTML = (d.events || []).map(e => '<li><span class="t">' + e.s.toFixed(0) + ' s</span><span>' + esc(e.text) + '</span></li>').join('');
  if ((d.trace || []).length) {
    $('trace').innerHTML = d.trace.map(x => '<li><span class="tool">' + esc({ read: 'lit', write: 'écrit', edit: 'modifie', exec: 'lance', say: 'dit' }[x.tool] || x.tool)
      + '</span><span>' + esc(x.target) + (x.code != null ? ' <b>→ code ' + esc(x.code) + '</b>' : '')
      + (x.out ? '<div class="out">' + esc(x.out) + '</div>' : '') + '</span></li>').join('');
  }
  const errs = j.status === 'ready' ? [] : (j.errors || []);
  $('err-box').hidden = !errs.length;
  $('errors').innerHTML = errs.map(e => '<li>' + esc(e) + '</li>').join('');
  $('refs').innerHTML = (d.refs || []).map(r => '<div class="ref"><img src="' + esc(r.url) + '" alt="">'
    + '<b>' + esc(r.image) + '</b><p>' + esc(r.took || (st === 'building' ? 'Devin la regarde…' : '')) + '</p></div>').join('');
  $('prompt').textContent = d.prompt || '';
  loadState(d.state_url);
  if (d.final_url) showFrame(d.final_url, 'La vue servie à Halo');
  else if (d.wip_url) showFrame(d.wip_url, 'La vue, telle que Devin l’écrit');
}
poll(); setInterval(poll, 1500);
</script>
</body>
</html>
"""
