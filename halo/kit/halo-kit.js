/*
 * Halo kit — the building blocks Devin uses for Halo schemes. Vanilla JS, no build step, global `Halo`.
 * README.md is the API. Load halo.css with it.
 *
 * Full screen, landscape (874×402 units = pt on an iPhone 17 Pro; the drawing always fits, the ground fills the screen). One scheme, no text
 * panel. Grainy dark ground, flat dark shapes with thin white outlines, black tags; the target flat white, no glow;
 * fire and smoke as grainy gradients inside their zone. Nothing else has a gradient, a glow or a texture. Colour only carries meaning (SITAC). One small instruction card on the
 * right (Halo.panel): a few imperative lines, nothing else.
 *
 * Halo.scene(svg, {rotate}) turns the drawing (streets, blocks, hazards, routes) like the reference's diagonal
 * composition; markers and labels stay upright. Views always draw in
 * scene coordinates. Positions and routes come from the state: the kit draws, it never decides where things are.
 */
(function (global) {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var W = 874, H = 402;
  // where the scheme is drawn: left of the instruction card, with empty ground between them so nothing reads as linked
  var AREA = { x: 40, y: 10, w: 480, h: 382 };
  var C = {
    ink: '#ffffff', line: '#dcdad5', dim: '#8e8c87', mute: '#3a3936', bg: '#000000', panel: '#0a0a0a',
    fire: '#ff3d1f', warn: '#ffc61a', risk: '#ff8a24', water: '#3b8cff', life: '#2fe07a'
  };
  var KIND_TONE = {
    door: 'ink', entrance: 'ink', stair: 'ink', elevator: 'ink', team: 'ink', truck: 'fire', fire: 'fire',
    hydrant: 'water', riser: 'water', person: 'life', wheelchair: 'life', gas: 'risk', elec: 'risk',
    smoke: 'warn', unknown: 'dim'
  };
  var LAYERS = ['base', 'hazard', 'route', 'mark', 'label'];
  var MAX_LABELS = 8;                                  // tags on one screen, at most
  var TURNED = { base: 1, hazard: 1, route: 1 };     // layers that follow Halo.scene's rotation

  function tone(t) { return C[t] || t || C.ink; }

  // ---- DOM ------------------------------------------------------------------------------------------------
  function el(tag, attrs, parent) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) if (attrs[k] !== undefined && attrs[k] !== null) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function svgOf(target) { return target.ownerSVGElement || target; }
  function layer(svg, name) {
    svg = svgOf(svg);
    var g = svg.querySelector(':scope > g[data-layer="' + name + '"]');
    if (!g) {
      defs(svg);
      LAYERS.forEach(function (n) {
        if (!svg.querySelector(':scope > g[data-layer="' + n + '"]')) el('g', { 'data-layer': n }, svg);
      });
      g = svg.querySelector(':scope > g[data-layer="' + name + '"]');
    }
    return g;
  }

  // ---- intro: elements draw themselves once; state updates redraw without replaying ----------------------
  // only the first drawing animates in; every redraw after it (state updates, up to 4/s) is still, or texts would flash
  var t0 = Date.now(), seq = 0, drawn = false;
  function intro() { return !drawn && Date.now() - t0 < 2000; }
  function nextDelay() { return Math.min(seq++ * 0.06, 1.2); }
  function drawIn(path, delay) {
    if (!intro()) return path;
    path.setAttribute('pathLength', '1');
    path.classList.add('h-draw');
    path.style.setProperty('--d', (delay === undefined ? nextDelay() : delay) + 's');
    path.addEventListener('animationend', function () {
      path.classList.remove('h-draw'); path.removeAttribute('pathLength'); path.style.removeProperty('--d');
    });
    return path;
  }
  // looping motion keeps its phase on the wall clock, so redrawing on every state update never restarts it
  var PERIOD = { 'h-blink': 1100, 'h-blink-fast': 700, 'h-flicker': 2600, 'h-breathe': 3600 };
  function loop(node, cls) {
    node.classList.add(cls);
    node.style.animationDelay = -(Date.now() % PERIOD[cls]) + 'ms';
    return node;
  }
  function fadeIn(node, delay) {
    if (!intro()) return node;
    node.classList.add('h-fade');
    node.style.setProperty('--d', (delay === undefined ? nextDelay() : delay) + 's');
    return node;
  }

  // ---- geometry -------------------------------------------------------------------------------------------
  function P(p) { return Array.isArray(p) ? { x: p[0], y: p[1] } : { x: p.x, y: p.y }; }
  function r1(v) { return Math.round(v * 10) / 10; }
  function sub(a, b) { return { x: a.x - b.x, y: a.y - b.y }; }
  function len(v) { return Math.sqrt(v.x * v.x + v.y * v.y) || 1; }
  function unit(v) { var l = len(v); return { x: v.x / l, y: v.y / l }; }
  function project(point, box) { var p = P(point); return { x: box.x + p.x / 1000 * box.w, y: box.y + p.y / 1000 * box.h }; }
  // area: [[x,y]…] | {points} | {x,y,w,h} | {cx,cy,r}  →  {d, box, c, circle}
  function area(a) {
    if (a && a.r !== undefined) {
      return { d: 'M' + (a.cx - a.r) + ',' + a.cy + 'a' + a.r + ',' + a.r + ' 0 1,0 ' + 2 * a.r + ',0a' + a.r + ',' + a.r + ' 0 1,0 ' +
        -2 * a.r + ',0Z', box: { x: a.cx - a.r, y: a.cy - a.r, w: 2 * a.r, h: 2 * a.r }, c: { x: a.cx, y: a.cy }, circle: true };
    }
    var pts = Array.isArray(a) ? a.map(P) : a.points ? a.points.map(P) :
      [{ x: a.x, y: a.y }, { x: a.x + a.w, y: a.y }, { x: a.x + a.w, y: a.y + a.h }, { x: a.x, y: a.y + a.h }];
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    pts.forEach(function (p) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y); });
    return { d: 'M' + pts.map(function (p) { return r1(p.x) + ',' + r1(p.y); }).join('L') + 'Z',
      box: { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }, c: { x: (x0 + x1) / 2, y: (y0 + y1) / 2 } };
  }
  function anchor(b, at) {
    return { x: at.indexOf('w') >= 0 ? b.x : at.indexOf('e') >= 0 ? b.x + b.w : b.x + b.w / 2,
             y: at.indexOf('n') >= 0 ? b.y : at.indexOf('s') >= 0 ? b.y + b.h : b.y + b.h / 2 };
  }
  // polyline with rounded corners
  function roundPath(pts, r) {
    var d = 'M' + r1(pts[0].x) + ',' + r1(pts[0].y);
    for (var i = 1; i < pts.length - 1; i++) {
      var p0 = pts[i - 1], p1 = pts[i], p2 = pts[i + 1], a = sub(p0, p1), b = sub(p2, p1);
      var rr = Math.min(r, len(a) / 2, len(b) / 2), ua = unit(a), ub = unit(b);
      d += 'L' + r1(p1.x + ua.x * rr) + ',' + r1(p1.y + ua.y * rr) + 'Q' + r1(p1.x) + ',' + r1(p1.y) + ' ' + r1(p1.x + ub.x * rr) + ',' + r1(p1.y + ub.y * rr);
    }
    var last = pts[pts.length - 1];
    return d + 'L' + r1(last.x) + ',' + r1(last.y);
  }
  // centroid of a zone (mean of its corners) and convex hull of points: the footprint of a building from its rooms
  function centroid(zone) {
    var pts = zone.map(P), x = 0, y = 0;
    pts.forEach(function (p) { x += p.x; y += p.y; });
    return { x: x / pts.length, y: y / pts.length };
  }
  function hull(points) {
    var pts = points.map(P).sort(function (a, b) { return a.x - b.x || a.y - b.y; });
    if (pts.length < 3) return pts;
    function cross(o, a, b) { return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x); }
    var lo = [], up = [];
    pts.forEach(function (p) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); });
    pts.slice().reverse().forEach(function (p) { while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); });
    return lo.slice(0, -1).concat(up.slice(0, -1)).map(function (p) { return [p.x, p.y]; });
  }
  function polyLength(pts) { var s = 0; for (var i = 1; i < pts.length; i++) s += len(sub(pts[i], pts[i - 1])); return s; }

  // ---- scene: the reference's diagonal composition ---------------------------------------------------------
  function scene(svg, opts) {
    svg = svgOf(svg); opts = opts || {};
    var deg = opts.rotate || 0, cx = opts.cx === undefined ? W / 2 : opts.cx, cy = opts.cy === undefined ? H / 2 : opts.cy;
    svg.__xf = { deg: deg, a: deg * Math.PI / 180, cx: cx, cy: cy };
    Object.keys(TURNED).forEach(function (n) { layer(svg, n).setAttribute('transform', 'rotate(' + deg + ' ' + cx + ' ' + cy + ')'); });
    if (svg.__ground) svg.__ground.redraw();
    return { to: function (p) { return xf(svg, p); } };
  }
  // scene point → screen point (markers and labels stay upright)
  function xf(svg, p) {
    p = P(p); var t = svgOf(svg).__xf;
    if (!t || !t.deg) return p;
    var dx = p.x - t.cx, dy = p.y - t.cy, c = Math.cos(t.a), s = Math.sin(t.a);
    return { x: t.cx + dx * c - dy * s, y: t.cy + dx * s + dy * c };
  }

  // ---- shared defs ----------------------------------------------------------------------------------------
  var uidN = 0;
  function uid(p) { return 'h-' + p + '-' + (++uidN); }
  function defs(svg) {
    svg = svgOf(svg);
    var d = svg.querySelector(':scope > defs');
    if (d) return d;
    d = el('defs', {}, null);
    svg.insertBefore(d, svg.firstChild);
    d.innerHTML = [
      // film grain: the background and the fire / smoke gradients only; shapes and roads stay clean
      '<pattern id="h-grain" width="64" height="64" patternUnits="userSpaceOnUse"><image href="' + grainTile().toDataURL('image/png') + '" width="64" height="64"/></pattern>',
      // fire: the brand's « Feu » ramp, hot core low, flickering
      '<radialGradient id="h-g-fire" cx=".5" cy=".62" r=".62" fx=".5" fy=".82">',
      '<stop offset="0" stop-color="#fffaf4"/><stop offset=".12" stop-color="#ffe6cf"/><stop offset=".26" stop-color="#ffbe78"/>',
      '<stop offset=".42" stop-color="#ff8a24"/><stop offset=".58" stop-color="#e2470f"/><stop offset=".74" stop-color="#a3220a"/>',
      '<stop offset=".9" stop-color="#4f0d04" stop-opacity=".7"/><stop offset="1" stop-color="#1a0402" stop-opacity="0"/>',
      '<animate attributeName="r" values=".56;.72;.6;.8;.64;.56" dur="2.3s" repeatCount="indefinite"/>',
      '<animate attributeName="fy" values=".82;.7;.86;.74;.8;.82" dur="1.7s" repeatCount="indefinite"/>',
      '<animate attributeName="cx" values=".5;.45;.54;.48;.5" dur="3.1s" repeatCount="indefinite"/></radialGradient>',
      // smoke: the brand's « Fumée » ramp, drifting and breathing
      '<radialGradient id="h-g-smoke" cx=".5" cy=".5" r=".6">',
      '<stop offset="0" stop-color="#ffffff"/><stop offset=".38" stop-color="#d6d3cc" stop-opacity=".85"/>',
      '<stop offset=".72" stop-color="#8f8d89" stop-opacity=".45"/><stop offset="1" stop-color="#3d3c3a" stop-opacity="0"/>',
      '<animate attributeName="cx" values=".32;.68;.32" dur="9s" repeatCount="indefinite"/>',
      '<animate attributeName="cy" values=".58;.4;.58" dur="7s" repeatCount="indefinite"/>',
      '<animate attributeName="r" values=".55;.78;.55" dur="6s" repeatCount="indefinite"/></radialGradient>',
      '<filter id="h-f-blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>',
      '<filter id="h-f-invert"><feColorMatrix type="matrix" values="-1 0 0 0 1 0 -1 0 0 1 0 0 -1 0 1 0 0 0 1 0"/></filter>'
    ].join('');
    return d;
  }
  // grain: a 128 px noise tile of faint dark and light specks, drawn once
  var tile = null;
  function grainTile() {
    if (tile) return tile;
    var n = 128, c = document.createElement('canvas'); c.width = c.height = n;
    var x = c.getContext('2d'), img = x.createImageData(n, n), d = img.data;
    for (var i = 0; i < d.length; i += 4) {
      var r = Math.random(), a = Math.abs(r - 0.5) * 2;
      d[i] = d[i + 1] = d[i + 2] = r > 0.5 ? 255 : 0;
      d[i + 3] = Math.round(a * a * 84);
    }
    x.putImageData(img, 0, 0);
    return (tile = c);
  }
  function grain(parent, d, opacity) { return el('path', { d: d, fill: 'url(#h-grain)', opacity: opacity }, parent); }

  // ---- ground: the dot-matrix map (canvas, drawn once per size) -----------------------------------------
  function hash(x, y) { var h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return h - Math.floor(h); }
  function vnoise(x, y) {
    var ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy, ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
    var a = hash(ix, iy), b = hash(ix + 1, iy), c = hash(ix, iy + 1), d = hash(ix + 1, iy + 1);
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
  }
  function fbm(x, y) { return 0.55 * vnoise(x, y) + 0.3 * vnoise(x * 2.1 + 5, y * 2.1 + 3) + 0.15 * vnoise(x * 4.3 + 9, y * 4.3 + 1); }
  function smooth(e0, e1, v) { var t = Math.max(0, Math.min(1, (v - e0) / (e1 - e0))); return t * t * (3 - 2 * t); }
  function ground(canvas, svg) {
    function draw() {
      var r = canvas.getBoundingClientRect(), w = Math.ceil(r.width), h = Math.ceil(r.height);
      if (!w || !h) return;
      var dpr = Math.min(global.devicePixelRatio || 1, 3);
      canvas.width = w * dpr; canvas.height = h * dpr;
      var ctx = canvas.getContext('2d');
      // soft, map-like patches on a coarse grid, aligned with the scene's turn, smoothed up, then grain
      var s = Math.min(w / W, h / H), ox = (w - W * s) / 2, oy = (h - H * s) / 2;
      var t = svg && svg.__xf, a = t ? -t.a : 0, ca = Math.cos(a), sa = Math.sin(a), cx = t ? t.cx : W / 2, cy = t ? t.cy : H / 2;
      var k = 6, sw = Math.ceil(w / k), sh = Math.ceil(h / k), lo = document.createElement('canvas');
      lo.width = sw; lo.height = sh;
      var lctx = lo.getContext('2d'), img = lctx.createImageData(sw, sh), d = img.data;
      for (var j = 0; j < sh; j++) {
        for (var i = 0; i < sw; i++) {
          var x = (i + 0.5) * k, y = (j + 0.5) * k, X = (x - ox) / s - cx, Y = (y - oy) / s - cy;
          var u = X * ca - Y * sa, v = X * sa + Y * ca;
          var tex = fbm(x * 0.02, y * 0.02), blot = smooth(0.42, 0.85, fbm(u * 0.011 + 7, v * 0.011 + 3));
          var val = (0.02 + 0.025 * hash(Math.floor(u / 96), Math.floor(v / 64)) + 0.07 * blot) * (0.55 + tex);
          var dx = X / W, dy = Y / H;
          val = Math.max(0, val * (1.1 - 1.5 * (dx * dx + dy * dy)));
          var g = Math.round(255 * val), o = (j * sw + i) * 4;
          d[o] = g; d[o + 1] = g; d[o + 2] = Math.round(g * 0.97); d[o + 3] = 255;
        }
      }
      lctx.putImageData(img, 0, 0);
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(lo, 0, 0, canvas.width, canvas.height);
      ctx.fillStyle = ctx.createPattern(grainTile(), 'repeat');     // grain at device pixels
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    draw();
    var tm;
    global.addEventListener('resize', function () { clearTimeout(tm); tm = setTimeout(draw, 120); });
    return { redraw: draw };
  }

  // ---- frame: the whole screen is the scheme --------------------------------------------------------------
  function frame(root, opts) {
    opts = opts || {};
    root = root || document.body;
    t0 = Date.now(); seq = 0; drawn = false;
    if (opts.title) document.title = opts.title;
    root.innerHTML = '';
    var screen = document.createElement('div'); screen.className = 'h-screen'; root.appendChild(screen);
    var canvas = document.createElement('canvas'); canvas.className = 'h-ground'; screen.appendChild(canvas);
    var svg = el('svg', { 'class': 'h-svg', viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'xMidYMid meet' }, screen);
    defs(svg); layer(svg, 'base');
    var card = document.createElement('div'); card.className = 'h-panel'; screen.appendChild(card);
    requestAnimationFrame(function () { svg.__ground = ground(canvas, svg); });
    return { svg: svg, W: W, H: H, panel: function (lines) { panel(card, lines); }, clear: function () { clear(svg); card.innerHTML = ''; } };
  }
  // panel: the instruction card on the right. A few imperative lines, the first one bigger. Nothing else.
  // lines: [{text, tone}] — plain words, no pictograms. Text never blinks: it must stay readable
  function panel(card, lines) {
    card.innerHTML = '';
    lines = (lines || []).filter(Boolean);
    if (lines.length > 4) console.warn('Halo: more than 4 instructions, extra dropped (RULES.md 3)');
    lines.slice(0, 4).forEach(function (l, i) {
      if (String(l.text).length > 18) console.warn('Halo: instruction too long for one line (RULES.md 3): ' + l.text);
      var row = document.createElement('div');
      row.className = 'h-step t-' + (l.tone || 'ink') + (i === 0 ? ' h-lead' : '');
      var t = document.createElement('span'); t.textContent = l.text; row.appendChild(t);
      card.appendChild(row);
    });
    // no fade: an instruction is readable at once (and WebKit could leave a re-styled fade stuck at 0)
  }
  // icon: a pictogram as inline SVG, for HTML
  function icon(kind, t) {
    var s = el('svg', { viewBox: '-13 -13 26 26', width: 26, height: 26 }, null);
    iconPath(s, kind, tone(t || KIND_TONE[kind] || 'ink'), 1);
    return s;
  }
  function clear(svg) {
    if (seq > 0) drawn = true;                         // something was drawn already: this is a redraw
    svgOf(svg).__tags = [];
    LAYERS.forEach(function (n) { var g = layer(svg, n); while (g.firstChild) g.removeChild(g.firstChild); });
  }

  // ---- structure (scene coordinates) ---------------------------------------------------------------------
  // block: a footprint. state: normal | target (flat white) | inferred | dim. Flat fills only.
  function block(svg, a, opts) {
    opts = opts || {};
    var s = area(a), b = s.box, state = opts.state || 'normal', g = el('g', { 'class': 'h-block' }, layer(svg, 'base'));
    if (state === 'target') {
      var lit = fadeIn(el('g', {}, g));
      el('path', { d: s.d, fill: '#ffffff' }, lit);                  // flat white: no glow, no gradient, no texture
      drawIn(el('path', { d: s.d, fill: 'none', stroke: C.ink, 'stroke-width': 2.4, 'stroke-linejoin': 'round' }, g));
    } else if (state === 'inferred') {
      el('path', { d: s.d, fill: '#0b0b0b' }, g);
      el('path', { d: s.d, fill: 'none', stroke: C.line, 'stroke-width': 2.2, 'stroke-dasharray': '0 6', 'stroke-linecap': 'round' }, g);
    } else {
      var dim = state === 'dim';
      el('path', { d: s.d, fill: dim ? '#060606' : '#141413' }, g);
      drawIn(el('path', { d: s.d, fill: 'none', stroke: dim ? C.mute : C.line, 'stroke-width': dim ? 1.8 : 2.2, 'stroke-linejoin': 'round' }, g));
    }
    if (opts.label) label(svg, anchor(b, opts.at || 'ne'), opts.label, { tone: opts.tone, big: opts.big, source: opts.source });
    if (opts.tap) tappable(g, opts.tap);
    return { g: g, box: b, c: s.c };
  }

  // street: a band of brighter dots with dotted kerbs
  function street(svg, a, opts) {
    opts = opts || {};
    var p0 = P(a.from), p1 = P(a.to), w = a.width || 46, u = unit(sub(p1, p0)), n = { x: -u.y * w / 2, y: u.x * w / 2 };
    var g = el('g', { 'class': 'h-street' }, layer(svg, 'base'));
    var pts = [{ x: p0.x + n.x, y: p0.y + n.y }, { x: p1.x + n.x, y: p1.y + n.y }, { x: p1.x - n.x, y: p1.y - n.y }, { x: p0.x - n.x, y: p0.y - n.y }];
    var s = area(pts);
    el('path', { d: s.d, fill: '#2b2a28' }, g);
    [[pts[0], pts[1]], [pts[3], pts[2]]].forEach(function (k) {
      el('path', { d: 'M' + r1(k[0].x) + ',' + r1(k[0].y) + 'L' + r1(k[1].x) + ',' + r1(k[1].y), stroke: '#5a5955', 'stroke-width': 1.6 }, g);
    });
    if (opts.label) label(svg, { x: p0.x + (p1.x - p0.x) * (opts.labelAt || 0.5), y: p0.y + (p1.y - p0.y) * (opts.labelAt || 0.5) }, opts.label, { tone: 'dim' });
    return { g: g };
  }

  // facade: front elevation, one band per level, windows as dot rows, front entrances as doors
  function facade(svg, opts) {
    var b = opts.box || { x: 300, y: 20, w: 280, h: 360 }, levels = (opts.levels || []).slice().sort(function (p, q) { return q.level - p.level; });
    var bh = b.h / (levels.length || 1), g = el('g', { 'class': 'h-facade' }, layer(svg, 'base')), bands = {};
    el('rect', { x: b.x, y: b.y, width: b.w, height: b.h, fill: '#141413' }, g);
    levels.forEach(function (lv, i) {
      var y = b.y + i * bh;
      bands[lv.level] = { x: b.x, y: y, w: b.w, h: bh, cx: b.x + b.w / 2, cy: y + bh / 2 };
      el('rect', { x: b.x + 14, y: y + bh * 0.3, width: b.w - 28, height: bh * 0.38, fill: '#2b2a28' }, g);
      if (i) el('path', { d: 'M' + b.x + ',' + y + 'h' + b.w, stroke: C.mute, 'stroke-width': 1.8 }, g);
      label(svg, { x: b.x - 10, y: y + bh / 2 }, lv.label, { align: 'end', tone: 'dim' });
    });
    drawIn(el('path', { d: area(b).d, fill: 'none', stroke: C.line, 'stroke-width': 2.2 }, g));
    (opts.entrances || []).filter(function (e) { return e.side === 'front'; }).forEach(function (e, i, all) {
      var x = b.x + b.w * (i + 1) / (all.length + 1);
      el('rect', { x: x - 14, y: b.y + b.h - bh * 0.7, width: 28, height: bh * 0.7, fill: '#000', stroke: C.ink, 'stroke-width': 2.4 }, g);
      label(svg, { x: x, y: b.y + b.h + 20 }, e.id, {});
    });
    return { g: g, band: function (lv) { return bands[lv]; } };
  }

  // focusLevels: the levels where something is going on. Seraph's building.levels[].focus when it sends it; else a
  // fire/smoke hazard, a person still inside, an engaged team, or a route's target on that level. Others are greyed.
  function focusLevels(state) {
    var b = (state && state.building) || {}, levels = b.levels || [], out = {};
    if (levels.some(function (l) { return typeof l.focus === 'boolean'; })) {
      levels.forEach(function (l) { if (l.focus) out[l.level] = true; });
      return out;
    }
    (b.hazards || []).forEach(function (h) { if ((h.kind === 'fire' || h.kind === 'smoke') && h.where && h.where.level != null) out[h.where.level] = true; });
    ((state && state.occupants) || []).forEach(function (o) { if (o.status !== 'safe_outside' && o.level != null) out[o.level] = true; });
    (((state && state.crew) || {}).teams || []).forEach(function (t) { if (t.status === 'engaged' && t.location && t.location.level != null) out[t.location.level] = true; });
    ((state && state.routes) || []).forEach(function (r) {
      var to = String(r.to || ''), room = to.indexOf('room:') === 0 && byId(b.rooms, to.slice(5));
      if (to.indexOf('level:') === 0) out[+to.slice(6)] = true;
      else if (room) out[room.level] = true;
    });
    return out;
  }

  // floorStack: side section, one band per level (top = highest), stair shafts at the sides.
  // focus ({level: true} from Halo.focusLevels): a level with nothing special is grey, no tag colour, no fill
  function floorStack(svg, opts) {
    var b = opts.box || { x: 150, y: 16, w: 574, h: 338 }, levels = (opts.levels || []).slice().sort(function (p, q) { return q.level - p.level; });
    var n = levels.length || 1, gap = 7, bh = (b.h - gap * (n - 1)) / n, sw = 38;
    var g = el('g', { 'class': 'h-stack' }, layer(svg, 'base')), bands = {}, shafts = {}, stairs = opts.stairs || [];
    var left = stairs.some(function (s) { return s.side !== 'right'; }) ? sw + 8 : 0, right = stairs.some(function (s) { return s.side === 'right'; }) ? sw + 8 : 0;
    levels.forEach(function (lv, i) {
      var y = b.y + i * (bh + gap), hi = opts.highlight === lv.level, off = opts.focus && !opts.focus[lv.level];
      var band = { x: b.x + left, y: y, w: b.w - left - right, h: bh, off: !!off };
      band.cx = band.x + band.w / 2; band.cy = y + bh / 2;
      bands[lv.level] = band;
      block(svg, band, { state: hi ? 'target' : off ? 'dim' : 'normal' });
      label(svg, { x: b.x - 10, y: band.cy }, lv.label, { align: 'end', tone: off ? 'dim' : 'ink' });
    });
    stairs.forEach(function (s) {
      var x = s.side === 'right' ? b.x + b.w - sw : b.x, box = { x: x, y: b.y, w: sw, h: b.h }, bad = s.status === 'smoke' || s.status === 'blocked';
      shafts[s.id] = box;
      el('rect', { x: x, y: b.y, width: sw, height: b.h, fill: '#050505' }, g);
      for (var y = b.y + 8; y < b.y + b.h - 8; y += 12) {
        el('path', { d: 'M' + (x + 8) + ',' + (y + 8) + 'h7v-6h7v-6h7', fill: 'none', stroke: bad ? C.mute : C.dim, 'stroke-width': 1.5 }, g);
      }
      drawIn(el('path', { d: area(box).d, fill: 'none', stroke: bad ? C.warn : C.line, 'stroke-width': 2.2,
        'stroke-dasharray': s.source && s.source.confirmed === false ? '0 6' : null, 'stroke-linecap': 'round' }, g));
      if (s.status === 'smoke') smoke(svg, box, { outline: false });
      label(svg, { x: x + sw / 2, y: b.y + b.h + 6 }, s.id, { tone: bad ? 'warn' : 'ink', valign: 'top' });
    });
    return { g: g, band: function (lv) { return bands[lv]; }, shaft: function (id) { return shafts[id]; } };
  }

  // plan: a level plan; zones and points on the 0–1000 image frame, cropped to what matters, fitted to the box
  function plan(svg, opts) {
    var box = opts.box || { x: 20, y: 14, w: W - 40, h: H - 28 }, zones = opts.zones || [], points = opts.points || [];
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    function grow(p) { p = P(p); x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y); }
    zones.forEach(function (z) { (z.zone || z.points || []).forEach(grow); });
    points.forEach(function (p) { grow(p.point || p); });
    var crop = opts.crop || (x0 < Infinity ? { x0: x0 - 40, y0: y0 - 40, x1: x1 + 40, y1: y1 + 40 } : { x0: 0, y0: 0, x1: 1000, y1: 1000 });
    var k = Math.min(box.w / (crop.x1 - crop.x0), box.h / (crop.y1 - crop.y0));
    var ox = box.x + (box.w - (crop.x1 - crop.x0) * k) / 2, oy = box.y + (box.h - (crop.y1 - crop.y0) * k) / 2;
    function proj(p) { p = P(p.point || p); return { x: ox + (p.x - crop.x0) * k, y: oy + (p.y - crop.y0) * k }; }
    var g = el('g', { 'class': 'h-plan' }, layer(svg, 'base'));
    var frameBox = { x: ox, y: oy, w: (crop.x1 - crop.x0) * k, h: (crop.y1 - crop.y0) * k };
    // a dark backdrop only under a plan photo (opts.frame); otherwise the rooms sit on the ground, no box
    if (opts.frame || opts.image_url) el('rect', { x: frameBox.x, y: frameBox.y, width: frameBox.w, height: frameBox.h, fill: '#000', opacity: 0.88 }, g);
    if (opts.image_url) {
      var o = proj({ x: 0, y: 0 }), clipId = uid('clip'), cp = el('clipPath', { id: clipId }, defs(svg));
      el('rect', { x: frameBox.x, y: frameBox.y, width: frameBox.w, height: frameBox.h }, cp);
      el('image', { href: opts.image_url, x: o.x, y: o.y, width: 1000 * k, height: 1000 * k, preserveAspectRatio: 'none',
        opacity: opts.dim === undefined ? 0.22 : opts.dim, filter: 'url(#h-f-invert)', 'clip-path': 'url(#' + clipId + ')' }, g);
    }
    var out = {};
    zones.forEach(function (z) {
      out[z.id] = block(svg, (z.zone || z.points).map(proj), { state: z.state, label: z.label, at: z.at || 'n', big: z.big, tap: z.tap, glow: z.glow });
    });
    return { g: g, project: proj, zone: function (id) { return out[id]; }, k: k, box: frameBox };
  }

  // ---- hazards: animated halftone gradients --------------------------------------------------------------
  function hazard(svg, a, opts, kind) {
    opts = opts || {};
    var s = area(a), b = s.box, fireish = kind === 'fire', g = el('g', { 'class': 'h-' + kind }, layer(svg, 'hazard'));
    var id = uid('clip'), cp = el('clipPath', { id: id }, defs(svg));
    el('path', { d: s.d }, cp);
    var inner = loop(el('g', { 'clip-path': 'url(#' + id + ')' }, g), fireish ? 'h-flicker' : 'h-breathe');
    var grad = fireish ? 'url(#h-g-fire)' : 'url(#h-g-smoke)';
    if (fireish) el('rect', { x: b.x, y: b.y, width: b.w, height: b.h, fill: '#1a0402' }, inner);
    el('rect', { x: b.x, y: b.y, width: b.w, height: b.h, fill: grad, opacity: fireish ? 1 : 0.85 }, inner);
    grain(inner, area(b).d);
    if (!s.circle && opts.outline !== false) {
      drawIn(el('path', { d: s.d, fill: 'none', stroke: fireish ? C.fire : C.warn, 'stroke-width': fireish ? 2.6 : 2.4,
        'stroke-dasharray': fireish ? null : '0 6', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, g));
    }
    fadeIn(g);
    if (opts.label) label(svg, anchor(b, opts.at || 'n'), opts.label, { tone: fireish ? 'fire' : 'warn', source: opts.source });
    return { g: g, box: b, c: s.c };
  }
  function fire(svg, a, opts) { return hazard(svg, a, opts, 'fire'); }
  function smoke(svg, a, opts) { return hazard(svg, a, opts, 'smoke'); }

  // ---- route arrow: draws itself, then black chevrons flow along it toward the tip ----------------------
  function arrow(svg, pathPoints, opts) {
    opts = opts || {};
    var pts = pathPoints.map(P);
    if (pts.length < 2) return null;
    var col = tone(opts.tone || 'ink'), w = opts.width || 7, inferred = opts.inferred || (opts.source && opts.source.confirmed === false);
    var g = el('g', { 'class': 'h-arrow' }, layer(svg, 'route'));
    var target = pts[pts.length - 1], dir = unit(sub(target, pts[pts.length - 2])), hl = 22, hw = 15;
    var end = opts.gap ? { x: target.x - dir.x * opts.gap, y: target.y - dir.y * opts.gap } : target;   // stop short of a marker
    var base = { x: end.x - dir.x * hl, y: end.y - dir.y * hl };
    var d = roundPath(pts.slice(0, -1).concat([base]), opts.radius || 20);
    var delay = intro() ? nextDelay() : 0;
    el('path', { d: d, fill: 'none', stroke: '#000', 'stroke-width': w + 10, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', opacity: 0.9 }, g);
    var main = el('path', { d: d, fill: 'none', stroke: col, 'stroke-width': w, 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
      'stroke-dasharray': inferred ? '0 ' + (w + 8) : null }, g);
    if (!inferred) drawIn(main, delay);
    fadeIn(el('path', {
      d: 'M' + r1(end.x) + ',' + r1(end.y) + 'L' + r1(base.x - dir.y * hw) + ',' + r1(base.y + dir.x * hw) + 'L' + r1(base.x + dir.y * hw) + ',' + r1(base.y - dir.x * hw) + 'Z',
      fill: col, stroke: '#000', 'stroke-width': 3, 'stroke-linejoin': 'round', 'paint-order': 'stroke'
    }, g), delay + 0.8);
    fadeIn(el('circle', { cx: pts[0].x, cy: pts[0].y, r: 7, fill: '#000', stroke: col, 'stroke-width': 3 }, g), delay);
    if (opts.animate !== false) {
      var L = polyLength(pts), dur = Math.max(1.6, L / (opts.speed || 75)), n = Math.max(2, Math.min(8, Math.round(L / 70)));
      for (var i = 0; i < n; i++) {
        var ch = el('g', {}, g), begin = (-i * dur / n).toFixed(2) + 's';
        el('path', { d: 'M-5,-7L3,0L-5,7', fill: 'none', stroke: '#000', 'stroke-width': 3.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, ch);
        el('animateMotion', { path: d, rotate: 'auto', dur: dur.toFixed(2) + 's', begin: begin, repeatCount: 'indefinite' }, ch);
        el('animate', { attributeName: 'opacity', values: '0;1;1;0', keyTimes: '0;.08;.9;1', dur: dur.toFixed(2) + 's', begin: begin, repeatCount: 'indefinite' }, ch);
      }
    }
    if (opts.ping) ping(svg, target, { tone: opts.tone || 'ink', r: 26 });
    return { g: g, d: d };
  }

  // ---- points: pictograms, blinking triangles, pings, cross-outs (upright, scene coordinates in) --------
  var ICONS = {
    door: 'M-6,9V-9H6V9M-9,9H9M2.5,0.5h0.1',
    entrance: 'M-6,9V-9H6V9M-9,9H9M2.5,0.5h0.1',
    hydrant: 'M-4,9V-2Q-4,-7 0,-7Q4,-7 4,-2V9M-7,9H7M-4,1H-8M4,1H8M0,-7V-10',
    truck: 'M-10,5V-4H3V5M3,-1H7L10,2V5H-10M-9,-7H2',
    person: 'M0,-3.5a3,3 0 1,0 0.01,0M-6,9Q-6,0 0,0Q6,0 6,9',
    wheelchair: 'M-2,-6.5a2.5,2.5 0 1,0 0.01,0M-2,-3V3H5L7,9M-6,0a6,6 0 1,0 9,6',
    team: 'M-9,4Q-9,-8 0,-8Q9,-8 9,4ZM-11,4H11M0,-8V4M-4,8H4',
    stair: 'M-9,9H-5V4H-1V-1H3V-6H7V-9H9',
    elevator: 'M-8,-9H8V9H-8ZM-3,-2L0,-6L3,-2ZM-3,2L0,6L3,2Z',
    riser: 'M-2,10V-8H2V10M2,-4H7M2,4H7M-2,-8V-10H2V-8',
    gas: 'M-8,-3L8,7V-3L-8,7ZM0,2V-8M-4,-8H4',
    elec: 'M2,-10L-6,2H0L-2,10L6,-2H0Z',
    fire: 'M0,-10C6,-3 8,1 6,5C4,9 -4,9 -6,5C-8,1 -4,-3 -2,-6C-1,-2 1,-1 2,-2C3,-5 1,-8 0,-10Z',
    smoke: 'M-9,-5Q-6,-8 -3,-5T3,-5T9,-5M-9,0Q-6,-3 -3,0T3,0T9,0M-9,5Q-6,2 -3,5T3,5T9,5',
    unknown: 'M-4,-4Q-4,-8 0,-8Q4,-8 4,-4Q4,-1 0,0V3M0,7.5h0.1'
  };
  function iconPath(parent, kind, col, scale) {
    return el('path', { d: ICONS[kind] || ICONS.unknown, fill: 'none', stroke: col, 'stroke-width': 2.3, 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
      transform: scale && scale !== 1 ? 'scale(' + scale + ')' : null, 'vector-effect': 'non-scaling-stroke' }, parent);
  }
  // marker(svg, kind, point, label, {tone, ring, ping, blink, crossed, source, at, r, big, tap})
  function marker(svg, kind, point, text, opts) {
    opts = opts || {};
    var p = opts.screen ? P(point) : xf(svg, point), t = opts.tone || KIND_TONE[kind] || 'ink', col = tone(t), r = opts.r || 16;
    if (opts.ping) ping(svg, p, { tone: opts.ring || t, r: r + 4, screen: true });
    var g = el('g', { 'class': 'h-marker', transform: 'translate(' + r1(p.x) + ',' + r1(p.y) + ')' }, layer(svg, 'mark'));
    var inferred = opts.inferred || (opts.source && opts.source.confirmed === false);
    el('circle', { r: r, fill: '#000', stroke: opts.ring ? tone(opts.ring) : col, 'stroke-width': opts.ring ? 3.2 : 2.2,
      'stroke-dasharray': inferred ? '0 6' : null, 'stroke-linecap': 'round' }, g);
    iconPath(g, kind, col, r / 14);
    if (opts.blink) loop(g, opts.blink === 'fast' ? 'h-blink-fast' : 'h-blink');
    fadeIn(g);
    if (opts.crossed) cross(svg, p, { size: r + 4, screen: true });
    if (text !== undefined && text !== null && text !== '') {
      var at = opts.at || 'e', off = r + 7;
      var lp = { x: p.x + (at === 'e' ? off : at === 'w' ? -off : 0), y: p.y + (at === 's' ? off : at === 'n' ? -off : 0) };
      label(svg, lp, text, { screen: true, tone: opts.labelTone, big: opts.big, source: opts.source,
        align: at === 'e' ? 'start' : at === 'w' ? 'end' : 'middle', valign: at === 's' ? 'top' : at === 'n' ? 'bottom' : 'middle' });
    }
    if (opts.tap) tappable(g, opts.tap, r + 14);
    return g;
  }
  // warn(svg, point, {level: 'warn'|'danger', size}): the blinking triangle
  function warn(svg, point, opts) {
    opts = opts || {};
    var p = opts.screen ? P(point) : xf(svg, point), danger = opts.level === 'danger', col = danger ? C.fire : C.warn, s = opts.size || 38, h = s * 0.866;
    if (danger) ping(svg, { x: p.x, y: p.y + h * 0.08 }, { tone: 'fire', r: s * 0.55, screen: true });
    var g = el('g', { 'class': 'h-warn', transform: 'translate(' + r1(p.x) + ',' + r1(p.y) + ')' }, layer(svg, 'mark'));
    var blink = loop(el('g', {}, g), danger ? 'h-blink-fast' : 'h-blink');
    el('path', { d: 'M0,' + r1(-h * 0.62) + 'L' + s / 2 + ',' + r1(h * 0.38) + 'L' + -s / 2 + ',' + r1(h * 0.38) + 'Z', fill: '#000', stroke: col, 'stroke-width': 3, 'stroke-linejoin': 'round' }, blink);
    el('path', { d: 'M0,' + r1(-h * 0.26) + 'V' + r1(h * 0.04), stroke: col, 'stroke-width': 3.4, 'stroke-linecap': 'round' }, blink);
    el('circle', { cy: r1(h * 0.2), r: 2.3, fill: col }, blink);
    fadeIn(g);
    return g;
  }
  // ping: two rings expanding from a point, the « here » signal
  function ping(svg, point, opts) {
    opts = opts || {};
    var p = opts.screen ? P(point) : xf(svg, point), col = tone(opts.tone || 'ink'), r = opts.r || 20, dur = opts.dur || 2;
    var g = el('g', { 'class': 'h-ping' }, layer(svg, 'mark'));
    for (var i = 0; i < 2; i++) {
      [['#000', 5.5], [col, 2.4]].forEach(function (st) {
        var c = el('circle', { cx: r1(p.x), cy: r1(p.y), r: r * 0.5, fill: 'none', stroke: st[0], 'stroke-width': st[1], opacity: 0 }, g);
        el('animate', { attributeName: 'r', values: r * 0.5 + ';' + r * 2, dur: dur + 's', begin: (-i * dur / 2) + 's', repeatCount: 'indefinite' }, c);
        el('animate', { attributeName: 'opacity', values: '.9;0', dur: dur + 's', begin: (-i * dur / 2) + 's', repeatCount: 'indefinite' }, c);
      });
    }
    return g;
  }
  // cross: crossed out (an entrance not to use)
  function cross(svg, point, opts) {
    opts = opts || {};
    var p = opts.screen ? P(point) : xf(svg, point), s = opts.size || 22, col = tone(opts.tone || 'fire');
    var g = el('g', { 'class': 'h-cross', transform: 'translate(' + r1(p.x) + ',' + r1(p.y) + ')' }, layer(svg, 'mark'));
    var d1 = 'M' + -s + ',' + -s + 'L' + s + ',' + s, d2 = 'M' + s + ',' + -s + 'L' + -s + ',' + s;
    [d1, d2].forEach(function (d) { el('path', { d: d, stroke: '#000', 'stroke-width': 11, 'stroke-linecap': 'round' }, g); });
    var delay = intro() ? nextDelay() + 0.3 : 0;
    drawIn(el('path', { d: d1, stroke: col, 'stroke-width': 5, 'stroke-linecap': 'round' }, g), delay);
    drawIn(el('path', { d: d2, stroke: col, 'stroke-width': 5, 'stroke-linecap': 'round' }, g), delay + 0.15);
    return g;
  }
  // wind: chevrons flowing the way the wind blows (dir_deg = where it comes from; north = scene up)
  function wind(svg, point, w) {
    if (!w) return null;
    var p = P(point), to = (w.dir_deg + 180) * Math.PI / 180, u = { x: Math.sin(to), y: -Math.cos(to) }, L = 60;
    var g = el('g', { 'class': 'h-wind' }, layer(svg, 'route'));
    var d = 'M' + r1(p.x - u.x * L / 2) + ',' + r1(p.y - u.y * L / 2) + 'L' + r1(p.x + u.x * L / 2) + ',' + r1(p.y + u.y * L / 2);
    el('path', { d: d, stroke: C.dim, 'stroke-width': 2.2, 'stroke-dasharray': '0 6', 'stroke-linecap': 'round' }, g);
    for (var i = 0; i < 3; i++) {
      var ch = el('g', {}, g);
      el('path', { d: 'M-6,-8L3,0L-6,8', fill: 'none', stroke: C.ink, 'stroke-width': 2.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, ch);
      el('animateMotion', { path: d, rotate: 'auto', dur: '2.4s', begin: (-i * 0.8) + 's', repeatCount: 'indefinite' }, ch);
      el('animate', { attributeName: 'opacity', values: '0;1;1;0', keyTimes: '0;.2;.75;1', dur: '2.4s', begin: (-i * 0.8) + 's', repeatCount: 'indefinite' }, ch);
    }
    return g;
  }
  // north: a small arrow in a screen corner, turned with the scene
  function north(svg, point) {
    var p = P(point || { x: AREA.x + AREA.w - 12, y: 30 }), t = svgOf(svg).__xf, deg = t ? t.deg : 0;   // the shell's top bar owns the top-right corner
    var g = el('g', { transform: 'translate(' + p.x + ',' + p.y + ') rotate(' + deg + ')' }, layer(svg, 'mark'));
    el('path', { d: 'M0,-14L7,9L0,4L-7,9Z', fill: C.dim }, g);
    return g;
  }

  // ---- labels: the black tags of the reference (« N.564 ») -----------------------------------------------
  function label(svg, point, text, opts) {
    opts = opts || {};
    var p = opts.screen ? P(point) : xf(svg, point), size = opts.size || (opts.big ? 30 : 22), pad = opts.big ? 10 : 8, h = size + (opts.big ? 14 : 12);
    var g = el('g', { 'class': 'h-label' }, layer(svg, 'label'));
    var rect = el('rect', { fill: C.panel, 'fill-opacity': 0.94 }, g);
    var t = el('text', { 'font-size': size, 'font-weight': opts.big ? 700 : 600, fill: tone(opts.tone || 'ink'), 'letter-spacing': '.03em', 'dominant-baseline': 'central' }, g);
    var inferred = opts.source && opts.source.confirmed === false;
    t.textContent = (inferred ? '~' : '') + String(text).toUpperCase();
    var w = 0;
    try { w = t.getComputedTextLength(); } catch (e) { /* not laid out */ }
    if (!w) w = String(t.textContent).length * size * 0.62;
    var bw = w + pad * 2;
    var x = opts.align === 'start' ? p.x : opts.align === 'end' ? p.x - bw : p.x - bw / 2;
    var y = opts.valign === 'top' ? p.y : opts.valign === 'bottom' ? p.y - h : p.y - h / 2;
    x = Math.max(4, Math.min(W - bw - 4, x)); y = Math.max(4, Math.min(H - h - 4, y));
    // never on top of another tag: slide down, up, right, left until free; give up (drop it) past MAX_LABELS
    var root = svgOf(svg), placed = root.__tags || (root.__tags = []);
    if (placed.length >= MAX_LABELS) { g.remove(); return null; }
    var hit = function (a) { return placed.some(function (q) { return a.x < q.x + q.w + 3 && q.x < a.x + a.w + 3 && a.y < q.y + q.h + 3 && q.y < a.y + a.h + 3; }); };
    var box = { x: x, y: y, w: bw, h: h };
    for (var k = 1; hit(box) && k < 6; k++) {
      var tries = [[0, k * (h + 4)], [0, -k * (h + 4)], [k * (bw / 2 + 6), 0], [-k * (bw / 2 + 6), 0]];
      for (var t = 0; t < tries.length; t++) {
        var nb = { x: Math.max(4, Math.min(W - bw - 4, x + tries[t][0])), y: Math.max(4, Math.min(H - h - 4, y + tries[t][1])), w: bw, h: h };
        if (!hit(nb)) { box = nb; break; }
      }
    }
    if (hit(box)) { g.remove(); return null; }
    placed.push(box); x = box.x; y = box.y;
    rect.setAttribute('x', r1(x)); rect.setAttribute('y', r1(y)); rect.setAttribute('width', r1(bw)); rect.setAttribute('height', h);
    if (inferred) { rect.setAttribute('stroke', C.warn); rect.setAttribute('stroke-width', 2); rect.setAttribute('stroke-dasharray', '0 6'); rect.setAttribute('stroke-linecap', 'round'); }
    t.setAttribute('x', r1(x + pad)); t.setAttribute('y', r1(y + h / 2 + 1));
    fadeIn(g);
    return g;
  }
  // tag: a source tag on the stage (dim; amber and dotted when inferred)
  function tag(svg, source, point) {
    if (!source) return null;
    return label(svg, point, source.label, { tone: source.confirmed === false ? 'warn' : 'dim', source: source });
  }
  // teamCard: the team as one tag, « B1 · R+3 »
  function teamCard(svg, team, point, opts) {
    opts = opts || {};
    var where = team.location ? (opts.levelLabel ? opts.levelLabel(team.location.level) : team.location.level) : '';
    return label(svg, point, team.id + (where !== '' ? ' · ' + where : ''), { big: opts.big, screen: opts.screen });
  }

  // ---- air: the exit countdown dial ---------------------------------------------------------------------
  // white > T-5 min, amber ≤ T-5, red at T-0 with « SORTEZ »: the ticks blink, the numbers never; vibrates at each step
  function countdown(svg, exitBy, opts) {
    opts = opts || {};
    var c = P(opts.center || { x: W / 2, y: H / 2 }), R = opts.r || 172, N = 60;
    var end = new Date(exitBy).getTime(), start = opts.start ? new Date(opts.start).getTime() : end - 20 * 60000;
    var g = el('g', { 'class': 'h-countdown' }, layer(svg, 'mark')), ticks = [];
    var ring = el('g', {}, g);                         // the ticks: the only part that blinks at T-0
    el('circle', { cx: c.x, cy: c.y, r: R + 4, fill: '#000', opacity: 0.85 }, g);
    for (var i = 0; i < N; i++) {
      var a = (i / N) * 2 * Math.PI - Math.PI / 2, ca = Math.cos(a), sa = Math.sin(a), major = i % 5 === 0, r0 = R - (major ? 26 : 16);
      ticks.push(el('path', { d: 'M' + r1(c.x + ca * r0) + ',' + r1(c.y + sa * r0) + 'L' + r1(c.x + ca * R) + ',' + r1(c.y + sa * R),
        stroke: C.mute, 'stroke-width': major ? 5 : 4, 'stroke-linecap': 'round' }, ring));
    }
    var head = el('circle', { r: 7, fill: C.ink }, g);
    var num = el('text', { x: c.x, y: c.y + 4, 'text-anchor': 'middle', 'dominant-baseline': 'central', 'font-size': opts.size || 112,
      'font-weight': 700, fill: C.ink, 'letter-spacing': '-.02em', style: 'font-variant-numeric: tabular-nums' }, g);
    var cap = el('text', { x: c.x, y: c.y + 74, 'text-anchor': 'middle', 'font-size': 24, 'font-weight': 700, fill: C.fire, 'letter-spacing': '.12em' }, g);
    if (opts.label) label(svg, { x: c.x, y: c.y - 70 }, opts.label, { screen: true });
    fadeIn(g);
    var step = -1;
    function update() {
      var left = end - Date.now(), frac = Math.max(0, Math.min(1, left / (end - start)));
      var st = left <= 0 ? 2 : left <= 5 * 60000 ? 1 : 0, col = st === 2 ? C.fire : st === 1 ? C.warn : C.ink, lit = Math.ceil(frac * N);
      for (var i = 0; i < N; i++) ticks[i].setAttribute('stroke', i < lit ? col : C.mute);
      var a = frac * 2 * Math.PI - Math.PI / 2;
      head.setAttribute('cx', r1(c.x + Math.cos(a) * (R + 13))); head.setAttribute('cy', r1(c.y + Math.sin(a) * (R + 13))); head.setAttribute('fill', col);
      var s = Math.abs(Math.round(left / 1000));
      num.textContent = (left < 0 ? '+' : '') + pad2(Math.floor(s / 60)) + ':' + pad2(s % 60);
      num.setAttribute('fill', col);
      cap.textContent = st === 2 ? 'SORTEZ' : '';
      if (st === 2 && !ring.classList.contains('h-blink-fast')) loop(ring, 'h-blink-fast');
      if (step !== -1 && st > step) vibrate(st === 2 ? [400, 150, 400, 150, 400] : [250, 120, 250]);
      step = st;
    }
    update();
    var timer = setInterval(update, 250);
    return { g: g, stop: function () { clearInterval(timer); } };
  }

  // ---- messaging: iframe (web shell) or React Native WebView (native shell) ------------------------------
  var latest = null;
  function parse(e) {
    var m = e.data;
    if (typeof m === 'string') { try { m = JSON.parse(m); } catch (err) { return null; } }   // RN WebView sends strings
    return m && typeof m === 'object' ? m : null;
  }
  function listen(fn) { global.addEventListener('message', fn); document.addEventListener('message', fn); }
  function onState(fn) {
    listen(function (e) { var m = parse(e); if (m && m.type === 'seraph:state' && m.state) { latest = m.state; fn(m.state); } });
    if (latest) fn(latest);
  }
  function onAlert(fn) { listen(function (e) { var m = parse(e); if (m && m.type === 'seraph:alert') fn(m.alert); }); }
  function post(msg) {
    try {
      if (global.ReactNativeWebView) global.ReactNativeWebView.postMessage(JSON.stringify(msg));
      else if (global.parent && global.parent !== global) global.parent.postMessage(msg, '*');
    } catch (e) { /* no shell */ }
  }
  // a view that breaks says so to the shell (logged there), instead of silently drawing half a scheme
  global.addEventListener('error', function (e) { post({ type: 'seraph:error', message: String(e.message), line: e.lineno, col: e.colno }); });
  function ready(viewId) { post({ type: 'seraph:ready', view_id: viewId || document.documentElement.getAttribute('data-view-id') || '' }); }
  function tap(target) { vibrate(30); post({ type: 'seraph:tap', target: target }); }
  function tappable(g, target, r) {
    g.style.cursor = 'pointer';
    if (r) el('circle', { r: r, fill: 'transparent' }, g);
    g.addEventListener('click', function () { tap(target); });
  }
  function vibrate(p) { try { if (navigator.vibrate) navigator.vibrate(p); } catch (e) { /* iOS: the shell vibrates */ } }

  // ---- helpers ------------------------------------------------------------------------------------------
  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function hhmm(d) { return pad2(d.getHours()) + ':' + pad2(d.getMinutes()); }
  function byId(list, id) { return (list || []).filter(function (x) { return x.id === id; })[0] || null; }
  function levelLabel(state, n) {
    var l = ((state && state.building && state.building.levels) || []).filter(function (x) { return x.level === n; })[0];
    return l ? l.label : n == null ? '' : 'N' + n;
  }

  global.Halo = {
    W: W, H: H, AREA: AREA, C: C, ICONS: ICONS,
    frame: frame, clear: clear, scene: scene, layer: layer, xf: xf,
    street: street, block: block, facade: facade, floorStack: floorStack, plan: plan,
    arrow: arrow, marker: marker, warn: warn, ping: ping, cross: cross, wind: wind, north: north,
    smoke: smoke, fire: fire, label: label, tag: tag, teamCard: teamCard, countdown: countdown, icon: icon,
    onState: onState, onAlert: onAlert, ready: ready, tap: tap, vibrate: vibrate,
    project: project, area: area, centroid: centroid, hull: hull, focusLevels: focusLevels, byId: byId, levelLabel: levelLabel, time: function (iso) { return hhmm(new Date(iso)); }
  };
})(window);
