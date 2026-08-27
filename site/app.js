window.Stellar = {
  THEMES: {
    void: {
      name: 'deep-field drift',
      hint: 'drag to bend space — the dark between galaxies',
      bg0: '#06070d', bg1: '#0c1020',
      hsl: [230, 45], accent: '#8b93ff', accent2: '#c58bff'
    },
    nebula: {
      name: 'stirring nebula',
      hint: 'stir the nursery of new suns',
      bg0: '#0c0612', bg1: '#190b26',
      hsl: [280, 70], accent: '#d98cff', accent2: '#ff9ad5'
    },
    ember: {
      name: 'ember current',
      hint: 'trace the slow burn of a dying star',
      bg0: '#100704', bg1: '#1f1007',
      hsl: [20, 55], accent: '#ffb45e', accent2: '#ff7847'
    },
    frozen: {
      name: 'glacial field',
      hint: 'follow the hush of absolute zero',
      bg0: '#050e12', bg1: '#0a1c22',
      hsl: [185, 45], accent: '#63d8e8', accent2: '#5b9dff'
    }
  },

  MODES: {
    drift: {
      label: 'Drift',
      fx: function (px, py, m) {
        const dx = m.x - px, dy = m.y - py, d = Math.hypot(dx, dy);
        const R = m.r * 2.4;
        if (d > R) return null;
        const a = Math.atan2(dy, dx) + Math.PI / 2;
        const s = 0.32 * (1 - d / R);
        return [Math.cos(a) * s, Math.sin(a) * s];
      }
    },
    attract: {
      label: 'Attract',
      fx: function (px, py, m) {
        const dx = m.x - px, dy = m.y - py, d = Math.hypot(dx, dy);
        const R = m.r * 2.8;
        if (d > R || d < 1) return null;
        const s = Math.min(0.55, 60 / d) * (1 - d / R);
        return [dx / d * s, dy / d * s];
      }
    },
    repel: {
      label: 'Repel',
      fx: function (px, py, m) {
        const dx = m.x - px, dy = m.y - py, d = Math.hypot(dx, dy);
        const R = m.r;
        if (d > R || d < 1) return null;
        const s = Math.min(1.5, 130 / d) * (1 - d / R);
        return [-dx / d * s, -dy / d * s];
      }
    },
    orbit: {
      label: 'Orbit',
      fx: function (px, py, m) {
        const dx = m.x - px, dy = m.y - py, d = Math.hypot(dx, dy);
        const R = m.r * 2.6;
        if (d > R || d < 1) return null;
        const tang = 0.16 * (1 - d / R);
        const pull = Math.min(0.4, 42 / d) * (1 - d / R);
        return [dx / d * pull - dy / d * tang, dy / d * pull + dx / d * tang];
      }
    }
  },

  fmt: function (n) { return String(n).replace(/,/g, '\u2009'); }
};
