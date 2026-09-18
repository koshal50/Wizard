"""Which client this project serves, and whether the wizard can be told about it.

The browser plane is what makes a web project's investigation different from any
other, and before this module nothing in the CLI ever mentioned it: the Runtime
only opens a browser when the request names a URL, and the user had no way to
know a URL was the missing piece, or which one, or that the answer is different
for every project. The run simply contained no browser steps and nothing said
why.

These tests are mostly about the two ways that discovery can lie. It can miss a
client that is right there (a reader that only knows one framework, or a probe
that only knows one loopback address), and it can invent one that is not (a
dependency name matched loosely, a built copy mistaken for a second client).
Either sends the user somewhere useless.
"""
import json
import socket
import textwrap
from pathlib import Path

import pytest

from wizard.cli.parser.frontend import (
    Frontend,
    find_frontends,
    hint_for,
    suggestion_for,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _package(root: Path, where: str, *, deps=None, dev_deps=None, scripts=None) -> Path:
    """Write a package.json at `where` (relative to root) and return its directory."""
    directory = root / where if where else root
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "package.json").write_text(json.dumps({
        "name": where or "root",
        "scripts": scripts if scripts is not None else {"dev": "vite"},
        "dependencies": deps or {},
        "devDependencies": dev_deps or {},
    }), encoding="utf-8")
    return directory


def _vite_config(directory: Path, port: int | None) -> None:
    body = "export default {\n  server: {\n    port: %s,\n  },\n};\n" % port
    (directory / "vite.config.js").write_text(body, encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    """A two-workspace project shaped like the one this was built against."""
    _package(tmp_path, "", scripts={"test": "npm test --workspaces"})   # root, not a client
    _package(tmp_path, "client", deps={"react": "^18"}, dev_deps={"vite": "^5"},
             scripts={"dev": "vite", "build": "vite build"})
    _vite_config(tmp_path / "client", 5173)
    _package(tmp_path, "server", deps={"express": "^4"}, scripts={"start": "node src/server.js"})
    return tmp_path


# ── Finding a client ──────────────────────────────────────────────────────────

def test_a_vite_client_is_found_with_the_port_it_declares(project):
    found = find_frontends(str(project), probe=False)
    assert len(found) == 1, "only client/ declares a dev server and a client framework"
    assert found[0].package_dir == "client"
    assert found[0].framework == "vite"
    assert found[0].script == "dev"
    assert found[0].port == 5173, "the port comes from vite.config.js, not a guess"
    assert found[0].url == "http://localhost:5173"


def test_the_frameworks_default_port_is_used_when_none_is_declared(tmp_path):
    """A client that declares no port still has one — the framework's own."""
    _package(tmp_path, "web", dev_deps={"next": "^14"}, scripts={"dev": "next dev"})
    found = find_frontends(str(tmp_path), probe=False)
    assert [(f.framework, f.port) for f in found] == [("next", 3000)]


def test_the_port_is_looked_for_at_the_repo_root_too(tmp_path):
    """A workspace hoists its vite config often enough that it cannot be missed."""
    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    _vite_config(tmp_path, 3001)          # beside the root package.json, not the client
    found = find_frontends(str(tmp_path), probe=False)
    assert found[0].port == 3001


def test_the_more_specific_framework_names_the_client(tmp_path):
    """A SvelteKit app carries `vite` as well; it is not described as a vite app."""
    _package(tmp_path, "app", dev_deps={"vite": "^5", "@sveltejs/kit": "^2"},
             scripts={"dev": "vite dev"})
    found = find_frontends(str(tmp_path), probe=False)
    assert [f.framework for f in found] == ["sveltekit"]


@pytest.mark.parametrize("scripts", [
    {"build": "vite build"},                       # no way to serve it
    {"test": "vitest run", "lint": "eslint ."},    # scripts, but none that serve
])
def test_a_package_that_cannot_be_served_is_not_a_client(tmp_path, scripts):
    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts=scripts)
    assert find_frontends(str(tmp_path), probe=False) == []


def test_a_served_package_that_is_not_a_client_is_not_a_client(tmp_path):
    """A server has a `start` script and is not a frontend.

    `express` is not a client framework, and offering its port as a page to
    browse would send the browser at a JSON API.
    """
    _package(tmp_path, "api", deps={"express": "^4"}, scripts={"start": "node server.js"})
    assert find_frontends(str(tmp_path), probe=False) == []


def test_a_dependency_whose_name_merely_contains_a_framework_is_not_one(tmp_path):
    """`latest` contains `vite`; `contest` contains `next`. Neither is a client."""
    _package(tmp_path, "a", deps={"latest": "^1"}, scripts={"dev": "node index.js"})
    _package(tmp_path, "b", deps={"contest": "^1"}, scripts={"dev": "node index.js"})
    assert find_frontends(str(tmp_path), probe=False) == []


