"""Start/adopt one Runtime service; capture its logs and stop only owned children."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

# How long to wait for a service we started to answer /health. The kernel
# imports the whole world (Playwright, FastAPI, storage) before it serves, so
# the first start on a cold machine is genuinely slow; 40s is generous but not
# unbounded — a service that cannot come up in 40s is broken, not slow.
START_TIMEOUT_S = 40.0
HEALTH_INTERVAL_S = 0.4


@dataclass(frozen=True)
class ServiceSpec:
    """How to find, start, and recognise one service.

    Attributes:
        key: Short name used in reports ("kernel").
        label: Human-readable name for the TUI.
        port: The port it listens on.
        health_path: Path that answers a liveness probe.
        cwd: Directory to start it from, relative to the repo root.
        argv: Command to start it, or None when it cannot be started here.
        needs: What the machine must have for `argv` to work (checked on PATH).
        why_unstartable: Why `argv` is None, phrased for the user.
    """

    key: str
    label: str
    port: int
    health_path: str
    cwd: str
    argv: tuple[str, ...] | None
    env: dict[str, str] | None = None
    needs: tuple[str, ...] = ()
    why_unstartable: str = ""


@dataclass
class ServiceState:
    """The outcome for one service, and the evidence for it.

    Attributes:
        spec: Which service this is.
        status: "adopted" | "started" | "unavailable".
        detail: Why — the real error, or where it was found.
        process: The child we own, when we started it. None for adopted.
    """

    spec: ServiceSpec
    status: str
    detail: str = ""
    process: "subprocess.Popen | None" = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.status in ("adopted", "started")


def repo_root() -> Path:
    """The wizard repo root — the directory holding all four modules.

    Resolved from this file's location (wizard/cli/tui/services.py) rather than
    from cwd: the TUI is launched from wherever the user happens to be, and the
    services live at fixed places relative to the code.
    """
    return Path(__file__).resolve().parents[3]


def _python() -> str:
    """The interpreter to start Python services with — the running one.

    sys.executable, not "python": the kernel needs Playwright and FastAPI,
    which are installed in the same venv that is running this code. A bare
    "python" from PATH can resolve to a different interpreter with neither.
    """
    return sys.executable


def _kernel_python() -> str:
    """Use the Runtime Engine environment when it exists.

    The CLI may be installed with a different interpreter from the Runtime's
    optional browser dependencies. Keep Planner/agent startup on the CLI
    interpreter, but launch the kernel with its existing project environment.
    """
    venv_python = repo_root() / "wizard-runtime-engine" / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    return str(venv_python) if venv_python.is_file() else _python()


def _workspace_build_id(root: Path) -> str:
    """Fingerprint the three service source trees so stale adopted workers fail closed."""
    digest = hashlib.sha256()
    source_roots = (
        root / "wizard-runtime-engine" / "src",
        root / "wizard-investigation-planner" / "src",
        root / "wizard_agents" / "wizard_agents" / "app",
    )
    for source_root in source_roots:
        if not source_root.is_dir():
            continue
        for path in sorted((*source_root.rglob("*.py"), *source_root.rglob("*.ts"))):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:20]


def build_specs(root: Path | None = None) -> list[ServiceSpec]:
    """Normal investigations run in one Runtime service with one model transport."""
    root = root or repo_root()
    build_id = _workspace_build_id(root)
    runtime_env = os.environ.copy()
    configured = {}
    # Only explicitly supported configuration enters Runtime from root .env.
    # Test input values remain in Runtime; prompts receive reference names only.
    try:
        from dotenv import dotenv_values
        configured = dotenv_values(root / ".env", interpolate=False)
        for name in ("CEREBRAS_KEY", "WIZARD_TEST_DATA_JSON", "WIZARD_ALLOW_DISPOSABLE_LOCAL_ACCOUNTS"):
            if not runtime_env.get(name) and configured.get(name):
                runtime_env[name] = configured[name]
    except OSError:
        pass
    runtime_env.update({
        "WIZARD_BUILD_ID": build_id,
        "WIZARD_LLM_MODEL": "gpt-oss-120b",
        "WIZARD_LLM_BASE_URL": "https://api.cerebras.ai",
        "WIZARD_CEREBRAS_GATE_DB": str(root / ".wizard" / "cerebras-rate-gate.sqlite3"),
        "PYTHONPATH": os.pathsep.join(filter(None, (
            str(root / "wizard-runtime-engine" / "src"), os.environ.get("PYTHONPATH", "")))),
    })
    # Website development is optional, never a prerequisite for local verification.
    account_specs = build_account_specs(root) if runtime_env.get(
        "WIZARD_ACCOUNT_AUTOSTART", configured.get("WIZARD_ACCOUNT_AUTOSTART")) == "1" else []
    return [ServiceSpec(
        key="kernel", label="Runtime Engine", port=8080, health_path="/health",
        cwd=str(root / "wizard-runtime-engine"),
        argv=(_kernel_python(), "-m", "uvicorn", "wizard_kernel.main:app",
              "--host", "127.0.0.1", "--port", "8080"),
        env=runtime_env, needs=("uvicorn",),
        why_unstartable="uvicorn is not importable by this interpreter",
    ), *account_specs]


def build_account_specs(root: Path | None = None) -> list[ServiceSpec]:
    """Manage the local website stack; remote account services stay external."""
    from urllib.parse import urlsplit
    from dotenv import dotenv_values

    root = root or repo_root()
    configured = dotenv_values(root / ".env", interpolate=False)
    url = os.environ.get("WIZARD_ACCOUNT_URL", configured.get("WIZARD_ACCOUNT_URL") or "")
    local = os.environ.get("WIZARD_ACCOUNT_LOCAL_DEV", configured.get("WIZARD_ACCOUNT_LOCAL_DEV"))
    parsed = urlsplit(url)
    if local != "1" or parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        return []
    port = parsed.port or 80
    if port not in {3000, 8090}:
        return []
    launcher = root / "backend" / "scripts" / "start-local-account-backend.ps1"
    backend = ServiceSpec(
        key="account", label="Account service", port=8090, health_path="/health",
        cwd=str(root),
        argv=("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
              str(launcher), "-PublicOrigin", url.rstrip("/")) if os.name == "nt" and launcher.is_file() else None,
        why_unstartable="Local account service launcher is unavailable",
    )
    if port == 8090:
        return [backend]
    website_root = next((p for p in (root.parent / "wizar-web", root.parent / "Wizard-web")
                         if (p / "wizardsite").is_dir()), root.parent / "wizar-web")
    website = Path(os.environ.get("WIZARD_WEBSITE_DIR", str(website_root / "wizardsite")))
    next_cli = website / "node_modules" / "next" / "dist" / "bin" / "next"
    node = shutil.which("node")
    return [backend, ServiceSpec(
        key="website", label="Account website", port=3000,
        health_path="/api/auth/context", cwd=str(website),
        argv=(node, str(next_cli), "dev", "--hostname", "127.0.0.1", "--port", "3000")
        if node and next_cli.is_file() else None,
        env={**os.environ, "WIZARD_ACCOUNT_LOCAL_DEV": "1",
             "WIZARD_ACCOUNT_BACKEND_URL": "http://127.0.0.1:8090"},
        why_unstartable="Local account website or its installed dependencies are unavailable",
    )]


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    """True if something accepts a TCP connection on `port`.

    A connection is not proof of health — a half-dead process holds its socket
    — which is why `healthy` below is the check that matters and this is only
    used to tell "nothing is there" from "something is there but unwell".
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def healthy(spec: ServiceSpec, timeout: float = 1.5) -> bool:
    """True if the service answers its health path with a 2xx."""
    url = f"http://127.0.0.1:{spec.port}{spec.health_path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def service_build_id(spec: ServiceSpec, timeout: float = 1.5) -> str | None:
    """Build fingerprint reported by a healthy Wizard service, if supported."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{spec.port}{spec.health_path}", timeout=timeout
        ) as response:
            payload = json.load(response)
        return payload.get("build_id") if isinstance(payload, dict) else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


#: The request fields this CLI sends that the Runtime must accept for the run to
#: be the run the user asked for. `question` is the user's own sentence, and the
#: planner writes the whole investigation from it.
#:
#: Checked by asking the Runtime's own schema rather than by comparing a version
#: number: `/health` reports the same `version` for every build of the engine,
#: so it cannot tell two of them apart, while the schema is the contract the
#: request is actually validated against.
_REQUIRED_REQUEST_FIELDS = ("question",)


def missing_request_fields(port: int, timeout: float = 3.0) -> tuple[str, ...]:
    """Request fields the Runtime on `port` does not accept. Empty if it accepts all.

    A Runtime older than a field does not fail on it — pydantic ignores what it
    does not know — so the field is dropped on arrival, the planner is handed a
    request with no sentence in it, and the run proceeds: degraded, and saying
    nothing about it. A silently degraded run is the one outcome this project
    forbids, so the CLI asks before it starts.

    Unreadable is not the same as missing. A schema that cannot be fetched
    leaves this returning () — the health probe is what reports an unreachable
    service, and two probes disagreeing about the same port would only make the
    failure message worse.
    """
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/openapi.json", timeout=timeout
        ) as response:
            schema = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return ()
    properties = (
        schema.get("components", {}).get("schemas", {})
        .get("InvestigationRequest", {}).get("properties", {})
    )
    if not properties:
        return ()
    return tuple(field for field in _REQUIRED_REQUEST_FIELDS if field not in properties)


# ── Bringing one service up ──────────────────────────────────────────────────

def _spawn(spec: ServiceSpec, log_dir: Path) -> "subprocess.Popen | None":
    """Start the service as a child, or return None with the reason recorded.

    stdout/stderr go to a per-service log file rather than a pipe. A pipe that
    nobody drains fills its buffer and blocks the child — a service that looks
    hung and is really just waiting for someone to read its output. The log
    path is reported so a failed start can be diagnosed from its real output.
    """
    assert spec.argv is not None
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{spec.key}.log"
    try:
        handle = open(log_path, "w", encoding="utf-8", errors="replace")
    except OSError:
        handle = subprocess.DEVNULL  # type: ignore[assignment]

    try:
        return subprocess.Popen(  # noqa: S603 — argv is built here, not user input
            list(spec.argv),
            cwd=spec.cwd,
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=spec.env,
            # Its own process group, so Ctrl-C in the TUI does not race the
            # child's own shutdown, and terminate() below reaches the whole
            # tree (uvicorn spawns workers).
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, ValueError) as exc:
        if handle is not subprocess.DEVNULL:
            handle.close()
        spec_log = log_path
        raise RuntimeError(f"could not start {spec.key}: {exc} (log: {spec_log})") from exc


def _retire_idle_runtime(spec: ServiceSpec) -> tuple[bool, str]:
    """Replace only a verified, idle Runtime from this Python environment.

    Never kill a process merely because it occupies the configured port.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{spec.port}/v1/investigations", timeout=3) as response:
            investigations = json.load(response)
        from wizard_kernel.contracts.status import is_terminal
        if not isinstance(investigations, list) or any(not is_terminal(item.get("status", "")) for item in investigations):
            return False, "Runtime is finishing an investigation; keep it running and reconnect after it finishes"
        if os.name != "nt" or not spec.argv:
            return False, "Stop the previous Runtime before loading this update"
        shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        # Fixed script: arguments are data via environment, never interpolated shell code.
        script = r"""
$ErrorActionPreference = 'Stop'
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort ([int]$env:WIZARD_REPLACE_PORT))
$owners = @($listeners.OwningProcess | Select-Object -Unique)
if ($owners.Count -ne 1) { exit 2 }
$target = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owners[0])
$launcher = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $target.ParentProcessId)
$owned = $target.ExecutablePath -ieq $env:WIZARD_REPLACE_PYTHON
if (-not $owned -and $launcher) {
    $owned = $launcher.ExecutablePath -ieq $env:WIZARD_REPLACE_PYTHON -and
        $launcher.CommandLine -match 'uvicorn\s+wizard_kernel\.main:app' -and
        $launcher.CreationDate -le $target.CreationDate
}
if (-not $owned -or
    $target.CommandLine -notmatch 'uvicorn\s+wizard_kernel\.main:app' -or
    $target.CommandLine -notmatch ('--port\s+' + $env:WIZARD_REPLACE_PORT + '(\s|$)')) { exit 3 }
Stop-Process -Id $target.ProcessId -ErrorAction Stop
"""
        result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "WIZARD_REPLACE_PORT": str(spec.port), "WIZARD_REPLACE_PYTHON": str(Path(spec.argv[0]).resolve())},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            return False, "Could not confirm ownership of the older Runtime; it was left untouched"
        deadline = time.monotonic() + 5
        while port_open(spec.port) and time.monotonic() < deadline:
            time.sleep(.1)
        return not port_open(spec.port), "Previous Runtime did not release its port"
    except (OSError, ValueError, urllib.error.URLError, subprocess.TimeoutExpired):
        return False, "Could not safely inspect the older Runtime; it was left untouched"


