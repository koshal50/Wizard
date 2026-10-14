"""LocalProcessRuntime — subprocess-based sandbox for dev and unit tests.
NOT secure isolation. Never claim full isolation in demos or reports.

Background process support: each exec_background() spawns a real subprocess
with stdout/stderr captured via pipes. Output is read on demand. Multiple
background processes run concurrently (each in its own OS process)."""
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from wizard_kernel.contracts.tool import CommandResult
from wizard_kernel.contracts.process import BackgroundProcess

_SAFE_ENV: frozenset[str] = frozenset({
    "PATH", "HOME", "USERPROFILE", "TEMP", "TMP",
    "SystemRoot", "COMSPEC", "LANG", "LC_ALL",
})


def _safe_env() -> dict[str, str]:
    """The ambient environment a sandboxed command runs with.

    On Windows the whitelist approach is abandoned: Node/npm/`concurrently` spawn
    sub-commands through `cmd.exe`, and locating it needs a cluster of Windows
    variables (ComSpec, SystemRoot, PATH, PATHEXT, SystemDrive, windir, APPDATA,
    LOCALAPPDATA, …) with their original casing. A reduced set dropped enough of
    them that every `npm run` script which shells out died with
    `spawn cmd.exe ENOENT` (-4058) — so the app never actually started, a signup
    POST hit no backend, and the run looked "broken" when the fault was here.
    The local sandbox is a dev runtime, not an isolation boundary, so passing the
    full environment is the correct, robust choice on Windows.

    On POSIX the whitelist stays: the comparison is case-insensitive because the
    platform's env casing differs from the whitelist's (e.g. SystemRoot).
    """
    if os.name == "nt":
        env = dict(os.environ)
        _ensure_windows_system_path(env)
        return env
    wanted = {name.upper() for name in _SAFE_ENV}
    return {k: v for k, v in os.environ.items() if k.upper() in wanted}


def _ensure_windows_system_path(env: dict[str, str]) -> None:
    """Guarantee the Windows system dirs are on PATH so `cmd.exe` resolves.

    `concurrently` and npm workspace scripts spawn `cmd.exe` by PATH lookup. When
    Wizard is launched from a shell whose PATH omits System32 (a Git-Bash-style
    PATH is the common case), that spawn fails with `spawn cmd.exe ENOENT` and no
    `npm run` script that shells out can start — the app never boots and the run
    blocks. COMSPEC being set is not enough: Node searches PATH for a bare
    `cmd.exe`. Derive the system dirs from SystemRoot / windir / COMSPEC (never a
    hardcoded drive) and prepend any that are missing, case-insensitively, under
    whatever casing the PATH key already uses.
    """
    root = (env.get("SystemRoot") or env.get("SYSTEMROOT") or env.get("windir")
            or env.get("WINDIR"))
    if not root:
        comspec = env.get("COMSPEC") or env.get("ComSpec")
        if comspec:
            # …\System32\cmd.exe → …  (the Windows root is two levels up)
            root = os.path.dirname(os.path.dirname(comspec))
    if not root:
        return
    system32 = os.path.join(root, "System32")
    needed = [system32, root, os.path.join(system32, "Wbem"),
              os.path.join(system32, "WindowsPowerShell", "v1.0")]
    # Find the PATH key under its actual casing (Windows usually "Path").
    path_key = next((k for k in env if k.upper() == "PATH"), "PATH")
    current = env.get(path_key, "")
    parts = current.split(os.pathsep) if current else []
    have = {p.rstrip("\\/").lower() for p in parts if p}
    missing = [d for d in needed if d.rstrip("\\/").lower() not in have and os.path.isdir(d)]
    if missing:
        env[path_key] = os.pathsep.join(missing + parts) if parts else os.pathsep.join(missing)

def _terminate_process(proc):
    if proc.poll() is not None:
        return
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True, timeout=4)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.kill()
    proc.wait(timeout=1)


