/* Guide steps with behaviour: 4 (connection test), 8 (write and check the story), 9 (make the film). */
(function () {
  'use strict';
  var Y = window.MVG_YAML, G = window.MVG_GCP, SC = window.StoryCheck;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var app = null;
  var schema = null, schemaText = null, promptTemplate = null, assetsError = '';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // Text with `code` spans, built without innerHTML.
  function inline(parent, text) {
    String(text || '').split('`').forEach(function (part, i) {
      if (!part) return;
      parent.appendChild(i % 2 ? el('code', null, part) : document.createTextNode(part));
    });
    return parent;
  }

  function codeBlock(text) {
    var d = el('div', 'code');
    var pre = el('pre');
    pre.appendChild(el('code', null, text));
    d.appendChild(pre);
    var b = el('button', 'copy', 'Copy');
    b.type = 'button';
    b.setAttribute('aria-label', 'Copy to clipboard');
    d.appendChild(b);
    return d;
  }

  // ---------- assets (fetched, never duplicated) ----------
  var assetsReady = Promise.all([
    fetch('assets/story.schema.json', { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error('story.schema.json: HTTP ' + r.status); return r.text(); }),
    fetch('assets/story_prompt.md', { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error('story_prompt.md: HTTP ' + r.status); return r.text(); })
  ]).then(function (res) {
    schemaText = res[0];
    schema = JSON.parse(schemaText);
    promptTemplate = res[1];
  }).catch(function (e) {
    assetsError = 'Could not load the schema and prompt (' + e.message + '). Open this page from a web server, not as a file.';
  });

  function buildPrompt(f) {
    if (promptTemplate == null || schemaText == null) return '';
    var map = {
      BRIEF: Y.gen.brief(f).replace(/\n+$/, ''),
      BRAND: Y.gen.brand(f).replace(/\n+$/, ''),
      SCHEMA: schemaText.replace(/\r\n/g, '\n').replace(/\n+$/, '')
    };
    return promptTemplate.replace(/\r\n/g, '\n').replace(/\{\{(BRIEF|BRAND|SCHEMA)\}\}/g, function (m, k) { return map[k]; });
  }

  // ---------- step 4: connection checks ----------
  function resultRow(level, title, detail, fix) {
    var li = el('li', level);
    li.appendChild(el('span', 'badge ' + level, level === 'run' ? '…' : level.toUpperCase()));
    li.appendChild(el('div', 'r-title', title));
    if (detail) li.appendChild(el('div', 'r-detail', detail));
    if (fix && (fix.text || fix.code)) {
      var fx = el('div', 'r-fix');
      var strong = el('strong', null, 'Fix: ');
      fx.appendChild(strong);
      inline(fx, fix.text);
      if (fix.code) fx.appendChild(codeBlock(fix.code));
      li.appendChild(fx);
    }
    return li;
  }

  async function runChecks() {
    var f = app.form;
    var list = $('#check-results'), status = $('#check-status'), btn = $('#run-checks');
    list.textContent = '';
    status.classList.remove('bad');
    var project = Y.val(f, 'gcp.project');
    if (!G.hasToken()) { status.textContent = 'Paste a token first.'; status.classList.add('bad'); $('#f-token').focus(); return; }
    if (!project) { status.textContent = 'Enter your project ID first.'; status.classList.add('bad'); $('#f-project-2').focus(); return; }
    btn.disabled = true;
    status.textContent = 'Running…';
    var rows = G.checkTitles.map(function (t) { var r = resultRow('run', t, 'Waiting…'); list.appendChild(r); return r; });
    var counts = { pass: 0, warn: 0, fail: 0, skip: 0 };
    var rejected = false;
    for (var i = 0; i < G.checks.length; i++) {
      var r;
      if (rejected) r = { level: 'skip', title: G.checkTitles[i], detail: 'Skipped: Google rejected the token (HTTP 401) above.' };
      else {
        try { r = await G.checks[i](f); }
        catch (e) { r = { level: 'fail', title: G.checkTitles[i], detail: String(e && e.message || e) }; }
        if (i > 0 && /^HTTP 401\b/.test(r.detail || '')) rejected = true;
      }
      counts[r.level] = (counts[r.level] || 0) + 1;
      var row = resultRow(r.level, r.title, r.detail, r.fix);
      list.replaceChild(row, rows[i]);
      rows[i] = row;
    }
    btn.disabled = false;
    status.textContent = counts.pass + ' passed, ' + counts.warn + ' warning' + (counts.warn === 1 ? '' : 's') + ', ' + counts.fail + ' failed' + (counts.skip ? ', ' + counts.skip + ' skipped.' : '.');
    if (counts.fail) status.classList.add('bad');
    updateTokenState();
  }

  function updateTokenState() {
    var none = $('#gemini-no-token');
    if (none) none.hidden = G.hasToken();
    var w = $('#gemini-write');
    if (w) w.disabled = !G.hasToken() || busy;
  }

  // ---------- step 8: story ----------
  var busy = false, controller = null, timer = null;

  function selectTab(id) {
    ['paste', 'gemini', 'cli'].forEach(function (t) {
      var tab = $('#tab-' + t), panel = $('#tp-' + t), on = t === id;
      tab.setAttribute('aria-selected', String(on));
      tab.tabIndex = on ? 0 : -1;
      panel.hidden = !on;
    });
  }

  function refreshPrompt(f) {
    var out = $('#prompt-out');
    if (!out) return;
    var st = $('#prompt-status');
    if (assetsError) { out.value = ''; st.textContent = assetsError; st.classList.add('bad'); return; }
    if (promptTemplate == null) { st.textContent = 'Loading…'; return; }
    var p = buildPrompt(f);
    if (out.value !== p) out.value = p;
    st.classList.remove('bad');
    st.textContent = p.length.toLocaleString() + ' characters';
    var missing = !String(f['brand.name'] || '').trim() || !String(f['brief.purpose'] || '').trim();
    $('#story-missing').hidden = !missing;
  }

  async function writeWithGemini() {
    var st = $('#gemini-status');
    st.classList.remove('bad');
    if (!G.hasToken()) { updateTokenState(); return; }
    if (!Y.val(app.form, 'gcp.project')) { st.textContent = 'Enter your project ID in step 3 or 4 first.'; st.classList.add('bad'); return; }
    await assetsReady;
    var prompt = buildPrompt(app.form);
    if (!prompt) { st.textContent = assetsError || 'The prompt is not ready.'; st.classList.add('bad'); return; }
    busy = true;
    controller = new AbortController();
    updateTokenState();
    $('#gemini-cancel').hidden = false;
    var t0 = Date.now();
    st.textContent = '';
    var spin = el('span', 'spinner'); spin.setAttribute('aria-hidden', 'true');
    var label = el('span', null, ' Writing… 0 s');
    st.appendChild(spin); st.appendChild(label);
    timer = setInterval(function () { label.textContent = ' Writing… ' + Math.round((Date.now() - t0) / 1000) + ' s'; }, 1000);
    var res;
    try { res = await G.writeStory(app.form, prompt, controller.signal); }
    finally {
      clearInterval(timer);
      busy = false;
      $('#gemini-cancel').hidden = true;
      updateTokenState();
    }
    st.textContent = '';
    if (res.ok) {
      var box = $('#story-in');
      box.value = res.text;
      app.set('story.text', res.text);
      st.textContent = 'Done in ' + Math.round((Date.now() - t0) / 1000) + ' s with ' + res.model + '. Checked below.';
      validate();
      box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      st.classList.add('bad');
      inline(st, res.detail + (res.fix && res.fix.text && !res.aborted ? ' Fix: ' + res.fix.text : ''));
      if (res.fix && res.fix.code && !res.aborted) st.appendChild(codeBlock(res.fix.code));
    }
  }

  function decoratePath(path, story) {
    var m = /^scenes\[(\d+)\]/.exec(path);
    if (m && story && Array.isArray(story.scenes)) {
      var sc = story.scenes[+m[1]];
      if (sc && typeof sc.id === 'string') return m[0] + ' (' + sc.id + ')' + path.slice(m[0].length);
    }
    return path || '(root)';
  }

  function issueList(items, cls, story) {
    var ul = el('ul', 'issues');
    items.forEach(function (it) {
      var li = el('li', cls);
      li.appendChild(el('b', null, decoratePath(it.path, story)));
      li.appendChild(document.createTextNode(' ' + it.message));
      ul.appendChild(li);
    });
    return ul;
  }

  function fmt(n) { return (Math.round(n * 10) / 10).toFixed(1); }

  function renderTimeline(story, timing) {
    var total = timing.total;
    var rows = timing.rows;
    if (!rows.length || !(total > 0)) return null;
    var wrap = el('div', 'timeline-wrap');
    var tl = el('div', 'timeline');
    tl.setAttribute('role', 'img');
    tl.setAttribute('aria-label', 'Timeline: ' + rows.length + ' scenes, ' + fmt(total) + ' seconds');
    wrap.appendChild(tl);
    var pct = function (s) { return Math.max(0, Math.min(100, (s / total) * 100)) + '%'; };

    var ruler = el('div', 'tl-row ruler');
    var step = total <= 20 ? 2 : total <= 60 ? 5 : total <= 150 ? 10 : 30;
    for (var s = 0; s <= total - step * 0.4; s += step) {
      var tick = el('span', 'tl-tick', s + 's');
      tick.style.left = pct(s);
      ruler.appendChild(tick);
    }
    var end = el('span', 'tl-tick', fmt(total) + 's');
    end.style.left = '100%';
    end.style.transform = 'translateX(-100%)';
    ruler.appendChild(end);
    tl.appendChild(ruler);

    var sceneRow = el('div', 'tl-row');
    var voiceRow = el('div', 'tl-row voice');
    rows.forEach(function (r, i) {
      var sc = r.scene || {};
      var visible = i < rows.length - 1 ? r.seconds - SC.CROSSFADE : r.seconds;
      var bar = el('div', 'tl-scene ' + (sc.kind === 'card' ? 'card' : 'live_action'));
      bar.style.left = pct(r.start);
      bar.style.width = pct(Math.max(0.2, visible));
      var what = sc.kind === 'card' ? (sc.card && sc.card.template) || 'card' : 'live action';
      bar.title = (sc.id || '?') + ' · ' + what + ' · ' + fmt(r.start) + '–' + fmt(r.start + r.seconds) + ' s';
      bar.appendChild(el('b', null, sc.id || '?'));
      bar.appendChild(el('span', null, fmt(r.seconds) + ' s · ' + what));
      sceneRow.appendChild(bar);
      (Array.isArray(sc.voice) ? sc.voice : []).forEach(function (line) {
        if (!line || typeof line.text !== 'string') return;
        var at = typeof line.at === 'number' ? line.at : 0.4;
        var dur = SC.words(line.text) / 2.6;
        var v = el('div', 'tl-voice' + (at + dur + 0.4 > r.seconds ? ' late' : ''));
        v.style.left = pct(r.start + at);
        v.style.width = pct(dur);
        v.title = '“' + line.text + '” at ' + fmt(r.start + at) + ' s, about ' + fmt(dur) + ' s';
        voiceRow.appendChild(v);
      });
    });
    tl.appendChild(sceneRow);
    tl.appendChild(voiceRow);

    var musicRow = el('div', 'tl-row music');
    var segs = (Array.isArray(story.music) ? story.music : []).map(function (m) {
      var idx = rows.findIndex(function (r) { return r.id === (m && m.starts_at); });
      return { m: m, idx: idx };
    }).filter(function (x) { return x.idx >= 0; }).sort(function (a, b) { return a.idx - b.idx; });
    segs.forEach(function (sg, i) {
      var start = rows[sg.idx].start;
      var stop = i + 1 < segs.length ? rows[segs[i + 1].idx].start : total;
      var b = el('div', 'tl-music', '♪ ' + (sg.m.id || 'music') + (sg.m.align === 'tail' ? ' (tail)' : ''));
      b.style.left = pct(start);
      b.style.width = pct(Math.max(0.2, stop - start));
      b.title = (sg.m.prompt || '').slice(0, 200);
      musicRow.appendChild(b);
    });
    tl.appendChild(musicRow);

    var legend = el('div', 'legend');
    [['lg-live', 'live action'], ['lg-card', 'card'], ['lg-voice', 'voice line (red: runs past the scene)'], ['lg-music', 'music segment']].forEach(function (x) {
      var s = el('span');
      s.appendChild(el('i', x[0]));
      s.appendChild(document.createTextNode(x[1]));
      legend.appendChild(s);
    });
    wrap.appendChild(legend);
    return wrap;
  }

  function sceneTable(timing) {
    var wrap = el('div', 'table-wrap');
    var t = el('table');
    var head = el('tr');
    ['#', 'Scene', 'Kind', 'Start', 'Seconds', 'Content', 'Voice'].forEach(function (h) { head.appendChild(el('th', null, h)); });
    var thead = el('thead'); thead.appendChild(head); t.appendChild(thead);
    var tb = el('tbody');
    timing.rows.forEach(function (r, i) {
      var sc = r.scene || {};
      var tr = el('tr');
      var content = sc.kind === 'card'
        ? ((sc.card && sc.card.template) || '') + (sc.card && (sc.card.headline || (sc.card.lines && sc.card.lines.join(' / '))) ? ': ' + (sc.card.headline || sc.card.lines.join(' / ')) : '')
        : (sc.shot ? (sc.shot.cast && sc.shot.cast.length ? '[' + sc.shot.cast.join(', ') + '] ' : '') + (sc.shot.action || '') : '');
      var voice = (Array.isArray(sc.voice) ? sc.voice : []).map(function (v) { return v && v.text; }).filter(Boolean).join(' / ');
      [String(i + 1), sc.id || '', sc.kind || '', fmt(r.start), fmt(r.seconds), content, voice].forEach(function (c, j) {
        var td = el('td', null, c);
        if (j === 1) { td.textContent = ''; td.appendChild(el('code', null, c)); }
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    return wrap;
  }

  async function validate() {
    var out = $('#story-result');
    out.textContent = '';
    await assetsReady;
    if (!schema) { out.appendChild(issueList([{ path: '(page)', message: assetsError }], 'error')); return; }
    var f = app.form;
    var res = SC.check(schema, $('#story-in').value, { targetSeconds: Y.targetSeconds(f), aspectRatio: Y.val(f, 'brief.aspect') });
    if (res.parseError) {
      out.appendChild(el('p', 'summary-line', '1 error'));
      out.appendChild(issueList([{ path: '(json)', message: res.parseError }], 'error'));
      out.dataset.errors = '1';
      return;
    }
    var t = res.timing;
    var cards = t.rows.filter(function (r) { return r.kind === 'card'; }).length;
    var hasScenes = res.story && typeof res.story === 'object' && Array.isArray(res.story.scenes);
    var summary = res.errors.length + ' error' + (res.errors.length === 1 ? '' : 's') + ', ' +
      res.warnings.length + ' warning' + (res.warnings.length === 1 ? '' : 's') +
      (hasScenes ? ' · ' + t.rows.length + ' scenes (' + cards + ' cards, ' + (t.rows.length - cards) + ' live action) · total ' + fmt(t.total) + ' s' +
        (Y.targetSeconds(f) ? ' (target ' + Y.targetSeconds(f) + ' s)' : '') : '');
    out.appendChild(el('p', 'summary-line', summary));
    out.dataset.errors = String(res.errors.length);
    out.dataset.warnings = String(res.warnings.length);
    if (res.errors.length) out.appendChild(issueList(res.errors, 'error', res.story));
    if (res.warnings.length) out.appendChild(issueList(res.warnings, 'warning', res.story));
    if (!res.errors.length && !res.warnings.length) {
      out.appendChild(issueList([{ path: 'story.json', message: 'is valid against the schema, and the timing checks pass.' }], 'ok'));
    }
    if (res.story && typeof res.story === 'object' && Array.isArray(res.story.scenes)) {
      var tlv = renderTimeline(res.story, t);
      if (tlv) {
        out.appendChild(el('h3', null, 'Timeline'));
        out.appendChild(tlv);
        var det = el('details', 'faq');
        det.appendChild(el('summary', null, 'Scene list (' + t.rows.length + ')'));
        det.appendChild(sceneTable(t));
        out.appendChild(det);
      }
    }
    if (!res.errors.length) {
      var p = el('p');
      inline(p, 'Next: download `story.json`, put it in your project folder and run `mvg story check` and `mvg plan`.');
      out.appendChild(p);
    }
  }

  // ---------- step 9: make the film ----------
  var MAKE = [
    { title: 'Set up the project folder', items: [
      { id: 'init', label: 'Create the project and add your files', cmd: function (f) { return Y.gen.init(f) + '\n' + Y.gen.copyFiles(f); },
        does: 'Creates the folder, then copies the files you downloaded in steps 5 to 8 (`studio.yaml`, `brand.yaml`, `brief.yaml`, `story.json`) into it, replacing the starter files. Put a logo, fonts or screenshots in `brand/`.',
        out: '`studio.yaml`, `brand.yaml`, `brief.yaml`, `story.json`', fix: 'Downloaded somewhere else? Copy the four files by hand. From another folder, add `-C DIR` to any command.' },
      { id: 'doctor', label: 'Check the setup', cmd: 'mvg doctor', does: 'Checks tools, sign-in, project, API, permission and every model.', out: 'A PASS / WARN / FAIL list in the terminal.', fix: 'See step 4 for each check and its fix.' },
      { id: 'check', label: 'Check the story', cmd: 'mvg story check', does: 'Validates `story.json` against the schema and reports timing.', out: 'Errors and the total length.', fix: 'Fix the reported fields in `story.json` (step 8 shows the same checks).' },
      { id: 'plan', label: 'See the plan', cmd: 'mvg plan', does: 'Prints the timeline, the length and everything that will be generated.', out: 'Terminal only. Nothing is generated or billed.', fix: 'Too long or short? Change scene `seconds` in `story.json`.' }
    ] },
    { title: 'Stage 1: cards first (cheap)', items: [
      { id: 'posters', label: 'Check your branding with card posters', cmd: 'mvg cards --posters', badge: 'free', does: 'Renders only a still of each card\'s last frame, in seconds. A quick check of colors, fonts, logo and wording before the full card renders.', out: 'One still per card scene.', fix: 'Wrong color or font: edit rand.yaml and run it again. Wrong words: edit the card in story.json.' },
      { id: 'cards', label: 'Render brand cards and captions', cmd: 'mvg cards', badge: 'free', does: 'Renders every card scene and caption from HTML in your colors and fonts, frame by frame at 24 fps, with Playwright.', out: '`renders/cards/`, `renders/captions/`', fix: 'Browser missing: `playwright install chromium`. Wrong font: check the family name in `brand.yaml`.' },
      { id: 'cast', label: 'Make cast reference stills', cmd: 'mvg cast', badge: 'billed', does: 'One reference still per fictional person, so they look the same in every shot (image model).', out: '`renders/cast/`', fix: 'Blocked by safety filters: describe an invented person (age range, look, clothing), then `mvg cast --force`.' },
      { id: 'keyframes', label: 'Make keyframes', cmd: 'mvg keyframes', badge: 'billed', does: 'The first frame of each live-action shot, using the cast stills and the brand look.', out: '`renders/keyframes/`', fix: 'Not right? Edit the shot in `story.json`, then `mvg keyframes <scene-id> --force`.' }
    ] },
    { title: 'Gate: review and approve', gate: true, items: [
      { id: 'review', label: 'Review everything', cmd: 'mvg review', badge: 'gate', does: 'Builds one page with every card, cast still and keyframe, and the exact prompts that will be sent.', out: '`build/review.html` (open it in your browser)', fix: 'Fix and re-run single scenes with `--force` and their ids, then `mvg review` again.' },
      { id: 'approve', label: 'Approve the shots', cmd: 'mvg approve --all\n# or only some: mvg approve s01-rain s06-shelf\n# take back:    mvg approve --revoke s06-shelf', badge: 'gate', does: 'Records which shots may be animated. Paid video is generated only for approved shots.', out: '`approvals.json`', fix: 'Changed a keyframe after approving? Review and approve it again.' }
    ] },
    { title: 'Preview: draft cut', items: [
      { id: 'animatic', label: 'Make the free animatic', cmd: 'mvg clips --animatic', badge: 'free', does: 'Turns each keyframe into a slow Ken Burns move on your computer, so the whole cut can be timed before any video is paid for.', out: 'Preview clips used by `mvg assemble` until real clips exist.', fix: 'Needs keyframes: run `mvg keyframes` first.' },
      { id: 'voice-ph', label: 'Placeholder voice', cmd: 'mvg voice --placeholder', does: 'Stand-in narration for each voice line, so the draft has its timing before the real voiceover is made.', out: 'Placeholder narration for the draft.', fix: 'A line runs past its scene: shorten it or lengthen the scene in `story.json`.' },
      { id: 'music-ph', label: 'Placeholder music', cmd: 'mvg music --placeholder', does: 'Stand-in score segments, so the draft has its music cues before Lyria is called.', out: 'Placeholder score for the draft.', fix: 'Segment starts at the wrong scene: fix `music[].starts_at` in `story.json`.' },
      { id: 'assemble1', label: 'Cut the draft', cmd: 'mvg assemble', does: 'Assembles the draft from the animatic, cards, captions and placeholder audio. Watch it and fix timing now; it is the cheapest moment.', out: '`build/<title>-draft.mp4`', fix: 'Missing card, clip, voice or music: the error names the step to run first.' }
    ] },
    { title: 'Stage 2: generate (billed)', items: [
      { id: 'clips', label: 'Generate the video clips', cmd: 'mvg clips', badge: 'billed', does: 'Animates each approved keyframe with Veo or Gemini Omni. Unapproved shots are skipped.', out: '`renders/clips/`', fix: '429: lower `limits.parallel` and run again (finished clips are kept). 404: check the video model and region. Safety block: rephrase the shot.' },
      { id: 'voice', label: 'Record the voiceover', cmd: 'mvg voice', badge: 'billed', does: 'Gemini TTS reads each voice line in the brand voice and direction.', out: '`audio/voice/` (one WAV per line)', fix: 'Line runs past its scene: shorten it or lengthen the scene, then `mvg voice <scene-id> --force`.' },
      { id: 'music', label: 'Compose the music', cmd: 'mvg music', badge: 'billed', does: 'Lyria makes each score segment from its prompt.', out: '`audio/music/`', fix: 'Wrong mood: edit the segment prompt in `story.json`, then `mvg music --force`.' }
    ] },    { title: 'Assemble', items: [
      { id: 'assemble2', label: 'Cut the final film', cmd: 'mvg assemble', does: 'ffmpeg joins every scene with 0.4 s crossfades, adds captions, places each voice line, fits the music per chapter and ducks it under the voice, and normalises loudness to -16 LUFS.', out: '`build/<title>.mp4` (1080p master), `-web` and `-phone` (720p)', fix: 'Changed one scene? Re-run only that step with `--force` and the scene id, then `mvg assemble` again.' }
    ] }
  ];

  function renderMake() {
    var root = $('#make-list');
    if (!root) return;
    MAKE.forEach(function (g) {
      var sec = el('section', 'cmd-group');
      var h = el('h3', null, g.title);
      sec.appendChild(h);
      g.items.forEach(function (it) {
        var box = el('div', 'cmd' + (g.gate ? ' gate' : ''));
        var head = el('div', 'cmd-head');
        var cb = el('input');
        cb.type = 'checkbox';
        cb.id = 'mk-' + it.id;
        cb.dataset.k = 'make.' + it.id;
        var lab = el('label', null, it.label + ' ');
        lab.htmlFor = cb.id;
        if (it.badge) lab.appendChild(el('span', 'tag tag-' + it.badge, it.badge));
        head.appendChild(cb); head.appendChild(lab);
        box.appendChild(head);
        var cbk = el('div', 'code');
        var pre = el('pre');
        var code = el('code');
        if (typeof it.cmd === 'function') code.dataset.gen = 'make_' + it.id;
        else code.textContent = it.cmd;
        pre.appendChild(code); cbk.appendChild(pre); box.appendChild(cbk);
        var dl = el('dl');
        [['What it does', it.does], ['Output', it.out], ['If it fails', it.fix]].forEach(function (p) {
          dl.appendChild(el('dt', null, p[0]));
          dl.appendChild(inline(el('dd'), p[1]));
        });
        box.appendChild(dl);
        sec.appendChild(box);
        if (typeof it.cmd === 'function') Y.gen['make_' + it.id] = it.cmd;
      });
      root.appendChild(sec);
    });
    var tip = el('div', 'callout');
    inline(tip, 'Shortcut: `mvg run` runs all steps in order and stops at the approval gate. After you approve, run it again to continue.');
    root.appendChild(tip);
    window.MVG.addCopyButtons(root);
  }

  function syncChecked() {
    document.querySelectorAll('#make-list .cmd').forEach(function (box) {
      var cb = box.querySelector('input[type=checkbox]');
      box.classList.toggle('checked', !!(cb && cb.checked));
    });
  }

  // ---------- wiring ----------
  window.MVG_STEPS = {
    beforeBind: function (a) {
      app = a;
      renderMake();
      var tok = $('#f-token');
      tok.addEventListener('input', function () { G.setToken(tok.value); updateTokenState(); });
      $('#forget-token').addEventListener('click', function () {
        tok.value = ''; G.setToken(''); updateTokenState();
        $('#check-results').textContent = '';
        $('#check-status').textContent = 'Token forgotten.';
      });
      $('#run-checks').addEventListener('click', runChecks);
      ['paste', 'gemini', 'cli'].forEach(function (t, i, all) {
        var tab = $('#tab-' + t);
        tab.addEventListener('click', function () { selectTab(t); });
        tab.addEventListener('keydown', function (e) {
          var d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
          if (!d) return;
          var n = all[(i + d + all.length) % all.length];
          selectTab(n); $('#tab-' + n).focus();
        });
      });
      $('#gemini-write').addEventListener('click', writeWithGemini);
      $('#gemini-cancel').addEventListener('click', function () { if (controller) controller.abort(); });
      $('#dl-prompt').addEventListener('click', function () {
        var p = buildPrompt(app.form);
        if (p) { window.MVG.download('story_prompt.md', p, 'text/markdown'); window.MVG.flash(this, 'Downloaded'); }
      });
      $('#validate').addEventListener('click', validate);
      $('#load-example-story').addEventListener('click', function () {
        fetch('assets/example-story.json', { cache: 'no-cache' }).then(function (r) { return r.text(); }).then(function (t) {
          $('#story-in').value = t;
          app.set('story.text', t);
          validate();
        });
      });
      $('#dl-story').addEventListener('click', function () {
        var t = SC.clean($('#story-in').value);
        if (!t) { $('#story-in').focus(); return; }
        window.MVG.download('story.json', t + '\n', 'application/json');
        window.MVG.flash(this, 'Downloaded');
      });
      a.onRefresh(function (f) { refreshPrompt(f); syncChecked(); updateTokenState(); });
      assetsReady.then(function () { refreshPrompt(app.form); });
    }
  };
})();
