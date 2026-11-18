/* Guide core: saved answers, form binding, step navigation, generated files and the brand preview.
   localStorage holds only form answers. Tokens and API keys are never stored. */
(function () {
  'use strict';
  var D = window.MVG_DATA, Y = window.MVG_YAML;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var STORE_KEY = 'mvg-guide-v1';
  var FORBIDDEN_KEY = /token|secret|password|api_key$|apikey/i;
  var hooks = [];

  // ---------- state ----------
  function load() {
    var s = null;
    try { s = JSON.parse(window.localStorage.getItem(STORE_KEY) || 'null'); } catch (e) { s = null; }
    if (!s || s.v !== 1 || typeof s.form !== 'object') s = { v: 1, done: [], form: {} };
    var form = Object.assign({}, D.DEFAULTS);
    Object.keys(s.form).forEach(function (k) { if (typeof s.form[k] === 'string' && !FORBIDDEN_KEY.test(k)) form[k] = s.form[k]; });
    return { v: 1, done: Array.isArray(s.done) ? s.done : [], form: form, step: s.step };
  }
  var state = load();
  var saveTimer = null;
  function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      var form = {};
      Object.keys(state.form).forEach(function (k) { if (!FORBIDDEN_KEY.test(k)) form[k] = String(state.form[k]); });
      try { window.localStorage.setItem(STORE_KEY, JSON.stringify({ v: 1, done: state.done, step: state.step, form: form })); }
      catch (e) { /* storage full or disabled: answers stay in memory */ }
    }, 150);
  }

  function setValues(values) {
    Object.keys(values).forEach(function (k) { state.form[k] = values[k]; });
    restoreInputs();
    save();
    refresh();
  }

  // ---------- form binding ----------
  function restoreInputs() {
    $$('[data-k]').forEach(function (el) {
      var v = state.form[el.dataset.k];
      v = v == null ? '' : String(v);
      if (el.type === 'radio') el.checked = el.value === v;
      else if (el.type === 'checkbox') el.checked = v === 'true';
      else if (el.type === 'color') { if (/^#[0-9a-fA-F]{6}$/.test(v)) el.value = v.toLowerCase(); }
      else if (el.value !== v) el.value = v;
    });
  }

  function onInput(e) {
    var el = e.target;
    if (!el.dataset || !el.dataset.k) return;
    var k = el.dataset.k, v;
    if (el.type === 'radio') { if (!el.checked) return; v = el.value; }
    else if (el.type === 'checkbox') v = el.checked ? 'true' : 'false';
    else if (el.type === 'color') v = el.value.toUpperCase();
    else v = el.value;
    state.form[k] = v;
    $$('[data-k="' + k + '"]').forEach(function (o) {
      if (o === el || o.type === 'radio' || o.type === 'checkbox') return;
      if (o.type === 'color') { if (/^#[0-9a-fA-F]{6}$/.test(v.trim())) o.value = v.trim().toLowerCase(); }
      else if (o.value !== v) o.value = v;
    });
    save();
    refresh();
  }

  // ---------- generated output ----------
  function gen(name) {
    var g = Y.gen[name];
    return g ? g(state.form) : '';
  }

  function applyShow() {
    $$('[data-show]').forEach(function (el) {
      var m = el.dataset.show.split('=');
      var v = String(state.form[m[0]] || '');
      var ok = m[1] === '*' ? v.trim() !== '' : m[1].split('|').indexOf(v) >= 0;
      el.hidden = !ok;
    });
  }

  function hint(id, text) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('bad', !!text);
  }

  function refresh() {
    $$('[data-gen]').forEach(function (el) { el.textContent = gen(el.dataset.gen); });
    var admin = $('#admin-msg');
    if (admin) admin.value = gen('adminMsg');
    $$('[data-os]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.os === state.form.os)); });
    applyShow();
    var p = (state.form['gcp.project'] || '').trim();
    hint('hint-project', p && !/^[a-z][a-z0-9-]{4,28}[a-z0-9]$/.test(p) ? 'Project IDs are 6-30 characters: lowercase letters, digits and hyphens, starting with a letter.' : '');
    var em = (state.form['gcp.email'] || '').trim();
    hint('hint-email', em && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(em) ? 'That does not look like an email address.' : '');
    updateBrandPreview();
    hooks.forEach(function (fn) { fn(state.form); });
  }

  // ---------- steps ----------
  var sections = $$('.step[data-step]');
  var STEPS = sections.map(function (s) { return s.dataset.step; });
  var current = null;

  function buildSidebar() {
    var ol = $('#step-list');
    sections.forEach(function (s, i) {
      var li = document.createElement('li');
      li.dataset.step = s.dataset.step;
      var a = document.createElement('a');
      a.href = '#' + s.dataset.step;
      var dot = document.createElement('span');
      dot.className = 'dot';
      dot.setAttribute('aria-hidden', 'true');
      var n = document.createElement('span'); n.className = 'n'; n.textContent = String(i + 1);
      var ck = document.createElement('span'); ck.className = 'ck'; ck.textContent = '✓';
      dot.appendChild(n); dot.appendChild(ck);
      var label = document.createElement('span');
      label.textContent = s.dataset.title;
      a.appendChild(dot); a.appendChild(label);
      li.appendChild(a);
      ol.appendChild(li);
    });
  }

  function updateSidebar() {
    $$('#step-list li').forEach(function (li) {
      var done = state.done.indexOf(li.dataset.step) >= 0;
      li.classList.toggle('done', done);
      var a = li.querySelector('a');
      if (li.dataset.step === current) a.setAttribute('aria-current', 'step'); else a.removeAttribute('aria-current');
      var si = STEPS.indexOf(li.dataset.step);
      a.setAttribute('aria-label', (si + 1) + '. ' + sections[si].dataset.title + (done ? ' (done)' : ''));
    });
    var n = STEPS.filter(function (s) { return state.done.indexOf(s) >= 0; }).length;
    $('#progress-text').textContent = n + ' of ' + STEPS.length + ' done';
    $('#progress-fill').style.width = (100 * n / STEPS.length) + '%';
    $('#progress-bar').setAttribute('aria-valuenow', String(n));
    var idx = STEPS.indexOf(current);
    $('#sidebar-toggle-label').textContent = 'Step ' + (idx + 1) + ' of ' + STEPS.length + ': ' + sections[idx].dataset.title;
  }

  function show(step, focus) {
    if (STEPS.indexOf(step) < 0) step = STEPS[0];
    current = step;
    state.step = step;
    sections.forEach(function (s) { s.hidden = s.dataset.step !== step; });
    var idx = STEPS.indexOf(step);
    $('#prev').disabled = idx === 0;
    $('#next').textContent = idx === STEPS.length - 1 ? 'Finish ✓' : 'Next →';
    $('#step-count').textContent = 'Step ' + (idx + 1) + ' of ' + STEPS.length;
    updateSidebar();
    $('#sidebar').classList.remove('open');
    $('#sidebar-toggle').setAttribute('aria-expanded', 'false');
    save();
    hooks.forEach(function (fn) { fn(state.form, step); });
    if (step === 'brand') loadFontsSoon(0);
    if (focus) {
      var h = sections[idx].querySelector('h2');
      if (h) { h.setAttribute('tabindex', '-1'); h.focus({ preventScroll: true }); }
      window.scrollTo(0, 0);
    }
  }

  function markDone(step) {
    if (state.done.indexOf(step) < 0) state.done.push(step);
    save();
    updateSidebar();
  }

  function go(step) {
    if (location.hash !== '#' + step) location.hash = step;
    else show(step, true);
  }

  // ---------- brand preview ----------
  var fontLink = null, fontKey = '', fontTimer = null;
  var FAMILY_RE = /^[A-Za-z0-9][A-Za-z0-9 ]{0,60}$/;

  function families() {
    var out = [];
    ['brand.fonts.heading', 'brand.fonts.body'].forEach(function (k) {
      var v = String(state.form[k] || '').trim();
      if (FAMILY_RE.test(v) && out.indexOf(v) < 0) out.push(v);
    });
    return out;
  }

  function loadFonts() {
    var fams = families();
    var key = fams.join('|');
    if (!fams.length || key === fontKey) return;
    fontKey = key;
    var url = 'https://fonts.googleapis.com/css2?' + fams.map(function (f) { return 'family=' + encodeURIComponent(f).replace(/%20/g, '+'); }).join('&') + '&display=swap';
    if (!fontLink) {
      fontLink = document.createElement('link');
      fontLink.rel = 'stylesheet';
      fontLink.referrerPolicy = 'no-referrer';
      document.head.appendChild(fontLink);
    }
    fontLink.href = url;
  }

  function loadFontsSoon(ms) {
    clearTimeout(fontTimer);
    fontTimer = setTimeout(loadFonts, ms == null ? 700 : ms);
  }

  function lum(h) {
    var c = [1, 3, 5].map(function (i) { return parseInt(h.substr(i, 2), 16) / 255; })
      .map(function (v) { return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  function ratio(a, b) {
    var x = lum(a), y = lum(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }

  var lastFamilies = '';
  function updateBrandPreview() {
    var card = $('#brand-card');
    if (!card) return;
    var f = state.form, colors = {};
    ['background', 'surface', 'primary', 'accent', 'text', 'muted'].forEach(function (c) {
      var v = String(f['brand.colors.' + c] || '').trim();
      if (/^#[0-9a-fA-F]{6}$/.test(v)) { colors[c] = v; card.style.setProperty('--b-' + (c === 'background' ? 'bg' : c), v); }
    });
    var hf = String(f['brand.fonts.heading'] || '').trim(), bf = String(f['brand.fonts.body'] || '').trim();
    card.style.setProperty('--b-head', (FAMILY_RE.test(hf) ? '"' + hf + '", ' : '') + 'Georgia, serif');
    card.style.setProperty('--b-body', (FAMILY_RE.test(bf) ? '"' + bf + '", ' : '') + 'system-ui, sans-serif');
    $('#bc-head').textContent = String(f['brand.name'] || '').trim() || 'Your brand';
    $('#bc-sub').textContent = String(f['brand.tagline'] || '').trim() || 'Your tagline';
    $('#bc-foot').textContent = (hf || 'heading') + ' · ' + (bf || 'body');
    var key = hf + '|' + bf;
    if (key !== lastFamilies) { lastFamilies = key; if (current === 'brand') loadFontsSoon(); }

    var sw = $('#swatches');
    sw.textContent = '';
    Object.keys(colors).forEach(function (c) {
      var d = document.createElement('span'); d.className = 'swatch';
      var i = document.createElement('i'); i.style.background = colors[c];
      d.appendChild(i); d.appendChild(document.createTextNode(c));
      sw.appendChild(d);
    });
    var ct = $('#contrast');
    ct.textContent = '';
    [['Headline on panel', 'accent', 'surface'], ['Text on panel', 'text', 'surface'], ['Text on background', 'text', 'background']].forEach(function (p) {
      if (!colors[p[1]] || !colors[p[2]]) return;
      var r = ratio(colors[p[1]], colors[p[2]]);
      var s = document.createElement('span');
      s.className = r >= 4.5 ? 'ok' : 'bad';
      s.textContent = p[0] + ' ' + r.toFixed(1) + ':1 ' + (r >= 4.5 ? '✓' : '(below 4.5:1, hard to read)');
      ct.appendChild(s);
      ct.appendChild(document.createTextNode('   '));
    });
  }

  // ---------- init ----------
  function init() {
    buildSidebar();
    var vs = $('#f-b-voice');
    if (vs) D.VOICES.forEach(function (v) {
      var o = document.createElement('option');
      o.value = v[0]; o.textContent = v[0] + ' (' + v[1] + ')';
      vs.appendChild(o);
    });
    window.MVG_STEPS && window.MVG_STEPS.beforeBind && window.MVG_STEPS.beforeBind(api);
    restoreInputs();
    document.addEventListener('input', onInput);
    document.addEventListener('change', onInput);

    document.addEventListener('click', function (e) {
      var t = e.target.closest('button, a');
      if (!t) return;
      if (t.dataset.os) { state.form.os = t.dataset.os; save(); refresh(); return; }
      if (t.dataset.example) { setValues(D.EXAMPLE[t.dataset.example]); return; }
      if (t.dataset.clear) {
        if (!window.confirm('Clear the ' + t.dataset.clear + ' answers?')) return;
        setValues(t.dataset.clear === 'brand' ? D.BRAND_DEFAULTS : D.BRIEF_DEFAULTS);
        return;
      }
      if (t.dataset.look) { setValues({ 'brand.look': D.LOOKS[t.dataset.look] }); return; }
      if (t.dataset.purpose) { setValues({ 'brief.purpose': t.dataset.purpose }); $('#f-r-purpose').focus(); return; }
      if (t.dataset.download) {
        var name = t.dataset.download;
        window.MVG.download(name + '.yaml', gen(name), 'application/yaml');
        window.MVG.flash(t, 'Downloaded');
        return;
      }
    });

    $('#reset-models').addEventListener('click', function () { setValues(D.MODEL_DEFAULTS); });
    $('#reset-all').addEventListener('click', function () {
      if (!window.confirm('Clear all saved answers in this browser and start over?')) return;
      try { window.localStorage.removeItem(STORE_KEY); } catch (e) { /* ignore */ }
      state = load();
      state.done = [];
      restoreInputs();
      refresh();
      go(STEPS[0]);
    });
    $('#prev').addEventListener('click', function () {
      var i = STEPS.indexOf(current);
      if (i > 0) go(STEPS[i - 1]);
    });
    $('#next').addEventListener('click', function () {
      markDone(current);
      var i = STEPS.indexOf(current);
      if (i < STEPS.length - 1) go(STEPS[i + 1]);
    });
    $('#sidebar-toggle').addEventListener('click', function () {
      var open = !$('#sidebar').classList.contains('open');
      $('#sidebar').classList.toggle('open', open);
      this.setAttribute('aria-expanded', String(open));
    });
    window.addEventListener('hashchange', function () { show(location.hash.slice(1), true); });

    window.MVG.addCopyButtons(document);
    refresh();
    var start = location.hash.slice(1);
    show(STEPS.indexOf(start) >= 0 ? start : (STEPS.indexOf(state.step) >= 0 ? state.step : STEPS[0]), false);
  }

  var api = {
    get form() { return state.form; },
    set: function (k, v) { state.form[k] = v; save(); },
    setValues: setValues,
    save: save,
    refresh: refresh,
    gen: gen,
    go: go,
    current: function () { return current; },
    onRefresh: function (fn) { hooks.push(fn); }
  };
  window.MVG_APP = api;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
