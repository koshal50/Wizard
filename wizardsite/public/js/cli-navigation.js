(function () {
  'use strict';
  if (new URLSearchParams(window.location.search).get('returnTo') !== '/cli/connect') return;
  document.querySelectorAll('a[href="login.html"], a[href="register.html"], a[href="forgot-password.html"]').forEach(function (link) {
    var url = new URL(link.getAttribute('href'), window.location.href);
    url.searchParams.set('returnTo', '/cli/connect');
    link.setAttribute('href', url.pathname + url.search);
  });
  var main = document.querySelector('.auth-main');
  if (!main) return;
  var notice = document.createElement('aside');
  notice.className = 'cli-navigation';
  notice.setAttribute('aria-label', 'Wizard CLI connection');
  var text = document.createElement('p');
  text.textContent = 'Sign in to review your pending Wizard CLI connection. A code is issued only after you approve.';
  var cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.textContent = 'Cancel CLI connection';
  cancel.addEventListener('click', async function () {
    cancel.disabled = true;
    try {
      var response = await fetch('/api/auth/context', { cache: 'no-store', credentials: 'same-origin' });
      var ctx = await response.json();
      if (!response.ok || !/^[a-f0-9]{64}$/.test(ctx.csrf)) throw new Error();
      response = await fetch('/api/cli/browser/cancel', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': ctx.csrf },
        body: '{}', signal: AbortSignal.timeout(8000)
      });
      var result = await response.json();
      if (!response.ok || result.state !== 'cancelled') throw new Error();
      text.textContent = 'Backend confirmed CLI connection cancellation.';
      cancel.remove();
    } catch (_) {
      text.textContent = 'Cancellation was not confirmed. Retry, or use /cancel-login in the original terminal.';
      cancel.disabled = false;
    }
  });
  notice.append(text, cancel);
  main.appendChild(notice);
})();