def ensure_service(spec: ServiceSpec, log_dir: Path, *, cancel_event=None) -> ServiceState:
    """Adopt the service if it is up, start it if it is not, else report why not.

    The order matters: probe BEFORE spawning, because spawning a second kernel
    on a busy port fails at bind time with a confusing error, and because an
    already-running service may hold live investigations we must not disturb.
    """
    if cancel_event is not None and cancel_event.is_set():
        return ServiceState(spec=spec, status="unavailable", detail="startup cancelled")
    if healthy(spec):
        expected_build = (spec.env or {}).get("WIZARD_BUILD_ID")
        if expected_build and service_build_id(spec) != expected_build:
            replaced, reason = _retire_idle_runtime(spec) if spec.key == "kernel" else (False, "Restart this service to load the update")
            if replaced:
                return ensure_service(spec, log_dir, cancel_event=cancel_event)
            return ServiceState(
                spec=spec,
                status="unavailable",
                detail=reason,
            )
        # An adopted Runtime is somebody else's process and may be an older
        # build than this CLI. Adopting it is still right — killing it would
        # lose the investigations it holds — but adopting it *silently* is not:
        # the new request fields would be dropped and the run would be a
        # different, worse run with nothing on screen saying so.
        if spec.key == "kernel":
            missing = missing_request_fields(spec.port)
            if missing:
                return ServiceState(
                    spec=spec,
                    status="unavailable",
                    detail=(f"the Runtime on :{spec.port} is an older build and does "
                            f"not accept {', '.join(missing)} — stop that process "
                            f"and run wizard again"),
                )
        return ServiceState(spec=spec, status="adopted", detail=f"already running on :{spec.port}")

    if spec.argv is None:
        return ServiceState(spec=spec, status="unavailable", detail=spec.why_unstartable)

    for tool in spec.needs:
        if tool == "node" and shutil.which("node") is None:
            return ServiceState(spec=spec, status="unavailable", detail=spec.why_unstartable)

    if port_open(spec.port):
        # Occupied but not healthy. Starting onto it would fail with EADDRINUSE,
        # so say exactly that instead of retrying for 40 seconds.
        return ServiceState(
            spec=spec,
            status="unavailable",
            detail=f"port {spec.port} is held by something that does not answer {spec.health_path}",
        )

    if cancel_event is not None and cancel_event.is_set():
        return ServiceState(spec=spec, status="unavailable", detail="startup cancelled")
    try:
        process = _spawn(spec, log_dir)
    except RuntimeError as exc:
        return ServiceState(spec=spec, status="unavailable", detail=str(exc))

    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            return ServiceState(spec=spec, status="unavailable", detail="startup cancelled", process=process)
        if healthy(spec):
            return ServiceState(
                spec=spec, status="started",
                detail=f"started on :{spec.port} (log: {log_dir / f'{spec.key}.log'})",
                process=process,
            )
        # A child that exits has already failed; waiting out the timeout would
        # just delay the same answer.
        if process.poll() is not None:
            tail = _log_tail(log_dir / f"{spec.key}.log")
            return ServiceState(
                spec=spec, status="unavailable",
                detail=f"exited with code {process.returncode}{tail}",
            )
        if cancel_event is None:
            time.sleep(HEALTH_INTERVAL_S)
        else:
            cancel_event.wait(HEALTH_INTERVAL_S)

    _terminate(process)
    return ServiceState(
        spec=spec, status="unavailable",
        detail=f"did not answer {spec.health_path} within {START_TIMEOUT_S:.0f}s",
    )


