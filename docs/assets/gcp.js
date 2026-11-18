/* In-browser Google Cloud checks and the Gemini story call.
   The access token lives only in this closure: never stored, never put in the page URL. */
(function () {
  'use strict';
  var Y = window.MVG_YAML;
  var token = '';

  function setToken(t) { token = String(t || '').trim().replace(/^Bearer\s+/i, ''); }
  function hasToken() { return token.length > 0; }

  async function gfetch(url, opts) {
    opts = opts || {};
    var headers = {};
    if (opts.auth !== false) headers.Authorization = 'Bearer ' + token;
    if (opts.body) headers['Content-Type'] = 'application/json; charset=utf-8';
    var r;
    try {
      r = await fetch(url, {
        method: opts.method || 'GET', headers: headers,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
        signal: opts.signal, cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer'
      });
    } catch (e) {
      return { status: 0, ok: false, network: true, aborted: e && e.name === 'AbortError', message: e && e.name === 'AbortError' ? 'Cancelled.' : 'Network error: ' + (e && e.message) };
    }
    var text = await r.text();
    var json = null;
    try { json = JSON.parse(text); } catch (e) { /* not JSON */ }
    var gerr = json && json.error && typeof json.error === 'object' ? json.error : null;
    var reason = '', service = '';
    if (gerr && Array.isArray(gerr.details)) {
      gerr.details.forEach(function (d) {
        if (d && d.reason) reason = reason || d.reason;
        if (d && d.metadata && d.metadata.service) service = service || d.metadata.service;
      });
    }
    var message = gerr ? (gerr.message || '') : (json && json.error_description) || (json && typeof json.error === 'string' ? json.error : '');
    return { status: r.status, ok: r.ok, json: json, message: message, gstatus: gerr && gerr.status, reason: reason, service: service };
  }

  // A fix for a failed Google API response: {text, code}
  function fixFor(res, f, kind) {
    var p = Y.project(f);
    if (res.network) {
      return { text: res.aborted ? 'Cancelled.' : 'The browser could not reach the API (offline, or blocked by an extension, proxy or network policy). Run `mvg doctor` on your computer instead.' };
    }
    var msg = (res.message || '').toLowerCase();
    if (res.status === 401) return { text: 'The token is invalid or expired (tokens last about an hour). Get a new one and paste it again:', code: 'gcloud auth print-access-token' };
    if (res.reason === 'SERVICE_DISABLED' || /has not been used|is disabled|it is disabled/.test(msg)) {
      var svc = res.service || 'aiplatform.googleapis.com';
      return { text: 'The API ' + svc + ' is not enabled in the project. Enable it (or ask your admin):', code: 'gcloud services enable ' + svc + ' --project=' + p };
    }
    if (res.reason === 'USER_PROJECT_DENIED' || /quota project|serviceusage\.services\.use/.test(msg)) {
      return { text: 'You may not use this project for quota. Grant Service Usage Consumer (an Owner or IAM admin must run it):', code: Y.grantLines(f)[1] };
    }
    if (res.status === 403) {
      if (kind === 'project') return { text: 'Check the project ID (the ID, not the display name) and that your account has a role in it.' };
      return { text: 'Permission denied. Check the project ID, then grant the roles (an Owner or IAM admin must run these):', code: Y.grantLines(f).join('\n') };
    }
    if (res.status === 404) {
      if (kind === 'model') return { text: 'Model not found. Check the model id and its location: Gemini 3 models are served on global, Veo is regional. Preview models may need access for your project.' };
      return { text: 'Project not found. Check the project ID (the ID, not the display name).' };
    }
    if (res.status === 429) return { text: 'Rate limit or quota reached. Wait a minute and try again; in studio.yaml lower limits.parallel.' };
    if (res.status === 400) return { text: 'Google rejected the request. Check the project ID and model id; the message above has the detail.' };
    if (res.status >= 500) return { text: 'Google returned a server error. Try again in a minute.' };
    return { text: 'Unexpected response. Run `mvg doctor` for details.' };
  }

  function detailOf(res) {
    if (res.network) return res.message;
    var s = 'HTTP ' + res.status;
    if (res.gstatus) s += ' ' + res.gstatus;
    if (res.reason && res.reason !== res.gstatus) s += ' (' + res.reason + ')';
    if (res.message) s += ': ' + res.message;
    return s;
  }

  function enc(s) { return encodeURIComponent(s); }

  async function checkToken(f) {
    var res = await gfetch('https://oauth2.googleapis.com/tokeninfo?access_token=' + enc(token), { auth: false });
    if (res.ok && res.json) {
      var j = res.json;
      var exp = parseInt(j.expires_in, 10);
      var who = j.email ? 'Token for ' + j.email : 'Token is valid';
      var detail = 'HTTP 200. ' + who + (isFinite(exp) ? ', expires in ' + Math.round(exp / 60) + ' min.' : '.');
      if (isFinite(exp) && exp < 300) return { level: 'warn', title: 'Token info', detail: detail, fix: { text: 'The token expires soon. Get a fresh one:', code: 'gcloud auth print-access-token' } };
      var wantEmail = Y.val(f, 'gcp.email');
      if (j.email && wantEmail && j.email.toLowerCase() !== wantEmail.toLowerCase()) {
        return { level: 'warn', title: 'Token info', detail: detail, fix: { text: 'This token belongs to ' + j.email + ', not ' + wantEmail + ' (step 3). Roles are granted per account.' } };
      }
      return { level: 'pass', title: 'Token info', detail: detail };
    }
    return { level: 'warn', title: 'Token info', detail: detailOf(res), fix: { text: 'Could not read token info. The other checks still run; if they fail with 401, get a new token with `gcloud auth print-access-token`.' } };
  }

  async function checkService(f) {
    var url = 'https://serviceusage.googleapis.com/v1/projects/' + enc(Y.val(f, 'gcp.project')) + '/services/aiplatform.googleapis.com';
    var res = await gfetch(url);
    var title = 'Vertex AI API enabled';
    if (res.ok && res.json) {
      if (res.json.state === 'ENABLED') return { level: 'pass', title: title, detail: 'HTTP 200. aiplatform.googleapis.com is ENABLED.' };
      return { level: 'fail', title: title, detail: 'HTTP 200. State is ' + (res.json.state || 'unknown') + '.', fix: { text: 'Enable it (needs Owner, Editor or Service Usage Admin):', code: 'gcloud services enable aiplatform.googleapis.com --project=' + Y.project(f) } };
    }
    if (res.status === 403 && !(res.reason === 'SERVICE_DISABLED' && res.service && res.service !== 'serviceusage.googleapis.com')) {
      return { level: 'warn', title: title, detail: detailOf(res), fix: { text: "Can't read the service state with your role. That is fine if the Gemini call below passes; otherwise ask your admin or run `mvg doctor`." } };
    }
    return { level: res.status === 401 ? 'fail' : (res.network ? 'warn' : 'fail'), title: title, detail: detailOf(res), fix: fixFor(res, f, 'project') };
  }

  async function checkIam(f) {
    var url = 'https://cloudresourcemanager.googleapis.com/v1/projects/' + enc(Y.val(f, 'gcp.project')) + ':testIamPermissions';
    var res = await gfetch(url, { method: 'POST', body: { permissions: ['aiplatform.endpoints.predict'] } });
    var title = 'Permission aiplatform.endpoints.predict';
    if (res.ok) {
      var perms = (res.json && res.json.permissions) || [];
      if (perms.indexOf('aiplatform.endpoints.predict') >= 0) return { level: 'pass', title: title, detail: 'HTTP 200. You may call models in this project.' };
      return { level: 'fail', title: title, detail: 'HTTP 200. The permission was not returned: your account lacks Vertex AI User.', fix: { text: 'Grant the roles (an Owner or IAM admin must run these):', code: Y.grantLines(f).join('\n') } };
    }
    return { level: res.network ? 'warn' : 'fail', title: title, detail: detailOf(res), fix: fixFor(res, f, 'project') };
  }

  function generateUrl(f, model) {
    return 'https://aiplatform.googleapis.com/v1/projects/' + enc(Y.val(f, 'gcp.project')) +
      '/locations/global/publishers/google/models/' + enc(model) + ':generateContent';
  }

  function replyText(json) {
    var c = json && json.candidates && json.candidates[0];
    var parts = (c && c.content && c.content.parts) || [];
    return parts.filter(function (p) { return p && typeof p.text === 'string' && !p.thought; }).map(function (p) { return p.text; }).join('');
  }

  async function checkGemini(f) {
    var model = Y.pingModel(f);
    var res = await gfetch(generateUrl(f, model), {
      method: 'POST',
      body: { contents: [{ role: 'user', parts: [{ text: 'Reply with the single word OK.' }] }], generationConfig: { maxOutputTokens: 64 } }
    });
    var title = 'Gemini call (' + model + ', global)';
    if (res.ok) {
      var t = replyText(res.json).trim();
      return { level: 'pass', title: title, detail: 'HTTP 200.' + (t ? ' Gemini replied: ' + t.slice(0, 60) : ' The model answered.') };
    }
    return { level: 'fail', title: title, detail: detailOf(res), fix: fixFor(res, f, 'model') };
  }

  var CHECKS = [checkToken, checkService, checkIam, checkGemini];
  var CHECK_TITLES = ['Token info', 'Vertex AI API enabled', 'Permission aiplatform.endpoints.predict', 'Gemini call'];

  async function writeStory(f, prompt, signal) {
    var model = Y.pingModel(f);
    var res = await gfetch(generateUrl(f, model), {
      method: 'POST', signal: signal,
      body: { contents: [{ role: 'user', parts: [{ text: prompt }] }], generationConfig: { responseMimeType: 'application/json', temperature: 0.8 } }
    });
    if (!res.ok) return { ok: false, detail: detailOf(res), fix: fixFor(res, f, 'model'), aborted: res.aborted };
    var text = replyText(res.json);
    if (!text) {
      var c = res.json && res.json.candidates && res.json.candidates[0];
      var why = (c && c.finishReason) || (res.json && res.json.promptFeedback && res.json.promptFeedback.blockReason) || 'no text';
      return { ok: false, detail: 'HTTP 200 but no story came back (' + why + ').', fix: { text: 'Try again, or use the copy-paste tab with another model.' } };
    }
    return { ok: true, text: text, model: model };
  }

  window.MVG_GCP = {
    setToken: setToken, hasToken: hasToken, checks: CHECKS, checkTitles: CHECK_TITLES,
    writeStory: writeStory, fixFor: fixFor, detailOf: detailOf
  };
})();
