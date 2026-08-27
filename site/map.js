// Stellar — Sky Map renderer. Projection, drawing, and interaction all live
// in this single self-contained script (uses app.js, maps.js, and data.js).
(function () {
  'use strict';
  var D = window.STAR_DATA;
  var ST = window.Stellar.MAP_STYLE;
  var P = ST.colours;
  var TYPE_OF = {
    't-galaxy': 'Galaxy',
    't-nebula': 'Nebula',
    't-cluster': 'Cluster',
    't-star': 'Star'
  };

  var canvas = document.getElementById('map');
  var ctx = canvas.getContext('2d');
  var wrap = canvas.parentElement;
  var card = document.getElementById('hovercard');
  var cardName = document.getElementById('hover-name');
  var cardSub = document.getElementById('hover-sub');

  // ---- collect the plotted objects (those with coordinates attached) ----
  var items = [];
  ['galaxies', 'nebulae', 'clusters', 'stars'].forEach(function (k) {
    (D[k] || []).forEach(function (o) {
      if (typeof o.ra === 'number' && typeof o.dec === 'number' && TYPE_OF[o.catClass]) {
        items.push(o);
      }
    });
  });

  var filter = 'all';
  var showLabels = true;
  var hovered = null;
  var dpr = 1, W = 0, H = 0, cx = 0, cy = 0, R = 0;
  var hits = []; // {x, y, r, o}
  var drawQueued = false;

  function magOf(o) {
    var v = parseFloat(o.vis);
    return isFinite(v) ? v : 9;
  }
  function radiusOf(o) {
    return Math.max(6, Math.min(30, 8 + 1.7 * (9 - magOf(o))));
  }

  // Azimuthal equidistant projection, north pole at center:
  // radius grows as |declination| drops, angle is right ascension.
  function project(o) {
    var a = o.ra * Math.PI / 180;
    var rr = (90 - Math.abs(o.dec)) / 90 * R;
    return [cx + Math.sin(a) * rr, cy - Math.cos(a) * rr];
  }

  function size() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = Math.max(280, wrap.clientWidth);
    H = W;
    canvas.style.height = H + 'px';
    canvas.width = Math.floor(W * dpr);
    canvas.height = Math.floor(H * dpr);
    cx = W / 2;
    cy = H / 2;
    R = W / 2 - 16;
  }

  function visible(o) {
    return filter === 'all' || TYPE_OF[o.catClass] === filter;
  }

  function draw() {
    drawQueued = false;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    hits = [];
    var i, o, pt, r0, rad, a;

    // disk
    var g = ctx.createRadialGradient(cx, cy - R * 0.3, R * 0.1, cx, cy, R);
    g.addColorStop(0, '#111729');
    g.addColorStop(1, '#070a14');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.fill();

    // grid: RA spokes (every 30°) and dec circles (60°, 30°)
    ctx.lineWidth = 1;
    ctx.strokeStyle = P.grid;
    for (a = 0; a < 360; a += 30) {
      var sa = a * Math.PI / 180;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.sin(sa) * R, cy - Math.cos(sa) * R);
      ctx.stroke();
    }
    var rr60 = R * (90 - 60) / 90;
    var rr30 = R * (90 - 30) / 90;
    ctx.beginPath(); ctx.arc(cx, cy, rr60, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, rr30, 0, Math.PI * 2); ctx.stroke();

    // pole mark (cardINALS come from the HTML compass overlay)
    ctx.fillStyle = 'rgba(190,205,240,0.55)';
    ctx.beginPath(); ctx.arc(cx, cy, 1.6, 0, Math.PI * 2); ctx.fill();

    // objects
    for (i = 0; i < items.length; i++) {
      o = items[i];
      if (!visible(o)) continue;
      pt = project(o);
      r0 = radiusOf(o);
      var col = P[o.catClass];
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      var layers = [[1.9, 0.09], [1.25, 0.20], [1.0, 0.45]];
      for (var li = 0; li < layers.length; li++) {
        ctx.globalAlpha = layers[li][1];
        ctx.fillStyle = col;
        ctx.beginPath();
        ctx.arc(pt[0], pt[1], r0 * layers[li][0], 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(pt[0], pt[1], r0 * 0.3, 0, Math.PI * 2);
      ctx.fill();
      if (o === hovered) {
        ctx.globalAlpha = 0.7;
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(pt[0], pt[1], r0 * 1.5 + 2, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.restore();

      if (showLabels) {
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = P.gridText;
        ctx.font = '10px ui-monospace, "SF Mono", Menlo, Consolas, monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(o.name, pt[0], pt[1] + r0 + 3);
        ctx.globalAlpha = 1;
      }
      hits.push({ x: pt[0], y: pt[1], r: r0, o: o });
    }
  }

  function requestDraw() {
    if (drawQueued) return;
    drawQueued = true;
    window.requestAnimationFrame(draw);
  }

  // ---- hover / tap inspection ----
  function objectAt(x, y) {
    var best = null, bestScore = -Infinity;
    for (var i = 0; i < hits.length; i++) {
      var h = hits[i];
      var d = Math.hypot(x - h.x, y - h.y);
      if (d <= Math.max(h.r * 1.5, 11)) {
        var score = h.r * 10 - d;
        if (score > bestScore) { bestScore = score; best = h.o; }
      }
    }
    return best;
  }

  function setHover(o, x, y) {
    if (o === hovered) return;
    hovered = o;
    if (o) {
      cardName.textContent = o.name;
      cardSub.textContent = o.desig + ' · ' + o.const + ' · ' + o.vis + ' mag · ' + o.dist;
      card.classList.remove('hidden');
      var cw = card.offsetWidth || 150;
      var ch = card.offsetHeight || 50;
      var lx = x + 14;
      var ly = y + 14;
      if (lx + cw > W - 4) lx = Math.max(4, x - cw - 14);
      if (ly + ch > H - 4) ly = Math.max(4, H - ch - 8);
      card.style.left = lx + 'px';
      card.style.top = ly + 'px';
    } else {
      card.classList.add('hidden');
    }
    requestDraw();
  }

  function localPoint(e) {
    var rect = canvas.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  }

  canvas.addEventListener('pointermove', function (e) {
    var p = localPoint(e);
    setHover(objectAt(p[0], p[1]), p[0], p[1]);
  });
  canvas.addEventListener('pointerdown', function (e) {
    var p = localPoint(e);
    setHover(objectAt(p[0], p[1]), p[0], p[1]);
  });
  canvas.addEventListener('pointerleave', function () {
    setHover(null, 0, 0);
  });

  // ---- filters ----
  function applyFilter(f) {
    filter = f;
    var shown = 0;
    for (var i = 0; i < items.length; i++) if (visible(items[i])) shown++;
    var label = f === 'all' ? 'all types' : { Galaxy: 'galaxies', Nebula: 'nebulae', Cluster: 'clusters', Star: 'stars' }[f];
    document.getElementById('countline').textContent =
      'Showing ' + shown + ' of ' + items.length + ' objects · ' + label;
    var chips = document.querySelectorAll('#map-controls [data-filter]');
    for (var c = 0; c < chips.length; c++) {
      chips[c].setAttribute('aria-pressed', String(chips[c].getAttribute('data-filter') === f));
    }
    requestDraw();
  }

  document.querySelectorAll('#map-controls [data-filter]').forEach(function (b) {
    b.addEventListener('click', function () { applyFilter(b.getAttribute('data-filter')); });
  });

  var labelsBtn = document.getElementById('labels');
  labelsBtn.addEventListener('click', function () {
    showLabels = !showLabels;
    labelsBtn.setAttribute('aria-pressed', String(showLabels));
    requestDraw();
  });

  // ---- boot ----
  size();
  window.addEventListener('resize', function () { size(); requestDraw(); });
  applyFilter('all');
  requestDraw();
})();
