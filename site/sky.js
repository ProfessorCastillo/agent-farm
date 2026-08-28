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
  var constellationMode = false;
  var userStars = [];
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

  function showDiscovery(obj) {
    var toast = document.getElementById('discovery-toast');
    if (toast) {
      toast.querySelector('.toast-content h4').textContent = 'Discovered: ' + obj.name;
      toast.querySelector('.toast-sub').textContent = obj.type + ' · ' + (obj.desig || obj.constellate || '');
      toast.classList.add('show');
      setTimeout(function () { toast.classList.remove('show'); }, 3000);
    }
  }

  var discoveryRings = [];

  function seed(n) {
    stars = [];
    for (var i = 0; i < n; i++) stars.push(makeStar());
    
    // Inject discoverable objects
    if (window.STAR_DATA) {
      var allObjs = [];
      var cats = ['galaxies', 'nebulae', 'clusters', 'stars'];
      for (var j = 0; j < cats.length; j++) {
        allObjs = allObjs.concat(window.STAR_DATA[cats[j]]);
      }
      
      for (var k = 0; k < allObjs.length; k++) {
        var obj = allObjs[k];
        var s = makeStar();
        s.isDiscoverable = true;
        s.obj = obj;
        s.discovered = false;
        stars.push(s);
      }
    }
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

  function updateDiscovery() {
    var found = 0, total = 0;
    for (var i = 0; i < stars.length; i++) {
      if (stars[i].isDiscoverable) {
        total++;
        if (stars[i].discovered) found++;
      }
    }
    document.getElementById('stat-found').textContent = found + '/' + total;
  }

  function drawDiscoveryRings() {
    for (var i = discoveryRings.length - 1; i >= 0; i--) {
      var ring = discoveryRings[i];
      ring.age++;
      var alpha = 1 - ring.age / 60;
      if (alpha <= 0) {
        discoveryRings.splice(i, 1);
        continue;
      }
    }
    
    ctx.globalCompositeOperation = 'lighter';
    for (var j = 0; j < discoveryRings.length; j++) {
      var r = discoveryRings[j];
      var rad = r.radius + r.age * 2;
      var alpha = (1 - r.age / 60) * 0.5;
      var hue = cur.hsl[0] + 40;
      var gr = ctx.createRadialGradient(r.x, r.y, 0, r.x, r.y, rad);
      gr.addColorStop(0, 'hsla(' + hue + ', 80%, 70%, 0)');
      gr.addColorStop(0.5, 'hsla(' + hue + ', 80%, 80%, ' + alpha.toFixed(3) + ')');
      gr.addColorStop(1, 'hsla(' + hue + ', 80%, 70%, 0)');
      ctx.fillStyle = gr;
      ctx.beginPath();
      ctx.arc(r.x, r.y, rad, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
  }

  function addDiscoveryRing(x, y) {
    discoveryRings.push({ x: x, y: y, radius: 15, age: 0 });
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
        
        if (s.isDiscoverable && !s.discovered) {
          var d_mouse = Math.hypot(mouse.x - s.x, mouse.y - s.y);
          if (d_mouse < 15) {
            s.discovered = true;
            updateDiscovery();
            showDiscovery(s.obj);
            addDiscoveryRing(s.x, s.y);
          }
        }
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

      drawDiscoveryRings();
      
      ctx.globalCompositeOperation = 'lighter';
      for (i = 0; i < stars.length; i++) {
        s = stars[i];
        s.tw += s.ts * 0.016;
        var twk = 0.6 + 0.4 * Math.sin(s.tw);
        var rad = s.r * (1.3 + 0.6 * twk);
        var hue = cur.hsl[0] + (s.tint - 1) * cur.hsl[1] * 0.6;
        
        if (s.isDiscoverable && s.discovered) {
          var rg = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, rad * 4);
          rg.addColorStop(0, 'hsla(' + hue + ',100%,95%,1)');
          rg.addColorStop(0.3, 'hsla(' + hue + ',80%,75%,0.6)');
          rg.addColorStop(0.8, 'hsla(40,100%,80%,0.2)');
          rg.addColorStop(1, 'hsla(0,0%,50%,0)');
          ctx.fillStyle = rg;
          ctx.beginPath();
          ctx.arc(s.x, s.y, rad * 4, 0, Math.PI * 2);
          ctx.fill();
        }
        
        var rg1 = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, rad * 3.4);
        rg1.addColorStop(0, 'hsla(' + hue + ',' + cur.hsl[1] + '%,88%,' + (0.85 * twk) + ')');
        rg1.addColorStop(0.45, 'hsla(' + hue + ',' + cur.hsl[1] + '%,65%,' + (0.25 * twk) + ')');
        rg1.addColorStop(1, 'hsla(0,0%,50%,0)');
        ctx.fillStyle = rg1;
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

  // Tonight's status — a seasonal recommendation driven by the system clock,
  // purely local (no network, no storage, no eval). Each visit feels distinct.
  (function () {
    var el = document.getElementById('seasonal-what');
    if (!el) return;
    var now = new Date();
    var m = now.getMonth(); // 0-11
    var month = now.getDate() + ' ' + ['January','February','March','April','May','June','July','August','September','October','November','December'][m];
    var recs = [
      { mo: [11,0,1], what: 'Drain your night vision, then walk out under the clearest sky you can reach.' },
      { mo: [1,2], what: 'Orion is overhead — scan his belt and let your eyes drop.' },
      { mo: [3,4], what: 'Follow thearc from Arcturus to Spica across the spring dark.' },
      { mo: [5,6,7], what: 'Chase the Summer Triangle and trace the Milky Way toward Sagittarius.' },
      { mo: [8,9,10], what: 'Let the autumn sky settle into black, then hunt the Andromeda Galaxy.' }
    ];
    for (var i=0;i<recs.length;i++){
      var r = recs[i];
      if (r.mo.indexOf(m) !== -1) {
        el.textContent = ' ' + r.what + ' (' + month + ')';
        return;
      }
    }
  })();

  // star trails animation layer (visual enhancement for long-exposure effect)
  (function () {
    var trails = document.getElementById('trails');
    var trailsCtx = trails ? trails.getContext('2d') : null;
    if (!trails || !trailsCtx) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    function trailSize() {
      trails.width = window.innerWidth * dpr;
      trails.height = window.innerHeight * dpr;
      trails.style.width = window.innerWidth + 'px';
      trails.style.height = window.innerHeight + 'px';
      trailsCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    trailSize();
    window.addEventListener('resize', trailSize);
    var toggleBtn = document.getElementById('night-dial') ? document.getElementById('night-dial').querySelector('.chip.icon') : null;
    var status = document.getElementById('trail-status');
    var active = false, trailAnimId = 0, trailLastT = 0;
    function trailFrame(t) {
      if (!active) return;
      trailAnimId = requestAnimationFrame(trailFrame);
      var dt = Math.max(16, Math.min(32, t - trailLastT)) || 16;
      trailLastT = t;
      // fade trails gradually
      trailsCtx.fillStyle = 'rgba(5,4,3,' + (dt/512).toFixed(3) + ')';
      trailsCtx.fillRect(0, 0, window.innerWidth, window.innerHeight);
      // draw new star glows from same positions as main sky stars
      var N = stars.length;
      for (var i = 0; i < N; i++) {
        var s = stars[i];
        var hue = cur.hsl[0] + (s.tint - 1) * cur.hsl[1] * 0.6;
        var tr = trailsCtx.createRadialGradient(s.x, s.y, 0, s.x, s.y, 8);
        tr.addColorStop(0, 'hsla(' + hue + ',' + cur.hsl[1] + '%,90%,' + (active?0.35:0.08) + ')');
        tr.addColorStop(0.5, 'hsla(' + hue + ',' + cur.hsl[1] + '%,70%,' + (active?0.12:0.03) + ')');
        tr.addColorStop(1, 'hsla(0,0%,50%,0)');
        trailsCtx.fillStyle = tr;
        trailsCtx.beginPath();
        trailsCtx.arc(s.x, s.y, 8, 0, Math.PI * 2);
        trailsCtx.fill();
      }
    }
    if (toggleBtn && status) {
      toggleBtn.addEventListener('click', function() {
        active = !active;
        if (active) {
          trails.classList.remove('hidden');
          trailsCtx.clearRect(0, 0, window.innerWidth, window.innerHeight);
          trailLastT = performance.now();
          trailAnimId = requestAnimationFrame(trailFrame);
          status.textContent = 'on';
          document.body.classList.add('trail-active');
        } else {
          cancelAnimationFrame(trailAnimId);
          trailsCtx.clearRect(0, 0, window.innerWidth, window.innerHeight);
          trails.classList.add('hidden');
          status.textContent = 'off';
          document.body.classList.remove('trail-active');
        }
      });
    }
   })();
  
  // Moon phase calculation and display
  (function () {
    var moonCanvas = document.getElementById('moon-canvas');
    var moonText = document.getElementById('moon-text');
    if (!moonCanvas || !moonText) return;
    
    var ctx = moonCanvas.getContext('2d');
    var CYCLE_DAYS = 29.53;
    var KNOWN_NEW_MOON = new Date('2000-01-06T18:14:00Z').getTime() / 86400000;
    
    function getMoonAge(date) {
      var daysSinceEpoch = (date.getTimezoneOffset() * 60 * 1000 + date.getTime()) / 86400000;
      var cyclesSinceEpoch = (daysSinceEpoch - KNOWN_NEW_MOON) / CYCLE_DAYS;
      return ((cyclesSinceEpoch % 1) * CYCLE_DAYS + CYCLE_DAYS) % CYCLE_DAYS;
    }
    
    function getPhaseName(age) {
      var phase = age / CYCLE_DAYS;
      if (phase < 0.06 || phase > 0.94) return 'New Moon';
      if (phase < 0.21) return 'Waxing Crescent';
      if (phase < 0.26) return 'First Quarter';
      if (phase < 0.41) return 'Waxing Gibbous';
      if (phase < 0.46) return 'Full Moon';
      if (phase < 0.61) return 'Waning Gibbous';
      if (phase < 0.66) return 'Third Quarter';
      return 'Waning Crescent';
    }
    
    function drawMoon(age) {
      var phase = age / CYCLE_DAYS;
      var radius = 28;
      var centerX = 32, centerY = 32;
      
      ctx.clearRect(0, 0, 64, 64);
      
      var gradient = ctx.createRadialGradient(centerX - 8, centerY - 8, 2, centerX, centerY, radius);
      gradient.addColorStop(0, '#f5e6d3');
      gradient.addColorStop(1, '#c4b599');
      
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.fill();
      
      var illumination = (Math.cos(phase * Math.PI * 2) + 1) / 2;
      var halfMoonPhase = phase - 0.5;
      if (halfMoonPhase < 0) halfMoonPhase += 1;
      halfMoonPhase = phase > 0.5 ? (phase - 0.5) * 2 : (0.5 - phase) * 2;
      
      var offset = Math.cos(phase * Math.PI * 2) * radius;
      
      ctx.fillStyle = '#0d0a08';
      ctx.beginPath();
      
      if (phase <= 0.5) {
        var leftEdge = centerX + offset / 2;
        ctx.arc(centerX, centerY, radius, -Math.PI / 6, Math.PI * 7 - Math.PI / 6);
        ctx.arc(leftEdge, centerY, Math.abs(offset), Math.PI * 7 - Math.PI / 6, -Math.PI / 6);
      } else {
        var rightEdge = centerX + offset / 2;
        ctx.arc(centerX, centerY, radius, Math.PI - Math.PI / 6, Math.PI + Math.PI / 6);
        ctx.arc(rightEdge, centerY, Math.abs(offset), Math.PI + Math.PI / 6, Math.PI - Math.PI / 6);
      }
      
      ctx.fill();
      
      ctx.fillStyle = '#8a7f6b';
      ctx.beginPath();
      ctx.arc(centerX - 10, centerY - 8, 5, 0, Math.PI * 2);
      ctx.arc(centerX + 8, centerY + 5, 4, 0, Math.PI * 2);
      ctx.arc(centerX + 12, centerY - 12, 3.5, 0, Math.PI * 2);
      ctx.fill();
    }
    
    function updateMoon() {
      var now = new Date();
      var age = getMoonAge(now);
      drawMoon(age);
      moonText.textContent = getPhaseName(age) + ' · ' + (age / CYCLE_DAYS * 100).toFixed(1) + '% illuminated';
    }
    
    updateMoon();
  })();
})();
