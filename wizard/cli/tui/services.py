"""Services — start and health-check the three services a run needs.

Bare `wizard` used to open a TUI that talked to nothing. The Runtime was not
running, the planner was not running, the agents were not running, and the only
signal was a connection error once you had already picked a command and typed an
intent. This module is what makes the promise "everything is already connected"
true: the TUI brings up whatever is missing before it shows the menu.

Three services, one process each:

    kernel    the Wizard Runtime Engine    127.0.0.1:8080   (Python, uvicorn)
    planner   the investigation planner    127.0.0.1:8787   (Node, TS)
    agents    Explorer + Verifier          127.0.0.1:8100   (Python, uvicorn)

Design rules, all of them in service of "no fallback, everything real":

  * A service already listening is ADOPTED, never restarted. Killing somebody
    else's kernel to start our own would lose whatever investigations it holds.
  * A service we start is a CHILD we own and stop on exit; a service we adopt
    is left running, because stopping something we did not start is not ours
    to do.
  * Every service reports one of: adopted / started / unavailable. There is no
    fourth "probably fine" state, and `unavailable` is always fatal for the
    kernel (nothing works without it) and never silent for the others.
  * Nothing here is mocked. Where a service cannot be started, the reason is a
    real error string from the real attempt.
"""

from __future__ import annotations

import importlib.util
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


def build_specs(root: Path | None = None) -> list[ServiceSpec]:
    """The three services, resolved against this checkout.

    The planner is optional in the strongest sense: the Runtime has a built-in
    deterministic planner, so an investigation still runs without it (its
    `seams.resolved` event says which planner it actually used). Its argv is
    None when Node is absent, and that is reported as unavailable rather than
    silently downgrading — the user can see the seam is not connected.
    """
    root = root or repo_root()
    node = shutil.which("node")

    return [
        ServiceSpec(
            key="kernel",
            label="Runtime Engine",
            port=8080,
            health_path="/health",
            cwd=str(root / "wizard-runtime-engine"),
            argv=(_python(), "-m", "uvicorn", "wizard_kernel.main:app",
                  "--host", "127.0.0.1", "--port", "8080"),
            needs=("uvicorn",),
            why_unstartable="uvicorn is not importable by this interpreter",
        ),
        ServiceSpec(
            key="planner",
            label="Investigation Planner",
            port=8787,
            health_path="/health",
            cwd=str(root / "wizard-investigation-planner"),
            argv=(node, "--experimental-strip-types", "src/http/server.ts") if node else None,
            needs=("node",),
            why_unstartable="node is not on PATH",
        ),
        ServiceSpec(
            key="agents",
            label="Explorer + Verifier agents",
            port=8100,
            health_path="/health",
            # wizard_agents/wizard_agents: the inner directory is the package
            # root, because `app` is the top-level module uvicorn imports.
            # Starting from the outer directory fails with "No module named
            # 'app'" — which is exactly what it did until this was corrected.
            cwd=str(root / "wizard_agents" / "wizard_agents"),
            argv=(_python(), "-m", "uvicorn", "app.api.main:app",
                  "--host", "127.0.0.1", "--port", "8100"),
            needs=("uvicorn",),
            why_unstartable="uvicorn is not importable by this interpreter",
        ),
    ]


# ── Probes ───────────────────────────────────────────────────────────────────

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
            # Its own process group, so Ctrl-C in the TUI does not race the
            # child's own shutdown, and terminate() below reaches the whole
            # tree (uvicorn spawns workers).
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        if handle is not subprocess.DEVNULL:
            handle.close()
        spec_log = log_path
        raise RuntimeError(f"could not start {spec.key}: {exc} (log: {spec_log})") from exc


def ensure_service(spec: ServiceSpec, log_dir: Path) -> ServiceState:
    """Adopt the service if it is up, start it if it is not, else report why not.

    The order matters: probe BEFORE spawning, because spawning a second kernel
    on a busy port fails at bind time with a confusing error, and because an
    already-running service may hold live investigations we must not disturb.
    """
    if healthy(spec):
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

    try:
        process = _spawn(spec, log_dir)
    except RuntimeError as exc:
        return ServiceState(spec=spec, status="unavailable", detail=str(exc))

    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
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
        time.sleep(HEALTH_INTERVAL_S)

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