class _BackgroundHandle:
    """Internal state for one background process."""
    def __init__(self, handle_id: str, proc: subprocess.Popen,
                 command: str, cwd: str) -> None:
        self.handle_id = handle_id
        self.proc = proc
        self.command = command
        self.cwd = cwd
        self._stdout_buf: list[str] = []
        self._stderr_buf: list[str] = []
        self._lock = threading.Lock()
        # Reader threads so output doesn't block
        self._t_out = threading.Thread(target=self._read_stdout, daemon=True)
        self._t_err = threading.Thread(target=self._read_stderr, daemon=True)
        self._t_out.start()
        self._t_err.start()

    def _read_stdout(self) -> None:
        for line in iter(self.proc.stdout.readline, ""):
            with self._lock:
                self._stdout_buf.append(line)

    def _read_stderr(self) -> None:
        for line in iter(self.proc.stderr.readline, ""):
            with self._lock:
                self._stderr_buf.append(line)

    def snapshot(self) -> BackgroundProcess:
        with self._lock:
            stdout = "".join(self._stdout_buf)
            stderr = "".join(self._stderr_buf)
        running = self.proc.poll() is None
        return BackgroundProcess(
            handle_id=self.handle_id,
            command=self.command,
            cwd=self.cwd,
            pid=self.proc.pid,
            is_running=running,
            exit_code=self.proc.returncode,
            stdout_so_far=stdout[-32768:],   # cap at 32KB
            stderr_so_far=stderr[-8192:],
        )

    def kill(self) -> None:
        _terminate_process(self.proc)


