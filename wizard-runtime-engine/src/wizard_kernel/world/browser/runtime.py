"""Small agent-browser CLI adapter; Runtime remains the execution authority."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit


def browser_command():
    executable = shutil.which("agent-browser")
    if not executable:
        raise RuntimeError("agent-browser unavailable; run npm install -g agent-browser and agent-browser install")
    if os.name == "nt":
        native = Path(executable).parent / "node_modules/agent-browser/bin/agent-browser-win32-x64.exe"
        if native.is_file():
            return str(native)
        raise RuntimeError("agent-browser native Windows binary is unavailable")
    return executable


class BrowserRuntime:
    def __init__(self, *, backend="local", cdp_url=None, headless=True,
                 nav_timeout_ms=15000, action_timeout_ms=8000, allowed_domains=None):
        if backend != "local" or cdp_url:
            raise ValueError("agent-browser uses isolated local sessions; external CDP cannot preserve this egress policy")
        self._headless = headless
        self._allowed = tuple(allowed_domains or [])
        self._timeout = max(nav_timeout_ms, action_timeout_ms)
        self._session = "wizard-" + uuid.uuid4().hex
        self._directory = None
        self._command = None
        self._started = False
        self._refs = {}
        self._last_snapshot = None

    @property
    def started(self):
        return self._started

    def start(self):
        if self._started:
            return
        if not self._allowed:
            raise ValueError("Browser allowed_domains is empty; navigation is blocked")
        self._command = browser_command()
        self._directory = tempfile.TemporaryDirectory(prefix="wizard-browser-")
        config = {}
        local_browsers = Path(sys.prefix) / "browser-home" / ".agent-browser" / "browsers"
        chrome = next(local_browsers.glob("chrome-*/chrome.exe"), None)
        if chrome is not None:
            config["executablePath"] = str(chrome)
        (Path(self._directory.name) / "config.json").write_text(json.dumps(config), encoding="utf-8")
        self._started = True  # CLI available; actual Chrome starts on accepted navigation.

    def _run(self, *args, input=None):
        if not self._started:
            raise RuntimeError("Browser is not started")
        # No model/provider credentials or user browser overrides enter the daemon.
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            "PATH", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE", "APPDATA",
            "LOCALAPPDATA", "TEMP", "TMP", "TMPDIR", "COMSPEC"}}
        env["AGENT_BROWSER_DEFAULT_TIMEOUT"] = str(self._timeout)
        argv = [self._command, "--session", self._session, "--config",
                str(Path(self._directory.name) / "config.json"), "--json",
                "--headed", "false" if self._headless else "true",
                "--allowed-domains", ",".join(self._allowed), *args]
        # Daemon startup may inherit handles on Windows. Output files prevent
        # communicate() waiting forever for an inherited pipe's EOF.
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output, tempfile.TemporaryFile(mode="w+", encoding="utf-8") as error:
            try:
                result = subprocess.run(argv, input=input, stdout=output, stderr=error, text=True,
                                        encoding="utf-8", errors="replace", env=env,
                                        cwd=str(Path.home()), timeout=self._timeout / 1000 + 15,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("agent-browser command exceeded its bounded timeout") from exc
            output.seek(0)
            raw = output.read()
        try:
            envelope = json.loads(raw)
        except ValueError as exc:
            raise RuntimeError("agent-browser returned no valid JSON result") from exc
        if isinstance(envelope, list):
            failures = [item for item in envelope if not isinstance(item, dict) or not item.get("success")]
            if result.returncode or failures:
                raise RuntimeError("agent-browser batch operation failed")
            return [item.get("data") for item in envelope]
        if result.returncode or not envelope.get("success"):
            # Never echo argv, stdin, field values or raw daemon logs.
            detail = str(envelope.get("error") or "Browser command failed")
            from wizard_kernel.control.flow_trace import safe_text
            raise RuntimeError(safe_text(detail))
        return envelope.get("data") or {}

    def _eval(self, script):
        data = self._run("eval", "--stdin", input=script)
        return data.get("result") if isinstance(data, dict) else data

    def stop(self):
        if not self._started:
            return
        try:
            self._run("close")  # Only this investigation's session, never --all.
        finally:
            self._started = False
            self._refs = {}
            if self._directory:
                self._directory.cleanup()
                self._directory = None

    def navigate(self, url):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError("Invalid browser target")
        if not any(parsed.hostname == d or (parsed.hostname or "").endswith("." + d) for d in self._allowed):
            raise ValueError("Browser target is outside allowed_domains")
        self._refs = {}
        self._last_snapshot = None
        result = self._run("open", url)
        return {"url": result.get("url", url), "title": result.get("title", "")}

    def snapshot(self):
        data = self._run("snapshot")
        self._refs = {"@" + key.lstrip("@"): value for key, value in (data.get("refs") or {}).items()}
        # Actual DOM facts supplement CLI refs; no values or HTML transcript.
        state = self._eval(r"""(() => ({url:location.href,title:document.title,
            links:Array.from(document.querySelectorAll('a[href]')).map(a=>({text:a.innerText,href:a.href})),
            text:(document.body?.innerText || '').slice(0,8000),
            text_truncated:(document.body?.innerText || '').length>8000,
            control_states:Array.from(document.querySelectorAll('input,textarea,select,button,a[href],[role]')).map(e=>({
              role:e.getAttribute('role') || (e.tagName==='BUTTON' || ['submit','button'].includes(e.type) ? 'button' : e.tagName==='A' ? 'link' : e.tagName==='SELECT' ? 'combobox' : e.type==='checkbox' ? 'checkbox' : e.type==='radio' ? 'radio' : e.type==='number' ? 'spinbutton' : e.type==='search' ? 'searchbox' : 'textbox'),
              name:e.getAttribute('aria-label') || (e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' ').trim() || Array.from(e.labels||[]).map(l=>l.textContent.trim()).join(' ') || e.getAttribute('placeholder') || e.innerText?.trim() || '',
              visible:Boolean(e.getClientRects().length) && getComputedStyle(e).visibility!=='hidden' && getComputedStyle(e).display!=='none',
              enabled:!e.matches(':disabled') && e.getAttribute('aria-disabled')!=='true'})),
            inputs:Array.from(document.querySelectorAll('input,textarea')).filter(e=>!e.disabled && e.type!=='hidden').map(e=>({
              name:e.getAttribute('aria-label') || (e.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' ').trim() || Array.from(e.labels||[]).map(l=>l.textContent.trim()).join(' ') || e.getAttribute('placeholder') || '',
              filled:Boolean(e.value),required:e.required})),
            submit_names:Array.from(document.querySelectorAll('button,input[type=submit]')).filter(b=>b.form && b.type==='submit').map(b=>b.getAttribute('aria-label')||b.innerText||b.value||'')}))()""") or {}
        controls = [{"selector": ref, "role": item.get("role", ""), "name": item.get("name", "")}
                    for ref, item in self._refs.items()]
        for control in controls:
            matches = [item for item in state.get("control_states", [])
                       if item["role"] == control["role"] and item["name"] == control["name"]]
            if len(matches) == 1:
                control.update(visible=matches[0]["visible"], enabled=matches[0]["enabled"])
            control["submits_form"] = control["role"] == "button" and control["name"] in state.get("submit_names", [])
            if control["role"] in {"textbox", "searchbox", "spinbutton"}:
                matches = [item for item in state.get("inputs", []) if item["name"] == control["name"]]
                if len(matches) == 1:
                    control.update(filled=matches[0]["filled"], required=matches[0]["required"])
        state.pop("submit_names", None)
        state.pop("inputs", None)
        state.pop("control_states", None)
        result = {**state, "snapshot": data.get("snapshot", ""), "controls": controls,
                  "node_count": len(controls), "controls_complete": not bool(data.get("truncated")),
                  "snapshot_truncated": bool(data.get("truncated"))}
        self._last_snapshot = result
        return result

    def _observed(self, selector):
        if selector not in self._refs:
            raise ValueError("STALE_BROWSER_REF: use a ref from the current agent-browser snapshot")
        return self._refs[selector]

    def click(self, selector):
        self._observed(selector)
        before = self._last_snapshot or {}
        # A submit event records the attempted operation, not application success.
        # Optional empty controls must not erase a real submission.
        self._eval("""(() => {window.__wizardSubmission=false;sessionStorage.removeItem("__wizardSubmission");
          if(!window.__wizardSubmitListener){document.addEventListener('submit',e=>{
            window.__wizardSubmission=e.target instanceof HTMLFormElement;
            if(window.__wizardSubmission)sessionStorage.setItem('__wizardSubmission','true');
          },true);window.__wizardSubmitListener=true;}return true;})()""")
        self._run("click", selector)
        submitted = bool(self._eval("Boolean(window.__wizardSubmission || sessionStorage.getItem('__wizardSubmission'))"))
        self._refs = {}
        after = self.snapshot()
        return {"selector": selector, "clicked": True, "submitted_form": submitted,
                "url": after.get("url"), "effect": _effect(before, after), "page_observation": after}

    def fill(self, selector, text):
        self._observed(selector)
        # Stdin batch keeps credential values out of process arguments/logs.
        try:
            self._run("batch", "--bail", input=json.dumps([["fill", selector, text]]))
            observed = self._run("get", "value", selector)
        except RuntimeError as exc:
            raise RuntimeError(str(exc).replace(text, "[REDACTED]") if text else str(exc)) from exc
        return {"selector": selector, "typed": observed.get("value") == text}

    def back(self):
        self._run("back")
        self._refs = {}
        return self.snapshot()

    def extract(self):
        return self.snapshot()

    def page_state(self):
        return self.snapshot()

    def page_view(self):
        return self._last_snapshot

    def assertion(self, field, operator, expected):
        if field not in {"url", "title", "snapshot", "text"} or operator not in {"equals", "contains", "not_contains"}:
            raise ValueError("Unsupported browser assertion")
        # Condition-based wait, never a fixed readiness delay. Final verdict is
        # always computed from the returned actual URL/title/ARIA snapshot.
        expression = "location.href" if field == "url" else "document.title" if field == "title" else "document.body.innerText"
        value = json.dumps(expected)
        condition = f"({expression}) === {value}" if operator == "equals" else f"({expression}).includes({value})"
        if operator == "not_contains":
            condition = "!(" + condition + ")"
        try:
            self._run("wait", "--fn", condition)
        except RuntimeError:
            pass  # A failed wait is not proof; actual state below decides.
        result = self.snapshot()
        actual = str(result.get(field) or "")
        matched = actual == expected if operator == "equals" else expected in actual
        if operator == "not_contains":
            matched = not matched
        return {**result, "expected_state_matched": matched}

    def screenshot(self, path):
        return self._run("screenshot", str(path))

_VIEW_CONTROL_KEYS = ("role", "name", "selector", "disabled", "visible", "value",
                      "input_type")


def _control_shape(controls: list[dict]) -> list[tuple]:
    """What the page offers, as a value two readings can be compared on.

    Every key of `_VIEW_CONTROL_KEYS` except `value` — the one key that moves for
    a reason that is not a response. Kept as tuples in DOM order rather than a
    set, because the order controls appear in is part of what the page is, and a
    count alone would call two entirely different pages the same.

    A missing key becomes `None` rather than being dropped, so two controls that
    differ only by a key one of them omits do not compare equal.
    """
    return [
        tuple(c.get(k) for k in _VIEW_CONTROL_KEYS if k != "value")
        for c in controls
        if isinstance(c, dict)
    ]


def _effect(before: dict, after: dict) -> str:
    """Whether an interaction changed the page: "changed" or "unchanged".

    This is the difference between *operating* an app and *walking* it. A walk
    records that a control was pressed; this records what pressing it did, and
    "nothing" is a real answer — a button wired to nothing, a form that rejects
    its own submit, a tab that does not switch. An action that always reported
    success would make all three look like a working app, which is the failure
    mode this whole plane exists to avoid.

    Compared on url + title + node count + the page's control set, and the
    control set is what makes this answer the question it claims to. The first
    three say the page became a *different* page; a page that responds without
    navigating keeps all three and still offers something new, and calling that
    "unchanged" is how a run that visibly worked came out looking inert. Read
    without `value` — see `_state` — because a field always holds what it was
    just typed into, and counting that as a response would make an inert box and
    a working one identical.

    Text is deliberately still absent from the fingerprint: text moves when a
    counter ticks, and a page that reformats what it already shows has not done
    anything a reader would call an effect. The control set does not tick — it
    changes when the page offers something different to press.
    """
    if before == after:
        return "unchanged"
    for key in ("url", "title", "node_count", "controls"):
        if before.get(key) != after.get(key):
            return "changed"
    return "unchanged"
