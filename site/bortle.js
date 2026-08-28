// Stellar — Bortle scale simulator.
// Grades the nine kinds of sky and shows which of the catalog's objects
// survive at each class, using only the local dataset and the coordinate
// layer attached by maps.js.
(function () {
  'use strict';
  var D = window.STAR_DATA;

  var CLASSES = [
    { b: 1, name: 'Excellent dark sky', limg: 10.5, starLims: 7.5,
      desc: 'Milky Way casts shadows; zodiacal light tints the dark.',
      town: 'None visible.', m33: 'Visible to the naked eye.' },
    { b: 2, name: 'Typical truly dark site', limg: 10.0, starLims: 7.0,
      desc: 'Milky Way is complex, with visible detail.',
      town: 'Barely detectable at most, maybe.', m33: 'Visible to the naked eye under ideal conditions.' },
    { b: 3, name: 'Rural sky', limg: 8.0, starLims: 6.5,
      desc: 'Milky Way is easily visible, though somewhat washed out at the horizon.',
      town: 'Distant glow above the horizon.', m33: 'Visible with averted vision.' },
    { b: 4, name: 'Rural / suburban transition', limg: 7.0, starLims: 6.0,
      desc: 'Milky Way is faint and hard to make out in most places.',
      town: 'Noticeable sky glow.', m33: 'At the bare limit — binoculars or averted vision.' },
    { b: 5, name: 'Suburban sky', limg: 6.0, starLims: 5.0,
      desc: 'Milky Way is only visible overhead, if anywhere.',
      town: 'Sky glow dominates the darker parts of the sky.', m33: 'Only in a strong instrument.' },
    { b: 6, name: 'Bright suburban sky', limg: 4.5, starLims: 4.0,
      desc: 'Milky Way is totally invisible; a bluish color in the sky near the horizon.',
      town: 'Distinct, bright sky glow.', m33: 'Not visible to the naked eye.' },
    { b: 7, name: 'Suburban / urban transition', limg: 4.0, starLims: 3.0,
      desc: 'Most of the sky is washed out; only bright stars stand out.',
      town: 'Intense, bright sky glow; fainter stars invisible.', m33: 'Not visible without a large instrument.' },
    { b: 8, name: 'City sky', limg: 2.5, starLims: 2.0,
      desc: 'Only the brightest objects are clearly visible.',
      town: 'Strong, intense, bright sky glow.', m33: 'Not visible to the eye.' },
    { b: 9, name: 'Inner city sky', limg: 1.5, starLims: 1.0,
      desc: 'The Moon is the only thing you can really notice. Only the brightest stars are visible.',
      town: 'Sky is brightly lit by city lights.', m33: 'Not visible to the eye.' }
  ];

  var TYPE_INFO = {
    Galaxy:  { label: 'Galaxy',  color: '#9db4ff' },
    Nebula:  { label: 'Nebula',  color: '#f0a6ff' },
    Cluster: { label: 'Cluster', color: '#7fe3c0' },
    Star:    { label: 'Star',    color: '#ffd98a' }
  };

  var items = [];
  ['galaxies', 'nebulae', 'clusters', 'stars'].forEach(function (k) {
    (D[k] || []).forEach(function (o) {
      if (!o || o.name === undefined || typeof o.ra !== 'number') return;
      var mag = parseFloat(o.vis);
      if (!isFinite(mag)) mag = 9.5;
      items.push({
        o: o,
        type: o.type,
        color: TYPE_INFO[o.type] ? TYPE_INFO[o.type].color : '#ffffff',
        mag: mag,
        ra: o.ra,
        dec: o.dec
      });
    });
  });

  items.sort(function (a, b) { return a.mag - b.mag; });

  var limitOfType = function (it, cls) {
    return it.type === 'Star' ? cls.starLims : cls.limg;
  };
  var isShown = function (it, cls) {
    return it.mag <= limitOfType(it, cls) + 0.25;
  };

  // ---- projection (azimuthal equidistant, pole at center) ----
  var canvas = document.getElementById('dome');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var wrap = canvas.parentElement;
  var card = document.getElementById('hovercard');
  var cardName = document.getElementById('hover-name');
  var cardSub = document.getElementById('hover-sub');
  var range = document.getElementById('bortle-range');
  var readout = document.getElementById('bortle-readout');
  var countEl = document.getElementById('countline');
  var pillsEl = document.getElementById('obj-pills');

  var dpr = 1, W = 0, H = 0, cx = 0, cy = 0, Rpad = 0;
  var cur = CLASSES[2];
  var hits = [];
  var hovered = null;
  var drawQueued = false;
  var t = 0; // twinkle clock

  function size() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = Math.max(280, wrap.clientWidth);
    H = W;
    canvas.style.height = H + 'px';
    canvas.width = Math.floor(W * dpr);
    canvas.height = Math.floor(H * dpr);
    cx = W / 2;
    cy = H / 2;
    Rpad = W / 2 - 8;
  }

  function project(it) {
    var a = it.ra * Math.PI / 180;
    var rr = (90 - Math.abs(it.dec)) / 90 * (Rpad - 24);
    return [cx + Math.sin(a) * rr, cy - Math.cos(a) * rr];
  }

  // sky background luminance: class 1 is near-black, class 9 is a strong yellow haze
  function skyBase(c) {
    var f = (c.b - 1) / 8;
    var top = [8 + 110 * f, 9 + 80 * f, 18 + 40 * f];
    var bot = [10 + 150 * f, 10 + 105 * f, 22 + 60 * f];
    return [top, bot];
  }
  function rgb(a) { return 'rgb(' + Math.round(a[0]) + ',' + Math.round(a[1]) + ',' + Math.round(a[2]) + ')'; }
  function rgba(a, al) { return 'rgba(' + Math.round(a[0]) + ',' + Math.round(a[1]) + ',' + Math.round(a[2]) + ',' + al + ')'; }

  function draw(now) {
    drawQueued = false;
    t = (now || 0) * 0.001;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    var base = skyBase(cur);
    var g = ctx.createRadialGradient(cx, cy * 0.8, Rpad * 0.1, cx, cy, Rpad);
    g.addColorStop(0, rgb(base[0]));
    g.addColorStop(1, rgb(base[1]));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(cx, cy, Rpad, 0, Math.PI * 2);
    ctx.fill();

    // horizon glow from towns, grows with class
    var glow = (cur.b / 9);
    if (glow > 0.05) {
      var hg = ctx.createRadialGradient(cx, cy, Rpad * 0.55, cx, cy, Rpad);
      hg.addColorStop(0, 'rgba(0,0,0,0)');
      hg.addColorStop(1, 'rgba(' + Math.round(70 + 165 * glow) + ',' + Math.round(58 + 120 * glow) + ',' + Math.round(25 + 60 * glow) + ',' + (0.35 + 0.4 * glow).toFixed(2) + ')');
      ctx.fillStyle = hg;
      ctx.beginPath();
      ctx.arc(cx, cy, Rpad, 0, Math.PI * 2);
      ctx.fill();
    }

    // grid
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(120,160,255,0.18)';
    for (var a2 = 0; a2 < 360; a2 += 30) {
      var sa = a2 * Math.PI / 180;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.sin(sa) * (Rpad - 24), cy - Math.cos(sa) * (Rpad - 24));
      ctx.stroke();
    }
    var rr60 = (Rpad - 24) * (90 - 60) / 90;
    var rr30 = (Rpad - 24) * (90 - 30) / 90;
    ctx.beginPath(); ctx.arc(cx, cy, rr60, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, rr30, 0, Math.PI * 2); ctx.stroke();

    // Milky Way band on class 1-3: soft slanted band of scattered micro-stars
    if (cur.b <= 3) {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(-0.5);
      var mw = ctx.createLinearGradient(0, -Rpad * 0.32, 0, Rpad * 0.32);
      var mwA = [0.16, 0.12, 0.08][cur.b - 1];
      mw.addColorStop(0, 'rgba(200,215,255,0)');
      mw.addColorStop(0.5, 'rgba(200,215,255,' + mwA + ')');
      mw.addColorStop(1, 'rgba(200,215,255,0)');
      ctx.fillStyle = mw;
      ctx.fillRect(-Rpad, -Rpad * 0.32, Rpad * 2, Rpad * 0.64);
      // seed micro stars deterministically
      for (var msi = 0; msi < 90; msi++) {
        var mx = ((msi * 37) % 1000) / 1000 * 2 - 1;
        var my = ((msi * 173) % 1000) / 1000 * 2 - 1;
        var md = Math.abs(my);
        if (md > 0.9) continue;
        var mscale = Rpad * 0.92 * (1 - md * 0.75);
        ctx.fillStyle = 'rgba(230,238,255,' + (mwA * 0.9).toFixed(2) + ')';
        ctx.beginPath();
        ctx.arc(mx * Rpad * 0.95, my * Rpad * 0.9, 0.6 + (msi % 3) * 0.3, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }

    // objects
    hits = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var shown = isShown(it, cur);
      var pt = project(it);
      var mag = it.mag;
      var r0 = Math.max(4, Math.min(22, 15 - mag * 1.15));
      var tw = 0.85 + 0.15 * Math.sin(t * (0.8 + ((i * 37) % 10) / 6) + i);

      if (shown) {
        var c = it.color;
        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        var layers = [[2.1, 0.10], [1.25, 0.22], [1.0, 0.5]];
        for (var li = 0; li < layers.length; li++) {
          ctx.globalAlpha = layers[li][1] * tw;
          ctx.strokeStyle = null;
          ctx.fillStyle = c;
          ctx.beginPath();
          ctx.arc(pt[0], pt[1], r0 * layers[li][0], 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.globalAlpha = 0.95 * tw;
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(pt[0], pt[1], Math.max(0.7, r0 * 0.3), 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        if (mag < 5.5) {
          ctx.globalAlpha = 0.6;
          ctx.fillStyle = 'rgba(200,210,240,0.75)';
          ctx.font = '10px ui-monospace, "SF Mono", Menlo, Consolas, monospace';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(it.o.name, pt[0], pt[1] + r0 + 2);
          ctx.globalAlpha = 1;
        }

        hits.push({ x: pt[0], y: pt[1], r: Math.max(r0, 9), o: it });
      } else {
        // ghost: a washed-out, barely-there dot
        ctx.save();
        ctx.globalAlpha = cur.b <= 5 ? 0.12 : 0.07;
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(pt[0], pt[1], Math.max(1, r0 * 0.35), 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    }

    // center mark
    ctx.fillStyle = 'rgba(190,205,240,0.6)';
    ctx.beginPath(); ctx.arc(cx, cy, 1.5, 0, Math.PI * 2); ctx.fill();
  }

  function requestDraw() {
    if (drawQueued) return;
    drawQueued = true;
    requestAnimationFrame(draw);
  }

  // ---- hover / tap inspection ----
  function objectAt(x, y) {
    var best = null, bestScore = -Infinity;
    for (var i = 0; i < hits.length; i++) {
      var h = hits[i];
      var d = Math.hypot(x - h.x, y - h.y);
      if (d <= Math.max(h.r * 1.4, 11)) {
        var score = h.r * 10 - d;
        if (score > bestScore) { bestScore = score; best = h.o; }
      }
    }
    return best;
  }

  function setHover(it, x, y) {
    if (it === hovered) return;
    hovered = it;
    if (it) {
      var lim = limitOfType(it, cur).toFixed(1);
      var ok = isShown(it, cur);
      cardName.textContent = it.o.name;
      cardSub.textContent = it.o.desig + ' · ' + it.o.const + ' · mag ' + it.o.vis;
      card.classList.remove('hidden');
      var cw = card.offsetWidth || 150;
      var ch = card.offsetHeight || 60;
      var lx = x + 14;
      var ly = y + 14;
      if (lx + cw > W - 4) lx = Math.max(4, x - cw - 14);
      if (ly + ch > H - 4) ly = Math.max(4, H - ch - 8);
      card.style.left = lx + 'px';
      card.style.top = ly + 'px';
      // add an extra line showing threshold vs class
      setCardVerdict(it, ok, lim);
    } else {
      card.classList.add('hidden');
    }
  }

  function setCardVerdict(it, ok, lim) {
    var v = card.querySelector('.hover-verdict');
    if (!v) {
      v = document.createElement('div');
      v.className = 'hover-verdict';
      v.style.cssText = 'margin-top:0.4rem;font-size:0.78rem;font-family:var(--font-mono);';
      card.appendChild(v);
    }
    if (ok) {
      v.textContent = '✓ visible at class ' + cur.b + ' (limit ≤ ' + lim + ' mag)';
      v.style.color = '#7fe3c0';
    } else {
      v.textContent = '✕ washed out at class ' + cur.b + ' — last visible at class ' + neededClass(it);
      v.style.color = '#f2c46c';
    }
  }

  // smallest Bortle class at which this object is visible
  function neededClass(it) {
    for (var k = 0; k < CLASSES.length; k++) {
      if (isShown(it, CLASSES[k])) return CLASSES[k].b;
    }
    return 1;
  }

  canvas.addEventListener('pointermove', function (e) {
    var rect = canvas.getBoundingClientRect();
    var x = e.clientX - rect.left, y = e.clientY - rect.top;
    setHover(objectAt(x, y), x, y);
  });
  canvas.addEventListener('pointerdown', function (e) {
    var rect = canvas.getBoundingClientRect();
    var x = e.clientX - rect.left, y = e.clientY - rect.top;
    setHover(objectAt(x, y), x, y);
  });
  canvas.addEventListener('pointerleave', function () {
    setHover(null, 0, 0);
  });

  // ---- pills ----
  var pills = [];
  (function buildPills() {
    var frag = document.createDocumentFragment();
    for (var i = 0; i < items.length; i++) {
      var el = document.createElement('span');
      el.className = 'b-pill';
      el.setAttribute('data-name', items[i].o.name);
      var dot = document.createElement('i');
      dot.style.background = items[i].color;
      var nm = document.createElement('span');
      nm.textContent = items[i].o.name + ' ' + (items[i].o.desig ? '· ' + items[i].o.desig : '');
      var em = document.createElement('em');
      el.appendChild(dot); el.appendChild(nm); el.appendChild(em);
      frag.appendChild(el);
      pills.push(el);
    }
    pillsEl.appendChild(frag);
  })();

  // ---- table of all nine classes ----
  (function buildTable() {
    var t = document.getElementById('scale-table');
    var html = '';
    for (var i = 0; i < CLASSES.length; i++) {
      var c = CLASSES[i];
      html += '<div class="b-row">' +
        '<span class="bn">class ' + c.b + '</span>' +
        '<span class="bname" style="color:' + (c.b <= 3 ? '#7fe3c0' : c.b <= 6 ? '#ffd98a' : '#f28a5f') + '">' + c.name + '</span>' +
        '<span class="bmag">naked-eye limit ≈ ' + c.starLims.toFixed(1) + ' mag · deep-sky limit ≈ ' + c.limg.toFixed(1) + ' mag</span>' +
        '<span class="bnote">' + c.desc + ' <b>Nearest town:</b> ' + c.town + ' <b>M33 test:</b> ' + c.m33 + '</span>' +
        '</div>';
    }
    t.innerHTML = html;
  })();

  // ---- apply a class ----
  function applyClass() {
    var b = Math.max(1, Math.min(9, parseInt(range.value, 10) || 3));
    cur = CLASSES[b - 1];
    readout.innerHTML = 'Class ' + b + ' — ' + cur.name +
      '<br><span style="color:var(--muted);font-size:0.75rem;">' + cur.desc + '</span>';

    var shownCount = 0;
    for (var i = 0; i < items.length; i++) {
      if (isShown(items[i], cur)) shownCount++;
      var p = pills[i];
      var shown = isShown(items[i], cur);
      p.classList.toggle('lost', !shown);
      p.querySelector('em').textContent = items[i].o.vis === '—' ? '—' : 'mag ' + items[i].o.vis;
    }
    countEl.textContent = shownCount + ' of ' + items.length + ' catalog objects are clearly visible at class ' + b +
      (shownCount < items.length ? ' — ' + (items.length - shownCount) + ' wash out in this glow.' : ' — the whole catalog is available tonight.');

    if (hovered) setCardVerdict(hovered, isShown(hovered, cur), limitOfType(hovered, cur).toFixed(1));
  }

  range.addEventListener('input', applyClass);

  // boot
  size();
  window.addEventListener('resize', function () { size(); requestDraw(); });
  applyClass();

  // gentle twinkle loop
  (function loop(ts) {
    requestAnimationFrame(loop);
    draw(ts);
  })(performance.now());
})();
