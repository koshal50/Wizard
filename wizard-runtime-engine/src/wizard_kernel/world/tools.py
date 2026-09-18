"""Tool executor — dispatches action dicts to sandbox operations.
No technology-specific knowledge here. All tools return {ok, data, error, meta}."""
import fnmatch
import json
import socket
from pathlib import Path
from wizard_kernel.world.sandbox.base import SandboxRuntime

_REGISTERED_TOOLS = frozenset({
    "list_tree", "read_file", "search_files",
    "execute_command", "check_port", "path_exists",
    "start_process", "read_process", "kill_process", "list_processes",
    # Agentic browser — a browser action is just another tool (opt-in).
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_back", "browser_extract",
})


class ToolExecutor:
    def __init__(self, sandbox: SandboxRuntime, repo_path: str, browser=None) -> None:
        self._sandbox = sandbox
        self._repo = Path(repo_path).resolve()
        self._browser = browser  # BrowserRuntime | None — set only when browser_enabled

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
        for dirpath, dirnames, filenames in os.walk(self._repo):
            rel = Path(dirpath).relative_to(self._repo)
            if len(rel.parts) >= max_depth:
                dirnames.clear()
                continue
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            tree.extend(str(rel / f) for f in filenames)
        return {"ok": True, "data": {"tree": tree, "count": len(tree)},
                "error": None, "meta": {}}

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
            "data": {"content": content, "parsed": parsed, "path": path, "bytes_read": len(raw)},
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
            "error": None,
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

    # ── Background process tools ───────────────────────────────────────────────

    def _tool_start_process(self, command: str, cwd: str = ".") -> dict:
        """Start a long-running process (server, watcher). Returns handle_id."""
        bg = self._sandbox.exec_background(command, cwd)
        return {"ok": True, "data": bg.model_dump(), "error": None,
                "meta": {"handle_id": bg.handle_id}}

    def _tool_read_process(self, handle_id: str) -> dict:
        """Poll a background process — get current output + running status."""
        bg = self._sandbox.read_process_output(handle_id)
        return {"ok": True, "data": bg.model_dump(), "is_running": bg.is_running,
                "stdout": bg.stdout_so_far, "stderr": bg.stderr_so_far,
                "error": None, "meta": {"handle_id": handle_id}}

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

    def _tool_browser_click(self, selector: str) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        data = self._browser.click(selector)
        return {"ok": True, "data": data, "error": None, "meta": {"selector": selector}}

    def _tool_browser_type(self, selector: str, text: str) -> dict:
        if (err := self._browser_ready()) is not None:
            return err
        data = self._browser.fill(selector, text)
        return {"ok": True, "data": data, "error": None, "meta": {"selector": selector}}

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
