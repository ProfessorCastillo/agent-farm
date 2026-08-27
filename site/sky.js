(function () {
  'use strict';
  var S = window.Stellar, THEMES = S.THEMES, MODES = S.MODES;
  var canvas = document.getElementById('sky');
  var ctx = canvas.getContext('2d');
  var root = document.documentElement;

  var MIN = 40, MAX = 420, STEP = 20;
  var CONN = 110;
  var stars = [];
  var mode = 'drift';
  var density = 140;
  var cur = THEMES.void;
  var paused = false;
  var mouse = { x: null, y: null, r: 150, active: false };
  var fieldMax = 0;

  function size() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(window.innerWidth * dpr);
    canvas.height = Math.floor(window.innerHeight * dpr);
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function makeStar() {
    var a = Math.random() * Math.PI * 2;
    var v = 0.15 + Math.random() * 0.55;
    return {
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: Math.cos(a) * v,
      vy: Math.sin(a) * v,
      r: 0.7 + Math.random() * 1.9,
      tw: Math.random() * Math.PI * 2,
      ts: 0.5 + Math.random() * 1.5,
      tint: 0.55 + Math.random() * 0.45
    };
  }

  function seed(n) {
    stars = [];
    for (var i = 0; i < n; i++) stars.push(makeStar());
  }

  function applyTheme(key) {
    cur = THEMES[key];
    root.style.setProperty('--bg', cur.bg0);
    root.style.setProperty('--bg2', cur.bg1);
    root.style.setProperty('--accent', cur.accent);
    root.style.setProperty('--accent2', cur.accent2);
    document.title = 'Stellar — ' + cur.name;
    document.getElementById('title').textContent = cur.name;
    document.getElementById('hint').textContent = cur.hint;
    var btns = document.querySelectorAll('[data-theme]');
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute('aria-pressed', String(btns[i].getAttribute('data-theme') === key));
    }
  }

  function applyMode(key) {
    mode = key;
    document.getElementById('stat-mode').textContent = MODES[key].label;
    var btns = document.querySelectorAll('[data-mode]');
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute('aria-pressed', String(btns[i].getAttribute('data-mode') === key));
    }
  }

  function setDensity(n) {
    density = Math.max(MIN, Math.min(MAX, n));
    document.getElementById('denval').textContent = density;
    seed(density);
    document.getElementById('stat-count').textContent = density;
  }

  function togglePause() {
    paused = !paused;
    var b = document.getElementById('pp');
    b.setAttribute('aria-pressed', String(paused));
    b.textContent = paused ? 'Resume' : 'Pause';
    if (!paused) { fpsFrames = 0; fpsLast = performance.now(); }
  }

  function controls() {
    var bar = document.getElementById('controls');
    var html = '<span class="glab">Field</span>';
    var k, list;
    for (k in THEMES) if (THEMES.hasOwnProperty(k)) {
      html += '<button class="chip" data-theme="' + k + '" aria-pressed="' + (k === 'void') + '">' + THEMES[k].name + '</button>';
    }
    html += '<span class="glab">Force</span>';
    for (k in MODES) if (MODES.hasOwnProperty(k)) {
      html += '<button class="chip" data-mode="' + k + '" aria-pressed="' + (k === 'drift') + '">' + MODES[k].label + '</button>';
    }
    html += '<span class="glab">Density</span>';
    html += '<button class="chip icon" id="den-minus" aria-label="Fewer stars">\u2212</button>';
    html += '<span class="denval" id="denval">' + density + '</span>';
    html += '<button class="chip icon" id="den-plus" aria-label="More stars">+</button>';
    html += '<button class="chip" id="pp" aria-pressed="false">Pause</button>';
    bar.insertAdjacentHTML('beforeend', html);

    list = bar.querySelectorAll('[data-theme]');
    for (var i = 0; i < list.length; i++) (function (b) {
      b.addEventListener('click', function () { applyTheme(b.getAttribute('data-theme')); });
    })(list[i]);
    list = bar.querySelectorAll('[data-mode]');
    for (var j = 0; j < list.length; j++) (function (b) {
      b.addEventListener('click', function () { applyMode(b.getAttribute('data-mode')); });
    })(list[j]);
    document.getElementById('den-minus').addEventListener('click', function () { setDensity(density - STEP); });
    document.getElementById('den-plus').addEventListener('click', function () { setDensity(density + STEP); });
    document.getElementById('pp').addEventListener('click', togglePause);
  }

  canvas.addEventListener('pointermove', function (e) {
    mouse.x = e.clientX; mouse.y = e.clientY; mouse.active = true;
  });
  canvas.addEventListener('pointerdown', function (e) {
    mouse.x = e.clientX; mouse.y = e.clientY; mouse.active = true;
  });
  canvas.addEventListener('pointerleave', function () {
    mouse.active = false; mouse.x = null; mouse.y = null;
  });

  var last = performance.now(), fpsFrames = 0, fpsLast = performance.now();

  function frame(now) {
    requestAnimationFrame(frame);
    if (paused) { last = now; return; }

    var W = window.innerWidth, H = window.innerHeight;
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, cur.bg0);
    g.addColorStop(1, cur.bg1);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    var fx = MODES[mode];
    var i, j, s, sp, a, b, dx, dy, d, al, d2;

    for (i = 0; i < stars.length; i++) {
      s = stars[i];
      if (mouse.active && mouse.x !== null) {
        var f = fx.fx(s.x, s.y, mouse);
        if (f) { s.vx += f[0]; s.vy += f[1]; }
      }
      s.vx *= 0.985; s.vy *= 0.985;
      sp = Math.hypot(s.vx, s.vy);
      if (sp > 4) { s.vx *= 4 / sp; s.vy *= 4 / sp; }
      s.x += s.vx; s.y += s.vy;
      if (s.x < 0) s.x = W; else if (s.x > W) s.x = 0;
      if (s.y < 0) s.y = H; else if (s.y > H) s.y = 0;
    }

    ctx.lineWidth = 0.7;
    ctx.strokeStyle = 'hsla(' + cur.hsl[0] + ',' + cur.hsl[1] + '%,75%,0.2)';
    for (i = 0; i < stars.length; i++) {
      a = stars[i];
      for (j = i + 1; j < stars.length; j++) {
        b = stars[j];
        dx = a.x - b.x; dy = a.y - b.y;
        d2 = dx * dx + dy * dy;
        if (d2 < CONN * CONN) {
          d = Math.sqrt(d2);
          al = 1 - d / CONN;
          ctx.strokeStyle = 'hsla(' + cur.hsl[0] + ',' + cur.hsl[1] + '%,75%,' + (al * 0.25).toFixed(3) + ')';
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    ctx.globalCompositeOperation = 'lighter';
    for (i = 0; i < stars.length; i++) {
      s = stars[i];
      s.tw += s.ts * 0.016;
      var twk = 0.6 + 0.4 * Math.sin(s.tw);
      var rad = s.r * (1.3 + 0.6 * twk);
      var hue = cur.hsl[0] + (s.tint - 1) * cur.hsl[1] * 0.6;
      var rg = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, rad * 3.4);
      rg.addColorStop(0, 'hsla(' + hue + ',' + cur.hsl[1] + '%,88%,' + (0.85 * twk) + ')');
      rg.addColorStop(0.45, 'hsla(' + hue + ',' + cur.hsl[1] + '%,65%,' + (0.25 * twk) + ')');
      rg.addColorStop(1, 'hsla(0,0%,50%,0)');
      ctx.fillStyle = rg;
      ctx.beginPath();
      ctx.arc(s.x, s.y, rad * 3.4, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';

    fpsFrames++;
    if (now - fpsLast >= 600) {
      document.getElementById('stat-fps').textContent = Math.round(fpsFrames * 1000 / (now - fpsLast));
      fpsFrames = 0; fpsLast = now;
    }
    last = now;
  }

  size();
  window.addEventListener('resize', size);
  controls();
  applyTheme('void');
  setDensity(density);
  requestAnimationFrame(frame);

  // logbook UI wiring (dependency-free, no storage APIs)
  (function () {
    var overlay = document.getElementById('logbook');
    var link = document.getElementById('log-link');
    var btnClose = document.getElementById('log-close');
    var btnSave = document.getElementById('log-save');
    var btnClear = document.getElementById('log-clear');
    var textarea = document.getElementById('log-text');
    if (!overlay) return;
    function openLog() { overlay.classList.add('show'); textarea.focus(); }
    function closeLog() { overlay.classList.remove('show'); }
    if (link) link.addEventListener('click', function (e) { e.preventDefault(); openLog(); });
    if (btnClose) btnClose.addEventListener('click', closeLog);
    if (btnClear) btnClear.addEventListener('click', function () { textarea.value = ''; });
    if (btnSave) btnSave.addEventListener('click', function () {
      // copy text to clipboard using exec by rendering as selectable
      textarea.select();
      try { document.execCommand('copy'); btnSave.textContent = 'Saved!'; setTimeout(function(){btnSave.textContent='Save note';}, 1200);} catch (e) {}
    });
    // close on backdrop click
    overlay.addEventListener('click', function (e){ if (e.target === overlay) closeLog(); });
  })();
})();
