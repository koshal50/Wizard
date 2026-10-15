(function () {
  'use strict';

  // A fixed frontend destination, not an authentication redirect handler.
  // Ignore arbitrary return URLs and leave ordinary auth visits untouched.
  var destination = '/cli/connect';
  if (new URLSearchParams(window.location.search).get('returnTo') !== destination) return;

  document.querySelectorAll('a[href="login.html"], a[href="register.html"], a[href="forgot-password.html"]').forEach(function (link) {
    var url = new URL(link.getAttribute('href'), window.location.href);
    url.searchParams.set('returnTo', destination);
    link.setAttribute('href', url.pathname + url.search);
  });

  var main = document.querySelector('.auth-main');
  if (!main) return;

  var notice = document.createElement('aside');
  notice.className = 'cli-navigation';
  notice.setAttribute('aria-label', 'Wizard CLI connection preview');

  var text = document.createElement('p');
  text.textContent = 'Wizard CLI connection preview. Automatic return after sign-in will be available when authorization is connected.';
  var preview = document.createElement('a');
  preview.href = destination;
  preview.textContent = 'Preview the connection screen';
  var cancel = document.createElement('a');
  cancel.href = '/';
  cancel.textContent = 'Cancel and return to website';

  notice.append(text, preview, document.createElement('br'), cancel);
  main.appendChild(notice);
})();
