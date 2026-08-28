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
      var map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
      return map[c] || c;
    });
  }

  function card(o) {
    return '<article class="card" data-type="' + esc(o.type) + '" data-name="' + esc(o.name).toLowerCase() + '">' +
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
  var searchInput = document.getElementById('catalog-search');
  var filter = 'all';
  var searchText = '';

  function apply() {
    var cards = wrap.querySelectorAll('.card');
    var shown = 0;
    for (var i = 0; i < cards.length; i++) {
      var cardEl = cards[i];
      var typeMatch = filter === 'all' || cardEl.getAttribute('data-type') === filter;
      var nameAttr = cardEl.getAttribute('data-name') || '';
      var searchMatch = !searchText || nameAttr.toLowerCase().indexOf(searchText.toLowerCase()) !== -1;
      var match = typeMatch && searchMatch;
      if (match) {
        shown++;
        if (isElementInDOM(cardEl)) {
          cardEl.style.display = '';
        } else {
          cardEl.classList.remove('hidden');
        }
      } else {
        cardEl.classList.add('hidden');
      }
    }
    var label = filter === 'all' ? 'all types' : filter.toLowerCase() + 's';
    var searchNote = searchText ? ' · matched "' + searchText + '"' : '';
    document.getElementById('countline').textContent =
      'Showing ' + shown + ' of ' + items.length + ' objects · ' + label + searchNote;

    for (var j = 0; j < chips.length; j++) {
      chips[j].setAttribute('aria-pressed', String(chips[j].getAttribute('data-filter') === filter));
    }
  }

  function isElementInDOM(el) { return !!el.offsetParent; }

  for (var c = 0; c < chips.length; c++) {
    chips[c].addEventListener('click', function () {
      filter = this.getAttribute('data-filter');
      apply();
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      searchText = this.value.trim();
      apply();
    });
  }

  apply();
})();
