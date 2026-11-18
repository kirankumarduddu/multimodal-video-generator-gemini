/* Generates studio.yaml, brand.yaml, brief.yaml and the shell commands from the guide's answers.
   A tiny YAML writer that matches the formatting of examples/kettle-and-kite. */
(function () {
  'use strict';
  var D = window.MVG_DATA;

  // ---------- YAML helpers ----------
  var BOOLISH = /^(y|Y|yes|Yes|YES|n|N|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF|null|Null|NULL|~)$/;

  function needsQuote(s, flow) {
    if (s === '') return true;
    if (/^\s|\s$/.test(s)) return true;
    if (/^[-?:,\[\]{}#&*!|>'"%@`]/.test(s)) return true;
    if (/: |:$| #|[\t\n\r]/.test(s)) return true;
    if (BOOLISH.test(s)) return true;
    if (/^[-+]?(\d[\d_]*(\.\d*)?|\.\d+)([eE][-+]?\d+)?$/.test(s)) return true;
    if (/^[-+]?0[xob]/.test(s)) return true;
    if (/^[\d:.\-]+$/.test(s)) return true; // 16:9, dates, times
    if (flow && /[,\[\]{}]/.test(s)) return true;
    return false;
  }

  function str(s, flow) {
    s = String(s == null ? '' : s);
    return needsQuote(s, flow) ? JSON.stringify(s) : s;
  }

  function scalar(v, flow) {
    if (v === null || v === undefined) return 'null';
    if (typeof v === 'boolean' || typeof v === 'number') return String(v);
    return str(v, flow);
  }

  function flowMap(obj) {
    return '{' + Object.keys(obj).map(function (k) { return k + ': ' + scalar(obj[k], true); }).join(', ') + '}';
  }

  function lines(text) {
    return String(text || '').split(/\r?\n/).map(function (x) { return x.trim(); }).filter(Boolean);
  }

  function list(key, items, indent) {
    indent = indent || '';
    if (!items.length) return indent + key + ': []';
    return indent + key + ':\n' + items.map(function (x) { return indent + '  - ' + str(x); }).join('\n');
  }

  function comment(line, text, col) {
    if (!text) return line;
    col = col || 26;
    var pad = Math.max(2, col - line.length);
    return line + new Array(pad + 1).join(' ') + '# ' + text;
  }

  // Folded block scalar (>-), wrapped at `width` characters like the example.
  function folded(key, text, width) {
    width = width || 100;
    var t = String(text || '').replace(/\s+/g, ' ').trim();
    if (!t) return key + ': ""';
    var out = [], cur = '';
    t.split(' ').forEach(function (w) {
      if (cur && (cur + ' ' + w).length > width) { out.push(cur); cur = w; }
      else cur = cur ? cur + ' ' + w : w;
    });
    if (cur) out.push(cur);
    return key + ': >-\n' + out.map(function (l) { return '  ' + l; }).join('\n');
  }

  function hex(v) {
    var s = String(v || '').trim();
    return /^#[0-9a-fA-F]{6}$/.test(s) ? s.toUpperCase() : s;
  }

  // ---------- form readers ----------
  function val(f, k) { var v = f[k]; return v == null ? '' : String(v).trim(); }

  function storyModel(f) {
    var p = val(f, 'story.provider') || 'gemini';
    if (p === 'openai') return { provider: 'openai', model: val(f, 'story.openai.model'), base_url: val(f, 'story.openai.base_url'), api_key_env: val(f, 'story.openai.api_key_env') };
    if (p === 'anthropic') return { provider: 'anthropic', model: val(f, 'story.anthropic.model'), api_key_env: val(f, 'story.anthropic.api_key_env') };
    if (p === 'manual') return { provider: 'manual' };
    return { provider: 'gemini', model: val(f, 'story.gemini.model'), location: val(f, 'story.gemini.location') || 'global' };
  }

  function pingModel(f) {
    return (val(f, 'story.provider') === 'gemini' && val(f, 'story.gemini.model')) || 'gemini-3.5-flash';
  }

  function gcsUri(f) {
    var b = val(f, 'gcp.bucket');
    if (!b) return '';
    if (/^gs:\/\//.test(b)) return b.replace(/\/+$/, '');
    return 'gs://' + b.replace(/^\/+|\/+$/g, '');
  }

  function bucketName(f) {
    var u = gcsUri(f);
    return u ? u.replace(/^gs:\/\//, '').split('/')[0] : '';
  }

  function targetSeconds(f) {
    var n = parseFloat(val(f, 'brief.length') === 'custom' ? val(f, 'brief.lengthCustom') : val(f, 'brief.length'));
    return isFinite(n) && n > 0 ? n : 0;
  }

  // ---------- files ----------
  function studio(f) {
    var res = val(f, 'video.resolution') || '1080p';
    var veo = { provider: 'veo', model: val(f, 'video.veo.model'), location: val(f, 'gcp.region') || 'us-central1', resolution: res, generate_audio: val(f, 'video.generate_audio') === 'true' };
    var omni = { provider: 'omni', model: val(f, 'video.omni.model'), location: val(f, 'video.omni.location') || 'global', resolution: res };
    var useOmni = val(f, 'video.provider') === 'omni';
    var image = { model: val(f, 'image.model'), location: val(f, 'image.location') || 'global' };
    var par = parseInt(val(f, 'limits.parallel'), 10);
    if (!(par >= 1)) par = 3;
    var gcs = gcsUri(f);
    var out = [
      '# Which Google Cloud project and models to use. Run `mvg doctor` after editing.',
      'gcp:',
      '  project: ' + str(val(f, 'gcp.project') || 'your-gcp-project-id'),
      '',
      'models:',
      '  # Story: any LLM. provider = gemini | openai | anthropic | manual',
      '  #   openai covers every OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, Ollama, LM Studio, vLLM...):',
      '  #     {provider: openai, model: gpt-5, base_url: https://api.openai.com/v1, api_key_env: OPENAI_API_KEY}',
      '  #   anthropic: {provider: anthropic, model: claude-sonnet-5, api_key_env: ANTHROPIC_API_KEY}',
      '  #   manual: `mvg story prompt` prints the prompt; paste it in any chat and save the reply as story.json',
      '  story: ' + flowMap(storyModel(f)),
      comment('  image: ' + flowMap(image), 'cast stills and keyframes' + (image.model === 'gemini-3-pro-image' ? ' (Nano Banana Pro)' : ''), 64),
      (useOmni ? '  # video: ' + flowMap(veo) : '  video: ' + flowMap(veo)),
      (useOmni ? '  video: ' + flowMap(omni) : '  # video: ' + flowMap(omni)),
      '  tts: ' + flowMap({ model: val(f, 'tts.model'), location: val(f, 'tts.location') || 'global' }),
      '  music: ' + flowMap({ model: val(f, 'music.model'), location: val(f, 'music.location') || 'global' }),
      '',
      'output:',
      comment('  gcs_uri: ' + (gcs ? str(gcs) : 'null'), 'optional gs://bucket/prefix for Veo output (needs storage.objects.create)'),
      '',
      'limits:',
      comment('  parallel: ' + par, 'concurrent image or video requests')
    ];
    return out.join('\n') + '\n';
  }

  function brand(f) {
    var logo = val(f, 'brand.logo');
    var out = [
      '# The brand. Cards use the colors, fonts and logo; every generated shot gets the look; the narrator uses the voice.',
      'name: ' + str(val(f, 'brand.name')),
      'tagline: ' + str(val(f, 'brand.tagline')),
      'colors:',
      comment('  background: ' + str(hex(f['brand.colors.background'])), 'stage behind cards'),
      comment('  surface: ' + str(hex(f['brand.colors.surface'])), 'card panels'),
      comment('  primary: ' + str(hex(f['brand.colors.primary'])), 'rules, highlights, buttons'),
      comment('  accent: ' + str(hex(f['brand.colors.accent'])), 'headlines'),
      '  text: ' + str(hex(f['brand.colors.text'])),
      '  muted: ' + str(hex(f['brand.colors.muted'])),
      'fonts:',
      comment('  heading: ' + str(val(f, 'brand.fonts.heading')), 'a Google Fonts family name, or {family: ..., file: brand/fonts/MyFont.ttf}'),
      '  body: ' + str(val(f, 'brand.fonts.body')),
      comment('logo: ' + (logo ? str(logo) : 'null'), 'optional: brand/logo.png (transparent PNG or SVG)'),
      folded('look', f['brand.look']),
      'voice:',
      comment('  name: ' + str(val(f, 'brand.voice.name')), 'a Gemini TTS prebuilt voice'),
      '  direction: ' + str(String(f['brand.voice.direction'] || '').replace(/\s+/g, ' ').trim()),
      list('rules', lines(f['brand.rules']))
    ];
    return out.join('\n') + '\n';
  }

  function brief(f) {
    var len = targetSeconds(f) || 60;
    var one = function (k) { return str(String(f[k] || '').replace(/\s+/g, ' ').trim()); };
    var out = [
      '# What the film is for. The story prompt includes this file word for word, so write facts only.',
      'purpose: ' + one('brief.purpose'),
      'audience: ' + one('brief.audience'),
      'length_seconds: ' + len,
      'aspect_ratio: ' + str(val(f, 'brief.aspect') || '16:9'),
      'language: ' + one('brief.language'),
      'key_message: ' + one('brief.key_message'),
      'story_angle: ' + one('brief.story_angle'),
      list('beats', lines(f['brief.beats'])),
      list('proof_points', lines(f['brief.proof_points'])),
      list('quotes', lines(f['brief.quotes'])),
      'call_to_action: ' + one('brief.call_to_action'),
      list('characters', lines(f['brief.characters'])),
      list('settings', lines(f['brief.settings'])),
      'mood: ' + one('brief.mood'),
      'music_mood: ' + one('brief.music_mood'),
      list('screenshots', lines(f['brief.screenshots'])),
      list('must_include', lines(f['brief.must_include'])),
      list('must_avoid', lines(f['brief.must_avoid']))
    ];
    return out.join('\n') + '\n';
  }

  // ---------- commands ----------
  function win(f) { return val(f, 'os') !== 'unix'; }
  function project(f) { return val(f, 'gcp.project') || 'PROJECT_ID'; }
  function email(f) { return val(f, 'gcp.email') || 'YOUR_EMAIL'; }
  function dir(f) {
    var d = val(f, 'project.dir') || 'my-film';
    return /[\s'"$`&;|<>()]/.test(d) ? '"' + d.replace(/"/g, '') + '"' : d;
  }

  function grantLines(f) {
    var p = project(f), m = 'user:' + email(f);
    return [
      'gcloud projects add-iam-policy-binding ' + p + ' --member=' + m + ' --role=roles/aiplatform.user',
      'gcloud projects add-iam-policy-binding ' + p + ' --member=' + m + ' --role=roles/serviceusage.serviceUsageConsumer'
    ];
  }

  function storageLines(f) {
    var b = bucketName(f);
    if (!b) return [];
    return [
      'gcloud services enable storage.googleapis.com',
      'gcloud storage buckets add-iam-policy-binding gs://' + b + ' --member=user:' + email(f) + ' --role=roles/storage.objectAdmin'
    ];
  }

  var C = {
    install: function (f) {
      return [
        'git clone ' + D.CLONE_URL,
        'cd ' + D.REPO_DIR,
        'python -m venv .venv',
        win(f) ? '.\\.venv\\Scripts\\Activate.ps1' : 'source .venv/bin/activate',
        'pip install -e .',
        'playwright install chromium'
      ].join('\n');
    },
    init: function (f) { return 'mvg init ' + dir(f) + '\ncd ' + dir(f); },
    initExample: function (f) { return 'mvg init ' + dir(f) + ' --example kettle-and-kite'; },
    gcloud: function (f) {
      var p = project(f);
      return [
        'gcloud auth login',
        'gcloud config set project ' + p,
        'gcloud services enable aiplatform.googleapis.com',
        'gcloud auth application-default login',
        'gcloud auth application-default set-quota-project ' + p,
        '# Owner or IAM admin only:'
      ].concat(grantLines(f)).concat(storageLines(f)).join('\n');
    },
    setupScript: function (f) {
      var b = bucketName(f);
      if (win(f)) {
        var ps = '.\\scripts\\setup-gcp.ps1 -Project ' + project(f) + ' -Email ' + email(f) + (b ? ' -Bucket ' + b : '');
        return '# in the cloned repo folder\n' + ps + '\n# not an owner? add -SkipGrant and send your admin the message below\n' + ps + ' -SkipGrant';
      }
      var sh = 'bash scripts/setup-gcp.sh ' + project(f) + ' ' + email(f) + (b ? ' ' + b : '');
      return '# in the cloned repo folder\n' + sh + '\n# not an owner? skip the role grants and send your admin the message below\nSKIP_GRANT=1 ' + sh;
    },
    adminMsg: function (f) {
      var lines = [
        'Hi, I would like to use Vertex AI (Gemini, Veo, Lyria) in the Google Cloud project ' + project(f) + ' for a video tool that runs on my computer with my own sign-in.',
        'Could you please run these commands (or grant the same in the console under IAM)?',
        '',
        'gcloud services enable aiplatform.googleapis.com --project=' + project(f)
      ].concat(grantLines(f)).concat(storageLines(f));
      lines.push('', 'Vertex AI User lets me call the models; Service Usage Consumer lets my credentials use the project for API quota. Usage is billed to the project. Thank you!');
      return lines.join('\n');
    },
    doctor: function (f) {
      return 'cd ' + dir(f) + '\nmvg doctor\nmvg doctor --deep        # also pings TTS and image';
    },
    pingModel: function (f) { return pingModel(f); },
    envKey: function (f) {
      var p = val(f, 'story.provider');
      var name = (p === 'anthropic' ? val(f, 'story.anthropic.api_key_env') : val(f, 'story.openai.api_key_env')) || 'API_KEY';
      return win(f)
        ? '$env:' + name + ' = "paste-your-key-here"    # this terminal only'
        : 'export ' + name + '="paste-your-key-here"    # this terminal only';
    },
    grant: function (f) { return grantLines(f).join('\n'); },
    enable: function (f) { return 'gcloud services enable aiplatform.googleapis.com --project=' + project(f); },
    quota: function (f) { return 'gcloud auth application-default set-quota-project ' + project(f); },
    copyFiles: function (f) {
      return win(f)
        ? 'Copy-Item "$HOME\\Downloads\\studio.yaml", "$HOME\\Downloads\\brand.yaml", "$HOME\\Downloads\\brief.yaml", "$HOME\\Downloads\\story.json" -Destination .'
        : 'cp ~/Downloads/studio.yaml ~/Downloads/brand.yaml ~/Downloads/brief.yaml ~/Downloads/story.json .';
    },
    studio: studio,
    brand: brand,
    brief: brief
  };

  window.MVG_YAML = {
    gen: C, str: str, needsQuote: needsQuote, folded: folded, flowMap: flowMap,
    pingModel: pingModel, targetSeconds: targetSeconds, project: project, email: email, dir: dir,
    grantLines: grantLines, val: val
  };
})();