class LocalProcessRuntime:
    def __init__(self) -> None:
        self._workspace: Path | None = None
        self._bg: dict[str, _BackgroundHandle] = {}
        self._resource_lock = threading.RLock()
        self._closed = False
        self.deadline_at = None
        self._foreground: dict[int, subprocess.Popen] = {}

    def start(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path).resolve()

    def stop(self) -> None:
        with self._resource_lock:
            self._closed = True
            handles = list(self._bg.values())
            self._bg.clear()
            self._workspace = None
            foreground = list(self._foreground.values())
        processes = foreground + [handle.proc for handle in handles]
        errors = []
        def terminate(proc):
            try:
                _terminate_process(proc)
            except Exception as exc:
                errors.append(exc)
        if sys.platform == 'win32' and len(processes) > 1:
            # Concurrent taskkill instances contend while enumerating Windows
            # process trees. Kill all owned trees in one bounded invocation.
            def terminate_owned_trees():
                try:
                    args = ['taskkill', '/F', '/T']
                    for proc in processes:
                        if proc.poll() is None:
                            args.extend(['/PID', str(proc.pid)])
                    if len(args) > 3:
                        subprocess.run(args, capture_output=True, timeout=4)
                    wait_deadline = time.monotonic() + 1
                    for proc in processes:
                        if proc.poll() is None:
                            proc.kill()
                        proc.wait(timeout=max(.001, wait_deadline - time.monotonic()))
                except Exception as exc:
                    errors.append(exc)
            workers = [threading.Thread(target=terminate_owned_trees, daemon=True)]
        else:
            workers = [threading.Thread(target=terminate, args=(proc,), daemon=True) for proc in processes]
        for worker in workers:
            worker.start()
        deadline = time.monotonic() + 5
        for worker in workers:
            worker.join(max(0, deadline - time.monotonic()))
        if errors or any(proc.poll() is None for proc in processes):
            raise RuntimeError('Some investigation processes could not be terminated')

    # ── Blocking exec ─────────────────────────────────────────────────────────

    def exec(self, command: str, cwd: str = ".", timeout_sec: int = 30) -> CommandResult:
        timeout_sec = self._remaining(timeout_sec)
        assert self._workspace, "call start() first"
        work_cwd = self._safe_cwd(cwd)
        env = _safe_env()
        t0 = time.monotonic()
        kwargs: dict = {}
        if sys.platform == "win32":
            # Captured stdout is insufficient: npm/cmd can mutate the inherited
            # console title directly. Do not attach investigation children to TUI.
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(
                command, shell=True, cwd=work_cwd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                # Command output is arbitrary bytes, and the locale codec is not
                # a decoder for it: on Windows the default is cp1252, which
                # raises on the UTF-8 box-drawing and tick characters that test
                # runners emit by default. The reader thread died mid-read,
                # communicate() came back as (None, None), and the failure
                # surfaced as "'NoneType' object is not subscriptable" — a
                # message about this file, reported as the project's error. A
                # replacement character in a log is a far smaller loss than
                # losing the log.
                encoding="utf-8", errors="replace", env=env, **kwargs
            )
            with self._resource_lock:
                if self._closed:
                    proc.kill()
                    raise RuntimeError('Investigation stopped before command execution')
                self._foreground[proc.pid] = proc
            try:
                stdout, stderr = proc.communicate(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                _terminate_process(proc)
                stdout, stderr = proc.communicate(timeout=1)
                return CommandResult(ok=False, exit_code=-1, stdout=stdout[:65536],
                                     stderr=f"timeout after {timeout_sec}s; {stderr[-4000:]}",
                                     duration_ms=timeout_sec * 1000.0)

            ms = (time.monotonic() - t0) * 1000
            return CommandResult(
                ok=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=stdout[:65536],
                stderr=stderr[:16384],
                duration_ms=ms,
            )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(ok=False, exit_code=-1, stdout="",
                                 stderr=str(exc), duration_ms=0.0)
        finally:
            if 'proc' in locals():
                with self._resource_lock:
                    self._foreground.pop(proc.pid, None)

    # ── File access ───────────────────────────────────────────────────────────

    def read_file(self, path: str, max_bytes: int = 65536) -> bytes:
        assert self._workspace
        fpath = (self._workspace / path).resolve()
        fpath.relative_to(self._workspace)  # path traversal guard
        with open(fpath, "rb") as f:
            return f.read(max_bytes)

    # ── Background process management ─────────────────────────────────────────

    def exec_background(self, command: str, cwd: str = ".") -> BackgroundProcess:
        """Start a long-running process (server, watcher, etc.) in the background.
        Returns immediately with a handle. Use read_process_output() to poll output."""
        self._remaining(1)
        if self._closed:
            raise RuntimeError('Investigation process session is closed')
        assert self._workspace, "call start() first"
        work_cwd = self._safe_cwd(cwd)
        env = _safe_env()
        kwargs: dict = {}
        if sys.platform == "win32":
            # Captured stdout is insufficient: npm/cmd can mutate the inherited
            # console title directly. Do not attach investigation children to TUI.
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            command, shell=True, cwd=work_cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            # Same decoder as exec(): a background server logs UTF-8 too, and a
            # reader thread that dies on it would silently stop capturing.
            encoding="utf-8", errors="replace", bufsize=1, **kwargs
        )
        handle_id = f"proc_{uuid.uuid4().hex[:8]}"
        handle = _BackgroundHandle(handle_id, proc, command, str(work_cwd))
        with self._resource_lock:
            if self._closed:
                handle.kill()
                raise RuntimeError('Investigation ended while starting process')
            self._bg[handle_id] = handle
        return handle.snapshot()

    def _remaining(self, timeout):
        if self.deadline_at is None:
            return timeout
        from datetime import datetime, timezone
        remaining = (self.deadline_at - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise TimeoutError('Investigation deadline reached')
        return min(timeout, remaining)

    def read_process_output(self, handle_id: str) -> BackgroundProcess:
        """Poll current status + buffered output of a background process."""
        if handle_id not in self._bg:
            return BackgroundProcess(
                handle_id=handle_id, command="", cwd="",
                is_running=False, exit_code=-1,
                stdout_so_far="", stderr_so_far="[handle not found]",
            )
        return self._bg[handle_id].snapshot()

    def kill_process(self, handle_id: str) -> None:
        """Terminate a specific background process."""
        if handle_id in self._bg:
            self._bg[handle_id].kill()
            del self._bg[handle_id]

    def list_processes(self) -> list[BackgroundProcess]:
        """List all background processes and their current status."""
        return [h.snapshot() for h in self._bg.values()]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _safe_cwd(self, cwd: str) -> Path:
        resolved = (self._workspace / cwd).resolve()
        resolved.relative_to(self._workspace)  # raises ValueError if outside
        return resolved
