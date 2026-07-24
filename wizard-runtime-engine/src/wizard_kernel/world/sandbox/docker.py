"""DockerSandboxRuntime — real isolation via Docker Desktop on Windows.

Shell-injection fix: cwd is passed via --workdir docker flag, never concatenated
into a shell string. shlex.quote() protects the command in exec_background.
"""
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from wizard_kernel.contracts.tool import CommandResult
from wizard_kernel.contracts.process import BackgroundProcess

_DEFAULT_IMAGE = "python:3.12-slim"


import posixpath


def _safe_workdir(cwd: str) -> str:
    """Resolve cwd to an absolute /workspace/<cwd> path.
    Rejects path traversal attempts before they reach Docker."""
    if not cwd or cwd in (".", "/"):
        return "/workspace"
    # Normalize using posixpath because container paths are always Linux style
    resolved = posixpath.normpath(posixpath.join("/workspace", cwd))
    if resolved != "/workspace" and not resolved.startswith("/workspace/"):
        raise ValueError(f"cwd escapes /workspace: {cwd!r}")
    return resolved


class _DockerBgHandle:
    def __init__(self, handle_id: str, container_id: str,
                 command: str, cwd: str) -> None:
        self.handle_id = handle_id
        self.container_id = container_id
        self.command = command
        self.cwd = cwd

    def snapshot(self, container_id: str) -> BackgroundProcess:
        try:
            # handle_id is our own hex — safe to embed directly
            inspect = subprocess.run(
                ["docker", "exec", container_id, "sh", "-c",
                 f"kill -0 $(cat /tmp/{self.handle_id}.pid 2>/dev/null)"
                 f" 2>/dev/null && echo running || echo stopped"],
                capture_output=True, text=True, timeout=5,
            )
            running = "running" in inspect.stdout

            logs = subprocess.run(
                ["docker", "exec", container_id, "sh", "-c",
                 f"tail -c 32768 /tmp/{self.handle_id}.out 2>/dev/null || true"],
                capture_output=True, text=True, timeout=5,
            )
            err_logs = subprocess.run(
                ["docker", "exec", container_id, "sh", "-c",
                 f"tail -c 8192 /tmp/{self.handle_id}.err 2>/dev/null || true"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:  # noqa: BLE001
            running, logs_out, err_out = False, "", ""
        else:
            logs_out = logs.stdout
            err_out = err_logs.stdout

        return BackgroundProcess(
            handle_id=self.handle_id,
            command=self.command,
            cwd=self.cwd,
            is_running=running,
            stdout_so_far=logs_out,
            stderr_so_far=err_out,
        )


class DockerSandboxRuntime:
    def __init__(self, image: str = _DEFAULT_IMAGE) -> None:
        self._image = image
        self._container_id: str | None = None
        self._workspace: str | None = None
        self._bg: dict[str, _DockerBgHandle] = {}

    def start(self, workspace_path: str) -> None:
        self._workspace = str(Path(workspace_path).resolve())
        result = subprocess.run(
            [
                "docker", "run", "-d",
                "--network", "none",
                "--memory", "512m",
                "--cpus", "1",
                "--read-only",
                "--tmpfs", "/tmp",
                "-v", f"{self._workspace}:/workspace:ro",
                "-w", "/workspace",
                self._image,
                "sleep", "3600",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"docker start failed: {result.stderr.strip()}")
        self._container_id = result.stdout.strip()

    def stop(self) -> None:
        if self._container_id:
            subprocess.run(["docker", "rm", "-f", self._container_id],
                           capture_output=True, timeout=30)
            self._container_id = None
        self._bg.clear()

    def exec(self, command: str, cwd: str = ".", timeout_sec: int = 60) -> CommandResult:
        """Execute a command inside the container.
        cwd is passed via --workdir flag — never concatenated into shell string."""
        assert self._container_id, "call start() first"
        workdir = _safe_workdir(cwd)
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                # FIX: --workdir separates cwd from command — no shell concat
                ["docker", "exec",
                 "--workdir", workdir,
                 self._container_id,
                 "sh", "-c", command],
                capture_output=True, text=True, timeout=timeout_sec,
            )
            ms = (time.monotonic() - t0) * 1000
            return CommandResult(
                ok=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout[:65536],
                stderr=result.stderr[:16384],
                duration_ms=ms,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(ok=False, exit_code=-1, stdout="",
                                 stderr=f"timeout after {timeout_sec}s",
                                 duration_ms=timeout_sec * 1000.0)
        except Exception as exc:  # noqa: BLE001
            return CommandResult(ok=False, exit_code=-1, stdout="",
                                 stderr=str(exc), duration_ms=0.0)

    def read_file(self, path: str, max_bytes: int = 65536) -> bytes:
        """Read via explicit argument list — no shell involved."""
        assert self._container_id
        # head -c with numeric arg, path as separate arg — no shell expansion
        result = subprocess.run(
            ["docker", "exec", self._container_id,
             "head", "-c", str(max_bytes), f"/workspace/{path}"],
            capture_output=True, timeout=30,
        )
        return result.stdout if result.returncode == 0 else b""

    def exec_background(self, command: str, cwd: str = ".") -> BackgroundProcess:
        """Start a long-running process inside the container.
        FIX: cwd via --workdir; command quoted via shlex.quote() for inner sh -c."""
        assert self._container_id
        workdir = _safe_workdir(cwd)
        handle_id = f"proc_{uuid.uuid4().hex[:8]}"
        # shlex.quote() prevents command from breaking out of the inner sh -c
        quoted_cmd = shlex.quote(command)
        bg_cmd = (
            f"nohup sh -c {quoted_cmd} "
            f"> /tmp/{handle_id}.out "
            f"2> /tmp/{handle_id}.err & "
            f"echo $! > /tmp/{handle_id}.pid"
        )
        subprocess.run(
            ["docker", "exec",
             "--workdir", workdir,
             self._container_id,
             "sh", "-c", bg_cmd],
            capture_output=True, timeout=10,
        )
        handle = _DockerBgHandle(handle_id, self._container_id, command, cwd)
        self._bg[handle_id] = handle
        return handle.snapshot(self._container_id)

    def read_process_output(self, handle_id: str) -> BackgroundProcess:
        if handle_id not in self._bg:
            return BackgroundProcess(handle_id=handle_id, command="", cwd="",
                                     is_running=False, exit_code=-1,
                                     stdout_so_far="", stderr_so_far="[handle not found]")
        return self._bg[handle_id].snapshot(self._container_id)

    def kill_process(self, handle_id: str) -> None:
        if handle_id in self._bg and self._container_id:
            subprocess.run(
                ["docker", "exec", self._container_id, "sh", "-c",
                 f"kill $(cat /tmp/{handle_id}.pid 2>/dev/null) 2>/dev/null || true"],
                capture_output=True, timeout=10,
            )
            del self._bg[handle_id]

    def list_processes(self) -> list[BackgroundProcess]:
        return [h.snapshot(self._container_id) for h in self._bg.values()]
