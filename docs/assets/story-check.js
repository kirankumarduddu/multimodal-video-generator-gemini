/* Story checks: a small JSON Schema validator for the subset used by story.schema.json,
   plus the pipeline's timing and reference checks. The schema itself is fetched at runtime. */
(function () {
  'use strict';

  var CROSSFADE = 0.4;
  var WORDS_PER_SECOND = 2.6;

  function typeOf(v) {
    if (v === null) return 'null';
    if (Array.isArray(v)) return 'array';
    if (typeof v === 'number') return Number.isInteger(v) ? 'integer' : 'number';
    return typeof v;
  }

  function typeMatches(t, v) {
    var actual = typeOf(v);
    if (t === 'number') return actual === 'number' || actual === 'integer';
    return actual === t;
  }

  function deepEqual(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
  }

  function show(v) {
    var s = JSON.stringify(v);
    if (s === undefined) return String(v);
    return s.length > 60 ? s.slice(0, 57) + '...' : s;
  }

  function joinPath(path, key) {
    if (typeof key === 'number') return path + '[' + key + ']';
    return path ? path + '.' + key : key;
  }

  function lookup(root, ref) {
    if (ref.indexOf('#/') !== 0) throw new Error('Unsupported $ref ' + ref);
    var node = root;
    ref.slice(2).split('/').forEach(function (part) {
      part = part.replace(/~1/g, '/').replace(/~0/g, '~');
      node = node == null ? undefined : node[part];
    });
    if (node === undefined) throw new Error('Unresolved $ref ' + ref);
    return node;
  }

  // Describes an "if" schema made of const properties, e.g. 'kind is "card"'.
  function describeIf(s) {
    if (!s || !s.properties) return '';
    var parts = [];
    Object.keys(s.properties).forEach(function (k) {
      if (s.properties[k] && s.properties[k].const !== undefined) parts.push(k + ' is ' + show(s.properties[k].const));
    });
    return parts.join(' and ');
  }

  function validate(schema, data) {
    var errors = [];

    function err(path, message) { errors.push({ path: path, message: message }); }

    function v(s, d, path, out, ctx) {
      var push = function (p, m) { out.push({ path: p, message: m + (ctx ? ' (needed when ' + ctx + ')' : '') }); };
      if (s === true || s == null) return;
      if (s === false) { push(path, 'is not allowed'); return; }
      if (s.$ref) v(lookup(schema, s.$ref), d, path, out, ctx);

      if (s.const !== undefined && !deepEqual(s.const, d)) push(path, 'must be ' + show(s.const));
      if (s.enum && !s.enum.some(function (e) { return deepEqual(e, d); })) {
        push(path, 'must be one of ' + s.enum.map(show).join(', ') + ' (got ' + show(d) + ')');
      }
      if (s.type) {
        var types = Array.isArray(s.type) ? s.type : [s.type];
        if (!types.some(function (t) { return typeMatches(t, d); })) {
          push(path, 'must be ' + (types.join(' or ')) + ' (got ' + typeOf(d) + ')');
          return;
        }
      }

      if (typeof d === 'string') {
        var len = Array.from(d).length;
        if (s.minLength !== undefined && len < s.minLength) push(path, s.minLength === 1 ? 'must not be empty' : 'must be at least ' + s.minLength + ' characters (has ' + len + ')');
        if (s.maxLength !== undefined && len > s.maxLength) push(path, 'must be at most ' + s.maxLength + ' characters (has ' + len + ')');
        if (s.pattern && !(new RegExp(s.pattern, 'u')).test(d)) push(path, 'must match ' + s.pattern + ' (got ' + show(d) + ')');
      }

      if (typeof d === 'number') {
        if (s.minimum !== undefined && d < s.minimum) push(path, 'must be >= ' + s.minimum + ' (got ' + d + ')');
        if (s.maximum !== undefined && d > s.maximum) push(path, 'must be <= ' + s.maximum + ' (got ' + d + ')');
      }

      if (Array.isArray(d)) {
        if (s.minItems !== undefined && d.length < s.minItems) push(path, 'must have at least ' + s.minItems + ' item' + (s.minItems === 1 ? '' : 's') + ' (has ' + d.length + ')');
        if (s.maxItems !== undefined && d.length > s.maxItems) push(path, 'must have at most ' + s.maxItems + ' items (has ' + d.length + ')');
        if (s.items) d.forEach(function (item, i) { v(s.items, item, joinPath(path, i), out); });
      }

      if (typeOf(d) === 'object') {
        (s.required || []).forEach(function (k) {
          if (!Object.prototype.hasOwnProperty.call(d, k)) push(path || '(root)', 'is missing required "' + k + '"');
        });
        var props = s.properties || {};
        Object.keys(d).forEach(function (k) {
          if (Object.prototype.hasOwnProperty.call(props, k)) v(props[k], d[k], joinPath(path, k), out);
          else if (s.additionalProperties === false) out.push({ path: joinPath(path, k), message: 'is not an allowed field' });
          else if (typeOf(s.additionalProperties) === 'object') v(s.additionalProperties, d[k], joinPath(path, k), out);
        });
      }

      (s.allOf || []).forEach(function (sub) { v(sub, d, path, out, ctx); });

      if (s.if !== undefined) {
        var probe = [];
        v(s.if, d, path, probe);
        var cond = describeIf(s.if);
        // Pragmatic: when the discriminating field is missing, report only that (it is required anyway).
        var keyMissing = cond && typeOf(d) === 'object' && Object.keys(s.if.properties).every(function (k) { return !(k in d); });
        if (keyMissing) { /* skip */ }
        else if (probe.length === 0 && s.then !== undefined) v(s.then, d, path, out, cond || ctx);
        else if (probe.length > 0 && s.else !== undefined) v(s.else, d, path, out, ctx);
      }

      if (s.not !== undefined) {
        var probeNot = [];
        v(s.not, d, path, probeNot);
        if (probeNot.length === 0) {
          var req = s.not.required;
          var msg = req && Object.keys(s.not).length === 1
            ? 'must not have "' + req.join('", "') + '"'
            : 'matches a forbidden pattern';
          out.push({ path: path || '(root)', message: msg + (ctx ? ' when ' + ctx : '') });
        }
      }
    }

    try { v(schema, data, '', errors); }
    catch (e) { err('(schema)', e.message); }
    return errors;
  }

  function words(text) {
    var t = String(text || '').trim();
    return t ? t.split(/\s+/).length : 0;
  }

  function round1(n) { return Math.round(n * 10) / 10; }

  // Start times on the timeline. Each scene overlaps the next by the crossfade.
  function timing(story) {
    var scenes = (story && Array.isArray(story.scenes)) ? story.scenes : [];
    var t = 0;
    var rows = scenes.map(function (sc, i) {
      var secs = (sc && typeof sc.seconds === 'number' && sc.seconds > 0) ? sc.seconds : 0;
      var row = { index: i, id: sc && sc.id, kind: sc && sc.kind, start: t, seconds: secs, scene: sc };
      t += secs - CROSSFADE;
      return row;
    });
    var total = 0;
    if (rows.length) total = rows.reduce(function (a, r) { return a + r.seconds; }, 0) - CROSSFADE * (rows.length - 1);
    return { rows: rows, total: Math.max(0, total) };
  }

  function semantic(story, opts) {
    opts = opts || {};
    var errors = [], warnings = [];
    if (typeOf(story) !== 'object') return { errors: errors, warnings: warnings };
    var scenes = Array.isArray(story.scenes) ? story.scenes : [];
    var cast = Array.isArray(story.cast) ? story.cast : [];
    var music = Array.isArray(story.music) ? story.music : [];

    function dupes(list, label, base) {
      var seen = {};
      list.forEach(function (item, i) {
        if (!item || typeof item.id !== 'string') return;
        if (seen[item.id] !== undefined) errors.push({ path: base + '[' + i + '].id', message: label + ' id "' + item.id + '" is used twice (also ' + base + '[' + seen[item.id] + '])' });
        else seen[item.id] = i;
      });
      return seen;
    }
    var sceneIds = dupes(scenes, 'scene', 'scenes');
    var castIds = dupes(cast, 'cast', 'cast');
    dupes(music, 'music', 'music');

    if (music.length && scenes.length && music[0] && scenes[0] && typeof scenes[0].id === 'string' && music[0].starts_at !== scenes[0].id) {
      errors.push({ path: 'music[0].starts_at', message: 'the first music segment must start at the first scene "' + scenes[0].id + '" (got ' + show(music[0].starts_at) + ')' });
    }
    var lastStart = -1;
    music.forEach(function (m, i) {
      if (!m || typeof m.starts_at !== 'string') return;
      if (sceneIds[m.starts_at] === undefined) {
        errors.push({ path: 'music[' + i + '].starts_at', message: 'scene "' + m.starts_at + '" does not exist' });
        return;
      }
      if (sceneIds[m.starts_at] <= lastStart) warnings.push({ path: 'music[' + i + '].starts_at', message: 'music segments should start at scenes in timeline order' });
      lastStart = sceneIds[m.starts_at];
    });

    scenes.forEach(function (sc, i) {
      if (!sc || typeof sc !== 'object') return;
      var p = 'scenes[' + i + ']';
      if (sc.shot && Array.isArray(sc.shot.cast)) {
        sc.shot.cast.forEach(function (c, j) {
          if (typeof c === 'string' && castIds[c] === undefined) errors.push({ path: p + '.shot.cast[' + j + ']', message: 'cast id "' + c + '" is not in the cast list' });
        });
      }
      if (sc.kind === 'live_action' && sc.shot && typeof sc.seconds === 'number') {
        var dur = typeof sc.shot.duration === 'number' ? sc.shot.duration : 8;
        var trim = typeof sc.trim_start === 'number' ? sc.trim_start : 0;
        if (trim + sc.seconds > dur + 1e-9) warnings.push({ path: p, message: 'trim_start + seconds = ' + round1(trim + sc.seconds) + ' s is longer than the ' + dur + ' s clip; the shot will run short' });
      }
      if (Array.isArray(sc.voice) && typeof sc.seconds === 'number') {
        sc.voice.forEach(function (line, j) {
          if (!line || typeof line.text !== 'string') return;
          var at = typeof line.at === 'number' ? line.at : 0.4;
          var need = at + words(line.text) / WORDS_PER_SECOND + 0.4;
          if (need > sc.seconds + 1e-9) {
            warnings.push({ path: p + '.voice[' + j + ']', message: 'line needs about ' + round1(need) + ' s (at ' + at + ' + ' + words(line.text) + ' words / 2.6 + 0.4) but the scene is ' + sc.seconds + ' s; lengthen the scene or shorten the line' });
          }
        });
      }
    });

    if (scenes.length) {
      var last = scenes[scenes.length - 1];
      if (!last || last.kind !== 'card' || !last.card || last.card.template !== 'endcard') {
        warnings.push({ path: 'scenes[' + (scenes.length - 1) + ']', message: 'the last scene should be an endcard card' });
      }
    }

    var t = timing(story);
    if (opts.targetSeconds > 0 && scenes.length) {
      var lo = opts.targetSeconds * 0.9, hi = opts.targetSeconds * 1.1;
      if (t.total < lo || t.total > hi) {
        warnings.push({ path: '(timing)', message: 'total is ' + round1(t.total) + ' s; the brief asks for ' + opts.targetSeconds + ' s (allowed ' + round1(lo) + '-' + round1(hi) + ' s)' });
      }
    }
    if (opts.aspectRatio && story.aspect_ratio && story.aspect_ratio !== opts.aspectRatio) {
      warnings.push({ path: 'aspect_ratio', message: 'is ' + show(story.aspect_ratio) + ' but the brief asks for ' + show(opts.aspectRatio) });
    }
    return { errors: errors, warnings: warnings };
  }

  // Removes ``` fences and any text around the JSON object.
  function clean(text) {
    var t = String(text || '').replace(/^\uFEFF/, '').trim();
    var fence = t.match(/```(?:json|JSON)?\s*\n([\s\S]*?)\n?```/);
    if (fence) t = fence[1].trim();
    if (t && t[0] !== '{') {
      var a = t.indexOf('{'), b = t.lastIndexOf('}');
      if (a >= 0 && b > a) t = t.slice(a, b + 1);
    }
    return t;
  }

  function check(schema, text, opts) {
    var cleaned = clean(text);
    var result = { cleaned: cleaned, story: null, parseError: null, errors: [], warnings: [], timing: null };
    if (!cleaned) { result.parseError = 'Nothing to check. Paste the JSON reply first.'; return result; }
    try { result.story = JSON.parse(cleaned); }
    catch (e) { result.parseError = 'Not valid JSON: ' + e.message; return result; }
    result.errors = validate(schema, result.story);
    var sem = semantic(result.story, opts);
    result.errors = result.errors.concat(sem.errors);
    result.warnings = sem.warnings;
    result.timing = timing(result.story);
    return result;
  }

  window.StoryCheck = { validate: validate, semantic: semantic, timing: timing, clean: clean, check: check, words: words, CROSSFADE: CROSSFADE };
})();