def _terminate(process: "subprocess.Popen", timeout: float = 5.0) -> None:
    """Stop a child we started, escalating only if it ignores the request."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()


# ── The browser binary ───────────────────────────────────────────────────────

# What Playwright's browser executables are called, per platform and for the
# headless shell it uses when launching headless.
_CHROMIUM_NAMES = (
    "chrome.exe", "headless_shell.exe", "chrome", "headless_shell",
    "Chromium", "chrome-headless-shell",
)


def _browsers_dir() -> Path:
    """Playwright's browser cache, honouring its own override variable."""
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override and override not in ("0",):
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ms-playwright"


def find_chromium(root: Path | None = None) -> Path | None:
    """The Chromium executable Playwright downloaded, or None.

    Looked for on disk rather than asked of Playwright. Asking means starting
    Playwright's driver subprocess, and that one-shot start-and-stop leaves a
    pending task whose teardown prints "Task was destroyed but it is pending!"
    and a TargetClosedError traceback — noise on the user's terminal on every
    single launch, to answer a question about a file's existence.
    """
    root = root or _browsers_dir()
    if not root.is_dir():
        return None
    # `chromium*`, not `chromium-*`: the headless shell lives in
    # chromium_headless_shell-<rev>, and that is the one a headless run uses.
    for version_dir in sorted(root.glob("chromium*")):
        for name in _CHROMIUM_NAMES:
            for hit in version_dir.rglob(name):
                if hit.is_file():
                    return hit
    return None


def ensure_chromium() -> str:
    """Make sure Playwright's Chromium is on disk, fetching it once if not.

    `pip install -e .` installs the Playwright *package* but not its browser
    binaries, and it cannot: Playwright downloads those from its own CDN, while
    pip installs wheels and has no post-install step to run. A `setup.py`
    install hook does not close the gap either — pip builds a wheel and installs
    that, bypassing the command. So the download happens here, on the first
    launch, which works however the package was installed.

    Returns the line to report, in the same shape as the service lines. Failure
    is not fatal: the browser is one tool of several, and a run that never
    touches a web page should not be blocked because a download failed.
    """
    # The binaries without the package that drives them are no use, and a cache
    # left behind by an uninstalled Playwright would otherwise read as ready.
    # find_spec imports nothing and starts nothing, so it stays silent.
    if importlib.util.find_spec("playwright") is None:
        return ("[x] Chromium (Playwright browser)  unavailable  "
                "the playwright package is not importable by this interpreter")

    if find_chromium() is not None:
        return "[=] Chromium (Playwright browser)  ready        already on disk"

    print("    fetching Chromium for the agentic browser "
          "(one time, ~150 MB)...", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True, timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ("[x] Chromium (Playwright browser)  unavailable  "
                f"download did not run: {exc}")

    if find_chromium() is not None:
        return "[+] Chromium (Playwright browser)  fetched      downloaded just now"

    # Its own last words, not a paraphrase: the usual causes are no network or a
    # proxy that needs configuring, and only its output says which.
    tail = " / ".join(
        line.strip() for line in (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        if line.strip()
    )
    return ("[x] Chromium (Playwright browser)  unavailable  "
            f"download failed{': ' + tail if tail else ''}")


# ── The supervisor the TUI holds ─────────────────────────────────────────────

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

    def ensure_all(self, specs: list[ServiceSpec] | None = None) -> ServiceReport:
        """Bring up every service, and record what happened to each."""
        specs = specs if specs is not None else build_specs()
        report = ServiceReport()
        for spec in specs:
            report.states.append(ensure_service(spec, self.log_dir))
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
        if by_key["planner"].ok:
            # Base origin only: the Runtime's HttpPlanner appends /plan/* itself.
            env["WIZARD_PLANNER_URL"] = f"http://127.0.0.1:{by_key['planner'].spec.port}"
        if by_key["agents"].ok:
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

    def stop(self) -> list[str]:
        """Stop the children we started. Returns the labels stopped.

        Adopted services are skipped by construction — `process` is None for
        them — so this can never take down a kernel the user started.
        """
        stopped: list[str] = []
        if self.report is None:
            return stopped
        for state in self.report.states:
            if state.process is not None:
                _terminate(state.process)
                stopped.append(state.spec.label)
        return stopped


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