def test_a_built_copy_is_not_a_second_client(tmp_path):
    """`dist/` holds a copy of the client, not another one.

    Descending into it would report the same frontend twice, on the same port,
    and offer the user the same URL twice.
    """
    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    _package(tmp_path, "client/dist", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    found = find_frontends(str(tmp_path), probe=False)
    assert [f.package_dir for f in found] == ["client"]


def test_a_client_buried_too_deep_is_not_this_projects_client(tmp_path):
    """A vendored or example app four levels down is not what `wizard` was pointed at."""
    _package(tmp_path, "a/b/c/d", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    assert find_frontends(str(tmp_path), probe=False) == []


def test_a_malformed_package_json_does_not_stop_the_search(tmp_path):
    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "package.json").write_text("{ not json", encoding="utf-8")
    assert [f.package_dir for f in find_frontends(str(tmp_path), probe=False)] == ["client"]


def test_a_directory_that_is_not_a_repository_finds_nothing(tmp_path):
    assert find_frontends(str(tmp_path / "does-not-exist"), probe=False) == []


# ── Whether anything is actually listening ────────────────────────────────────

def _free_port() -> int:
    """A port nothing is listening on, found rather than assumed.

    Assumed ports are how a probe test passes for the wrong reason: the fact
    that 5173 is busy on this machine is a fact about this machine, not about
    the code.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _listener(family: int) -> tuple[socket.socket, int]:
    """A listening socket on an ephemeral port, bound to one address family."""
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1" if family == socket.AF_INET else "::1", 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


def test_a_serving_client_is_reported_as_listening(tmp_path):
    sock, port = _listener(socket.AF_INET)
    try:
        _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
        _vite_config(tmp_path / "client", port)
        found = find_frontends(str(tmp_path))
        assert found[0].listening is True
        assert found[0].port == port
    finally:
        sock.close()


def test_a_client_serving_on_ipv6_only_is_still_found(tmp_path):
    """The bug this was written for, kept as a test.

    Vite binds `::1` and nothing else, and on Windows `localhost` resolves to
    `::1` first. A probe that tried only `127.0.0.1` therefore reported a client
    that was serving perfectly well as not running — and the hint sent the user
    to start a dev server that was already up, every time, with no way to tell
    that the wizard was the thing that was wrong.
    """
    if not socket.has_ipv6:
        pytest.skip("no IPv6 on this machine")
    try:
        sock, port = _listener(socket.AF_INET6)
    except OSError:
        pytest.skip("cannot bind an IPv6 loopback socket here")
    try:
        _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
        _vite_config(tmp_path / "client", port)
        assert find_frontends(str(tmp_path))[0].listening is True
    finally:
        sock.close()


def test_a_port_nothing_answers_on_is_not_listening(tmp_path):
    """A closed port must read as closed — the whole hint turns on the difference."""
    closed = _free_port()
    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    _vite_config(tmp_path / "client", closed)
    found = find_frontends(str(tmp_path))
    assert found[0].port == closed, "the declared port was not the one read back"
    assert found[0].listening is False


def test_a_single_digit_port_is_still_read_from_the_config(tmp_path):
    """`\\d{2,5}` silently ignored these and fell back to the framework default.

    The user was then told about a port nothing was serving on, and the hint's
    "not running" was about the wrong number — so following it changed nothing.
    Probed off: what is under test is the parse, and whether anything answers on
    the port is a fact about the machine running the suite.
    """
    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    _vite_config(tmp_path / "client", 9)
    assert find_frontends(str(tmp_path), probe=False)[0].port == 9


def test_a_port_of_zero_is_treated_as_undeclared(tmp_path):
    """`port: 0` means "any free port", not "port zero" — the default is the honest answer."""
    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    _vite_config(tmp_path / "client", 0)
    assert find_frontends(str(tmp_path), probe=False)[0].port == 5173


def test_the_probe_can_be_skipped(tmp_path):
    """`probe=False` answers the question without touching the network."""
    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    assert find_frontends(str(tmp_path), probe=False)[0].listening is False


# ── What the user is told ─────────────────────────────────────────────────────

def test_a_serving_client_is_offered_by_its_url():
    """The actionable half: the user has a page and needs to name it."""
    line = hint_for(Frontend("client", "vite", "dev", 5173, listening=True))
    assert "http://localhost:5173" in line
    assert "not running" not in line


def test_a_client_that_is_not_running_is_given_a_start_command():
    """Telling this user to 'pass its URL' sends them to type one that answers nothing.

    The browser phase would then fail to navigate, and the failure would look
    like the wizard's rather than like a server that was never started.
    """
    line = hint_for(Frontend("client", "vite", "dev", 5173, listening=False))
    assert "cd client" in line and "npm run dev" in line
    assert "http://localhost:5173" not in line


def test_the_start_command_does_not_assume_a_workspace(tmp_path):
    """`--workspace` is shorter but only correct when the root declares one.

    A wrong start command is worse than a longer one: it fails, and the user
    concludes the wizard is wrong rather than the instruction.
    """
    line = hint_for(Frontend("client", "vite", "dev", 5173, listening=False))
    assert "--workspace" not in line


def test_a_client_at_the_repo_root_needs_no_cd():
    line = hint_for(Frontend("", "vite", "dev", 5173, listening=False))
    assert "cd " not in line and "npm run dev" in line


def test_a_serving_client_is_offered_in_preference_to_one_that_is_not(tmp_path):
    """Only one is shown, so it has to be the one the user can act on.

    `client/` is found first by directory order, but it is not running and
    `site/` is: offering the first would give the user a URL that answers
    nothing, while a working page sat one directory over.
    """
    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    _vite_config(tmp_path / "client", 1)
    sock, port = _listener(socket.AF_INET)
    try:
        _package(tmp_path, "site", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
        _vite_config(tmp_path / "site", port)
        frontend, hint = suggestion_for(str(tmp_path))
        assert frontend.package_dir == "site"
        assert str(port) in hint
    finally:
        sock.close()


def test_a_project_with_no_client_is_told_nothing(tmp_path):
    """No client means no hint. An empty suggestion must not read as a finding."""
    _package(tmp_path, "api", deps={"express": "^4"}, scripts={"start": "node s.js"})
    assert suggestion_for(str(tmp_path)) == (None, "")


def test_a_directory_that_is_not_a_repository_is_told_nothing(tmp_path):
    assert suggestion_for(str(tmp_path / "nope")) == (None, "")


# ── What gets browsed without being asked for ─────────────────────────────────

def test_a_serving_client_is_browsed_without_being_asked_for(tmp_path):
    """The user typed no URL and should not have to.

    `wizard <repo>` is a request to investigate that repository, and a web
    client it is already serving is part of it. Before this the run contained
    no browser steps at all and nothing anywhere said a URL was the missing
    piece.
    """
    from wizard.cli.parser.frontend import browsable

    sock, port = _listener(socket.AF_INET)
    try:
        _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
        _vite_config(tmp_path / "client", port)
        assert browsable(str(tmp_path)).url == f"http://localhost:{port}"
    finally:
        sock.close()


def test_a_client_that_is_not_running_is_not_browsed(tmp_path):
    """A URL is being put into the request on the user's behalf; it has to answer.

    Browsing a dead port starts the browser plane, watches it fail to navigate,
    and reports a failure that reads as the wizard's rather than as a server
    nobody started. The intent screen still names it — that is a suggestion to
    the reader, not a target for the runtime.
    """
    from wizard.cli.parser.frontend import browsable

    _package(tmp_path, "client", dev_deps={"vite": "^5"}, scripts={"dev": "vite"})
    _vite_config(tmp_path / "client", _free_port())
    assert browsable(str(tmp_path)) is None
    assert suggestion_for(str(tmp_path))[1] != "", "the user is still told about it"


def test_a_project_with_no_client_browses_nothing(tmp_path):
    from wizard.cli.parser.frontend import browsable

    _package(tmp_path, "api", deps={"express": "^4"}, scripts={"start": "node s.js"})
    assert browsable(str(tmp_path)) is None


def test_a_directory_that_is_not_a_repository_browses_nothing(tmp_path):
    from wizard.cli.parser.frontend import browsable

    assert browsable(str(tmp_path / "nope")) is None


def test_the_hint_says_the_browser_will_open_it_not_that_the_user_must():
    """Telling the reader to do what the wizard already does makes a working
    feature read as a missing one — which is how this was reported."""
    line = hint_for(Frontend("client", "vite", "dev", 5173, listening=True))
    assert "will open it" in line
    assert "add that URL" not in line


# ── The intent screen ─────────────────────────────────────────────────────────

def _intent_frame(hint: str, has_frontend: bool) -> str:
    """The intent screen's text, with the ANSI escapes resolved."""
    from prompt_toolkit.formatted_text import to_formatted_text

    from wizard.cli.tui.widgets import command_box, intent_content, render_to_ansi

    ansi = render_to_ansi(
        command_box(intent_content("investigate", "architecture", "/repo",
                                   hint, has_frontend)),
        78,
    )
    return "".join(text for _, text in to_formatted_text(ansi))


def test_the_intent_screen_shows_the_hint():
    frame = _intent_frame("vite client is serving at http://localhost:5173", True)
    assert "http://localhost:5173" in frame
    assert "F2" in frame, "the hint is not actionable without saying how to accept it"


def test_the_intent_screen_is_unchanged_when_there_is_no_client():
    """A project with no client must not grow an empty section saying so."""
    frame = _intent_frame("", False)
    assert "◈" not in frame
    assert "F2" not in frame
