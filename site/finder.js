// Seasonal finder widget for Stellar
// Uses season selection chips instead of date inputs (no forms, no data collection)
(function () {
  'use strict';

  var finderWidget = document.getElementById('finder');
  if (!finderWidget) return;

  // Visibility seasons based on typical northern hemisphere viewing windows
  var VISIBILITY = {
    winter:    { months: [11, 0, 1], objects: ['Orion', 'Betelgeuse', 'Rigel', 'Sirius', 'Pleiades'] },
    spring:    { months: [2, 3, 4],   objects: ['Arcturus', 'M81', 'M82', 'Hercules', 'Ursa Major'] },
    summer:    { months: [5, 6, 7],   objects: ['Vega', 'Deneb', 'Ring', 'Lagoon', 'Trifid', 'Antares', 'Scorpius'] },
    autumn:    { months: [8, 9, 10],  objects: ['Andromeda', 'Double Cluster', 'Cassiopeia', 'M31'] }
  };

  var OBJECT_INFO = {};
  if (window.STAR_DATA) {
    var cats = ['galaxies', 'nebulae', 'clusters', 'stars'];
    cats.forEach(function(catKey) {
      window.STAR_DATA[catKey].forEach(function(obj) {
        OBJECT_INFO[obj.name] = obj;
      });
    });
  }

  function getSeason(month) {
    for (var key in VISIBILITY) {
      if (VISIBILITY.hasOwnProperty(key)) {
        var v = VISIBILITY[key];
        if (v.months.indexOf(month) !== -1) {
          return { name: key, objects: v.objects };
        }
      }
    }
    return null;
  }

  function getSeasonName(season) {
    var names = { winter: 'Winter', spring: 'Spring', summer: 'Summer', autumn: 'Autumn' };
    return names[season] || season;
  }

  function monthName(index) {
    var months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    return months[index];
  }

  function formatMagnitude(mag) {
    if (mag === 'n/a' || mag === '—') return 'Var';
    var num = parseFloat(mag);
    if (isNaN(num)) return '~6';
    return String(num.toFixed(1));
  }

  function renderResults(seasonKey) {
    var resultsDiv = document.getElementById('finder-results');
    if (!resultsDiv) return;

    var season = getSeason(new Date().getMonth());
    if (!season && !seasonKey) {
      resultsDiv.innerHTML = '<p>No seasonal data available for this period.</p>';
      return;
    }

    var key = seasonKey || season.name;
    var seasonData = VISIBILITY[key];
    if (!seasonData) {
      resultsDiv.innerHTML = '<p>No seasonal data available for this period.</p>';
      return;
    }

    var html = '';
    html += '<div class="result-header">' + capitalize(key.toUpperCase()) + ' viewing season</div>';

    var foundObjects = [];
    var requested = seasonData.objects || [];
    for (var i = 0; i < requested.length; i++) {
      var objName = requested[i];
      if (OBJECT_INFO[objName]) {
        foundObjects.push({ name: objName, info: OBJECT_INFO[objName] });
      }
    }

    if (foundObjects.length === 0) {
      html += '<p>No notable targets available this season.</p>';
    } else {
      var byType = {};
      foundObjects.forEach(function(item) {
        var type = item.info.type;
        if (!byType[type]) byType[type] = [];
        byType[type].push(item);
      });

      var types = Object.keys(byType).sort();
      for (var j = 0; j < types.length; j++) {
        var type = types[j];
        html += '<div class="result-item"><span class="result-name">' + type + 's</span><span class="result-detail">visible this season</span></div>';
        var items = byType[type];
        for (var k = 0; k < items.length; k++) {
          var item = items[k];
          var shortDesc = (item.info.desig || '') + ' · ' + (item.info.const || '');
          html += '<div class="result-item">' +
            '<span class="result-name">' + item.name + '</span>' +
            '<span class="result-detail">mag ' + formatMagnitude(item.info.vis) + '<br><span style="opacity:0.7;font-size:0.88em">' + shortDesc + '</span></span>' +
            '</div>';
        }
      }
    }

    html += '<div class="result-header" style="margin-top:0.8rem">Tip</div>';
    var tips = {
      winter: 'Clear winter nights reveal Orion low in the south. Let your eyes adapt fully before hunting for faint nebulae.',
      spring: 'Spring skies are sparse but rich in galaxies; bring binoculars or a scope for Virgo Cluster targets.',
      summer: 'The Milky Way arcs overhead from dusk through midnight—use averted vision to reveal Lagoon and Trifid.',
      autumn: 'Andromeda rises east by late evening. Allow your eyes dark-adaptation time before attempting.'
    };
    html += '<div class="result-item"><span class="result-detail" style="text-align:left;max-width:85%;opacity:0.9">' + (tips[key] || 'Observe from the darkest site you can reach.') + '</span></div>';

    resultsDiv.innerHTML = html;
  }

  function capitalize(str) {
    return str.replace(/(^|\s)\S/g, function(c) {
      return c.toUpperCase();
    });
  }

  function init() {
    finderWidget.style.display = 'block';

    var chipsContainer = document.getElementById('season-chips');
    if (chipsContainer) {
      var seasons = Object.keys(VISIBILITY);
      for (var s = 0; s < seasons.length; s++) {
        var btn = document.createElement('button');
        btn.className = 'chip';
        btn.setAttribute('data-season', seasons[s]);
        btn.textContent = capitalize(seasons[s]) + ' sky';
        chipsContainer.appendChild(btn);
      }

      for (var ci = 0; ci < chipsContainer.children.length; ci++) {
        (function(chip) {
          var seasonKey = chip.getAttribute('data-season');
          chip.addEventListener('click', function() {
            // Update aria-pressed on all chips
            for (var c = 0; c < chipsContainer.children.length; c++) {
              chipsContainer.children[c].setAttribute('aria-pressed', String(chipsContainer.children[c] === chip));
            }
            renderResults(seasonKey);
          });
        })(chipsContainer.children[ci]);
      }

      // Default to current season
      var currentSeason = getSeason(new Date().getMonth());
      if (currentSeason) {
        renderResults(currentSeason.name);
      }
    }
  }

  init();

})();
