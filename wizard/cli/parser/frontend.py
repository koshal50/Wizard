"""Which web client this repository serves, and at what URL.

Three separate things have to line up before the Runtime drives a browser at a
project, and two of them were already in place:

  1. the Runtime must enable a browser plane          — `options.browser_enabled`
  2. the Planner must plan browser nodes for it       — it does, from a URL target
  3. somebody must name a URL                         — **nothing did**

A URL cannot be invented by either half. The Runtime's egress guard is
fail-closed and rejects any host the user did not allow, so a URL the Runtime
made up would be refused by its own validator; and inventing network targets is
not the Planner's business either (invariant 3, invariant 5). The URL has to
come from the user — which is fine, except that a user running `wizard` against
their own checkout has no way to know the wizard wanted one, or which one, or
that the answer is different for every project.

So this module reads the answer out of the repository and the machine: find the
package that declares a dev server, take the port that package declares (or the
framework's default when it declares none), and ask whether anything is
listening there. It is a fact about *this checkout on this machine*, which the
CLI is entitled to observe — it is not a claim about the project, and nothing
here reaches the kernel. The user still types or accepts the URL, so the egress
guard goes on seeing an explicit, user-named target.

This module has ZERO LLM logic and makes no network requests: one TCP connect
per candidate port, to the loopback interface only.
"""
from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass
from pathlib import Path

# Directories that never hold hand-written source. `dist` and `build` matter as
# much as `node_modules`: they contain a *copy* of the client, so descending
# into one would report a second frontend on the same port and the user would be
# offered the same URL twice.
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "dist", "build", ".next", ".nuxt", ".svelte-kit",
    "coverage", ".venv", "venv", "__pycache__", "out", ".output",
})

# Findings deeper than this are not the project's own client. A dependency
# vendored into the tree, or an example app three levels down, is not what
# `wizard` was pointed at.
_MAX_DEPTH = 3

# How a package announces it is a client, what to call that, and where its dev
# server lands when it declares no port. Ordered most-specific first: a package
# carrying both `vite` and `svelte` is a SvelteKit app, and its port comes from
# the same framework rule either way, but the name shown to the user should be
# the one they would recognise.
_CLIENT_DEPS: tuple[tuple[str, str, int], ...] = (
    ("@sveltejs/kit", "sveltekit", 5173),
    ("next", "next", 3000),
    ("nuxt", "nuxt", 3000),
    ("react-scripts", "create-react-app", 3000),
    ("@angular/core", "angular", 4200),
    ("@vue/cli-service", "vue-cli", 8080),
    ("webpack-dev-server", "webpack", 8080),
    ("parcel", "parcel", 1234),
    ("vite", "vite", 5173),
)

# The scripts that put a page on a port, most-canonical first. `preview` is
# last: it serves a build rather than the sources, which is a real page but not
# the one a developer means by "the frontend".
_SERVE_SCRIPTS = ("dev", "start", "serve", "preview")

# Vite's config, and every extension it accepts. Read only for a port.
_VITE_CONFIGS = ("vite.config.ts", "vite.config.js", "vite.config.mjs",
                 "vite.config.mts", "vite.config.cjs")

# `port: 5173`, `port: "5173"`, and the same inside `preview: { ... }`. The
# nearest preceding `server:`/`preview:` key is not tracked — a file with two
# ports is rare, and taking the first number after `port:` is right for the
# `server` block that a dev run uses, which is the one being asked about.
#
# One digit, not two: `\d{2,5}` looked like a guard against a stray `port: 0`
# and was really a silent fallback, because a config declaring any single-digit
# port failed to match and the framework's default was used instead. The user
# was then told about a port nothing was serving on, and the hint's "not
# running" was about the wrong number. Port 0 is rejected by the range below,
# which is the specific thing that needed guarding.
_PORT_RE = re.compile(r"\bport\s*:\s*[\"']?(\d{1,5})")


@dataclass(frozen=True)
class Frontend:
    """A servable client found in the repository."""

    package_dir: str    # relative to the repo root; "" when it is the root
    framework: str      # "vite", "next", ...
    script: str         # the npm script that serves it ("dev", "start", ...)
    port: int
    listening: bool     # is something already answering on that port

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"


