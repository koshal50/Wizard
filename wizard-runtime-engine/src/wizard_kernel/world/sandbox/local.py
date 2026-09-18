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
    """The ambient environment reduced to the variables a command needs to run.

    The comparison is case-insensitive on purpose. Windows upper-cases the keys
    of ``os.environ``, so a whitelist entry spelled "SystemRoot" never matches
    the key the platform hands back ("SYSTEMROOT") — while "COMSPEC", spelled
    upper-case on both sides, survives by luck. Dropping SystemRoot is not a
    cosmetic loss: without it a process cannot create a listening socket, so
    every test that binds a port dies with `listen UNKNOWN: unknown error`,
    inside the sandbox only. The investigation then reports a working project as
    broken, and the fault is in here rather than in the project.
    """
    wanted = {name.upper() for name in _SAFE_ENV}
    return {k: v for k, v in os.environ.items() if k.upper() in wanted}


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
        import sys
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
        else:
            try:
                import os, signal
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except Exception:
                pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            self.proc.kill()


class LocalProcessRuntime:
    def __init__(self) -> None:
        self._workspace: Path | None = None
        self._bg: dict[str, _BackgroundHandle] = {}

    def start(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path).resolve()

    def stop(self) -> None:
        for handle in list(self._bg.values()):
            handle.kill()
        self._bg.clear()
        self._workspace = None

    # ── Blocking exec ─────────────────────────────────────────────────────────

    def exec(self, command: str, cwd: str = ".", timeout_sec: int = 30) -> CommandResult:
        assert self._workspace, "call start() first"
        work_cwd = self._safe_cwd(cwd)
        env = _safe_env()
        t0 = time.monotonic()
        kwargs: dict = {}
        if sys.platform != "win32":
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
            try:
                stdout, stderr = proc.communicate(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                   capture_output=True)
                else:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except OSError:
                        pass
                proc.kill()
                proc.communicate()
                return CommandResult(ok=False, exit_code=-1, stdout="",
                                     stderr=f"timeout after {timeout_sec}s",
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

    # ── File access ───────────────────────────────────────────────────────────

    def read_file(self, path: str, max_bytes: int = 65536) -> bytes:
        assert self._workspace
        fpath = (self._workspace / path).resolve()
        fpath.relative_to(self._workspace)  # path traversal guard
        try:
            with open(fpath, "rb") as f:
                return f.read(max_bytes)
        except OSError:
            return b""

    # ── Background process management ─────────────────────────────────────────

    def exec_background(self, command: str, cwd: str = ".") -> BackgroundProcess:
        """Start a long-running process (server, watcher, etc.) in the background.
        Returns immediately with a handle. Use read_process_output() to poll output."""
        assert self._workspace, "call start() first"
        work_cwd = self._safe_cwd(cwd)
        env = _safe_env()
        kwargs: dict = {}
        if sys.platform != "win32":
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            command, shell=True, cwd=work_cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            # Same decoder as exec(): a background server logs UTF-8 too, and a
            # reader thread that dies on it would silently stop capturing.
            encoding="utf-8", errors="replace", bufsize=1, **kwargs
        )
        handle_id = f"proc_{uuid.uuid4().hex[:8]}"
        self._bg[handle_id] = _BackgroundHandle(handle_id, proc, command, str(work_cwd))
        return self._bg[handle_id].snapshot()

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
