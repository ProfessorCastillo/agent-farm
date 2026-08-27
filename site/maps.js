// Sky-map coordinate layer. Adds a projected position (ra, dec) plus a category
// colour to every catalog entry stored on window.STAR_DATA, then exposes the
// whole dataset through window.Stellar for the map renderer.
(function () {
  'use strict';
  var R = window.Stellar, D = window.STAR_DATA;

  var ENTRY = {
    galaxies: [
      [0, 10.74, 41.17, 't-galaxy'], [1, 19.40, 47.20, 't-galaxy'],
      [2, 18.51, -11.17, 't-galaxy'], [3, 21.88, 54.92, 't-galaxy'],
      [4, 23.95, 69.24, 't-galaxy'], [5, 23.97, 69.97, 't-galaxy'],
      [6, 3.56, 30.48, 't-galaxy'], [7, 18.52, 12.39, 't-galaxy'],
      [8, 1.55, 15.70, 't-galaxy']
    ],
    nebulae: [
      [0, 8.91, -5.39, 't-nebula'], [1, 4.89, 33.98, 't-nebula'],
      [2, 27.07, -13.79, 't-nebula'], [3, 8.68, -2.75, 't-nebula'],
      [4, 29.02, -30.23, 't-nebula'], [5, 27.09, -27.02, 't-nebula'],
      [6, 32.02, 25.77, 't-nebula']
    ],
    clusters: [
      [0, 7.42, 24.11, 't-cluster'], [1, 33.24, 36.53, 't-cluster'],
      [2, 11.77, 19.15, 't-cluster'], [3, 4.52, 59.22, 't-cluster'],
      [4, 7.17, 15.92, 't-cluster'], [5, 31.71, -52.80, 't-cluster']
    ],
    stars: [
      [0, 16.33, 16.49, 't-star'], [1, 27.93, 38.78, 't-star'],
      [2, 14.92, 7.41, 't-star'], [3, 6.91, -8.20, 't-star'],
      [4, 24.75, -26.43, 't-star'], [5, 10.25, 5.24, 't-star']
    ]
  };

  var PALETTE = {
    't-galaxy': function (m) { var k = Math.min(1, Math.log(10000) / Math.max(1, m)); return 'hsl(228,' + (58 + 28 * k) + '%,' + 70 + k * 18 + '%);'; },
    't-nebula': function (m) { var k = Math.min(1, Math.log(10000) / Math.max(1, m)); return 'hsl(320,' + (58 + 24 * k) + '%,' + 66 + k * 22 + '%);'; },
    't-cluster': function (m) { var k = Math.min(1, Math.log(10000) / Math.max(1, m)); return 'hsl(160,' + (46 + 34 * k) + '%,' + 70 + k * 18 + '%);'; },
    't-star': function (m) { var k = Math.min(1, Math.log(10000) / Math.max(1, m)); return 'hsl(42,' + (58 + 22 * k) + '%,' + 70 + k * 22 + '%);'; }
  };

  Object.keys(ENTRY).forEach(function (key) {
    ENTRY[key].forEach(function (e) {
      var entry = D[key][e[0]];
      entry.ra = e[1]; entry.dec = e[2]; entry.catClass = e[3];
      entry.glow = PALETTE[e[3]];
      entry.mapSize = Math.max(3, 9 - Math.log(10000) / Math.max(1, e[1]));
    });
  });

  R.MAP_STYLE = {
    colours: {
      'Galaxy': 'hsl(228,72%,82%)',
      'Nebula': 'hsl(320,78%,80%)',
      'Cluster': 'hsl(160,66%,78%)',
      'Star': 'hsl(42,84%,78%)',
      't-galaxy': 'hsl(228,72%,82%)',
      't-nebula': 'hsl(320,78%,80%)',
      't-cluster': 'hsl(160,66%,78%)',
      't-star': 'hsl(42,84%,78%)',
      grid: 'rgba(120,160,255,0.16)',
      gridText: 'rgba(150,180,230,0.65)',
      line: 'rgba(140,170,230,0.32)'
    }
  };
})();