def _log_tail(path: Path, lines: int = 4) -> str:
    """The last few lines of a service log, for an actionable failure message."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except OSError:
        return ""
    if not content:
        return ""
    return "; " + " / ".join(line.strip() for line in content[-lines:] if line.strip())


def _terminate(process: "subprocess.Popen", timeout: float = 4.0, *, additional=()) -> None:
    """Stop a child we started, escalating only if it ignores the request."""
    processes = [proc for proc in (process, *additional) if proc.poll() is None]
    if not processes:
        return
    if os.name == "nt":
        # A Windows venv executable redirects to a child Python process.
        # Terminating only the launcher leaves uvicorn/LLM workers orphaned.
        try:
            args = ["taskkill", "/T", "/F"]
            for proc in processes:
                args.extend(["/PID", str(proc.pid)])
            subprocess.run(
                args,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            # WMI can finish killing the tree before taskkill itself exits.
            # Reap the launcher instead of leaking a traceback on clean exit.
            for proc in processes:
                if proc.poll() is None:
                    proc.kill()
    else:
        import signal
        os.killpg(process.pid, signal.SIGTERM)
    for proc in processes:
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait(timeout=1)


# ── The browser binary ───────────────────────────────────────────────────────

# What Playwright's browser executables are called, per platform and for the
# headless shell it uses when launching headless.
_CHROMIUM_NAMES = (
    "chrome.exe", "headless_shell.exe", "chrome", "headless_shell",
    "Chromium", "chrome-headless-shell",
)


def find_chromium(root: Path | None = None) -> Path | None:
    """Compatibility probe: detect the configured agent-browser CLI."""
    from wizard_kernel.world.browser.runtime import browser_command
    try:
        return Path(browser_command())
    except RuntimeError:
        return None


def ensure_chromium() -> str:
    """Dependency installation remains explicit, never a TUI startup side effect."""
    return "agent-browser available" if find_chromium() else "Install npm install -g agent-browser@0.27.0, then agent-browser install"


@dataclass
class ServiceReport:
    """What `ensure_all` found and did, in the order it did it.

    Attributes:
        states: One ServiceState per service.
        env: Environment variables the CLI must set so its requests reach the
            services that are actually up. Applied to os.environ by the caller.
    """

    states: list[ServiceState] = field(default_factory=list)

    @property
    def by_key(self) -> dict[str, ServiceState]:
        return {s.spec.key: s for s in self.states}

    @property
    def kernel_ok(self) -> bool:
        state = self.by_key.get("kernel")
        return bool(state and state.ok)

    @property
    def investigation_stack_ok(self) -> bool:
        by_key = self.by_key
        return bool(by_key.get("kernel") and by_key["kernel"].ok)

    def lines(self) -> list[str]:
        """One honest line per service, for display before the menu appears.

        ASCII markers, not the ●/▲/✗ the Rich panel uses. These lines are
        written with plain `print()` to whatever console launched the CLI, and
        a Windows console on a legacy code page (cp1252) raises
        UnicodeEncodeError on them — which would take down `wizard` before the
        TUI was ever drawn. The panel inside the app can use the pretty ones
        because Rich negotiates the encoding; this cannot.
        """
        marks = {"adopted": "[=]", "started": "[+]", "unavailable": "[x]"}
        out: list[str] = []
        for state in self.states:
            mark = marks.get(state.status, "[?]")
            out.append(f"{mark} {state.spec.label:<28} {state.status:<12} {state.detail}")
        return out


class ServiceSupervisor:
    """Owns the child processes the TUI started, and stops them on exit.

    A service started here lives exactly as long as the TUI does. One that was
    already running is adopted and deliberately outlives it — the user may have
    started it to keep investigations alive across sessions, and this class has
    no business ending that.
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or (Path(os.getcwd()) / ".wizard" / "logs")
        self.report: ServiceReport | None = None

    def ensure_all(self, specs: list[ServiceSpec] | None = None, *, cancel_event=None) -> ServiceReport:
        """Bring up every service, and record what happened to each."""
        specs = specs if specs is not None else build_specs()
        report = ServiceReport()
        self.report = report
        for spec in specs:
            if cancel_event is not None and cancel_event.is_set():
                break
            if cancel_event is None:
                report.states.append(ensure_service(spec, self.log_dir))
            else:
                report.states.append(ensure_service(spec, self.log_dir, cancel_event=cancel_event))
        self.report = report
        return report

    def env(self) -> dict[str, str]:
        """The environment the CLI's requests need, derived from what is up.

        Written from the SERVICES rather than from what we hoped to start: if
        the planner failed to come up, no planner URL is exported, the Runtime
        is not told about one, and its `seams.resolved` event says the built-in
        planner was used. Pointing at a dead planner would be worse than not
        pointing at one — the Runtime would fail the call instead of falling
        back to something that works.
        """
        if self.report is None:
            return {}
        by_key = self.report.by_key
        env: dict[str, str] = {}

        if by_key["kernel"].ok:
            env["WIZARD_ENGINE_URL"] = f"http://127.0.0.1:{by_key['kernel'].spec.port}"
        if by_key.get("planner") and by_key["planner"].ok:
            # Base origin only: the Runtime's HttpPlanner appends /plan/* itself.
            env["WIZARD_PLANNER_URL"] = f"http://127.0.0.1:{by_key['planner'].spec.port}"
        if by_key.get("agents") and by_key["agents"].ok:
            port = by_key["agents"].spec.port
            # Full paths, because the agent client POSTs verbatim.
            env["WIZARD_EXPLORER_URL"] = f"http://127.0.0.1:{port}/agent/explorer"
            env["WIZARD_VERIFIER_URL"] = f"http://127.0.0.1:{port}/agent/verifier"
        return env

    def apply_env(self) -> dict[str, str]:
        """Set the derived variables in os.environ and return them.

        Set (not merely returned) because `RequestOptions.from_env()` is what
        the commands actually read — they re-read the environment per run, so
        exporting here is what connects the TUI to the services for every
        later request without threading options through the UI.
        """
        env = self.env()
        os.environ.update(env)
        return env

    def stop(self, *, announce: bool = True) -> list[str]:
        """Stop the children we started. Returns the labels stopped.

        Adopted services are skipped by construction — `process` is None for
        them — so this can never take down a kernel the user started.
        """
        stopped: list[str] = []
        if self.report is None:
            return stopped
        import threading
        workers = []
        failures = []
        def terminate(states):
            try:
                _terminate(states[0].process, additional=[state.process for state in states[1:]])
            except (OSError, subprocess.SubprocessError):
                failures.extend(state.spec.label for state in states)
        owned = [state for state in self.report.states if state.process is not None]
        groups = [owned] if os.name == "nt" and owned else [[state] for state in owned]
        for states in groups:
            worker = threading.Thread(target=terminate, args=(states,), daemon=True)
            worker.start()
            workers.append(worker)
            stopped.extend(state.spec.label for state in states)
        deadline = time.monotonic() + 6
        for worker in workers:
            worker.join(timeout=max(0, deadline - time.monotonic()))
        failures.extend(state.spec.label for state in owned if state.process.poll() is None)
        if failures:
            message = "Could not stop owned services: " + ", ".join(failures)
            if announce:
                print(message, flush=True)
            else:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                with (self.log_dir / "cleanup.log").open("a", encoding="utf-8") as stream:
                    stream.write(message + "\n")
        return [label for label in stopped if label not in failures]


def probe_only(specs: list[ServiceSpec] | None = None) -> ServiceReport:
    """Health-check without starting anything — no side effects.

    Used by tests and by any caller that wants to report status rather than
    change it.
    """
    specs = specs if specs is not None else build_specs()
    report = ServiceReport()
    for spec in specs:
        if healthy(spec):
            report.states.append(ServiceState(spec, "adopted", f"already running on :{spec.port}"))
        elif spec.argv is None:
            report.states.append(ServiceState(spec, "unavailable", spec.why_unstartable))
        else:
            report.states.append(ServiceState(spec, "unavailable", f"not running on :{spec.port}"))
    return report


__all__ = [
    "ServiceSpec", "ServiceState", "ServiceReport", "ServiceSupervisor",
    "build_specs", "ensure_service", "healthy", "port_open", "probe_only",
    "repo_root",
]
