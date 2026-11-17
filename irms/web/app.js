/* IRMS ému pro — interface. Aucun module externe, compatible Safari 15. */
(function () {
  'use strict';

  // ------------------------------------------------------------------ outils
  function $(id) { return document.getElementById(id); }
  function esc(text) {
    return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(value, digits) {
    if (value == null || isNaN(value)) return '—';
    return Number(value).toFixed(digits || 0).replace('.', ',');
  }
  function signed(value, digits) {
    if (value == null || isNaN(value)) return '—';
    var text = Math.abs(value).toFixed(digits == null ? 3 : digits).replace('.', ',');
    return (value > 0 ? '+' : value < 0 ? '−' : '±') + text;
  }
  function fmtTime(ms) {
    if (ms == null || !(ms > 0)) return '—';
    ms = Math.round(ms);
    var m = Math.floor(ms / 60000);
    var s = (ms % 60000) / 1000;
    return m + ':' + (s < 10 ? '0' : '') + s.toFixed(3);
  }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  function api(path, options) {
    options = options || {};
    var init = { method: options.method || 'GET', headers: {} };
    if (options.body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(options.body);
    }
    return fetch(path, init).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) throw new Error(data.error || ('Erreur ' + res.status));
        return data;
      });
    });
  }

  function toast(message, bad) {
    var el = document.createElement('div');
    el.className = 'toast' + (bad ? ' bad' : '');
    el.textContent = message;
    $('toasts').appendChild(el);
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, bad ? 6000 : 3800);
  }
  function fail(error) { toast(error && error.message ? error.message : String(error), true); }

  // ------------------------------------------------------------------- état
  var S = {
    tab: 'direct', status: null, combos: [], comboId: null, overview: null, track: null, coaching: null,
    lapId: null, corner: null, mapMode: 'drive', cursor: null, live: null, liveTrack: null, liveTrackKey: null,
    revision: null, eventSeq: null, ipad: false, loading: 0, colors: null
  };

  function colors() {
    if (!S.colors) {
      S.colors = {
        ink: cssVar('--ink'), ink2: cssVar('--ink-2'), ink3: cssVar('--ink-3'), line: cssVar('--line'),
        accent: cssVar('--accent'), brake: cssVar('--brake'), gas: cssVar('--gas'), part: cssVar('--part'),
        coast: cssVar('--coast'), good: cssVar('--good'), bad: cssVar('--bad'), track: cssVar('--track'),
        glass: cssVar('--glass-strong')
      };
    }
    return S.colors;
  }

  // ----------------------------------------------------------------- canvas
  function fit(canvas) {
    var rect = canvas.parentNode.getBoundingClientRect();
    var ratio = Math.min(window.devicePixelRatio || 1, 2.5);
    var w = Math.max(10, Math.round(rect.width));
    var h = Math.max(10, Math.round(rect.height));
    if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
      canvas.width = Math.round(w * ratio);
      canvas.height = Math.round(h * ratio);
    }
    var ctx = canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx: ctx, w: w, h: h };
  }

  var SPEED_STOPS = [[43, 108, 255], [36, 182, 160], [230, 184, 0], [224, 53, 43]];
  function speedColor(t) {
    t = clamp(t, 0, 1) * (SPEED_STOPS.length - 1);
    var i = Math.min(SPEED_STOPS.length - 2, Math.floor(t));
    var f = t - i, a = SPEED_STOPS[i], b = SPEED_STOPS[i + 1];
    return 'rgb(' + Math.round(a[0] + f * (b[0] - a[0])) + ',' + Math.round(a[1] + f * (b[1] - a[1])) + ',' +
      Math.round(a[2] + f * (b[2] - a[2])) + ')';
  }

  /* Couleur de chaque point du tracé selon le mode choisi. */
  function pointColors(track, mode) {
    var c = colors(), n = track.n, out = new Array(n + 1), i;
    var ch = (track.lap || track.ref).channels;
    if (mode === 'speed') {
      var lo = Infinity, hi = -Infinity;
      for (i = 0; i <= n; i++) { if (ch.speed[i] < lo) lo = ch.speed[i]; if (ch.speed[i] > hi) hi = ch.speed[i]; }
      for (i = 0; i <= n; i++) out[i] = speedColor((ch.speed[i] - lo) / Math.max(1, hi - lo));
    } else if (mode === 'delta' && track.delta) {
      var k = Math.max(2, Math.round(20 / track.step));
      for (i = 0; i <= n; i++) {
        var slope = track.delta[Math.min(n, i + k)] - track.delta[Math.max(0, i - k)];
        out[i] = slope > 0.006 ? c.bad : slope < -0.006 ? c.good : c.ink3;
      }
    } else {
      for (i = 0; i <= n; i++) {
        out[i] = ch.brake[i] > 0.08 ? c.brake : ch.gas[i] >= 0.95 ? c.gas : ch.gas[i] > 0.2 ? c.part : c.coast;
      }
    }
    return out;
  }

  function mapTransform(track, w, h, pad) {
    var x = track.x, y = track.y, minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, i;
    for (i = 0; i < x.length; i++) {
      if (x[i] < minX) minX = x[i]; if (x[i] > maxX) maxX = x[i];
      if (y[i] < minY) minY = y[i]; if (y[i] > maxY) maxY = y[i];
    }
    var bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
    var scale = Math.min((w - 2 * pad) / bw, (h - 2 * pad) / bh);
    var ox = (w - bw * scale) / 2 - minX * scale, oy = (h - bh * scale) / 2 - minY * scale;
    return { px: function (i) { return x[i] * scale + ox; }, py: function (i) { return y[i] * scale + oy; }, scale: scale };
  }

  function drawMap(canvas, track, opts) {
    var f = fit(canvas), ctx = f.ctx, c = colors();
    if (!track || !track.ready || !track.has_pos) return null;
    var n = track.n, pad = opts.pad || 34, T = mapTransform(track, f.w, f.h, pad), i;
    var thick = opts.thick || 7;
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    // support : piste en gris translucide
    ctx.beginPath();
    for (i = 0; i <= n; i++) { if (i) ctx.lineTo(T.px(i), T.py(i)); else ctx.moveTo(T.px(i), T.py(i)); }
    ctx.closePath();
    ctx.strokeStyle = c.track; ctx.lineWidth = thick + 9; ctx.stroke();
    // tracé coloré
    var cols = opts.colors, sel = opts.sel, a = 0, b = n;
    if (sel != null && track.corners[sel]) {
      a = Math.round(track.corners[sel].seg_start / track.step);
      b = Math.round(track.corners[sel].seg_end / track.step);
    }
    var start = 0;
    for (i = 1; i <= n; i++) {
      if (i === n || cols[i] !== cols[start] || (sel != null && (i === a || i === b))) {
        ctx.beginPath(); ctx.moveTo(T.px(start), T.py(start));
        for (var j = start + 1; j <= i; j++) ctx.lineTo(T.px(j), T.py(j));
        ctx.strokeStyle = cols[start];
        ctx.globalAlpha = (sel == null || (start >= a && start < b)) ? 1 : 0.22;
        ctx.lineWidth = thick; ctx.stroke();
        start = i;
      }
    }
    ctx.globalAlpha = 1;
    // ligne de départ
    var tx = T.px(3) - T.px(0), ty = T.py(3) - T.py(0), tl = Math.sqrt(tx * tx + ty * ty) || 1;
    ctx.beginPath();
    ctx.moveTo(T.px(0) - ty / tl * 11, T.py(0) + tx / tl * 11);
    ctx.lineTo(T.px(0) + ty / tl * 11, T.py(0) - tx / tl * 11);
    ctx.strokeStyle = c.ink; ctx.lineWidth = 3; ctx.stroke();
    // repères de freinage de la référence et noms des virages
    var k = Math.max(2, Math.round(8 / track.step));
    ctx.font = '650 ' + (opts.font || 12) + 'px ' + getComputedStyle(document.body).fontFamily;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    track.corners.forEach(function (corner, index) {
      var dim = sel != null && sel !== index;
      ctx.globalAlpha = dim ? 0.3 : 1;
      var ia = clamp(Math.round(corner.apex / track.step), k, n - k);
      var ax = T.px(ia) - T.px(ia - k), ay = T.py(ia) - T.py(ia - k);
      var bx = T.px(ia + k) - T.px(ia), by = T.py(ia + k) - T.py(ia);
      var len = Math.sqrt((ax + bx) * (ax + bx) + (ay + by) * (ay + by)) || 1;
      var ux = (ax + bx) / len, uy = (ay + by) / len;
      var side = (ax * by - ay * bx) > 0 ? -1 : 1; // extérieur du virage
      var off = (opts.font || 12) + 12;
      var lx = T.px(ia) + side * -uy * off, ly = T.py(ia) + side * ux * off;
      var label = corner.name, tw = ctx.measureText(label).width + 12, th = (opts.font || 12) + 8;
      lx = clamp(lx, tw / 2 + 2, f.w - tw / 2 - 2); ly = clamp(ly, th / 2 + 2, f.h - th / 2 - 2);
      ctx.fillStyle = c.glass; roundRect(ctx, lx - tw / 2, ly - th / 2, tw, th, th / 2); ctx.fill();
      ctx.strokeStyle = c.line; ctx.lineWidth = 1; ctx.stroke();
      ctx.fillStyle = c.ink; ctx.fillText(label, lx, ly + 0.5);
      if (corner.ref.brake_on != null) {
        var ib = clamp(Math.round(corner.ref.brake_on / track.step), 2, n - 2);
        var dx = T.px(ib + 2) - T.px(ib - 2), dy = T.py(ib + 2) - T.py(ib - 2), dl = Math.sqrt(dx * dx + dy * dy) || 1;
        ctx.beginPath();
        ctx.moveTo(T.px(ib) - dy / dl * (thick + 5), T.py(ib) + dx / dl * (thick + 5));
        ctx.lineTo(T.px(ib) + dy / dl * (thick + 5), T.py(ib) - dx / dl * (thick + 5));
        ctx.strokeStyle = c.brake; ctx.lineWidth = 3; ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;
    function dot(index, radius, color) {
      index = clamp(index, 0, n);
      var i0 = Math.floor(index), fr = index - i0, i1 = Math.min(n, i0 + 1);
      var x = T.px(i0) + fr * (T.px(i1) - T.px(i0)), y = T.py(i0) + fr * (T.py(i1) - T.py(i0));
      ctx.beginPath(); ctx.arc(x, y, radius + 5, 0, 6.2832); ctx.fillStyle = color; ctx.globalAlpha = 0.25; ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath(); ctx.arc(x, y, radius, 0, 6.2832); ctx.fillStyle = color; ctx.fill();
      ctx.lineWidth = 2; ctx.strokeStyle = '#fff'; ctx.stroke();
    }
    if (opts.cursor != null) dot(opts.cursor, 5, c.ink);
    if (opts.car != null) dot(opts.car, opts.carRadius || 7, c.accent);
    return T;
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.arc(x + w - r, y + r, r, -1.5708, 0);
    ctx.lineTo(x + w, y + h - r); ctx.arc(x + w - r, y + h - r, r, 0, 1.5708);
    ctx.lineTo(x + r, y + h); ctx.arc(x + r, y + h - r, r, 1.5708, 3.1416);
    ctx.lineTo(x, y + r); ctx.arc(x + r, y + r, r, 3.1416, 4.7124); ctx.closePath();
  }

  var CHART_PAD = { l: 44, r: 10, t: 16, b: 20 };

  function chartRange() {
    var track = S.track;
    if (S.corner != null && track.corners[S.corner]) {
      var corner = track.corners[S.corner];
      return [Math.max(0, corner.seg_start - 30), Math.min(track.length, corner.seg_end + 30)];
    }
    return [0, track.length];
  }

  function niceStep(span, target) {
    var raw = span / target, pow = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), m = raw / pow;
    return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * pow;
  }

  function drawChart(canvas, cfg) {
    var f = fit(canvas), ctx = f.ctx, c = colors(), track = S.track;
    var P = CHART_PAD, w = f.w - P.l - P.r, h = f.h - P.t - P.b;
    var range = chartRange(), x0 = range[0], x1 = range[1], step = track.step;
    var i0 = Math.max(0, Math.floor(x0 / step)), i1 = Math.min(track.n, Math.ceil(x1 / step));
    var lo = cfg.min, hi = cfg.max, s, i;
    if (lo == null || hi == null) {
      lo = Infinity; hi = -Infinity;
      for (s = 0; s < cfg.series.length; s++) {
        for (i = i0; i <= i1; i++) { var v = cfg.series[s].data[i]; if (v < lo) lo = v; if (v > hi) hi = v; }
      }
      if (cfg.zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
      var padY = Math.max((hi - lo) * 0.08, cfg.minSpan || 1e-3);
      lo -= padY; hi += padY;
    }
    function X(d) { return P.l + (d - x0) / (x1 - x0) * w; }
    function Y(v) { return P.t + (1 - (v - lo) / (hi - lo)) * h; }
    ctx.font = '600 11px ' + getComputedStyle(document.body).fontFamily;
    // bandes de virages
    track.corners.forEach(function (corner, index) {
      if (corner.end < x0 || corner.start > x1) return;
      var a = X(Math.max(x0, corner.start)), b = X(Math.min(x1, corner.end));
      ctx.fillStyle = c.accent; ctx.globalAlpha = S.corner === index ? 0.16 : 0.07;
      ctx.fillRect(a, P.t, Math.max(1, b - a), h);
      ctx.globalAlpha = 1;
      if (cfg.names && b - a > 0) {
        ctx.fillStyle = c.ink3; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
        var label = corner.name;
        if (ctx.measureText(label).width < Math.max(26, (b - a) + 30)) ctx.fillText(label, (a + b) / 2, P.t - 4);
      }
    });
    // graduations
    var ys = niceStep(hi - lo, 3.2);
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.lineWidth = 1;
    for (var gy = Math.ceil(lo / ys) * ys; gy <= hi + 1e-9; gy += ys) {
      ctx.strokeStyle = c.line; ctx.beginPath(); ctx.moveTo(P.l, Y(gy)); ctx.lineTo(P.l + w, Y(gy)); ctx.stroke();
      ctx.fillStyle = c.ink3; ctx.fillText(cfg.fmt ? cfg.fmt(gy) : String(Math.round(gy)), P.l - 6, Y(gy));
    }
    var xs = niceStep(x1 - x0, 7);
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (var gx = Math.ceil(x0 / xs) * xs; gx <= x1; gx += xs) {
      ctx.fillStyle = c.ink3; ctx.fillText(Math.round(gx) + ' m', clamp(X(gx), P.l + 14, P.l + w - 16), P.t + h + 5);
    }
    if (cfg.zero) {
      ctx.strokeStyle = c.ink3; ctx.beginPath(); ctx.moveTo(P.l, Y(0)); ctx.lineTo(P.l + w, Y(0)); ctx.stroke();
    }
    // courbes
    ctx.save(); ctx.beginPath(); ctx.rect(P.l, P.t - 1, w, h + 2); ctx.clip();
    ctx.lineJoin = 'round';
    cfg.series.forEach(function (serie) {
      ctx.beginPath();
      for (i = i0; i <= i1; i++) {
        var px = X(i * step), py = Y(serie.data[i]);
        if (i === i0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      if (serie.fill) {
        ctx.lineTo(X(i1 * step), Y(serie.base || 0)); ctx.lineTo(X(i0 * step), Y(serie.base || 0)); ctx.closePath();
        ctx.fillStyle = serie.color; ctx.globalAlpha = 0.16; ctx.fill(); ctx.globalAlpha = 1;
        ctx.beginPath();
        for (i = i0; i <= i1; i++) {
          var qx = X(i * step), qy = Y(serie.data[i]);
          if (i === i0) ctx.moveTo(qx, qy); else ctx.lineTo(qx, qy);
        }
      }
      ctx.strokeStyle = serie.color; ctx.lineWidth = serie.width || 2;
      ctx.setLineDash(serie.dash || []); ctx.stroke(); ctx.setLineDash([]);
    });
    if (S.cursor != null) {
      var cx = X(S.cursor * step);
      ctx.strokeStyle = c.ink; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(cx, P.t); ctx.lineTo(cx, P.t + h); ctx.stroke();
    }
    ctx.restore();
    canvas._x = { x0: x0, x1: x1, l: P.l, w: w };
  }

  // ---------------------------------------------------------------- données
  function loadStatus() {
    return api('/api/status').then(function (status) {
      S.status = status;
      $('version').textContent = status.version;
      document.title = 'IRMS ému pro ' + status.version;
      renderPedals();
      renderDiagnostic();
    });
  }

  function loadCombos() {
    return api('/api/combos').then(function (data) {
      S.combos = data.combos;
      var exists = S.combos.some(function (c) { return c.id === S.comboId; });
      if (!exists) {
        S.comboId = null;
        var current = S.combos.filter(function (c) { return c.id === data.current; })[0];
        if (current) S.comboId = current.id; else if (S.combos.length) S.comboId = S.combos[0].id;
        S.lapId = null; S.corner = null;
      }
      renderComboSelect();
    });
  }

  function loadCombo() {
    if (S.comboId == null) {
      S.overview = null; S.track = null; S.coaching = null;
      renderAll();
      return Promise.resolve();
    }
    var id = S.comboId, token = ++S.loading;
    var lap = S.lapId ? '?lap=' + S.lapId : '';
    return Promise.all([
      api('/api/combos/' + id), api('/api/combos/' + id + '/track' + lap), api('/api/combos/' + id + '/coaching')
    ]).then(function (res) {
      if (token !== S.loading) return;
      S.overview = res[0]; S.track = res[1]; S.coaching = res[2];
      if (S.lapId && !(S.track.lap)) S.lapId = null;
      if (S.corner != null && (!S.track.corners || !S.track.corners[S.corner])) S.corner = null;
      S.cursor = null;
      renderAll();
    });
  }

  function reload() {
    return loadCombos().then(loadCombo).catch(fail);
  }

  function selectCombo(id) {
    if (id === S.comboId) return;
    S.comboId = id; S.lapId = null; S.corner = null;
    renderComboSelect();
    loadCombo().catch(fail);
  }

  // ------------------------------------------------------------------ rendu
  function comboLabel(c) { return c.car + ' — ' + c.track + (c.config ? ' (' + c.config + ')' : ''); }

  function renderComboSelect() {
    var select = $('combo-select'), html = '';
    S.combos.forEach(function (c) {
      html += '<option value="' + c.id + '"' + (c.id === S.comboId ? ' selected' : '') + '>' + esc(comboLabel(c)) +
        ' · ' + c.laps + ' tour' + (c.laps > 1 ? 's' : '') + '</option>';
    });
    if (!S.combos.length) html = '<option value="">Aucun tour enregistré</option>';
    else if (S.comboId == null) html = '<option value="" selected>Nouveau profil : roule un tour complet</option>' + html;
    select.innerHTML = html;
    select.disabled = !S.combos.length;
  }

  function renderKpis() {
    var o = S.overview, html = '';
    function kpi(label, value, small) {
      html += '<div class="kpi"><span>' + label + '</span><b>' + value + (small ? '<small>' + small + '</small>' : '') + '</b></div>';
    }
    if (o) {
      kpi('Record', fmtTime(o.best_ms));
      kpi('Meilleur théorique', fmtTime(o.theoretical_ms),
        o.best_ms && o.theoretical_ms ? signed((o.theoretical_ms - o.best_ms) / 1000, 2) + ' s' : '');
      kpi('Régularité', o.stats.stdev_ms != null ? '± ' + num(o.stats.stdev_ms / 1000, 2) + ' s' : '—',
        o.stats.recent ? 'sur ' + o.stats.recent + ' tours' : '');
      kpi('Tours valides', o.stats.valid + ' / ' + o.stats.total);
    }
    $('kpis').innerHTML = html;
  }

  function lapOptionLabel(lap) {
    return 'Tour ' + lap.no + ' · ' + fmtTime(lap.time_ms) + (lap.is_best ? ' · record' : '') +
      (lap.valid ? '' : ' · invalide');
  }

  function renderAnalyse() {
    var o = S.overview, track = S.track, select = $('lap-select');
    var ready = track && track.ready;
    var html = '<option value="">Tour de référence seul</option>';
    if (o) {
      o.laps.slice().reverse().forEach(function (lap) {
        if (lap.is_ref) return;
        html += '<option value="' + lap.id + '"' + (lap.id === S.lapId ? ' selected' : '') + '>' + esc(lapOptionLabel(lap)) + '</option>';
      });
    }
    select.innerHTML = html;
    select.disabled = !ready;
    $('btn-fullap').hidden = S.corner == null;
    var empty = $('map-empty');
    if (!ready) {
      empty.className = 'empty on';
      empty.textContent = S.comboId == null ? 'Aucun tour enregistré pour ce profil. Roule un tour complet : le plan se dessine tout seul.'
        : 'Pas encore de tour complet pour ce profil.';
    } else if (!track.has_pos) {
      empty.className = 'empty on';
      empty.textContent = 'Ce tour ne contient pas de position sur le circuit : le plan est indisponible, mais les courbes et les virages restent analysés.';
    } else {
      empty.className = 'empty';
    }
    var note = '';
    if (ready) {
      var refLap = o && o.laps.filter(function (l) { return l.is_ref; })[0];
      note = 'Référence : tour ' + (refLap ? refLap.no : '?') + ' · ' + fmtTime(track.ref.time_ms) +
        (o && o.ref_pinned ? ' (choisie)' : track.ref_provisional ? ' (provisoire : aucun tour valide)' : ' (ton record)');
    }
    $('map-note').textContent = note;
    $('chart-note').textContent = ready ? (track.lap ? 'Bleu : tour ' + lapNo(track.lap.lap_id) + ' · Gris : référence' : 'Choisis un tour pour le comparer à la référence') : '';
    renderLegend();
    renderCornerTable();
    drawAnalyse();
  }

  function lapNo(id) {
    var lap = S.overview && S.overview.laps.filter(function (l) { return l.id === id; })[0];
    return lap ? lap.no : '?';
  }

  function renderLegend() {
    var html;
    if (S.mapMode === 'speed') {
      html = '<span><i class="sw sw-grad"></i>Lent → rapide</span>';
    } else if (S.mapMode === 'delta') {
      html = S.track && S.track.lap
        ? '<span><i class="sw sw-good"></i>Tu gagnes du temps</span><span><i class="sw sw-bad"></i>Tu perds du temps</span><span><i class="sw sw-ref"></i>Équivalent</span>'
        : '<span>Choisis un tour étudié pour voir où il gagne et perd du temps.</span>';
    } else {
      html = '<span><i class="sw sw-brake"></i>Freinage</span><span><i class="sw sw-gas"></i>Plein gaz</span>' +
        '<span><i class="sw sw-part"></i>Gaz partiels</span><span><i class="sw sw-coast"></i>Roue libre</span>';
    }
    html += '<span><i class="sw sw-brake" style="width:4px;height:14px"></i>Début de freinage de référence</span>';
    $('map-legend').innerHTML = html;
  }

  function pair(lapValue, refValue, digits, hasLap) {
    if (!hasLap) return num(refValue, digits);
    return '<b>' + num(lapValue, digits) + '</b> <span class="pair">/ ' + num(refValue, digits) + '</span>';
  }

  function renderCornerTable() {
    var table = $('corner-table'), track = S.track;
    if (!track || !track.ready || !track.corners.length) {
      table.innerHTML = '<tbody><tr><td class="left muted">' +
        (track && track.ready ? 'Aucun virage détecté sur ce tour.' : 'Les virages apparaissent après le premier tour complet.') + '</td></tr></tbody>';
      return;
    }
    var hasLap = !!track.lap;
    var head = '<thead><tr><th class="left">Virage</th><th>Début du freinage<span class="sub">m avant la corde</span></th>' +
      '<th>Vitesse mini<span class="sub">km/h</span></th><th>Reprise des gaz<span class="sub">m après la corde</span></th>' +
      '<th>Vitesse de sortie<span class="sub">km/h</span></th><th>Temps du tronçon<span class="sub">s</span></th>' +
      (hasLap ? '<th>Écart<span class="sub">tour − référence</span></th>' : '') +
      '<th>Ton meilleur<span class="sub">s</span></th></tr></thead>';
    var rows = track.corners.map(function (corner) {
      var r = corner.ref, l = corner.lap || {};
      function before(m) { return m.brake_on == null ? null : corner.apex - m.brake_on; }
      function after(m) { return m.gas_on == null ? null : m.gas_on - corner.apex; }
      var loss = hasLap ? corner.loss : null;
      var brakeCell = (hasLap ? before(l) : before(r)) == null && before(r) == null ? '<span class="pair">sans freiner</span>'
        : pair(before(l), before(r), 0, hasLap);
      return '<tr class="click' + (S.corner === corner.index ? ' sel' : '') + '" data-corner="' + corner.index + '">' +
        '<td class="left"><b class="cname">' + esc(corner.name) + '</b><span class="sub">' + esc(corner.dir) + ' · ' +
        esc(corner.kind) + (corner.angle != null ? ' · ' + corner.angle + '°' : '') +
        ' · <button class="linkbtn" data-rename="' + corner.index + '">renommer</button></span></td>' +
        '<td>' + brakeCell + '</td>' +
        '<td>' + pair(l.min_speed, r.min_speed, 0, hasLap) + '</td>' +
        '<td>' + pair(after(l), after(r), 0, hasLap) + '</td>' +
        '<td>' + pair(l.exit_speed, r.exit_speed, 0, hasLap) + '</td>' +
        '<td>' + pair(l.time, r.time, 2, hasLap) + '</td>' +
        (hasLap ? '<td class="' + (loss > 0.02 ? 'pos' : loss < -0.02 ? 'neg' : '') + '">' + signed(loss, 2) + '</td>' : '') +
        '<td>' + num(corner.best_time, 2) + '</td></tr>';
    }).join('');
    table.innerHTML = head + '<tbody>' + rows + '</tbody>';
  }

  function drawAnalyse() {
    var track = S.track;
    ['ch-speed', 'ch-pedals', 'ch-delta'].forEach(function (id) { fit($(id)); });
    if (!track || !track.ready) { fit($('map')); return; }
    var c = colors();
    drawMap($('map'), track, { colors: pointColors(track, S.mapMode), sel: S.corner, cursor: S.cursor });
    var ref = track.ref.channels, lap = track.lap ? track.lap.channels : null;
    var series = [{ data: ref.speed, color: c.ink3, width: lap ? 1.6 : 2.2 }];
    if (lap) series.push({ data: lap.speed, color: c.accent, width: 2.2 });
    drawChart($('ch-speed'), { series: series, names: true, minSpan: 5 });
    var main = lap || ref;
    function pct(a) { return a.map(function (v) { return v * 100; }); }
    var pedals = [{ data: pct(main.gas), color: c.gas, width: 1.8, fill: true }, { data: pct(main.brake), color: c.brake, width: 1.8, fill: true }];
    if (lap) {
      pedals.unshift({ data: pct(ref.brake), color: c.brake, width: 1.2, dash: [4, 3] });
      pedals.unshift({ data: pct(ref.gas), color: c.gas, width: 1.2, dash: [4, 3] });
    }
    drawChart($('ch-pedals'), { series: pedals, min: -4, max: 104 });
    if (track.delta) {
      drawChart($('ch-delta'), { series: [{ data: track.delta, color: c.accent, width: 2.2, fill: true }], zero: true, minSpan: 0.05,
        fmt: function (v) { return signed(v, Math.abs(v) < 1 ? 2 : 1); } });
    } else {
      var f = fit($('ch-delta'));
      f.ctx.fillStyle = c.ink3; f.ctx.font = '600 13px ' + getComputedStyle(document.body).fontFamily;
      f.ctx.textAlign = 'center'; f.ctx.textBaseline = 'middle';
      f.ctx.fillText('Choisis un tour étudié pour afficher son écart à la référence.', f.w / 2, f.h / 2);
    }
    renderReadout();
  }

  function renderReadout() {
    var track = S.track, el = $('readout');
    if (!track || !track.ready || S.cursor == null) { el.textContent = ''; return; }
    var i = S.cursor, ref = track.ref.channels, lap = track.lap ? track.lap.channels : null, main = lap || ref;
    var text = Math.round(i * track.step) + ' m · ' + num(main.speed[i]) + ' km/h';
    if (lap) text += ' (réf. ' + num(ref.speed[i]) + ')';
    text += ' · rapport ' + main.gear[i] + ' · gaz ' + num(main.gas[i] * 100) + ' % · frein ' + num(main.brake[i] * 100) + ' %';
    if (track.delta) text += ' · écart ' + signed(track.delta[i], 3) + ' s';
    el.textContent = text;
  }

  var SEVERITY = { 'prioritaire': 'bad', 'à travailler': 'warn', 'à surveiller': '' };

  function renderCoaching() {
    var data = S.coaching, head = $('coach-head'), cards = $('coach-cards');
    if (!data) {
      head.innerHTML = '<div class="text">Aucun profil sélectionné.</div>';
      cards.innerHTML = '';
      return;
    }
    if (!data.ready) {
      var done = Math.min(data.valid_laps, data.needed);
      head.innerHTML = '<div class="big"><span>Tours valides</span><b>' + data.valid_laps + ' / ' + data.needed + '</b></div>' +
        '<div class="text">Le coaching compare tes passages entre eux : il lui faut au moins ' + data.needed +
        ' tours valides avec cette voiture sur ce circuit.</div>';
      cards.innerHTML = '<div class="panel glass wait"><h3>Encore ' + (data.needed - done) + ' tour' + (data.needed - done > 1 ? 's' : '') +
        ' valide' + (data.needed - done > 1 ? 's' : '') + '</h3><p>Roule proprement, sans sortir des limites de piste. Les conseils apparaissent ici tout seuls.</p>' +
        '<div class="progress"><i style="width:' + (100 * done / data.needed) + '%"></i></div></div>' + data.cards.map(cardHtml).join('');
      return;
    }
    var strengths = data.strengths.length ? 'Tes points forts : ' + data.strengths.map(esc).join(', ') + ' (moins de 0,04 s perdue en moyenne).'
      : 'Aucun virage n\'est encore parfaitement régulier : c\'est normal au début.';
    head.innerHTML = '<div class="big"><span>Gain possible par tour</span><b>' + num(data.potential_s, 2) + ' s</b></div>' +
      '<div class="big"><span>Record</span><b>' + fmtTime(data.best_ms) + '</b></div>' +
      '<div class="big"><span>Meilleur théorique</span><b>' + fmtTime(data.theoretical_ms) + '</b></div>' +
      '<div class="text">Analyse de tes ' + data.laps_used + ' derniers tours valides, virage par virage, par rapport à ton meilleur passage dans chacun. ' + strengths + '</div>';
    cards.innerHTML = data.cards.length ? data.cards.map(cardHtml).join('')
      : '<div class="panel glass wait"><h3>Rien à signaler</h3><p>Tes derniers tours sont réguliers partout. Pour progresser encore, cherche un nouveau record : il deviendra la nouvelle cible.</p></div>';
  }

  function cardHtml(card) {
    var evidence = '';
    if (card.evidence && card.evidence.length) {
      evidence = '<table class="evi"><thead><tr><th>Mesure</th><th>Tes tours</th><th>Ton meilleur passage</th></tr></thead><tbody>' +
        card.evidence.map(function (e) {
          function cell(v) {
            if (e.kind === 'rel') {
              if (v == null) return 'pas atteint dans le virage';
              return num(Math.abs(v), 0) + ' m ' + (v < 0 ? 'avant' : 'après') + ' la corde';
            }
            return num(v, 0) + ' ' + esc(e.unit);
          }
          return '<tr><td>' + esc(e.label) + '</td><td><b>' + cell(e.you) + '</b></td><td>' + cell(e.target) + '</td></tr>';
        }).join('') + '</tbody></table>';
    }
    var chips = '<span class="tag ' + (SEVERITY[card.severity] || '') + '">' + esc(card.severity) + '</span>' +
      '<span class="tag">' + esc(card.pattern) + '</span>';
    if (card.frequency) chips += '<span class="tag">' + card.frequency[0] + ' tour' + (card.frequency[0] > 1 ? 's' : '') + ' sur ' + card.frequency[1] + '</span>';
    var gain = card.gain_s != null ? '<span class="gain">' + (card.corner != null ? '−' : '') + num(card.gain_s, 2) + ' s</span>' : '';
    return '<article class="panel glass card">' +
      '<div class="card-top">' + chips + gain + '</div>' +
      '<h3>' + esc(card.title) + '</h3>' +
      '<dl><div><dt>Constat</dt><dd>' + esc(card.observation) + '</dd></div>' +
      '<div><dt>Hypothèse</dt><dd>' + esc(card.hypothesis) + '</dd></div>' +
      '<div><dt>Exercice</dt><dd class="exo">' + esc(card.exercise) + '</dd></div></dl>' + evidence +
      '<div class="card-foot"><span class="muted">' + (card.confidence ? 'Confiance : ' + esc(card.confidence) : '') + '</span>' +
      (card.corner != null ? '<button class="btn" data-see="' + card.corner + '">Voir sur la piste</button>' : '') + '</div></article>';
  }

  function renderPedals() {
    var value = S.status ? S.status.pedals : 'position';
    Array.prototype.forEach.call($('pedals-seg').children, function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-pedals') === value ? 'true' : 'false');
    });
  }

  function renderLaps() {
    var o = S.overview, table = $('lap-table');
    $('btn-del-combo').disabled = !o;
    if (!o || !o.laps.length) {
      table.innerHTML = '<tbody><tr><td class="left muted">Aucun tour pour ce profil. Les tours complets s\'enregistrent tout seuls quand tu roules.</td></tr></tbody>';
      $('profile-card').innerHTML = '<h3>Profil mesuré de la voiture</h3><p class="muted" style="margin-top:8px">Disponible après le premier tour complet.</p>';
      return;
    }
    var bs = o.best_sectors;
    var head = '<thead><tr><th class="left">Tour</th><th>Temps</th><th>Écart</th><th>S1</th><th>S2</th><th>S3</th><th class="left">État</th><th class="left">Actions</th></tr></thead>';
    var rows = o.laps.slice().reverse().map(function (lap) {
      function sector(k) {
        if (!lap.sectors) return '<td>—</td>';
        var best = lap.valid && bs && Math.abs(lap.sectors[k] - bs[k]) < 0.0005;
        return '<td class="' + (best ? 'neg' : '') + '">' + num(lap.sectors[k], 3) + '</td>';
      }
      var state = lap.valid ? '<span class="tag good">Valide</span>' : '<span class="tag bad">Invalide</span>';
      if (lap.is_ref) state += ' <span class="tag accent">Référence</span>';
      if (lap.is_best) state += ' <span class="tag good">Record</span>';
      var sub = lap.valid ? '' : '<span class="sub">' + esc(lap.reason || 'raison inconnue') + '</span>';
      return '<tr data-lap="' + lap.id + '"><td class="left"><b>' + lap.no + '</b><span class="sub">' + esc(String(lap.created_at).slice(0, 16)) +
        ' · temps ' + esc(lap.time_source) + '</span></td>' +
        '<td><b>' + fmtTime(lap.time_ms) + '</b></td>' +
        '<td class="' + (lap.gap_ms > 0 ? 'pos' : '') + '">' + (lap.gap_ms == null ? '—' : lap.gap_ms === 0 ? '—' : signed(lap.gap_ms / 1000, 3)) + '</td>' +
        sector(0) + sector(1) + sector(2) +
        '<td class="left">' + state + sub + '</td>' +
        '<td class="left"><span class="row-actions">' +
        '<button class="btn small" data-act="study">Étudier</button>' +
        '<button class="btn small" data-act="ref">' + (lap.is_ref && o.ref_pinned ? 'Libérer la référence' : 'Référence') + '</button>' +
        '<button class="btn small" data-act="valid">' + (lap.valid ? 'Invalider' : 'Valider') + '</button>' +
        '<a class="btn small" href="/api/laps/' + lap.id + '/export?format=json" download>JSON</a>' +
        '<a class="btn small" href="/api/laps/' + lap.id + '/export?format=csv" download>CSV</a>' +
        '<button class="btn small danger" data-act="delete">Supprimer</button></span></td></tr>';
    }).join('');
    table.innerHTML = head + '<tbody>' + rows + '</tbody>';
    var p = o.profile, html = '<h3>Profil mesuré de la voiture</h3><p class="muted" style="margin-top:4px">' + esc(o.combo.car) +
      ', d\'après ton tour de référence. Ce sont tes mesures, pas des données constructeur.</p>';
    if (p) {
      html += '<div class="stat-list">' +
        '<span>Vitesse maximale</span><b>' + num(p.top_speed) + ' km/h</b>' +
        '<span>Vitesse minimale</span><b>' + num(p.min_speed) + ' km/h</b>' +
        '<span>Freinage le plus fort</span><b>' + num(p.brake_g, 2) + ' g</b>' +
        '<span>Accélération la plus forte</span><b>' + num(p.accel_g, 2) + ' g</b>' +
        '<span>Appui latéral (98e centile)</span><b>' + num(p.lat_g, 2) + ' g</b>' +
        '<span>Rapport le plus haut</span><b>' + p.max_gear + '</b>' +
        '<span>Part du tour à plein gaz</span><b>' + num(p.full_throttle) + ' %</b>' +
        '<span>Part du tour au frein</span><b>' + num(p.braking) + ' %</b>' +
        '<span>Virages détectés</span><b>' + o.corners + '</b></div>';
    }
    $('profile-card').innerHTML = html;
  }

  function renderDiagnostic() {
    var s = S.status, live = S.live || {};
    if (!s) return;
    function item(state, title, detail) {
      return '<li><span class="dot ' + state + '">' + (state === 'ok' ? '✓' : state === 'ko' ? '!' : '·') + '</span><div><b>' + esc(title) +
        '</b><small>' + esc(detail) + '</small></div></li>';
    }
    var demo = s.source === 'demo', html = '<h2>État de la connexion</h2><ul class="checks">';
    html += item('ok', 'IRMS ému pro ' + s.version, demo ? 'Mode démo : données simulées, aucun lien avec le jeu.' : 'Source : mémoire partagée d\'Assetto Corsa EVO, en lecture seule.');
    if (!demo) {
      html += item(s.platform_ok ? 'ok' : 'ko', 'Système compatible', s.platform_ok ? 'Windows détecté.' : 'La mémoire partagée du jeu n\'existe que sous Windows.');
      html += item(live.connected ? 'ok' : 'na', 'Jeu détecté', live.connected ? 'Assetto Corsa EVO ' + (s.game_version || '') + ' publie ses données.' : 'Lance le jeu et charge une session : la connexion est automatique.');
      var problems = live.problems || s.problems || [];
      html += item(!live.connected ? 'na' : problems.length ? 'ko' : 'ok', 'Données cohérentes',
        !live.connected ? 'Vérifié dès que le jeu est détecté.' : problems.length ? 'Disposition mémoire inattendue : ' + problems.join(' ; ') + '. Enregistrement suspendu. Signale-le sur GitHub avec le rapport ci-dessous.' : 'Les valeurs lues sont plausibles pour cette version du jeu.');
    }
    var suspect = live.connected && live.status !== 2 && live.suspect && live.suspect.length;
    html += item(suspect ? 'ko' : live.connected && live.status === 2 ? 'ok' : 'na', 'En piste',
      !live.connected ? 'En attente.'
        : suspect ? 'Statut lu : ' + (live.status_label || '—') + ', mais certaines valeurs sont anormales (' + live.suspect.join(' ; ') + '). Si tu roules en ce moment, la mise à jour du jeu a changé la disposition mémoire : signale-le sur GitHub avec le rapport ci-dessous.'
        : live.status === 2 ? 'Statut : en piste.'
        : 'Statut lu : ' + (live.status_label || '—') + '. Si tu roules et que ce statut ne passe pas à « en piste », signale-le sur GitHub avec le rapport ci-dessous.');
    html += item(live.car ? 'ok' : 'na', 'Voiture et circuit reconnus', live.car ? live.car + ' — ' + live.track + (live.config ? ' (' + live.config + ')' : '') : 'Affichés dès qu\'une session est chargée.');
    html += '</ul><p class="muted" style="margin-top:12px">' + esc(live.message || s.message || '') + '</p>';
    if (demo && s.demo_cars && s.demo_cars.length) {
      html += '<h3 style="margin-top:16px">Voiture de démonstration</h3><p class="muted" style="margin:4px 0 10px">Change de voiture pour voir IRMS la détecter et basculer sur son propre profil.</p><span class="row-actions">' +
        s.demo_cars.map(function (car) {
          return '<button class="btn small" data-demo-car="' + esc(car) + '"' + (live.car === car ? ' disabled' : '') + '>' + esc(car) + '</button>';
        }).join('') + '</span>';
    }
    if (html !== lastUi.diagStatus) { lastUi.diagStatus = html; $('diag-status').innerHTML = html; }
    var ipad = '<h2>Afficher sur l\'iPad</h2>';
    if (s.lan && s.lan_urls.length) {
      ipad += '<p class="muted" style="margin-top:6px">Le PC et l\'iPad doivent être sur le même Wi-Fi. Ouvre Safari sur l\'iPad et tape :</p>' +
        s.lan_urls.map(function (u) { return '<span class="url">' + esc(u) + '?vue=ipad</span>'; }).join('') +
        '<ol class="steps"><li>Dans Safari, touche le bouton Partager.</li><li>Choisis « Sur l\'écran d\'accueil » pour l\'ouvrir en plein écran.</li><li>L\'iPad affiche les données ; les modifications se font sur le PC.</li></ol>';
    } else if (s.lan) {
      ipad += '<p class="muted" style="margin-top:6px">Mode réseau actif, mais aucune adresse réseau trouvée. Vérifie que le PC est connecté au Wi-Fi ou au réseau.</p>';
    } else {
      ipad += '<p class="muted" style="margin-top:6px">Le mode réseau est désactivé : seul ce PC peut ouvrir IRMS.</p>' +
        '<ol class="steps"><li>Ferme la fenêtre noire d\'IRMS.</li><li>Double-clique <b>DEMARRER_IPAD.bat</b>.</li><li>Reviens sur cette page : l\'adresse à taper sur l\'iPad s\'affichera ici.</li></ol>';
    }
    if (ipad !== lastUi.diagIpad) { lastUi.diagIpad = ipad; $('diag-ipad').innerHTML = ipad; }
  }

  function loadReport() {
    api('/api/doctor').then(function (data) { $('diag-report').textContent = JSON.stringify(data, null, 2); }).catch(fail);
  }

  function renderAll() {
    renderKpis();
    renderAnalyse();
    renderCoaching();
    renderLaps();
    drawLive(true);
  }

  // ----------------------------------------------------------------- direct
  var PHASES = { gaz: 'Accélère', approche: 'Prépare le freinage', frein: 'Freine', corde: 'Vise la corde', passe: 'Sans freiner' };
  var lastUi = {};
  function setText(id, value) { if (lastUi[id] !== value) { lastUi[id] = value; $(id).textContent = value; } }
  function setWidth(id, value) { var v = Math.round(value * 10) / 10; if (lastUi[id] !== v) { lastUi[id] = v; $(id).style.width = v + '%'; } }
  function setClass(id, value) { if (lastUi[id + ':c'] !== value) { lastUi[id + ':c'] = value; $(id).className = value; } }
  function setAttr(id, name, value) { var k = id + ':' + name; if (lastUi[k] !== value) { lastUi[k] = value; $(id).setAttribute(name, value); } }

  function renderConn(prefix) {
    var live = S.live || {}, state = 'off', text = 'Connexion…';
    if (live.source === 'demo') { state = 'demo'; text = 'Mode démo'; }
    else if (!live.connected) { state = 'idle'; text = S.status && !S.status.platform_ok ? 'Windows requis' : 'En attente du jeu'; }
    else if (live.problems && live.problems.length) { state = 'bad'; text = 'Données incohérentes'; }
    else if (live.status === 2) { state = 'live'; text = 'Connecté · en piste'; }
    else { state = 'idle'; text = 'Connecté · ' + (live.status_label || 'en attente'); }
    setAttr(prefix + 'conn', 'data-state', state);
    setText(prefix + 'conn-text', text);
  }

  function gearLabel(g) { return g < 0 ? 'R' : g === 0 ? 'N' : String(g); }

  function renderCue(prefix, live) {
    var cue = live.cue, id = prefix + 'cue';
    if (!live.connected || live.status !== 2) {
      setAttr(id, 'data-phase', ''); setText(id + '-name', '—'); setText(id + '-dir', '');
      setText(id + '-action', live.connected ? 'En attente de la piste' : 'En attente du jeu'); setWidth(id + '-bar', 0);
      setText(id + '-meta', live.connected ? 'Les repères s\'affichent quand tu roules.' : (live.message || ''));
      return;
    }
    if (!cue) {
      setAttr(id, 'data-phase', ''); setText(id + '-name', 'Découverte'); setText(id + '-dir', '');
      setText(id + '-action', 'Roule un tour complet'); setWidth(id + '-bar', 0);
      setText(id + '-meta', 'Pas encore de tour de référence pour cette voiture sur ce circuit.');
      return;
    }
    setAttr(id, 'data-phase', cue.phase);
    setText(id + '-name', cue.name);
    setText(id + '-dir', 'virage à ' + cue.dir);
    var action = PHASES[cue.phase] || '';
    var bar = 0;
    if (cue.phase === 'approche' && cue.to_brake != null) { action = 'Frein dans ' + cue.to_brake + ' m'; bar = 100 * (1 - cue.to_brake / 200); }
    else if (cue.phase === 'frein') { bar = 100; }
    else if (cue.phase === 'gaz' && cue.to_brake != null) { bar = 0; }
    setText(id + '-action', action);
    setWidth(id + '-bar', clamp(bar, 0, 100));
    var meta = 'Corde dans ' + Math.max(0, cue.to_apex) + ' m · ' + cue.min_speed + ' km/h mini en ' + gearLabel(cue.min_gear) + (cue.min_gear > 0 ? 'e' : '');
    if (!cue.braking) meta += ' · la référence ne freine pas ici';
    setText(id + '-meta', meta);
  }

  function renderLive() {
    var live = S.live;
    if (!live) return;
    renderConn(''); renderConn('i-');
    var on = live.connected, driving = on && live.status === 2;
    var title = on && live.car ? live.car : (live.source === 'evo' || !live.source ? 'En attente d\'Assetto Corsa EVO' : 'En attente');
    var sub = on && live.track ? live.track + (live.config ? ' · ' + live.config : '') + ' · ' + Math.round(live.length) + ' m' : (live.message || '');
    setText('live-title', title); setText('live-sub', sub);
    setText('i-car', on && live.car ? live.car : 'En attente du jeu'); setText('i-track', on && live.track ? live.track + (live.config ? ' · ' + live.config : '') : '');
    var speed = on ? Math.round(live.speed) : 0;
    setText('speed', String(speed)); setText('i-speed', String(speed));
    setText('gear', on ? gearLabel(live.gear) : 'N'); setText('i-gear', on ? gearLabel(live.gear) : 'N');
    var rpm = on && live.max_rpm > 0 ? clamp(100 * live.rpm / live.max_rpm, 0, 100) : 0;
    setWidth('rpm', rpm); setWidth('i-rpm', rpm);
    setWidth('p-gas', on ? live.gas * 100 : 0); setWidth('p-brake', on ? live.brake * 100 : 0);
    setWidth('i-gas', on ? live.gas * 100 : 0); setWidth('i-brake', on ? live.brake * 100 : 0);
    setText('v-gas', on ? String(Math.round(live.gas * 100)) : '0'); setText('v-brake', on ? String(Math.round(live.brake * 100)) : '0');
    setText('refspeed', driving && live.ref_speed != null ? String(Math.round(live.ref_speed)) : '—');
    var delta = driving ? live.delta : null;
    var deltaText = delta == null ? '—' : signed(delta, 2);
    var deltaClass = 'delta' + (delta == null ? '' : delta <= 0 ? ' good' : ' bad');
    setText('delta', deltaText); setClass('delta', deltaClass); setText('i-delta', deltaText); setClass('i-delta', deltaClass);
    var cur = on ? fmtTime(live.lap_time_ms).slice(0, -2) : '—';
    setText('t-cur', cur); setText('i-cur', cur);
    setText('t-last', on ? fmtTime(live.last_lap_ms) : '—'); setText('i-last', on ? fmtTime(live.last_lap_ms) : '—');
    setText('t-ref', on ? fmtTime(live.ref_ms) : '—'); setText('i-ref', on ? fmtTime(live.ref_ms) : '—');
    var state = '', stateClass = 'lapstate';
    if (driving) {
      if (live.in_pit) state = 'Dans les stands : ce tour ne comptera pas.';
      else if (!live.recording) state = 'Tour de lancement : l\'enregistrement démarre à la ligne.';
      else if (!live.valid) { state = 'Tour invalide : ' + (live.reason || 'signalé par le jeu') + '.'; stateClass += ' bad'; }
      else { state = 'Enregistrement du tour en cours.'; stateClass += ' good'; }
    }
    setText('lapstate', state); setClass('lapstate', stateClass);
    renderCue('', live); renderCue('i-', live);
  }

  function liveTrackNeeded() {
    var live = S.live;
    if (!live || !live.connected || live.combo_id == null) { S.liveTrack = null; S.liveTrackKey = null; return; }
    var key = live.combo_id + ':' + live.revision;
    if (key === S.liveTrackKey) return;
    S.liveTrackKey = key;
    if (live.combo_id === S.comboId && S.track && !S.lapId) { S.liveTrack = S.track; return; }
    api('/api/combos/' + live.combo_id + '/track').then(function (track) {
      if (S.liveTrackKey === key) { S.liveTrack = track; drawLive(true); }
    }).catch(function () { S.liveTrackKey = null; });
  }

  var liveColors = null, liveColorsFor = null;
  function drawLive(force) {
    var live = S.live, track = S.liveTrack;
    var canvas = S.ipad ? $('i-map') : $('live-map');
    if (!S.ipad && S.tab !== 'direct') return;
    var empty = $('live-map-empty');
    if (!track || !track.ready || !track.has_pos) {
      fit(canvas);
      var message = !live || !live.connected ? (live && live.message ? live.message : 'En attente du jeu.')
        : track && track.ready ? 'Position sur le circuit indisponible pour cette référence.'
        : 'Nouveau profil détecté. Termine un tour complet : le plan du circuit et tes repères de freinage apparaîtront ici.';
      empty.textContent = message; empty.className = 'empty on';
      return;
    }
    empty.className = 'empty';
    if (liveColorsFor !== track || force) { liveColors = pointColors({ n: track.n, step: track.step, ref: track.ref }, 'drive'); liveColorsFor = track; }
    var car = live && live.connected && live.status === 2 ? live.dist / track.step : null;
    drawMap(canvas, track, { colors: liveColors, car: car, pad: S.ipad ? 44 : 34, thick: S.ipad ? 8 : 7, font: S.ipad ? 14 : 12, carRadius: S.ipad ? 9 : 7 });
  }

  function onLive(live) {
    S.live = live;
    if (live.event && live.event.seq !== S.eventSeq) {
      if (S.eventSeq !== null || live.event) {
        if (S.eventSeq !== null) {
          toast(live.event.valid ? 'Tour enregistré : ' + fmtTime(live.event.time_ms)
            : 'Tour invalide (' + (live.event.reason || 'signalé par le jeu') + ') : ' + fmtTime(live.event.time_ms));
        }
      }
      S.eventSeq = live.event.seq;
    } else if (!live.event && S.eventSeq === null) {
      S.eventSeq = 0;
    }
    if (live.revision != null && live.revision !== S.revision) {
      var first = S.revision === null;
      S.revision = live.revision;
      if (!first) scheduleReload();
    }
    if ($('follow').checked && live.connected && live.car) {
      var key = live.car + '|' + live.track + '|' + live.config;
      if (key !== S.followKey) {
        var had = S.followKey != null;
        S.followKey = key;
        if (had) toast('Détecté : ' + live.car + ' — ' + live.track);
        S.followPending = true;
      }
      if (S.followPending && live.combo_id !== S.comboId) {
        S.followPending = live.combo_id == null;
        S.comboId = live.combo_id; S.lapId = null; S.corner = null;
        renderComboSelect();
        loadCombo().catch(fail);
      } else if (S.followPending && live.combo_id === S.comboId) {
        S.followPending = false;
      }
    }
    liveTrackNeeded();
    if (!frameQueued) { frameQueued = true; requestAnimationFrame(frame); }
  }

  var frameQueued = false, diagTick = 0;
  function frame() {
    frameQueued = false;
    renderLive();
    drawLive(false);
    if (S.tab === 'diagnostic' && ++diagTick % 30 === 0) renderDiagnostic();
  }

  var reloadTimer = null;
  function scheduleReload() {
    clearTimeout(reloadTimer);
    reloadTimer = setTimeout(function () { loadStatus().catch(function () {}); reload(); }, 400);
  }

  function connect() {
    var es;
    try { es = new EventSource('/api/live'); } catch (e) { return poll(); }
    es.onmessage = function (event) { try { onLive(JSON.parse(event.data)); } catch (e) { /* image ignorée */ } };
    es.onerror = function () {
      S.live = { connected: false, message: 'IRMS ne répond plus. Vérifie que la fenêtre noire est toujours ouverte sur le PC.', source: S.live && S.live.source };
      renderLive(); drawLive(false);
    };
  }
  function poll() {
    api('/api/live.json').then(onLive).catch(function () {});
    setTimeout(poll, 250);
  }

  // ------------------------------------------------------------ interactions
  function setTab(tab) {
    S.tab = tab;
    Array.prototype.forEach.call(document.querySelectorAll('.tabs button'), function (b) {
      b.setAttribute('aria-selected', b.getAttribute('data-tab') === tab ? 'true' : 'false');
    });
    Array.prototype.forEach.call(document.querySelectorAll('.view'), function (v) {
      v.hidden = v.getAttribute('data-view') !== tab;
    });
    $('context').style.display = tab === 'diagnostic' ? 'none' : '';
    if (tab === 'analyse') drawAnalyse();
    if (tab === 'direct') drawLive(true);
    if (tab === 'diagnostic') { renderDiagnostic(); loadReport(); }
    try { history.replaceState(null, '', location.pathname + location.search + '#' + tab); } catch (e) { /* sans importance */ }
  }

  function setIpad(on) {
    S.ipad = on;
    $('ipad').hidden = !on;
    document.body.className = on ? 'ipad-on' : '';
    try {
      var url = location.pathname + (on ? '?vue=ipad' : '') + location.hash;
      history.replaceState(null, '', url);
    } catch (e) { /* sans importance */ }
    lastUi = {};
    renderLive(); drawLive(true);
    if (!on && S.tab === 'analyse') drawAnalyse();
  }

  function setTheme(theme, save) {
    document.documentElement.setAttribute('data-theme', theme);
    S.colors = null; liveColorsFor = null;
    if (save) { try { localStorage.setItem('irms-theme', theme); } catch (e) { /* stockage indisponible */ } }
    drawAnalyse(); drawLive(true);
  }

  function selectCorner(index) {
    S.corner = S.corner === index ? null : index;
    S.cursor = null;
    $('btn-fullap').hidden = S.corner == null;
    renderCornerTable();
    drawAnalyse();
  }

  function chartHover(event) {
    var track = S.track, canvas = event.currentTarget, info = canvas._x;
    if (!track || !track.ready || !info) return;
    var point = event.touches ? event.touches[0] : event;
    var rect = canvas.getBoundingClientRect();
    var d = info.x0 + (point.clientX - rect.left - info.l) / info.w * (info.x1 - info.x0);
    S.cursor = clamp(Math.round(d / track.step), 0, track.n);
    drawAnalyse();
  }

  function mapHover(event) {
    var track = S.track;
    if (!track || !track.ready || !track.has_pos) return;
    var canvas = $('map'), rect = canvas.getBoundingClientRect();
    var point = event.touches ? event.touches[0] : event;
    var T = mapTransform(track, rect.width, rect.height, 34);
    var mx = point.clientX - rect.left, my = point.clientY - rect.top, best = -1, bestD = 40 * 40;
    for (var i = 0; i <= track.n; i++) {
      var dx = T.px(i) - mx, dy = T.py(i) - my, dd = dx * dx + dy * dy;
      if (dd < bestD) { bestD = dd; best = i; }
    }
    if (best >= 0 && best !== S.cursor) { S.cursor = best; drawAnalyse(); }
  }

  function clearCursor() { if (S.cursor != null) { S.cursor = null; drawAnalyse(); } }

  function lapAction(lapId, action) {
    var o = S.overview;
    var lap = o.laps.filter(function (l) { return l.id === lapId; })[0];
    if (!lap) return;
    if (action === 'study') {
      S.lapId = lap.is_ref ? null : lap.id; S.corner = null;
      setTab('analyse');
      loadCombo().catch(fail);
    } else if (action === 'ref') {
      var release = lap.is_ref && o.ref_pinned;
      api('/api/combos/' + S.comboId + '/reference', { method: 'POST', body: { lap_id: release ? null : lap.id } })
        .then(function () { toast(release ? 'Référence automatique : ton record.' : 'Tour ' + lap.no + ' défini comme référence.'); if (S.lapId === lap.id) S.lapId = null; return reload(); }).catch(fail);
    } else if (action === 'valid') {
      api('/api/laps/' + lap.id + '/valid', { method: 'POST', body: { valid: !lap.valid } }).then(reload).catch(fail);
    } else if (action === 'delete') {
      if (!window.confirm('Supprimer définitivement le tour ' + lap.no + ' (' + fmtTime(lap.time_ms) + ') ?')) return;
      if (S.lapId === lap.id) S.lapId = null;
      api('/api/laps/' + lap.id, { method: 'DELETE' }).then(function () { toast('Tour supprimé.'); return reload(); }).catch(fail);
    }
  }

  function renameCorner(index) {
    var track = S.track, corner = track.corners[index];
    var name = window.prompt('Nom du virage (laisser vide pour revenir à la numérotation)', corner.name);
    if (name === null) return;
    var names = {};
    track.corners.forEach(function (c, i) {
      var value = i === index ? name.trim() : c.name;
      if (value && !/^T\d+$/.test(value)) names[String(c.apex)] = value;
    });
    api('/api/combos/' + S.comboId + '/corners', { method: 'POST', body: { names: names } }).then(reload).catch(fail);
  }

  function bind() {
    document.querySelector('.tabs').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button') : null;
      if (b) setTab(b.getAttribute('data-tab'));
    });
    document.querySelector('.brand').addEventListener('click', function (e) { e.preventDefault(); setTab('direct'); });
    $('combo-select').addEventListener('change', function (e) {
      $('follow').checked = false;
      var value = parseInt(e.target.value, 10);
      if (!isNaN(value)) selectCombo(value);
    });
    $('follow').addEventListener('change', function (e) { if (e.target.checked) { S.followKey = null; } });
    $('lap-select').addEventListener('change', function (e) {
      S.lapId = e.target.value ? parseInt(e.target.value, 10) : null;
      loadCombo().catch(fail);
    });
    $('map-mode').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button') : null;
      if (!b) return;
      S.mapMode = b.getAttribute('data-mode');
      Array.prototype.forEach.call($('map-mode').children, function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
      renderLegend(); drawAnalyse();
    });
    $('btn-fullap').addEventListener('click', function () { if (S.corner != null) selectCorner(S.corner); });
    $('corner-table').addEventListener('click', function (e) {
      var rename = e.target.closest ? e.target.closest('button[data-rename]') : null;
      if (rename) { renameCorner(parseInt(rename.getAttribute('data-rename'), 10)); return; }
      var row = e.target.closest ? e.target.closest('tr[data-corner]') : null;
      if (row) selectCorner(parseInt(row.getAttribute('data-corner'), 10));
    });
    ['ch-speed', 'ch-pedals', 'ch-delta'].forEach(function (id) {
      var canvas = $(id);
      canvas.addEventListener('mousemove', chartHover);
      canvas.addEventListener('touchstart', chartHover, { passive: true });
      canvas.addEventListener('touchmove', chartHover, { passive: true });
      canvas.addEventListener('mouseleave', clearCursor);
    });
    $('map').addEventListener('mousemove', mapHover);
    $('map').addEventListener('touchstart', mapHover, { passive: true });
    $('map').addEventListener('touchmove', mapHover, { passive: true });
    $('map').addEventListener('mouseleave', clearCursor);
    $('coach-cards').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button[data-see]') : null;
      if (!b) return;
      S.corner = parseInt(b.getAttribute('data-see'), 10);
      setTab('analyse'); renderAnalyse();
      window.scrollTo(0, 0);
    });
    $('pedals-seg').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button') : null;
      if (!b) return;
      api('/api/settings', { method: 'POST', body: { pedals: b.getAttribute('data-pedals') } })
        .then(loadStatus).then(loadCombo).catch(fail);
    });
    $('lap-table').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button[data-act]') : null;
      if (!b) return;
      lapAction(parseInt(b.closest('tr').getAttribute('data-lap'), 10), b.getAttribute('data-act'));
    });
    $('btn-import').addEventListener('click', function () { $('file-import').click(); });
    $('file-import').addEventListener('change', function (e) {
      var file = e.target.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function () {
        var data;
        try { data = JSON.parse(reader.result); } catch (err) { return fail(new Error('Ce fichier n\'est pas un JSON lisible.')); }
        api('/api/import', { method: 'POST', body: data }).then(function (res) {
          toast('Tour importé.'); $('follow').checked = false; S.comboId = res.combo_id; S.lapId = null; return reload();
        }).catch(fail);
      };
      reader.readAsText(file);
      e.target.value = '';
    });
    $('btn-del-combo').addEventListener('click', function () {
      var o = S.overview;
      if (!o) return;
      if (!window.confirm('Supprimer le profil « ' + comboLabel(o.combo) + ' » et ses ' + o.laps.length + ' tours ? Cette action est définitive.')) return;
      api('/api/combos/' + o.combo.id, { method: 'DELETE' }).then(function () { toast('Profil supprimé.'); S.comboId = null; return reload(); }).catch(fail);
    });
    $('btn-copy-report').addEventListener('click', function () {
      var text = $('diag-report').textContent;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { toast('Rapport copié.'); }, function () { toast('Copie impossible : sélectionne le texte à la main.', true); });
      } else {
        var range = document.createRange(); range.selectNodeContents($('diag-report'));
        var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
        try { document.execCommand('copy'); toast('Rapport copié.'); } catch (err) { toast('Sélectionné : copie-le à la main.'); }
      }
    });
    $('diag-status').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button[data-demo-car]') : null;
      if (!b) return;
      $('follow').checked = true;
      api('/api/demo/car', { method: 'POST', body: { car: b.getAttribute('data-demo-car') } })
        .then(function () { setTimeout(renderDiagnostic, 400); }).catch(fail);
    });
    $('btn-refresh-report').addEventListener('click', function () { loadStatus().then(loadReport).catch(fail); });
    $('btn-theme').addEventListener('click', function () {
      setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark', true);
    });
    $('btn-ipad').addEventListener('click', function () { setIpad(true); });
    $('btn-ipad-exit').addEventListener('click', function () { setIpad(false); });
    var resizeTimer = null;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () { if (S.tab === 'analyse' && !S.ipad) drawAnalyse(); drawLive(true); }, 80);
    });
  }

  // -------------------------------------------------------------- démarrage
  function start() {
    var theme = null;
    try { theme = localStorage.getItem('irms-theme'); } catch (e) { /* stockage indisponible */ }
    if (!theme) theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    bind();
    var tab = (location.hash || '').slice(1);
    if (['direct', 'analyse', 'coaching', 'tours', 'diagnostic'].indexOf(tab) >= 0) setTab(tab);
    if (/[?&]vue=ipad/.test(location.search)) setIpad(true);
    loadStatus().then(reload).then(connect).catch(function (error) { fail(error); connect(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
