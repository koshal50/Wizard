(function () {
  'use strict';
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  // Show / hide password
  document.querySelectorAll('.toggle-pw').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.getElementById(btn.getAttribute('aria-controls'));
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.textContent = show ? 'Hide' : 'Show';
      btn.setAttribute('aria-pressed', String(show));
    });
  });

  // Password strength + live requirements (register page)
  var meter = document.getElementById('meter');
  var pw = document.querySelector('#register-form #password');
  if (meter && pw) {
    var rules = {
      len: function (v) { return v.length >= 12; },
      letter: function (v) { return /[A-Za-z]/.test(v); },
      number: function (v) { return /[0-9]/.test(v); }
    };
    pw.addEventListener('input', function () {
      var v = pw.value, met = 0;
      document.querySelectorAll('#pw-reqs li').forEach(function (li) {
        var ok = rules[li.dataset.rule](v);
        li.classList.toggle('met', ok);
        if (ok) met++;
      });
      var score = v ? met + (v.length >= 14 && /[^A-Za-z0-9]/.test(v) ? 1 : 0) : 0;
      score = Math.min(score, 4);
      meter.dataset.score = score;
      meter.setAttribute('aria-label', 'Password strength: ' + ['none', 'weak', 'fair', 'good', 'strong'][score]);
    });
  }

  function setError(form, name, msg) {
    var out = document.getElementById(name + '-error');
    var input = form.elements[name];
    if (out) out.textContent = msg || '';
    if (input) input.setAttribute('aria-invalid', msg ? 'true' : 'false');
    return !!msg;
  }

  var checks = {
    login: function (f, e) {
      var bad = false;
      if (!EMAIL_RE.test(f.elements.email.value.trim())) bad = e('email', 'Enter a valid email address.') || bad;
      if (!f.elements.password.value) bad = e('password', 'Enter your password.') || bad;
      return bad;
    },
    forgot: function (f, e) {
      return !EMAIL_RE.test(f.elements.email.value.trim()) && e('email', 'Enter a valid email address.');
    },
    register: function (f, e) {
      var bad = false, v = function (n) { return f.elements[n].value; };
      if (v('fullName').trim().length < 2) bad = e('fullName', 'Enter your full name.') || bad;
      if (!EMAIL_RE.test(v('email').trim())) bad = e('email', 'Enter a valid email address.') || bad;
      var p = v('password');
      if (p.length < 12 || p.length > 256 || !/[A-Za-z]/.test(p) || !/[0-9]/.test(p)) bad = e('password', 'Password does not meet the requirements below.') || bad;
      if (p !== v('confirmPassword')) bad = e('confirmPassword', 'Passwords do not match.') || bad;
      if (!f.elements.acceptTerms.checked) bad = e('acceptTerms', 'Accept the terms to create an account.') || bad;
      return bad;
    }
  };

  async function accountJSON(response) {
    try { return await response.json(); }
    catch (_) {
      throw new Error('The account service returned an invalid response (HTTP ' + response.status + '). Check that the Wizard account backend is running and the website points to its port.');
    }
  }

  var contextRequest;
  async function sessionContext() {
    if (contextRequest) return contextRequest;
    contextRequest = (async function () {
      var response = await fetch('/api/auth/context', {
        credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(8000)
      });
      var context = await accountJSON(response);
      if (!response.ok || !/^[a-f0-9]{64}$/.test(context.csrf) ||
          typeof context.cli_pending !== 'boolean' ||
          (context.account !== null && (!context.account || typeof context.account.id !== 'string' ||
            typeof context.account.email !== 'string'))) throw new Error('Cannot verify your session. Reload and retry.');
      return context;
    })();
    try { return await contextRequest; } finally { contextRequest = null; }
  }

  function alertMessage(message, success) {
    var box = document.getElementById('form-alert');
    if (!box) return;
    box.textContent = message;
    box.classList.toggle('error', !success);
    box.classList.toggle('success', !!success);
    box.classList.add('show');
    if (!success) box.focus();
  }

  function showExistingSession(form, context) {
    var old = form.parentNode.querySelector('[data-existing-session]');
    if (old) old.remove();
    var notice = document.createElement('aside');
    notice.setAttribute('data-existing-session', '');
    notice.setAttribute('aria-label', 'Current signed-in account');
    notice.className = 'alert success show';
    var message = document.createElement('p');
    message.textContent = 'This browser is already signed in as ' + context.account.email + '.';
    var actions = document.createElement('div');
    actions.className = 'row';
    var proceed = document.createElement('button');
    proceed.type = 'button'; proceed.className = 'btn secondary';
    proceed.textContent = 'Continue as ' + (context.account.full_name || context.account.email);
    var signOut = document.createElement('button');
    signOut.type = 'button'; signOut.className = 'btn secondary'; signOut.textContent = 'Sign out';
    proceed.addEventListener('click', async function () {
      proceed.disabled = true;
      try {
        var current = await sessionContext();
        if (!current.account) { notice.remove(); throw new Error('Your session expired. Sign in again.'); }
        if (current.account.id !== context.account.id) {
          showExistingSession(form, current);
          throw new Error('The signed-in account changed. Review the account before continuing.');
        }
        window.location.assign(current.cli_pending ? '/cli/connect' : '/dashboard');
      } catch (error) { alertMessage(error.message || 'Session unavailable. Retry.'); proceed.disabled = false; }
    });
    signOut.addEventListener('click', async function () {
      signOut.disabled = true;
      try {
        var current = await sessionContext();
        if (current.account) {
          var response = await fetch('/logout', {
            method: 'POST', credentials: 'same-origin', cache: 'no-store',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': current.csrf },
            body: '{}', signal: AbortSignal.timeout(8000)
          });
          var result = await accountJSON(response);
          if (!response.ok || result.signed_out !== true) throw new Error('Sign out was not confirmed. Retry.');
        }
        if ((await sessionContext()).account) throw new Error('Sign out was not confirmed. Reload and retry.');
        notice.remove();
        form.querySelectorAll('input[type=password]').forEach(function (input) { input.value = ''; });
        alertMessage('Signed out. You can now sign in or create an account.', true);
      } catch (error) { alertMessage(error.message || 'Sign out was not confirmed. Retry.'); signOut.disabled = false; }
    });
    actions.append(proceed, signOut); notice.append(message, actions); form.before(notice);
  }

  document.querySelectorAll('form[data-form]').forEach(function (form) {
    var btn = form.querySelector('button[type=submit]');
    var label = btn.textContent;
    if (form.dataset.form !== 'forgot') {
      sessionContext().then(function (context) { if (context.account) showExistingSession(form, context); }).catch(function () {});
    }

    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      if (btn.disabled) return;
      var box = document.getElementById('form-alert');
      if (box) { box.classList.remove('show'); box.textContent = ''; }
      form.querySelectorAll('.field-error').forEach(function (el) { el.textContent = ''; });
      form.querySelectorAll('[aria-invalid]').forEach(function (el) { el.setAttribute('aria-invalid', 'false'); });

      if (checks[form.dataset.form](form, function (n, m) { return setError(form, n, m); })) {
        ev.preventDefault();
        var first = form.querySelector('[aria-invalid=true]');
        if (first) first.focus();
        return;
      }
      // Submit established handlers with fresh session CSRF and safe redirects.
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
      btn.innerHTML = '<span class="spinner" aria-hidden="true"></span><span></span>';
      btn.lastChild.textContent = btn.dataset.loading || 'Working…';
      try {
        var ctx = await sessionContext();
        if (ctx.account && form.dataset.form !== 'forgot') {
          showExistingSession(form, ctx);
          throw new Error('This browser is already signed in. Continue with the account shown above, or sign out to use another account.');
        }
        var fields = new URLSearchParams();
        new FormData(form).forEach(function (value, key) { fields.append(key, value); });
        fields.set('csrf', ctx.csrf);
        var response = await fetch(form.getAttribute('action'), {
          method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'manual',
          headers: { 'X-CSRF-Token': ctx.csrf }, body: fields, signal: AbortSignal.timeout(15000)
        });
        if (response.type === 'opaqueredirect') {
          // Manual redirects preserve rotated cookies without fetching the destination HTML.
          // A redirect is not authentication proof: re-read the verified server session.
          var verifiedResponse = await fetch('/api/auth/context', {
            credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(8000)
          });
          var verified = await accountJSON(verifiedResponse);
          if (!verifiedResponse.ok || !verified.account || typeof verified.account.id !== 'string' ||
              typeof verified.cli_pending !== 'boolean') {
            throw new Error('Authentication was not verified. Reload and try signing in.');
          }
          window.location.assign(verified.cli_pending ? '/cli/connect' : '/dashboard');
          return;
        }
        var result = await accountJSON(response);
        if (result.error === 'already_authenticated') {
          var current = await sessionContext();
          if (current.account) showExistingSession(form, current);
        }
        var message = response.status === 429 ? 'Too many attempts. Wait at least ' + (response.headers.get('Retry-After') || '60') + ' seconds.'
          : result.error === 'password_reset_delivery_unconfigured' ? 'Password reset email delivery is not configured.'
          : response.status === 401 ? 'Email or password was not accepted.'
          : result.error === 'already_authenticated' ? 'This browser is already signed in. Continue with the account shown above, or sign out.'
          : result.error === 'session_changed' ? 'Your session changed in another tab. Reload and retry.'
          : result.error === 'registration_unavailable' ? 'An account could not be created with these details. Try signing in or use a different email address.'
          : response.status === 503 ? 'The sign-in service is unavailable. Retry when the local account service is running.'
          : 'Authentication was not confirmed. Check your details and retry.';
        throw new Error(message);
      } catch (error) {
        alertMessage(error.message || 'Connection failed. Retry.');
        form.querySelectorAll('input[type=password]').forEach(function (input) { input.value = ''; });
        btn.disabled = false;
        btn.removeAttribute('aria-busy');
        btn.textContent = label;
      }

    });

    // Restore the button when returning via the back button
    window.addEventListener('pageshow', function () {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      btn.textContent = label;
    });
  });
})();
