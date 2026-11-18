/* Shared helpers: copy buttons for code blocks and file downloads. No network calls. */
(function () {
  'use strict';

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy') ? resolve() : reject(new Error('copy failed')); }
      catch (e) { reject(e); }
      finally { document.body.removeChild(ta); }
    });
  }

  function flash(btn, label) {
    var old = btn.dataset.label || btn.textContent;
    btn.dataset.label = old;
    btn.textContent = label;
    btn.classList.add('done');
    clearTimeout(btn._t);
    btn._t = setTimeout(function () { btn.textContent = old; btn.classList.remove('done'); }, 1400);
  }

  function addCopyButtons(root) {
    (root || document).querySelectorAll('.code').forEach(function (block) {
      if (block.querySelector(':scope > .copy')) return;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'copy';
      b.textContent = 'Copy';
      b.setAttribute('aria-label', 'Copy to clipboard');
      block.appendChild(b);
    });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.code > .copy, [data-copy-from]');
    if (!btn) return;
    var text;
    if (btn.hasAttribute('data-copy-from')) {
      var src = document.getElementById(btn.getAttribute('data-copy-from'));
      text = !src ? '' : (src.tagName === 'TEXTAREA' || src.tagName === 'INPUT') ? src.value : src.textContent;
    } else {
      var pre = btn.parentElement.querySelector('pre');
      text = pre ? pre.textContent : '';
    }
    copyText(text.replace(/\s+$/, '')).then(
      function () { flash(btn, 'Copied'); },
      function () { flash(btn, 'Press Ctrl+C'); }
    );
  });

  function download(name, text, type) {
    var blob = new Blob([text], { type: (type || 'text/plain') + ';charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  window.MVG = { copyText: copyText, download: download, addCopyButtons: addCopyButtons, flash: flash };
  document.addEventListener('DOMContentLoaded', function () { addCopyButtons(document); });
})();
