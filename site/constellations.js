// Constellation drawings for Observatio.
// Each constellation is drawn on a canvas showing its traditional star pattern.
// Stars are sized by brightness; lines connect recognized shapes.

(function () {
  'use strict';

  var grid = document.getElementById('constellations');
  if (!grid) return;

  var CONSTELLATIONS = [
    {
      name: 'Ursa Major',
      subtitle: 'The Great Bear — Spring, northern sky',
      objects: ['M81 (Bode\x27s Galaxy)', 'M82 (Cigar Galaxy)', 'M101 (Pinwheel)'],
      color: '#9db4ff',
      stars: [
        { x: 30, y: 15 },
        { x: 50, y: 10 },
        { x: 72, y: 18 },
        { x: 75, y: 42 },
        { x: 52, y: 60 },
        { x: 30, y: 78 },
        { x: 10, y: 90 }
      ],
      lines: [[0,1],[1,2],[2,3],[3,0],[0,3],[3,4],[4,5],[5,6]]
    },
    {
      name: 'Orion',
      subtitle: 'The Hunter — Winter, southern sky',
      objects: ['M42 (Orion Nebula)', 'B33 (Horsehead)', 'Betelgeuse (\u03b1 Ori)', 'Rigel (\u03b2 Ori)'],
      color: '#ffd98a',
      stars: [
        { x: 85, y: 10 },
        { x: 72, y: 60 },
        { x: 45, y: 60 },
        { x: 38, y: 60 },
        { x: 25, y: 75 },
        { x: 10, y: 90 },
        { x: 48, y: 30 }
      ],

      lines: [[0,6],[6,2],[2,3],[3,4],[4,5]]
    },
    {
      name: 'Leo',
      subtitle: 'The Lion — Spring, eastern sky',
      objects: ['M65 (Leo I)', 'M66 (Leo II)', 'M96 Group'],
      color: '#ffd98a',

      stars: [
        { x: 12, y: 80 },
        { x: 25, y: 60 },
        { x: 40, y: 45 },
        { x: 60, y: 35 },
        { x: 82, y: 30 },
        { x: 100, y: 45 }
      ],

      lines: [[1,2],[2,3],[0,1],[3,4],[4,5],[1,0]]
    },
    {
      name: 'Cassiopeia',
      subtitle: 'The Queen — Autumn, circumpolar northern sky',
      objects: ['NGC 457 (E Tetrady)', 'NGC 1474'],
      color: '#7fe3c0',

      stars: [
        { x: 10, y: 65 },
        { x: 28, y: 30 },
        { x: 45, y: 55 },
        { x: 62, y: 28 },
        { x: 80, y: 50 }
      ],

      lines: [[0,1],[1,2],[2,3],[3,4]]
    },
    {
      name: 'Scorpius',
      subtitle: 'The Scorpion — Summer, southern sky',
      objects: ['M4 (globular cluster)', 'NGC 6273', 'Antares (\u03b1 Sco)'],
      color: '#f0a6ff',

      stars: [
        { x: 50, y: 10 },
        { x: 45, y: 30 },
        { x: 38, y: 50 },
        { x: 30, y: 75 },
        { x: 20, y: 100 },
        { x: 15, y: 90 },
        { x: 22, y: 80 },
        { x: 30, y: 70 }
      ],

      lines: [[0,1],[1,2],[2,3],[3,4],[3,5],[5,6],[6,7]]
    },
    {
      name: 'Cygnus',
      subtitle: 'The Swan — Summer, overhead in northern sky',
      objects: ['Deneb (\u03b1 Cyg)', 'Double Stars (nearby)'],
      color: '#f2c46c',

      stars: [
        { x: 55, y: 10 },
        { x: 55, y: 35 },
        { x: 55, y: 55 },
        { x: 55, y: 78 },
        { x: 30, y: 55 },
        { x: 12, y: 47 },
        { x: 45, y: 68 },
        { x: 80, y: 55 }
      ],

      lines: [[0,1],[1,2],[2,3],[3,4],[4,5],[2,6],[6,7]]
    },
    {
      name: 'Pleiades',
      subtitle: 'The Seven Sisters — Taurus cluster (winter)',
      objects: ['M45 (Pleiades)', 'Wisps of birth cloud'],
      color: '#9db4ff',

      stars: [
        { x: 60, y: 35 },
        { x: 50, y: 28 },
        { x: 70, y: 40 },
        { x: 55, y: 50 },
        { x: 65, y: 55 },
        { x: 48, y: 18 },
        { x: 58, y: 62 }
      ],

      lines: [[0,1],[1,3],[3,4],[4,2],[2,0],[5,1],[6,4]]
    },
    {
      name: 'Lyra',
      subtitle: 'The Harp — Summer, overhead in northern sky',
      objects: ['M57 (Ring Nebula)', 'Vega (\u03b1 Lyr)'],
      color: '#e9a8ff',

      stars: [
        { x: 55, y: 30 },
        { x: 40, y: 28 },
        { x: 70, y: 32 },
        { x: 42, y: 65 },
        { x: 68, y: 60 }
      ],

      lines: [[1,2],[2,4],[4,3],[3,1],[0,1],[0,2]]
    }
  ];

  function drawConstellation(canvasId, c) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var scale = 2;
    canvas.width = 120 * scale;
    canvas.height = 120 * scale;
    ctx.scale(scale, scale);

    if (c.lines) {
      ctx.beginPath();
      ctx.strokeStyle = c.color;
      ctx.globalAlpha = 0.35;
      ctx.lineWidth = 0.8;
      for (var i = 0; i < c.lines.length; i++) {
        var first = c.stars[c.lines[i][0]];
        var second = c.stars[c.lines[i][1]];
        ctx.moveTo(first.x, first.y);
        ctx.lineTo(second.x, second.y);
      }
      ctx.stroke();
    }

    ctx.globalAlpha = 0.9;
    ctx.fillStyle = c.color;
    for (var j = 0; j < c.stars.length; j++) {
      var star = c.stars[j];
      ctx.beginPath();
      ctx.arc(star.x, star.y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function cardHTML(c, i) {
    var objects = [];
    for (var k = 0; k < c.objects.length; k++) {
      objects.push('<li>' + c.objects[k] + '</li>');
    }
    return '<div class="constellation-card">' +
      '<canvas id="const-canvas-' + i + '" style="width:100%; max-width:18rem; height:auto; display:block; margin:0 auto;"></canvas>' +
      '<h3 style="color:' + c.color + '">' + c.name + '</h3>' +
      '<p class="lede" style="margin-top:0.25rem">' + c.subtitle + '</p>' +
      '<p class="cat-text">Notable objects:</p>' +
      '<ul style="font-size:0.82rem;color:var(--muted);margin-top:0.4rem;margin-left:1rem;line-height:1.7">' + objects.join('') + '</ul>' +
    '</div>';
  }

  var out = [];
  for (var m = 0; m < CONSTELLATIONS.length; m++) {
    out.push(cardHTML(CONSTELLATIONS[m], m));
  }
  grid.innerHTML = out.join('');

  for (var n = 0; n < CONSTELLATIONS.length; n++) {
    drawConstellation('const-canvas-' + n, CONSTELLATIONS[n]);
  }

})();
