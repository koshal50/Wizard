"""Tool executor — dispatches action dicts to sandbox operations.
No technology-specific knowledge here. All tools return {ok, data, error, meta}."""
import fnmatch
import hashlib
import json
import socket
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path
from wizard_kernel.world.sandbox.base import SandboxRuntime

_REGISTERED_TOOLS = frozenset({
    "list_tree", "read_file", "search_files",
    "execute_command", "check_port", "path_exists",
    "start_process", "read_process", "kill_process", "list_processes",
    # Agentic browser — a browser action is just another tool (opt-in).
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_fill_form", "browser_back", "browser_extract",
    "browser_assertion",
    "http_request",
    "browser_screenshot",
})


class ToolExecutor:
    def __init__(self, sandbox: SandboxRuntime, repo_path: str, browser=None, *, investigation_id=None, private_capture=False) -> None:
        self._sandbox = sandbox
        self._repo = Path(repo_path).resolve()
        self._browser = browser  # BrowserRuntime | None — set only when browser_enabled
        self._investigation_id = investigation_id
        self._private_capture = private_capture

    @property
    def browser(self):
        """The live browser, or None. For narration, never for a plan step.

        Read by the loop when it emits a browser event, so the event can carry
        what the page looks like at that moment. Nothing that reads this is a
        tool: the page a viewer sees is not an Observation and cannot become a
        claim, which is why this is a property on the executor rather than a
        seventh entry in `_REGISTERED_TOOLS`.
        """
        return self._browser

    def execute(self, action: dict, _: str | None = None) -> dict:
        """Main dispatch called from the investigation loop."""
        if getattr(self, 'control', None):
            self.control.check()
        tool = action.get("tool", "")
        params = action.get("params", {})
        if tool not in _REGISTERED_TOOLS:
            return {"ok": False, "error": f"unknown tool: {tool!r}", "data": None, "meta": {}}
        try:
            return getattr(self, f"_tool_{tool}")(**params)
        except Exception as exc:  # noqa: BLE001  — tool failures → payload, not crashes
            return {"ok": False, "error": str(exc), "data": None, "meta": {"tool": tool}}

    # ── Tools ──────────────────────────────────────────────────────────────────

    def _tool_list_tree(self, max_depth: int = 3) -> dict:
        import os
        tree: list[str] = []
        errors = []
        for dirpath, dirnames, filenames in os.walk(self._repo, onerror=errors.append):
            rel = Path(dirpath).relative_to(self._repo)
            if len(rel.parts) >= max_depth:
                dirnames.clear()
                continue
            from wizard_kernel.world.scanner import _SKIP_DIRS
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in _SKIP_DIRS]
            tree.extend((rel / f).as_posix() for f in filenames)
        return {"ok": not errors, "data": {"tree": tree, "count": len(tree), "incomplete": bool(errors)},
                "error": 'Repository listing incomplete: ' + ', '.join(sorted({type(e).__name__ for e in errors})) if errors else None,
                "meta": {}}

    def _tool_read_file(self, path: str, max_bytes: int = 65536) -> dict:
        raw = self._sandbox.read_file(path, max_bytes)
        content = raw.decode("utf-8", errors="replace")
        parsed = None
        if path.endswith(".json"):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                pass
        return {
            "ok": True,
            "data": {"content": content, "parsed": parsed, "path": path, "bytes_read": len(raw),
                     "truncated": len(raw) >= max_bytes},
            "error": None,
            "meta": {"path": path},
        }

    def _tool_search_files(self, pattern: str, glob: str = "**/*") -> dict:
        matches = [
            str(p.relative_to(self._repo))
            for p in self._repo.rglob(glob)
            if fnmatch.fnmatch(p.name, pattern) and p.is_file()
        ]
        return {"ok": True, "data": {"matches": matches[:100], "total": len(matches)},
                "error": None, "meta": {"pattern": pattern, "glob": glob}}

    def _tool_execute_command(self, command: str, cwd: str = ".",
                              timeout_sec: int = 30) -> dict:
        result = self._sandbox.exec(command, cwd, timeout_sec)
        return {
            "ok": result.ok,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
            "error": None if result.ok else (result.stderr or result.stdout or f'Command exited with code {result.exit_code}'),
            "meta": {"command": command},
        }

    def _tool_check_port(self, port: int, host: str = "localhost") -> dict:
        try:
            with socket.create_connection((host, port), timeout=2):
                active = True
        except OSError:
            active = False
        return {"ok": True, "status_code": 200 if active else 0,
                "data": {"active": active, "host": host, "port": port},
                "error": None, "meta": {}}

    def _tool_path_exists(self, path: str) -> dict:
        exists = (self._repo / path).exists()
        return {"ok": True, "exists": exists,
                "data": {"path": path, "exists": exists},
                "error": None, "meta": {}}

    def _tool_http_request(self, url: str, method: str = "GET", body: str | None = None, require_ready: bool = False) -> dict:
        """Make the validated, allow-listed HTTP request and retain a bounded response."""
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        safe_netloc = host + (f":{parsed.port}" if parsed.port else "")
        safe_url = urlunsplit((parsed.scheme, safe_netloc, parsed.path, "", ""))
        timeout = min(10, self.control.remaining()) if getattr(self, 'control', None) else 10
        request = Request(url, data=body.encode("utf-8") if body is not None else None,
                          method=method.upper())
        if body is not None:
            try:
                json.loads(body)
            except (ValueError, TypeError):
                pass
            else:
                request.add_header("Content-Type", "application/json")
        class _NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        try:
            response = build_opener(_NoRedirect).open(request, timeout=timeout)
            status = response.status
            raw = response.read(8193)
        except HTTPError as exc:
            status = exc.code
            raw = exc.read(8193)
        except OSError as exc:
            return {
                "ok": False,
                "data": {"url": safe_url, "method": method.upper(), "status_code": None, "timeout_sec": timeout},
                "error": str(exc)[:500],
                "meta": {"url": safe_url, "method": method.upper()},
            }
        complete = len(raw) <= 8192
        text = raw[:8192].decode("utf-8", errors="replace")
        structured = None
        json_valid = False
        if complete:
            try:
                from wizard_kernel.control.flow_trace import safe_parameters
                structured = safe_parameters({"response": json.loads(text)})["response"]
                json_valid = True
            except (ValueError, TypeError):
                pass
        text = re.sub(r"(?i)(authorization|api[_ -]?key|token|secret|password)(\s*[:=]\s*)[^\s,;]+",
                      r"\1\2[REDACTED]", text)
        return {"ok": True, "data": {"url": safe_url, "method": method.upper(),
                "status_code": status, "body_preview": text[:2000], "body_preview_truncated": not complete or len(text) > 2000, "json_body": structured,
                "body_complete": complete, "json_valid": json_valid, "timeout_sec": timeout}, "error": None,
                "meta": {"url": safe_url, "method": method.upper(), "status_code": status}}

    # ── Background process tools ───────────────────────────────────────────────

    def _tool_start_process(self, command: str, cwd: str = ".") -> dict:
        """Start a long-running process (server, watcher). Returns handle_id."""
        bg = self._sandbox.exec_background(command, cwd)
        return {"ok": True, "data": bg.model_dump(), "error": None,
                "meta": {"handle_id": bg.handle_id}}

    def _tool_read_process(self, handle_id: str) -> dict:
        """Poll a background process — get current output + running status."""
        bg = self._sandbox.read_process_output(handle_id)
        ok = bg.is_running or bg.exit_code == 0
        return {"ok": ok, "data": bg.model_dump(), "is_running": bg.is_running,
                "stdout": bg.stdout_so_far, "stderr": bg.stderr_so_far,
                "error": None if ok else (bg.stderr_so_far or f'Process exited with code {bg.exit_code}'),
                "meta": {"handle_id": handle_id}}

    def _tool_kill_process(self, handle_id: str) -> dict:
        """Terminate a background process."""
        self._sandbox.kill_process(handle_id)
        return {"ok": True, "data": {"killed": handle_id}, "error": None, "meta": {}}

    def _tool_list_processes(self) -> dict:
        """List all running background processes and their status."""
        processes = [p.model_dump() for p in self._sandbox.list_processes()]
        return {"ok": True, "data": {"processes": processes, "count": len(processes)},
                "error": None, "meta": {}}

    # ── Agentic browser tools ────────────────────────────────────────────────
    # A browser action is just another tool: it returns the same {ok,data,error,meta}
    # envelope and any Playwright failure (timeout, missing element) propagates to
    # execute()'s except clause → Observation, never a crash (invariant 4).

    def _browser_ready(self) -> dict | None:
        if self._browser is None:
            return {"ok": False, "error": "browser not enabled for this investigation",
                    "data": None, "meta": {}}
        # Browser capability is provisioned per investigation, but Chromium is
        # launched only when a validated browser action reaches this executor.
        if not getattr(self._browser, "started", True):
            try:
                self._browser.start()
            except Exception as exc:  # noqa: BLE001 — startup failure is an observation
                return {"ok": False, "error": f"browser failed to start: {exc}",
                        "data": None, "meta": {}}
        return None

    def _tool_browser_navigate(self, url: str) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        data = self._browser.navigate(url)
        return {"ok": True, "data": data, "error": None, "meta": {"url": data.get("url")}}

    def _tool_browser_snapshot(self) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        data = self._browser.snapshot()
        return {"ok": True, "data": data, "error": None, "meta": {"url": data.get("url")}}

    def _tool_browser_assertion(self, field: str, operator: str, expected: str) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        data = self._browser.assertion(field, operator, expected)
        matched = data["expected_state_matched"]
        return {"ok": matched, "data": data, "error": None if matched else "Expected page state was not observed",
                "meta": {"url": data.get("url")}}

    def _tool_browser_click(self, selector: str) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        data = self._browser.click(selector)
        # A click can replace the page (for example, a login page's sign-up
        # link). Return the resulting live page schema with the action so the
        # next Explorer decision sees the fields it can actually address.
        if data.get("clicked"):
            try:
                data["page_observation"] = self._browser.snapshot()
            except Exception as exc:  # the click already happened; preserve it
                data["page_observation_error"] = type(exc).__name__
        return {"ok": True, "data": data, "error": None, "meta": {"selector": selector}}

    def _tool_browser_type(self, selector: str, text: str) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        data = self._browser.fill(selector, text)
        if data.get("typed"):
            try:
                data["page_observation"] = self._browser.snapshot()
            except Exception as exc:  # keep the actual fill result intact
                data["page_observation_error"] = type(exc).__name__
        typed = bool(data.get("typed"))
        return {"ok": typed, "data": data,
                "error": None if typed else "Observed field did not retain the requested value",
                "meta": {"selector": selector}}

    def _tool_browser_fill_form(self, fields=None) -> dict:
        """Fill several observed form controls in one validated action.

        `fields` is a list of {"selector": <observed controls[].selector>,
        "text": <value>}. Filling the whole form in one tool call means one
        Explorer decision (one gated model call) instead of one per field —
        which is what left a 4-field signup form unfilled under the per-field
        model. Each field is filled through the SAME BrowserRuntime.fill used by
        browser_type (no second engine); per-field outcomes are captured, a
        value for a password-ish field is never echoed back, and submission is
        NOT performed here — Explorer inspects the result and decides next.
        """
        if (err := self._browser_ready()) is not None:
            return err
        if not isinstance(fields, list) or not fields:
            return {"ok": False, "error": "browser_fill_form requires a non-empty 'fields' list",
                    "data": None, "meta": {}}
        results = []
        all_ok = True
        for item in fields:
            selector = (item or {}).get("selector")
            text = (item or {}).get("text", "")
            secretish = bool(re.search(r"pass|secret|token|otp|cvv", str(selector or ""), re.I))
            if not selector:
                results.append({"selector": selector, "typed": False, "error": "missing selector"})
                all_ok = False
                continue
            try:
                r = self._browser.fill(selector, text)
                typed = bool(r.get("typed"))
                all_ok = all_ok and typed
                results.append({"selector": selector, "typed": typed,
                                # Never echo a secret value back into evidence.
                                "value": ("<redacted>" if secretish else text) if typed else None,
                                "error": None if typed else r.get("error")})
            except Exception as exc:  # noqa: BLE001 — a field failure is data, not a crash
                all_ok = False
                # Playwright locator errors (especially a stale selector) are
                # actionable context for Explorer. Redact the supplied value in
                # case an upstream error happens to echo it, then keep the
                # diagnostic bounded for persistence and the next prompt.
                detail = str(exc).replace(str(text), "[REDACTED]")[:240]
                results.append({"selector": selector, "typed": False,
                                "error": detail or type(exc).__name__})
        data = {"fields": results, "all_filled": all_ok}
        # One fresh snapshot after the batch so the next decision sees the
        # resulting state (and any validation messages) once, not per field.
        try:
            data["page_observation"] = self._browser.snapshot()
        except Exception as exc:  # noqa: BLE001
            data["page_observation_error"] = type(exc).__name__
        # `ok` is the execution result, not merely whether the wrapper ran.
        # A partially filled form must not unlock a planned submit/dependent
        # step; per-field successes remain in data as truthful observations.
        return {"ok": all_ok, "data": data,
                "error": None if all_ok else "one or more observed form fields could not be filled",
                "meta": {"filled": sum(1 for r in results if r["typed"]), "total": len(results)}}

    def _tool_browser_back(self) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        data = self._browser.back()
        return {"ok": True, "data": data, "error": None, "meta": {"url": data.get("url")}}

    def _tool_browser_extract(self) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        data = self._browser.extract()
        return {"ok": True, "data": data, "error": None, "meta": {"url": data.get("url")}}

    def _tool_browser_screenshot(self) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        if self._private_capture:
            return {'ok': False, 'data': None, 'meta': {},
                    'error': 'Screenshot withheld because configured private inputs may be visible'}
        import uuid
        from wizard_kernel.storage import fs_store
        inv_id = self._investigation_id or getattr(getattr(getattr(self, 'control', None), 'inv', None), 'id', None)
        if not inv_id:
            raise RuntimeError('Screenshot capture requires an investigation owner')
        path = fs_store.ensure(inv_id) / f'screenshot_{uuid.uuid4().hex}.png'
        self._browser.screenshot(str(path))
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError('Browser did not capture a screenshot')
        if path.stat().st_size > 10 * 1024 * 1024:
            path.unlink()
            raise RuntimeError('Screenshot exceeded the 10 MB artifact limit')
        image = path.read_bytes()
        if not image.startswith(b'\x89PNG\r\n\x1a\n'):
            path.unlink()
            raise RuntimeError('Browser capture is not a PNG artifact')
        return {'ok': True, 'data': {'path': path.name, 'bytes': len(image),
                'sha256': hashlib.sha256(image).hexdigest(),
                'url': (self._browser.page_view() or {}).get('url')}, 'meta': {}, 'error': None}
