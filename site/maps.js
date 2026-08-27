// Sky-map coordinate layer. Adds a projected position (ra, dec) plus a category
// colour to every catalog entry stored on window.STAR_DATA, then exposes the
// whole dataset through window.Stellar for the map renderer.
(function () {
  'use strict';
  var R = window.Stellar, D = window.STAR_DATA;

  // coordinates: [index_in_data_array, right_ascension (hours), declination (deg), class]
  var ENTRY = {
    galaxies: [
      [0, 71.681, 47.200, 't-galaxy'],   // Andromeda M31
      [1, 196.785, 47.195, 't-galaxy'],  // Whirlpool M51
      [2, 270.252, -16.629, 't-galaxy'], // Pinwheel M101
      [3, 322.879, -11.622, 't-galaxy'], // Sombrero M104
      [4, 245.859, 69.088, 't-galaxy'],  // Bode's M81
      [5, 245.787, 69.664, 't-galaxy'],  // Cigar M82
      [6, 230.839, 30.667, 't-galaxy'],  // Triangulum M33
      [7, 187.706, 12.391, 't-galaxy'],  // M87
      [8, 205.361, 43.456, 't-galaxy']   // M100
    ],
    nebulae: [
      [0, 85.249, -5.391, 't-nebula'],   // Orion M42
      [1, 74.869, 33.891, 't-nebula'],   // Ring M57
      [2, 358.000, -13.917, 't-nebula'], // Eagle M16
      [3, 134.000, -2.700, 't-nebula'],  // Horsehead B33
      [4, 435.478, -30.245, 't-nebula'], // Lagoon M8
      [5, 329.616, -27.015, 't-nebula'], // Trifid M20
      [6, 483.206, 25.748, 't-nebula']   // Dumbbell M27
    ],
    clusters: [
      [0, 85.295, 24.116, 't-cluster'],   // Pleiades M45
      [1, 73.578, 36.790, 't-cluster'],   // Beehive M44
      [2, 250.423, 36.461, 't-cluster'],  // Hercules M13
      [3, 5.509, 57.149, 't-cluster'],    // Double Cluster NGC 869/884 (RA in hours → deg)
      [4, 32.255, 15.920, 't-cluster'],   // Hyades
      [5, 14.180, -61.182, 't-cluster']   // Jewel Box NGC 4755
    ],
    stars: [
      [0, 93.972, -8.725, 't-star'],   // Sirius
      [1, 279.234, 38.783, 't-star'],  // Vega
      [2, 88.792, 9.806, 't-star'],    // Betelgeuse (approx)
      [3, 78.634, -5.883, 't-star'],   // Rigel
      [4, 319.145, 26.067, 't-star'],  // Arcturus
      [5, 227.842, 45.987, 't-star'],  // Capella
      [6, 187.638, -67.339, 't-star'], // Canopus (bonus)
      [7, 41.280, 45.278, 't-star'],   // Polaris (bonus)
      [8, 14.535, 38.683, 't-star'],   // Aldebaran (bonus)
      [9, 171.356, -5.120, 't-star']   // Antares (bonus)
    ]
  };

  var PALETTE = {
    't-galaxy': 'hsl(228,72%,82%)',
    't-nebula': 'hsl(320,78%,80%)',
    't-cluster': 'hsl(160,66%,78%)',
    't-star': 'hsl(42,84%,78%)'
  };

  Object.keys(ENTRY).forEach(function (key) {
    ENTRY[key].forEach(function (e) {
      var entry = D[key][e[0]];
      if (!entry) return;
      // Convert RA hours to degrees
      entry.ra = e[1] * 15;
      entry.dec = e[2];
      entry.catClass = e[3];
      entry.glow = PALETTE[e[3]];
      var visNum = parseFloat(entry.vis);
      var magVal = isNaN(visNum) ? 9 : Math.min(9, Math.max(-2, visNum));
      entry.mapSize = Math.max(6, 14 - magVal * 1.1);
    });
  });

  R.MAP_STYLE = {
    colours: {
      'Galaxy': 'hsl(228,72%,82%)',
      'Nebula': 'hsl(320,78%,80%)',
      'Cluster': 'hsl(160,66%,78%)',
      'Star': 'hsl(42,84%,78%)',
      grid: 'rgba(120,160,255,0.16)',
      gridText: 'rgba(150,180,230,0.65)',
      line: 'rgba(140,170,230,0.32)'
    }
  };
})();
