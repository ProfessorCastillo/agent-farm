(function () {
  'use strict';
  var D = window.STAR_DATA;
  var items = ['galaxies', 'nebulae', 'clusters', 'stars'].reduce(function (acc, k) {
    return acc.concat(D[k]);
  }, []);

  var typeClass = {
    Galaxy: 't-galaxy',
    Nebula: 't-nebula',
    Cluster: 't-cluster',
    Star: 't-star'
  };

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function card(o) {
    return '<article class="card" data-type="' + esc(o.type) + '">' +
      '<div><h3>' + esc(o.name) + '<span class="cat">' + esc(o.desig) + '</span></h3>' +
      '<span class="type-badge ' + (typeClass[o.type] || '') + '">' + esc(o.type) + '</span></div>' +
      '<p class="blurb">' + esc(o.blurb) + '</p>' +
      '<dl class="facts">' +
      '<div><dt>Type</dt><dd>' + esc(o.cat) + '</dd></div>' +
      '<div><dt>Const.</dt><dd>' + esc(o.const) + '</dd></div>' +
      '<div><dt>App. mag</dt><dd>' + esc(o.vis) + '</dd></div>' +
      '<div><dt>Distance</dt><dd>' + esc(o.dist) + '</dd></div>' +
      '<div><dt>Disk / span</dt><dd>' + esc(o.size) + '</dd></div>' +
      '</dl>' +
      '<details class="more"><summary>Field notes</summary><p>' + esc(o.long) + '</p></details>' +
      '</article>';
  }

  var wrap = document.getElementById('cards');
  wrap.innerHTML = items.map(card).join('');

  var chips = document.querySelectorAll('[data-filter]');

  function apply(filter) {
    var cards = wrap.querySelectorAll('.card');
    var shown = 0;
    for (var i = 0; i < cards.length; i++) {
      var match = filter === 'all' || cards[i].getAttribute('data-type') === filter;
      cards[i].classList.toggle('hidden', !match);
      if (match) shown++;
    }
    var label = filter === 'all' ? 'all types' : filter.toLowerCase() + 's';
    document.getElementById('countline').textContent =
      'Showing ' + shown + ' of ' + items.length + ' objects · ' + label;

    for (var j = 0; j < chips.length; j++) {
      chips[j].setAttribute('aria-pressed', String(chips[j].getAttribute('data-filter') === filter));
    }
  }

  for (var c = 0; c < chips.length; c++) {
    chips[c].addEventListener('click', function () {
      apply(this.getAttribute('data-filter'));
    });
  }
  apply('all');
})();
