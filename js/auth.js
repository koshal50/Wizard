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
      len: function (v) { return v.length >= 10; },
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
      if (p.length < 10 || !/[A-Za-z]/.test(p) || !/[0-9]/.test(p)) bad = e('password', 'Password does not meet the requirements below.') || bad;
      if (p !== v('confirmPassword')) bad = e('confirmPassword', 'Passwords do not match.') || bad;
      if (!f.elements.acceptTerms.checked) bad = e('acceptTerms', 'Accept the terms to create an account.') || bad;
      return bad;
    }
  };

  document.querySelectorAll('form[data-form]').forEach(function (form) {
    var btn = form.querySelector('button[type=submit]');
    var label = btn.textContent;

    form.addEventListener('submit', function (ev) {
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
      // Valid: the form now submits normally to its action URL.
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
      btn.innerHTML = '<span class="spinner" aria-hidden="true"></span><span></span>';
      btn.lastChild.textContent = btn.dataset.loading || 'Working…';
    });

    // Restore the button when returning via the back button
    window.addEventListener('pageshow', function () {
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      btn.textContent = label;
    });
  });
})();