def _listening(port: int, timeout: float = 0.25) -> bool:
    """True if something accepts a TCP connection on the loopback `port`.

    Every address `localhost` resolves to is tried, because that is what a
    browser does and because a probe that tries only one of them answers the
    wrong question. On Windows `localhost` resolves to `::1` *first*, and Vite
    binds only that: a `127.0.0.1`-only probe — which is what this was — reports
    a client that is serving perfectly well as not running, and sends the user
    to start a dev server that is already up. The symptom is a hint that never
    changes however many times they start it.

    Defined here rather than imported from `tui.services`, which has a similar
    probe: `tui` imports this package, so reaching back into it would make the
    two mutually dependent for a few lines of socket code.
    """
    try:
        addresses = socket.getaddrinfo("localhost", port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, _type, _proto, _canon, sockaddr in addresses:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            try:
                if sock.connect_ex(sockaddr) == 0:
                    return True
            except OSError:
                continue
    return False


def _package_json(root: Path) -> list[tuple[str, dict]]:
    """Every package.json under `root`, as (relative dir, parsed), sorted.

    Sorted so the result is deterministic — two runs over one checkout offer the
    same frontend first, which matters because only the first is shown.
    """
    found: list[tuple[str, dict]] = []
    for path in sorted(root.rglob("package.json")):
        rel = path.relative_to(root)
        if len(rel.parts) - 1 > _MAX_DEPTH:
            continue
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A malformed package.json is the project's problem and the
            # investigation will report it. Here it just is not a frontend.
            continue
        if isinstance(data, dict):
            found.append((str(rel.parent) if len(rel.parts) > 1 else "", data))
    return found


def _vite_port(root: Path, package_dir: str) -> int | None:
    """The port a Vite client declares, or None when it declares none.

    Searched in the client's own directory first, then the repository root: a
    workspace hoists its config to the top often enough that looking only beside
    the package.json would miss it half the time.
    """
    for where in (root / package_dir, root):
        for name in _VITE_CONFIGS:
            config = where / name
            if not config.is_file():
                continue
            try:
                text = config.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hit = _PORT_RE.search(text)
            if hit and int(hit.group(1)) > 0:
                return int(hit.group(1))
    return None


def _declared_port(root: Path, package_dir: str, framework: str,
                   fallback: int) -> int:
    if framework in ("vite", "sveltekit"):
        return _vite_port(root, package_dir) or fallback
    return fallback


def find_frontends(repo_path: str, *, probe: bool = True) -> list[Frontend]:
    """Every client in `repo_path` that declares a way to serve itself.

    Ordered by directory, so the caller can take the first. `probe=False` skips
    the socket check, for a caller that wants the list without touching the
    network.
    """
    root = Path(repo_path)
    if not root.is_dir():
        return []

    out: list[Frontend] = []
    for package_dir, data in _package_json(root):
        scripts = data.get("scripts") or {}
        if not isinstance(scripts, dict):
            continue
        script = next((s for s in _SERVE_SCRIPTS if s in scripts), None)
        if script is None:
            continue

        deps = set()
        for key in ("dependencies", "devDependencies"):
            block = data.get(key) or {}
            if isinstance(block, dict):
                deps.update(block)

        for dep, framework, default_port in _CLIENT_DEPS:
            if dep not in deps:
                continue
            port = _declared_port(root, package_dir, framework, default_port)
            out.append(Frontend(
                package_dir=package_dir,
                framework=framework,
                script=script,
                port=port,
                listening=_listening(port) if probe else False,
            ))
            break  # one framework per package: the first match is the most specific

    return out


def hint_for(frontend: Frontend, *, manager: str = "npm") -> str:
    """One line telling the user how to get a browser phase for this client.

    Two different situations, said differently, because they need different
    things from the reader. A client that is already serving needs a URL typed;
    one that is not needs to be started first, and telling that user to "pass
    its URL" would send them to type a URL that answers nothing — the browser
    phase would then fail to navigate, and the failure would look like the
    wizard's.

    The start command is written as a `cd` rather than as `npm run <script>
    --workspace <dir>`, which is shorter but only correct when the repository
    root happens to declare that directory as a workspace. `cd` is right either
    way, and a wrong start command is worse than a longer one.
    """
    where = frontend.package_dir
    if frontend.listening:
        # "will open it", not "add that URL to your intent": the run does it
        # without being asked. Telling the reader to do something the wizard
        # already does is how a working feature reads as a missing one.
        return (f"{frontend.framework} client is serving at {frontend.url} "
                f"— the browser phase will open it")
    target = f"cd {where} && {manager} run {frontend.script}" if where else f"{manager} run {frontend.script}"
    return (f"{frontend.framework} client in {where or 'this repo'}/ is not running — "
            f"start it with `{target}` to give the browser phase a page to open")


def suggestion_for(repo_path: str, *, probe: bool = True) -> tuple[Frontend | None, str]:
    """The client worth offering, and the line to show. (None, "") when there is none."""
    frontends = find_frontends(repo_path, probe=probe)
    if not frontends:
        return None, ""
    # A serving client beats a found one, whichever directory each is in: the
    # user can act on the first and not on the second, and offering a URL that
    # answers nothing is how a working browser phase reads as a broken one.
    frontends.sort(key=lambda f: (not f.listening, f.package_dir))
    return frontends[0], hint_for(frontends[0])


def browsable(repo_path: str) -> Frontend | None:
    """The client the browser phase may open without being asked, or None.

    Narrower than `suggestion_for` in exactly one way, and it is the whole
    point: only a client that is *already serving* qualifies. A URL is put into
    the request on the user's behalf here, so it has to be one that will answer
    — naming a port nothing is listening on would start the browser plane,
    watch it fail to navigate, and report a failure that reads as the wizard's
    rather than as a server nobody started.

    A client that was found but is not running is still reported by
    `suggestion_for`, which is what the intent screen shows. The difference
    between the two is the difference between "this will be browsed" and "start
    this and it will be".
    """
    frontend, _ = suggestion_for(repo_path)
    return frontend if frontend is not None and frontend.listening else None
