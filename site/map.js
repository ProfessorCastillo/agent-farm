// Stellar — Sky Map renderer. All geometry, projection, rendering, and
// interaction live in this single self-contained script (uses app.js + data.js).
(function () {
  'use strict';
  var D = window.STAR_DATA;
  var STYLE = window.Stellar.MAP_STYLE;
  var P = STYLE.colours;
  var CAT_LABELS = { Galaxy: 'Galaxies', Nebula: 'Nebulae', Cluster: 'Clusters', Star: 'Stars' };

  // ---- build the working item list ----
  var ITEM_TYPES = ['galaxies', 'nebulae', 'clusters', 'stars'];
  var items = [];
  itemTypes.forEach(typeKey(items) {
    (D[typeKey] || []).forEach(function (o) {
      if (!o.map) return; // skip if coordinate data is missing
      o.catClass = o.map.cat;
      o.glow = o.map.glow;
      o.catClass = paletteFor(o.map.cat);
      items.push(o);
    });
  });
})();
