// Stellar — constellation atlas.
// Sixteen patterns hand-plotted on a 120-unit plate: stars sized by their
// real magnitude, lines tracing the traditional figure, one named star per
// figure, and a short field note on how to find each pattern overhead.
// Seasonal chips filter the grid; circumpolar shapes stay in all season.
(function () {
  'use strict';

  var grid = document.getElementById('constellations');
  if (!grid) return;

  var C = [
    {
      name: 'Ursa Major', kind: 'constellation', color: '#9db4ff',
      seasons: ['spring'], when: 'Best in spring — the Great Bear overhead all night',
      find: 'The simplest find in the sky: the Big Dipper, a seven-star bowl with a handle. Pair the two stars on the outside of the bowl, Merak and Dubhe, and stretch that line out five of its lengths to land on Polaris.',
      objects: ['M81 · Bode’s Galaxy', 'M82 · Cigar Galaxy', 'M101 · Pinwheel', 'Mizar · the naked-eye double'],
      glow: null,
      stars: [
        { x: 88, y: 8, m: 2.37, label: 'Dubhe' },
        { x: 88, y: 34, m: 2.37, label: 'Merak' },
        { x: 60, y: 40, m: 2.44 },
        { x: 60, y: 12, m: 3.31 },
        { x: 40, y: 18, m: 1.77, label: 'Alioth' },
        { x: 22, y: 26, m: 2.04, label: 'Mizar' },
        { x: 16, y: 12, m: 3.4, label: 'Alcor' },
        { x: 6, y: 40, m: 1.86, label: 'Alkaid' }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 0], [3, 4], [4, 5], [5, 6], [5, 7]]
    },
    {
      name: 'Ursa Minor', kind: 'constellation', color: '#9db4ff',
      seasons: ['winter', 'spring', 'summer', 'autumn'], when: 'Circumpolar — in the wheel all year',
      find: 'Find Polaris first, then back off along the Dipper handle’s line: the Little Dipper sits there, a fainter, more delicate mirror of its great-bear sister, with the red star Kochab capping the bowl.',
      objects: ['Polaris · α UMi — the Pole Star', 'Kochab · β UMi, a red anchor', 'Pherkad · γ UMi'],
      glow: null,
      stars: [
        { x: 8, y: 40, m: 1.97, label: 'Polaris' },
        { x: 26, y: 32, m: 4.29 },
        { x: 44, y: 40, m: 4.90 },
        { x: 60, y: 34, m: 3.00, label: 'Pherkad' },
        { x: 70, y: 52, m: 4.09 },
        { x: 86, y: 48, m: 4.36 },
        { x: 84, y: 26, m: 2.08, label: 'Kochab' }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 3]]
    },
    {
      name: 'Cepheus', kind: 'constellation', color: '#9db4ff',
      seasons: ['winter', 'spring', 'summer', 'autumn'], when: 'Circumpolar — the house-shaped corner of the wheel',
      find: 'A pentagon like a small house, wedged between Cassiopeia’s W and the Great Bear’s handle. It occupies the region of the sky that everything else circles: from mid-northern latitudes it never sets.',
      objects: ['δ Cephei — the first variable star ever found', 'Cepheids — a whole star class named for it'],
      glow: null,
      stars: [
        { x: 16, y: 82, m: 2.45, label: 'Alderamin' },
        { x: 22, y: 40, m: 3.78 },
        { x: 48, y: 20, m: 3.19 },
        { x: 78, y: 26, m: 3.32 },
        { x: 94, y: 52, m: 3.53 },
        { x: 78, y: 78, m: 3.35 }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 0]]
    },
    {
      name: 'Cassiopeia', kind: 'constellation', color: '#9db4ff',
      seasons: ['winter', 'spring', 'summer', 'autumn'], when: 'Circumpolar — the Queen’s W never sets',
      find: 'Five bright stars in a broken W — one of the surest landmarks in the northern sky, opposite Polaris across the pole from the Big Dipper. When the W lies with its open end up, the outer stars are Caph and Segin.',
      objects: ['Schedar · α Cas, warm red-orange', 'Caph · β Cas', 'Navi · γ Cas, a runaway spinning star', 'Ruchbah · δ Cas'],
      glow: null,
      stars: [
        { x: 10, y: 48, m: 2.27, label: 'Caph' },
        { x: 34, y: 70, m: 2.24, label: 'Schedar' },
        { x: 56, y: 44, m: 2.47, label: 'Navi' },
        { x: 78, y: 70, m: 2.68, label: 'Ruchbah' },
        { x: 102, y: 48, m: 3.39, label: 'Segin' }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 4]]
    },
    {
      name: 'Draco', kind: 'constellation', color: '#f0a6ff',
      seasons: ['winter', 'spring', 'summer', 'autumn'], when: 'Circumpolar — the long serpent coiling around the pole',
      find: 'The longest constellation in the sky: its head sits between Cepheus and the Little Dipper, and its body coils the full way around Polaris, reaching the Great Bear. Follow the dim chain from Epsilon toward the Dipper’s bowl.',
      objects: ['Eltanin · γ Dra, the head’s gold star', 'Rastaban · θ Dra', 'Edasich · α Dra'],
      glow: null,
      stars: [
        { x: 8, y: 18, m: 3.05, label: 'Eltanin' },
        { x: 28, y: 10, m: 2.75 },
        { x: 48, y: 18, m: 3.29 },
        { x: 66, y: 24, m: 3.34 },
        { x: 84, y: 16, m: 3.10, label: 'Epsilon' },
        { x: 58, y: 48, m: 3.94 },
        { x: 40, y: 72, m: 3.07 },
        { x: 22, y: 92, m: 4.15 }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 4], [3, 5], [5, 6], [6, 7]]
    },
    {
      name: 'Orion', kind: 'constellation', color: '#ffd98a',
      seasons: ['winter'], when: 'Best in deep winter — the Hunter low in the south',
      find: 'Unmistakable: ruddy Betelgeuse at one shoulder, white Bellatrix at the other, the three-star belt across the middle, and brilliant blue Rigel at the foot. Point along the belt’s middle star, Alnilam, and you land on the Sword.',
      objects: ['M42 · the Orion Nebula', 'B33 · the Horsehead', 'Betelgeuse · α Ori', 'Rigel · β Ori'],
      glow: { x: 56, y: 74, r: 20, color: 'rgba(255,110,199,0.30)' },
      stars: [
        { x: 80, y: 18, m: 0.45, label: 'Betelgeuse' },
        { x: 38, y: 24, m: 1.64, label: 'Bellatrix' },
        { x: 44, y: 56, m: 2.23 },
        { x: 56, y: 54, m: 1.69, label: 'Alnilam' },
        { x: 68, y: 52, m: 1.77 },
        { x: 62, y: 90, m: 2.09 },
        { x: 34, y: 88, m: 0.13, label: 'Rigel' }
      ],
      lines: [[0, 4], [0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [2, 6], [5, 6]]
    },
    {
      name: 'Leo', kind: 'constellation', color: '#ffd98a',
      seasons: ['spring'], when: 'Best in spring — high in the east after dusk',
      find: 'Draw the Sickle and hold it over a triangle and you have the Lion: Regulus at the base of the curve, Algieba glowing gold at the head, and the hindquarter triangle closing with blue-white Denebola. The Lion is the sky’s clearest spring outline.',
      objects: ['Regulus · α Leo', 'Algieba · γ Leo, gold', 'Denebola · β Leo', 'M65 · M66 — the Leo pair'],
      glow: null,
      stars: [
        { x: 14, y: 88, m: 1.35, label: 'Regulus' },
        { x: 24, y: 66, m: 3.51 },
        { x: 34, y: 44, m: 2.28, label: 'Algieba' },
        { x: 44, y: 28, m: 3.50 },
        { x: 56, y: 22, m: 4.03 },
        { x: 94, y: 64, m: 2.14, label: 'Denebola' },
        { x: 70, y: 50, m: 2.57 },
        { x: 72, y: 80, m: 2.62 }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 4], [2, 6], [5, 6], [6, 7], [5, 7]]
    },
    {
      name: 'Scorpius', kind: 'constellation', color: '#f0a6ff',
      seasons: ['summer'], when: 'Best in summer — the hook low after dusk',
      find: 'Start at Antares, the ruddy heart, and trace the dim hook down through Sargas; the stinger then hooks back up past Shaula. From mid-northern latitudes most of the scorpion never rises — what you see is the head, the heart, and the beginning of the tail.',
      objects: ['Antares · α Sco, the red heart', 'M4 · a rich cluster at the heart', 'Shaula · λ Sco, the stinger’s tip'],
      glow: null,
      stars: [
        { x: 28, y: 14, m: 2.29, label: 'Dschubba' },
        { x: 36, y: 24, m: 2.90 },
        { x: 44, y: 12, m: 3.33 },
        { x: 46, y: 46, m: 0.96, label: 'Antares' },
        { x: 52, y: 66, m: 2.31 },
        { x: 62, y: 82, m: 3.93 },
        { x: 78, y: 94, m: 1.86, label: 'Sargas' },
        { x: 92, y: 84, m: 3.32 },
        { x: 96, y: 66, m: 2.70 },
        { x: 88, y: 50, m: 2.89 },
        { x: 98, y: 42, m: 1.62, label: 'Shaula' },
        { x: 90, y: 34, m: 2.69 }
      ],
      lines: [[0, 1], [1, 2], [1, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8], [8, 9], [9, 10], [10, 11]]
    },
    {
      name: 'Cygnus', kind: 'constellation', color: '#f2c46c',
      seasons: ['summer'], when: 'Best in summer — the Northern Cross high overhead',
      find: 'Find Deneb, the bright star in the north, and swing down to Sadr at the cross’s center: the Northern Cross arms stretch outward from there, with Albireo — a gold-and-sapphire double star — at one wingtip. The whole cross glides through the summer Milky Way.',
      objects: ['Deneb · α Cyg, corner of the Summer Triangle', 'Albireo · β Cyg — gold and sapphire', 'Sadr · γ Cyg'],
      glow: null,
      stars: [
        { x: 52, y: 12, m: 1.25, label: 'Deneb' },
        { x: 48, y: 46, m: 2.23, label: 'Sadr' },
        { x: 56, y: 84, m: 2.44 },
        { x: 16, y: 58, m: 3.08, label: 'Albireo' },
        { x: 84, y: 60, m: 2.32 }
      ],
      lines: [[0, 1], [1, 2], [1, 3], [1, 4]]
    },
    {
      name: 'Lyra', kind: 'constellation', color: '#c9b8ff',
      seasons: ['summer'], when: 'Best in summer — a small harp between Swan and Eagle',
      find: 'Vega blazes at the top of a small parallelogram one star-hop on each side. It is the brightest star of the Summer Triangle — a right angle of light between it, Altair, and Deneb — and it holds the whole summer sky together.',
      objects: ['Vega · α Lyr', 'M57 · the Ring Nebula', 'ζ Lyrae — the double-double'],
      glow: null,
      stars: [
        { x: 42, y: 18, m: 0.03, label: 'Vega' },
        { x: 58, y: 46, m: 3.52, label: 'Sheliak' },
        { x: 72, y: 74, m: 3.25, label: 'Sulafat' },
        { x: 44, y: 70, m: 4.22 },
        { x: 34, y: 42, m: 4.28 }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 0], [3, 4]]
    },
    {
      name: 'Andromeda', kind: 'constellation', color: '#d4a465',
      seasons: ['autumn'], when: 'Best in autumn — a long chain climbing into the east',
      find: 'From the northeast corner of the Square of Pegasus — Alpheratz — follow the chain stars Mirach and Almach outward into the open sky. Far past μ Andromedae, where the chain ends, a faint glow is waiting: the Andromeda Galaxy.',
      objects: ['M31 · the Andromeda Galaxy', 'M110 · its faithful companion', 'Alpheratz · α And', 'Mirach · β And'],
      glow: null,
      stars: [
        { x: 8, y: 44, m: 2.06, label: 'Alpheratz' },
        { x: 28, y: 64, m: 2.05, label: 'Mirach' },
        { x: 44, y: 28, m: 1.99, label: 'Almach' },
        { x: 70, y: 50, m: 3.27 },
        { x: 94, y: 60, m: 3.4, label: 'M31', galaxy: true }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 4]]
    },
    {
      name: 'Boötes', kind: 'constellation', color: '#ffd98a',
      seasons: ['spring'], when: 'Best in spring — the kite anchored on Arcturus',
      find: 'Arcturus — the brightest star of the northern sky — sits at the base of a kite that opens to Izar above, Muphrid across, and Seginus below. A warm yellow giant with an eccentric orbit through the galaxy, it is the brightest beacon of the spring vault.',
      objects: ['Arcturus · α Boo, deep orange', 'Izar · ε Boo, gold against white', 'Muphrid · η Boo'],
      glow: null,
      stars: [
        { x: 16, y: 26, m: 2.68, label: 'Muphrid' },
        { x: 76, y: 20, m: 2.34, label: 'Izar' },
        { x: 62, y: 54, m: -0.05, label: 'Arcturus' },
        { x: 24, y: 72, m: 2.95, label: 'Seginus' },
        { x: 42, y: 46, m: 2.93 }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 0], [4, 0], [4, 2]]
    },
    {
      name: 'Auriga', kind: 'constellation', color: '#f2c46c',
      seasons: ['winter'], when: 'Best in winter — the pentagon above Taurus’s V',
      find: 'A five-star pentagon — an ice-cream cone — riding between the bright winter stars of Taurus and Orion. Capella, the cone’s point, shines gold; the Pleiades cluster nestles in the cone’s left side, and the Beehive in its belly.',
      objects: ['Capella · α Aur, gold at the point', 'M36 · M37 · M38 — three clusters in one field', 'Menkalinan · β Aur'],
      glow: null,
      stars: [
        { x: 54, y: 18, m: 0.08, label: 'Capella' },
        { x: 82, y: 40, m: 1.91, label: 'Menkalinan' },
        { x: 72, y: 66, m: 3.06 },
        { x: 42, y: 72, m: 2.61 },
        { x: 26, y: 46, m: 2.53 }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0]]
    },
    {
      name: 'Perseus', kind: 'constellation', color: '#7fe3c0',
      seasons: ['autumn', 'winter'], when: 'Best from autumn into winter — the hero with his demon star',
      find: 'Mirfak anchors a chain that swings out to Algol at the hand: its light winks in and out every 2.87 days — the first variable star ever timed, and the eponym of the Algol paradox. The double cluster pair floats off the chain like a set of jewels.',
      objects: ['Algol · β Per — the Demon Star', 'M34 · the Perseus cluster', 'NGC 869 · NGC 884 — the double cluster', 'NGC 891 · the Mirror Galaxy'],
      glow: null,
      stars: [
        { x: 60, y: 16, m: 3.32 },
        { x: 38, y: 34, m: 1.79, label: 'Mirfak' },
        { x: 26, y: 58, m: 2.57, label: 'Algenib' },
        { x: 52, y: 70, m: 2.12, label: 'Algol' },
        { x: 72, y: 84, m: 3.23 },
        { x: 92, y: 72, m: 3.58 }
      ],
      lines: [[0, 1], [1, 2], [1, 3], [3, 4], [4, 5]]
    },
    {
      name: 'Aquila', kind: 'constellation', color: '#d4a465',
      seasons: ['summer'], when: 'Best in summer — a small keystone in the Milky Way',
      find: 'A little triangle: Altair, the bright star of the Summer Triangle’s third corner, with Tarazed set above it and Alshain below. The whole figure glides through the summer Milky Way between the Swan and the Archer.',
      objects: ['Altair · α Aql — third of the Summer Triangle', 'Tarazed · γ Aql', 'Alshain · β Aql'],
      glow: null,
      stars: [
        { x: 46, y: 54, m: 0.76, label: 'Altair' },
        { x: 74, y: 38, m: 2.72, label: 'Tarazed' },
        { x: 42, y: 86, m: 3.71 }
      ],
      lines: [[0, 1], [0, 2], [1, 2]]
    },
    {
      name: 'The Seven Sisters', kind: 'asterism', color: '#9db4ff',
      seasons: ['winter'], when: 'Best in winter — a loose heptagon inside Taurus',
      find: 'Not a constellation but a cluster — and the most famous asterism of the northern sky. Alcyone leads a tight heptagon of blue-white stars; in genuinely dark air the group is wrapped in a thin veil of the birth cloud that still surrounds it.',
      objects: ['M45 · the Pleiades', 'Alcyone · η Tau, the brightest', 'the Pleiades — in the catalog of clusters'],
      glow: { x: 50, y: 55, r: 26, color: 'rgba(127,170,255,0.22)' },
      stars: [
        { x: 46, y: 50, m: 2.87, label: 'Alcyone' },
        { x: 36, y: 38, m: 3.63 },
        { x: 58, y: 36, m: 3.69 },
        { x: 64, y: 54, m: 3.87 },
        { x: 42, y: 66, m: 4.18 },
        { x: 66, y: 70, m: 4.31 },
        { x: 52, y: 78, m: 5.03 }
      ],
      lines: [[0, 1], [1, 2], [2, 3], [3, 5], [0, 4], [4, 6]]
    }
  ];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] || c;
    });
  }

  // Deterministic star-scatter so the background field is stable across visits.
  function lcg(seed) {
    var s = seed % 2147483647;
    if (s <= 0) s += 2147483646;
    return function () {
      s = (s * 16807) % 2147483647;
      return (s - 1) / 2147483646;
    };
  }

  function drawCard(i, c) {
    var canvas = document.getElementById('const-canvas-' + i);
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var SCALE = 2; // the 120-unit plate rendered at 2× for sharpness
    canvas.width = 120 * SCALE * dpr;
    canvas.height = 120 * SCALE * dpr;
    ctx.setTransform(dpr * SCALE, 0, 0, dpr * SCALE, 0, 0);

    // plate vignette
    var bg = ctx.createRadialGradient(60, 52, 8, 60, 60, 70);
    bg.addColorStop(0, 'rgba(24,28,42,0.85)');
    bg.addColorStop(1, 'rgba(7,7,10,0.15)');
    ctx.fillStyle = bg;
    ctx.beginPath();
    ctx.arc(60, 60, 58, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 0.6;
    ctx.beginPath();
    ctx.arc(60, 60, 58, 0, Math.PI * 2);
    ctx.stroke();

    // faint background field
    var rnd = lcg(7919 * (i + 1));
    for (var q = 0; q < 64; q++) {
      var ang = rnd() * Math.PI * 2;
      var rr = Math.sqrt(rnd()) * 56;
      var px = 60 + Math.cos(ang) * rr;
      var py = 60 + Math.sin(ang) * rr;
      ctx.globalAlpha = 0.05 + rnd() * 0.18;
      ctx.fillStyle = 'rgb(214,222,248)';
      ctx.beginPath();
      ctx.arc(px, py, 0.24 + rnd() * 0.4, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    // optional nebular / cluster glow behind the pattern
    if (c.glow) {
      var gg = ctx.createRadialGradient(c.glow.x, c.glow.y, 1, c.glow.x, c.glow.y, c.glow.r);
      gg.addColorStop(0, c.glow.color);
      gg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = gg;
      ctx.beginPath();
      ctx.arc(c.glow.x, c.glow.y, c.glow.r, 0, Math.PI * 2);
      ctx.fill();
    }

    // figure lines
    ctx.strokeStyle = c.color;
    ctx.globalAlpha = 0.55;
    ctx.lineWidth = 0.8;
    ctx.lineCap = 'round';
    ctx.beginPath();
    for (var L = 0; L < c.lines.length; L++) {
      var a = c.stars[c.lines[L][0]];
      var b = c.stars[c.lines[L][1]];
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
    }
    ctx.stroke();
    ctx.globalAlpha = 1;

    // stars, sized by magnitude
    for (var sI = 0; sI < c.stars.length; sI++) {
      var s = c.stars[sI];
      if (s.galaxy) {
        ctx.save();
        ctx.translate(s.x, s.y);
        ctx.rotate(-0.6);
        var e = ctx.createRadialGradient(0, 0, 0, 0, 0, 10);
        e.addColorStop(0, 'rgba(235,240,255,0.85)');
        e.addColorStop(0.45, 'rgba(178,198,255,0.42)');
        e.addColorStop(1, 'rgba(120,140,255,0)');
        ctx.fillStyle = e;
        ctx.beginPath();
        ctx.ellipse(0, 0, 10, 4.6, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      } else {
        var r = Math.max(1.3, 4.8 - s.m * 0.52);
        var halo = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, r * 2.7);
        halo.addColorStop(0, c.color);
        halo.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.globalAlpha = 0.26;
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(s.x, s.y, r * 2.7, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
        ctx.fill();
      }
      if (s.label) {
        ctx.fillStyle = 'rgba(228,231,244,0.82)';
        ctx.font = '5.5px ui-monospace, "SF Mono", Menlo, Consolas, monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'alphabetic';
        ctx.fillText(s.label, s.x, s.y - (s.galaxy ? 9 : 3.6));
      }
    }
  }

  function card(c, i) {
    var objs = '';
    for (var k = 0; k < c.objects.length; k++) {
      objs += '<span class="c-obj">' + esc(c.objects[k]) + '</span>';
    }
    return '<article class="constellation-card" data-seasons="' + esc(c.seasons.join(' ')) + '">' +
      '<div class="c-top">' +
      '<h3 class="c-name" style="color:' + esc(c.color) + '">' + esc(c.name) + '</h3>' +
      '<span class="c-kind' + (c.kind === 'asterism' ? ' asterism' : '') + '">' + esc(c.kind) + '</span>' +
      '</div>' +
      '<div class="c-when">' + esc(c.when) + '</div>' +
      '<div style="width:100%;aspect-ratio:1;border-radius:12px;background:radial-gradient(ellipse at 50% 40%,#141824,#070608);display:flex;align-items:center;justify-content:center;overflow:hidden;">' +
      '<canvas id="const-canvas-' + i + '" style="width:100%;height:100%;" aria-label="' + esc(c.name) + ' star chart"></canvas>' +
      '</div>' +
      '<p class="c-find">' + esc(c.find) + '</p>' +
      '<div class="c-objs">' + objs + '</div>' +
      '</article>';
  }

  var out = [];
  for (var m = 0; m < C.length; m++) {
    out.push(card(C[m], m));
  }
  grid.innerHTML = out.join('');

  for (var d = 0; d < C.length; d++) {
    drawCard(d, C[d]);
  }

  // seasonal filter
  function applyFilter(season) {
    var cards = grid.querySelectorAll('.constellation-card');
    var shown = 0;
    for (var i = 0; i < cards.length; i++) {
      var el = cards[i];
      var seasons = (el.getAttribute('data-seasons') || '').split(' ');
      var ok = season === 'all' || seasons.indexOf(season) !== -1;
      if (ok) {
        el.classList.remove('hidden');
        shown++;
      } else {
        el.classList.add('hidden');
      }
    }
    var label = season === 'all' ? 'all seasons' : season + ' is best';
    var count = document.getElementById('const-count');
    if (count) {
      count.textContent = 'Showing ' + shown + ' of ' + C.length + ' patterns · ' + label;
    }
    var chips = document.querySelectorAll('#season-chips [data-season]');
    for (var j = 0; j < chips.length; j++) {
      chips[j].setAttribute('aria-pressed', String(chips[j].getAttribute('data-season') === season));
    }
  }

  var chips = document.querySelectorAll('#season-chips [data-season]');
  for (var cI = 0; cI < chips.length; cI++) {
    chips[cI].addEventListener('click', function () {
      applyFilter(this.getAttribute('data-season'));
    });
  }

  applyFilter('all');
})();
