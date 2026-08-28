// Seasonal finder widget for Observatio
// Determines what objects are favorably placed on any given date
(function () {
  'use strict';

  var finderWidget = document.getElementById('finder');
  if (!finderWidget) return;

  // Visibility seasons based on typical northern hemisphere viewing windows
  var VISIBILITY = {
    // Winter: December-February (primarily)
    winter: { months: [11, 0, 1], objects: ['Orion', 'Betelgeuse', 'Rigel', 'Sirius', 'Pleiades'] },
    // Spring: March-May
    spring: { months: [2, 3, 4], objects: ['Arcturus', 'M81', 'M82', 'Hercules', 'Ursa Major'] },
    // Summer: June-August
    summer: { months: [5, 6, 7], objects: ['Vega', 'Deneb', 'Ring', 'Lagoon', 'Trifid', 'Antares', 'Scorpius'] },
    // Autumn: September-November
    autumn: { months: [8, 9, 10], objects: ['Andromeda', 'Double Cluster', 'Cassiopeia', 'M31'] }
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

  function renderResults(dateStr, seasonKey) {
    var resultsDiv = document.getElementById('finder-results');
    if (!resultsDiv) return;

    var dateObj;
    if (/^\d{4}-\d{2}$/.test(dateStr)) {
      var parts = dateStr.split('-');
      dateObj = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, 1);
    } else {
      resultsDiv.innerHTML = '<p>Selected date is invalid. Please pick a valid month.</p>';
      return;
    }

    var month = dateObj.getMonth();
    var year = dateObj.getFullYear();
    var season = getSeason(month);
    
    if (!season) {
      resultsDiv.innerHTML = '<p>No seasonal data available for this period.</p>';
      return;
    }

    var html = '';
    html += '<div class="result-header">' + capitalize(seasonKey.toUpperCase()) + ' viewing season</div>';
    
    var foundObjects = [];
    var requested = season.objects || [];
    for (var i = 0; i < requested.length; i++) {
      var objName = requested[i];
      if (OBJECT_INFO[objName]) {
        foundObjects.push({ name: objName, info: OBJECT_INFO[objName] });
      }
    }

    if (foundObjects.length === 0) {
      html += '<p>No notable targets available this month.</p>';
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
        html += '<div class="result-item"><span class="result-name">' + type + 's</span><span class="result-detail">visible ' + monthName(month) + ' ' + year + '</span></div>';
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
    html += '<div class="result-item"><span class="result-detail" style="text-align:left;max-width:85%;opacity:0.9">' + (tips[seasonKey] || 'Observe from the darkest site you can reach.') + '</span></div>';

    resultsDiv.innerHTML = html;
  }

  function capitalize(str) {
    return str.replace(/(^|\s)\S/g, function(c) {
      return c.toUpperCase();
    });
  }

  function handleSearch(e) {
    if (e) e.preventDefault();
    var dateInput = document.getElementById('finder-date');
    var dateValue = dateInput ? dateInput.value : '';
    if (!dateValue) {
      renderResults(null, null);
      return;
    }
    var parts = dateValue.split('-');
    if (parts.length === 2 && /^\d{4}$/.test(parts[0]) && /^\d{1,2}$/.test(parts[1])) {
      var month = parseInt(parts[1]) - 1;
      if (month >= 0 && month <= 11) {
        var season = getSeason(month);
        renderResults(dateValue, season ? season.name : null);
      }
    }
  }

  function init() {
    finderWidget.style.display = 'block';
    var now = new Date();

    var summary = document.querySelector('#finder-panel summary');
    if (summary) {
      summary.addEventListener('click', function(e) {
        setTimeout(function() {
          var input = document.getElementById('finder-date');
          if (input && !document.activeElement) {
            input.focus();
          }
        }, 100);
      });
    }

    var dateInput = document.getElementById('finder-date');
    var mm = ('0' + (now.getMonth() + 1)).slice(-2);
    if (dateInput) {
      dateInput.value = now.getFullYear() + '-' + mm;
      dateInput.addEventListener('change', function() {
        handleSearch();
      });
    }

    var searchBtn = document.getElementById('finder-search');
    if (searchBtn) {
      searchBtn.addEventListener('click', handleSearch);
    }
  }

  init();

})();
