/*
 * Seraph field — the ring of light, in each module's colour. No dependencies, no build step.
 * Exposes a global `SeraphField`.
 *
 *   const ring = SeraphField.mount(el, { module: 'gabriel' });
 *   ring.set({ module: 'silex' });   // crossfades to Silex's colour over ~600 ms
 *   ring.destroy();
 *
 * Options: module, focus (1 = crisp near edge, 0 = all soft), energy (brightness), grain, zoom, offset [x, y],
 * speed, maxDpr, fps, still (one frame, also forced by prefers-reduced-motion), time (start time, seconds).
 */
(function (global) {
  'use strict';

  var STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

  // One tint scale per module, 50 (lightest) to 950 (darkest). `core` is the module's colour.
  var SCALES = {
    halo: {
      label: 'Halo', core: 50, ref: 'Blanc thermique',
      steps: { 50: '#f5f5f4', 100: '#e7e6e4', 200: '#d0cecb', 300: '#b2afab', 400: '#8f8c88', 500: '#6e6b67',
               600: '#54524f', 700: '#3d3c3a', 800: '#282726', 900: '#171615', 950: '#0b0a0a' }
    },
    seraph: {
      label: 'Seraph', core: 500, ref: 'Corps noir · 800 → 3000 K',
      steps: { 50: '#fff4ec', 100: '#ffe3cc', 200: '#ffc496', 300: '#ff9c5a', 400: '#ff7a2e', 500: '#f2560f',
               600: '#c93c08', 700: '#9a2a07', 800: '#6b1d06', 900: '#3e1004', 950: '#210802' }
    },
    gabriel: {
      label: 'Gabriel', core: 400, ref: 'Flamme bleue · CH* 431 nm',
      steps: { 50: '#eef2ff', 100: '#dce3ff', 200: '#bccbff', 300: '#92a8ff', 400: '#6b84ff', 500: '#4a5ff5',
               600: '#3644d6', 700: '#2a33a8', 800: '#1f2677', 900: '#131846', 950: '#0a0c26' }
    },
    rosetta: {
      label: 'Rosetta', core: 400, ref: 'Thermique ironbow',
      steps: { 50: '#fdf0fa', 100: '#fadcf3', 200: '#f5b9e7', 300: '#ee8ad6', 400: '#e45cc2', 500: '#d036a8',
               600: '#ad2389', 700: '#851a6a', 800: '#5c134a', 900: '#360b2c', 950: '#1d0518' }
    },
    silex: {
      label: 'Silex', core: 400, ref: 'Flamme verte · C₂ 516 nm',
      steps: { 50: '#ecfdf4', 100: '#d2f9e4', 200: '#a6f2ca', 300: '#6ee6a9', 400: '#3fd68a', 500: '#1fbb6e',
               600: '#149658', 700: '#117447', 800: '#0d5235', 900: '#08311f', 950: '#041b11' }
    }
  };

  // Ring brightness (0 = dark, 1 = brightest) mapped onto the module's scale.
  function ramp(name) {
    var s = (SCALES[name] || SCALES.halo).steps;
    return [[0, '#050505'], [0.16, s[950]], [0.3, s[800]], [0.45, s[600]], [0.6, s[400]], [0.75, s[200]], [0.9, s[50]], [1, '#ffffff']];
  }

  function cssGradient(name, angle) {
    var stops = ramp(name).map(function (s) { return s[1] + ' ' + (s[0] * 100).toFixed(1) + '%'; });
    return 'linear-gradient(' + (angle || '90deg') + ', ' + stops.join(', ') + ')';
  }

  var VERT = 'attribute vec2 a;void main(){gl_Position=vec4(a,0.0,1.0);}';

  var FRAG = [
    'precision highp float;',
    'uniform vec2 u_res;',
    'uniform float u_t;',
    'uniform float u_gt;',
    'uniform float u_focus;',
    'uniform float u_energy;',
    'uniform float u_swap;',
    'uniform float u_grain;',
    'uniform vec3 u_view;',
    'uniform sampler2D u_ramp;',

    'float hash(vec2 p){vec3 p3=fract(vec3(p.xyx)*0.1031);p3+=dot(p3,p3.yzx+33.33);return fract((p3.x+p3.y)*p3.z);}',
    'float noise(vec2 p){vec2 i=floor(p);vec2 f=fract(p);vec2 u=f*f*(3.0-2.0*f);',
    '  return mix(mix(hash(i),hash(i+vec2(1.0,0.0)),u.x),mix(hash(i+vec2(0.0,1.0)),hash(i+vec2(1.0,1.0)),u.x),u.y);}',
    'float fbm(vec2 p){float v=0.0;float a=0.5;for(int i=0;i<4;i++){v+=a*noise(p);p=mat2(1.6,1.2,-1.2,1.6)*p+3.1;a*=0.5;}return v;}',
    'vec2 rot(vec2 v,float a){float c=cos(a);float s=sin(a);return vec2(c*v.x-s*v.y,s*v.x+c*v.y);}',
    'float g2(float d,float w){return exp(-(d*d)/(w*w));}',

    'void main(){',
    '  vec2 fc=gl_FragCoord.xy;',
    '  float m=min(u_res.x,u_res.y);',
    '  vec2 p=(fc-0.5*u_res)/m/u_view.z+u_view.xy;',
    '  float t=u_t;',
    '  vec2 wv=vec2(fbm(p*1.4+t*0.02),fbm(p*1.4+vec2(4.1,2.3)-t*0.02))-0.5;',
    '  vec2 pp=p+wv*0.05;',
    // tilted ellipse seen with depth of field: crisp where it is near, diffuse where it is far
    '  vec2 q=rot(pp,0.62-0.06*sin(t*0.07));',
    '  q.y/=0.64;',
    '  float d=length(q)-0.4*(1.0+0.02*sin(t*0.11));',
    '  float f=pow(0.5+0.5*cos(atan(q.y,q.x)+0.35-0.25*sin(t*0.045)),1.1);',
    '  float sharp=mix(0.045,0.006,u_focus);',
    '  float w=mix(0.17,sharp,f);',
    '  float L=g2(d,w*(d<0.0?0.6:1.45))*mix(0.3+0.3*u_energy,1.0,f);',
    '  L+=g2(d,sharp*0.8)*f*f*f*0.9;',
    '  L+=smoothstep(-0.004,0.004,d)*g2(d,0.07)*f*0.22;',
    '  L*=0.75+0.5*u_energy;',

    '  float I=clamp(L,0.0,1.0);',
    '  vec3 col=mix(texture2D(u_ramp,vec2(I,0.25)).rgb,texture2D(u_ramp,vec2(I,0.75)).rgb,u_swap);',
    '  vec2 uv=fc/u_res;',
    '  col*=1.0-0.35*pow(length(uv-0.5)*1.25,2.2);',
    '  float n=hash(fc+u_gt*vec2(37.1,91.7))*0.65+hash(floor(fc*0.5)+u_gt*vec2(13.3,7.9)+17.0)*0.35-0.5;',
    '  float lum=dot(col,vec3(0.299,0.587,0.114));',
    '  col+=n*u_grain*(0.6+1.6*lum*(1.0-lum));',
    '  gl_FragColor=vec4(clamp(col,0.0,1.0),1.0);',
    '}'
  ].join('\n');

  var reduceMotion = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  function mount(target, options) {
    var opts = Object.assign({}, options || {});
    var moduleName = SCALES[opts.module] ? opts.module : 'halo';

    var canvas = target;
    var ownCanvas = false;
    if (!(target instanceof HTMLCanvasElement)) {
      canvas = document.createElement('canvas');
      canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block';
      if (getComputedStyle(target).position === 'static') target.style.position = 'relative';
      target.appendChild(canvas);
      ownCanvas = true;
    }

    var state = {
      speed: opts.speed !== undefined ? opts.speed : 1,
      maxDpr: opts.maxDpr || 1.5,
      fps: opts.fps || 60,
      still: opts.still !== undefined ? !!opts.still : reduceMotion
    };
    var goal = {
      focus: opts.focus !== undefined ? opts.focus : 1,
      energy: opts.energy !== undefined ? opts.energy : 0.5,
      grain: opts.grain !== undefined ? opts.grain : 0.09,
      swap: 0,
      zoom: opts.zoom || 1,
      ox: (opts.offset || [0, 0])[0],
      oy: (opts.offset || [0, 0])[1]
    };
    var cur = Object.assign({}, goal);
    var from = moduleName;
    var to = moduleName;

    var gl = canvas.getContext('webgl', {
      antialias: false, premultipliedAlpha: false, preserveDrawingBuffer: !!opts.preserve, powerPreference: 'low-power'
    });

    if (!gl) {
      // No WebGL: a plain gradient in the module's colours so the surface still reads.
      (ownCanvas ? target : canvas).style.background = cssGradient(moduleName, '160deg');
      return { set: function () {}, pause: function () {}, play: function () {}, destroy: function () {}, canvas: canvas, gl: false };
    }

    var prog, loc = {}, rampCanvas, rampTex;

    function compile(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error('SeraphField shader: ' + gl.getShaderInfoLog(s));
      return s;
    }

    function init() {
      prog = gl.createProgram();
      gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
      gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error('SeraphField link: ' + gl.getProgramInfoLog(prog));
      gl.useProgram(prog);
      var buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      var a = gl.getAttribLocation(prog, 'a');
      gl.enableVertexAttribArray(a);
      gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0);
      ['u_res', 'u_t', 'u_gt', 'u_focus', 'u_energy', 'u_swap', 'u_grain', 'u_view', 'u_ramp']
        .forEach(function (n) { loc[n] = gl.getUniformLocation(prog, n); });
      rampTex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, rampTex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      uploadRamp();
    }

    // Ramp texture rows: 0 = current module, 1 = module being crossfaded in.
    function uploadRamp() {
      if (!rampCanvas) {
        rampCanvas = document.createElement('canvas');
        rampCanvas.width = 256;
        rampCanvas.height = 2;
      }
      var ctx = rampCanvas.getContext('2d');
      [from, to].forEach(function (name, row) {
        var g = ctx.createLinearGradient(0, 0, 256, 0);
        ramp(name).forEach(function (s) { g.addColorStop(s[0], s[1]); });
        ctx.fillStyle = g;
        ctx.fillRect(0, row, 256, 1);
      });
      gl.bindTexture(gl.TEXTURE_2D, rampTex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, rampCanvas);
    }

    var t = opts.time !== undefined ? opts.time : 20 + Math.random() * 200;
    var last = 0, lastDraw = 0, raf = 0, running = true, visible = true, alive = true;
    var startReal = performance.now();

    function resize() {
      var dpr = Math.min(global.devicePixelRatio || 1, state.maxDpr);
      var w = Math.max(1, Math.round(canvas.clientWidth * dpr));
      var h = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
    }

    function settleSwap() {
      if (from !== to && cur.swap > 0.995) {
        from = to;
        cur.swap = goal.swap = 0;
        uploadRamp();
      }
    }

    function ease(dt) {
      var k = 1 - Math.exp(-dt / 0.22);
      for (var key in goal) cur[key] += (goal[key] - cur[key]) * k;
      settleSwap();
    }

    function draw() {
      resize();
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(loc.u_res, canvas.width, canvas.height);
      gl.uniform1f(loc.u_t, t);
      gl.uniform1f(loc.u_gt, state.still ? 3 : Math.floor((performance.now() - startReal) / 1000 * 24) % 64);
      gl.uniform1f(loc.u_focus, cur.focus);
      gl.uniform1f(loc.u_energy, cur.energy);
      gl.uniform1f(loc.u_swap, cur.swap);
      gl.uniform1f(loc.u_grain, cur.grain);
      gl.uniform3f(loc.u_view, cur.ox, cur.oy, cur.zoom);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, rampTex);
      gl.uniform1i(loc.u_ramp, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    function frame(now) {
      raf = 0;
      if (!alive) return;
      var dt = last ? Math.min((now - last) / 1000, 0.1) : 0.016;
      last = now;
      t += dt * state.speed;
      ease(dt);
      if (now - lastDraw >= 1000 / state.fps - 2) {
        draw();
        lastDraw = now;
      }
      schedule();
    }

    function schedule() {
      if (raf || !alive || !running || !visible || document.hidden) return;
      if (state.still) {
        for (var key in goal) cur[key] = goal[key];
        cur.swap = 1;
        settleSwap();
        draw();
        return;
      }
      raf = requestAnimationFrame(frame);
    }

    function onVisibility() { last = 0; schedule(); }

    var io = null;
    if (opts.autoPause !== false && typeof IntersectionObserver === 'function') {
      io = new IntersectionObserver(function (entries) {
        visible = entries[0].isIntersecting;
        last = 0;
        schedule();
      }, { rootMargin: '120px' });
      io.observe(canvas);
    }
    var ro = typeof ResizeObserver === 'function' ? new ResizeObserver(function () { if (state.still) draw(); }) : null;
    if (ro) ro.observe(canvas);
    document.addEventListener('visibilitychange', onVisibility);

    canvas.addEventListener('webglcontextlost', function (e) { e.preventDefault(); cancelAnimationFrame(raf); raf = 0; });
    canvas.addEventListener('webglcontextrestored', function () { init(); schedule(); });

    init();
    schedule();

    return {
      canvas: canvas,
      gl: true,
      set: function (o) {
        if (o.module && SCALES[o.module] && o.module !== to) {
          from = to;
          to = o.module;
          cur.swap = 0;
          goal.swap = 1;
          uploadRamp();
        }
        ['focus', 'energy', 'grain', 'zoom'].forEach(function (k) { if (o[k] !== undefined) goal[k] = o[k]; });
        if (o.offset) { goal.ox = o.offset[0]; goal.oy = o.offset[1]; }
        if (o.speed !== undefined) state.speed = o.speed;
        if (o.still !== undefined) state.still = !!o.still;
        schedule();
      },
      pause: function () { running = false; cancelAnimationFrame(raf); raf = 0; },
      play: function () { running = true; last = 0; schedule(); },
      snapshot: function () { draw(); return canvas.toDataURL('image/png'); },
      destroy: function () {
        alive = false;
        cancelAnimationFrame(raf);
        if (io) io.disconnect();
        if (ro) ro.disconnect();
        document.removeEventListener('visibilitychange', onVisibility);
        var ext = gl.getExtension('WEBGL_lose_context');
        if (ext) ext.loseContext();
        if (ownCanvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
      }
    };
  }

  global.SeraphField = { mount: mount, scales: SCALES, steps: STEPS, ramp: ramp, cssGradient: cssGradient };
})(typeof window !== 'undefined' ? window : this);
