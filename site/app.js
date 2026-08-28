window.Stellar = {
  THEMES: {
    void: {
      name: 'deep-field drift',
      hint: 'drag to bend space — the dark between galaxies',
      bg0: '#0b0a08', bg1: '#14110d',
      hsl: [28, 45], accent: '#f2c46c', accent2: '#e07a5f'
    },
    nebula: {
      name: 'stirring nebula',
      hint: 'stir the nursery of new suns',
      bg0: '#0c0410', bg1: '#1a0f22',
      hsl: [320, 55], accent: '#e9a8ff', accent2: '#ffb3d9'
    },
    ember: {
      name: 'ember current',
      hint: 'trace the slow burn of a dying star',
      bg0: '#100704', bg1: '#1f1007',
      hsl: [20, 55], accent: '#f2c46c', accent2: '#e07a5f'
    },
    frozen: {
      name: 'glacial field',
      hint: 'follow the hush of absolute zero',
      bg0: '#050e12', bg1: '#0a1c22',
      hsl: [200, 45], accent: '#c9e6f2', accent2: '#b6d4ff'
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
    },
    pulsar: {
      label: 'Pulsar',
      fx: function (px, py, m) {
        const dx = m.x - px, dy = m.y - py, d = Math.hypot(dx, dy);
        const R = m.r * 3.0;
        if (d > R || d < 1) return null;
        const s = Math.sin(Date.now() * 0.01) * 0.5 * (1 - d / R);
        return [0, s];
      }
    },
    supernova: {
      label: 'Supernova',
      fx: function (px, py, m) {
        const dx = m.x - px, dy = m.y - py, d = Math.hypot(dx, dy);
        const R = m.r * 5.0;
        if (d > R || d < 1) return null;
        const s = Math.sin(Date.now() * 0.05) * 2.0 * (1 - d / R);
        return [dx / d * s, dy / d * s];
      }
    },
    constellations: {
      label: 'Constellations',
      fx: function () { return null; }
    }
  },

  fmt: function (n) { return String(n).replace(/,/g, '\u2009'); },
  toggleNightVision: function () {
    document.body.classList.toggle('night-vision');
    const btn = document.querySelector('.nv-toggle');
    if (btn) btn.setAttribute('aria-pressed', String(document.body.classList.contains('night-vision')));
  }
};
