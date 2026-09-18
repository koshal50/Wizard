"""What the live browser pane is told, and what it must never be told.

The pane is the only place a user watches an investigation happen, and every
sentence it shows comes from `GET /frontier`. Two ways it used to mislead:

  * A finished run still advertised a `next` node. The loop stops the moment
    every goal is satisfied, so planned work that turned out to be unnecessary
    stays `waiting` forever — and the pane rendered that as "Next: browser_navigate"
    under a status of "completed".
  * A blank pane could not say WHY it was blank. "The agent never opened a page"
    and "you opened this view after the run finished and the browser closed with
    it" look identical from a blank frame, and they need opposite responses.

And one way the Engine misled about its own refusals: a 400 whose reason lived in
the JSON body reached the CLI as the bare string "HTTP Error 400: Bad Request",
because HTTPError subclasses URLError and the generic handler won.
"""
import pytest
from fastapi.testclient import TestClient

from wizard_kernel.api.app import app
from wizard_kernel.api.deps import get_manager
from wizard_kernel.contracts.node import InvestigationNode, Hypothesis
from wizard_kernel.contracts.request import InvestigationRequest, InvestigationOptions
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.control.investigation_graph import InvestigationGraph, register_graph
from wizard_kernel.session.manager import InvestigationManager


@pytest.fixture
def client():
    fresh = InvestigationManager()
    app.dependency_overrides[get_manager] = lambda: fresh
    with TestClient(app, raise_server_exceptions=True) as c:
        c.manager = fresh
        yield c
    app.dependency_overrides.clear()


def _node(node_id: str, tool: str, state: str, url: str = "", depends_on=None):
    """A minimal real node — the graph stores pydantic models, not dicts."""
    return InvestigationNode(
        id=node_id,
        type="browser" if tool.startswith("browser_") else "read",
        action={"tool": tool, "params": {"url": url} if url else {}},
        hypothesis=Hypothesis(kind="always_success", rationale="test"),
        depends_on=depends_on or [],
        state=state,
    )


def _set_state(client, inv: str, state: LifecycleState) -> None:
    """Move the investigation to `state`, and prove it got there.

    Asserted rather than assumed: `manager.update` refuses to move an
    investigation out of a terminal state, so a test that quietly failed to set
    the state it meant would assert against the wrong one and could pass for a
    reason that has nothing to do with the code.
    """
    client.manager.update(inv, state=state)
    actual = client.manager.get(inv).state
    assert actual == state, f"could not put the investigation in {state}: it is {actual}"


def _graph(inv_id: str, nodes: list[InvestigationNode]) -> InvestigationGraph:
    graph = InvestigationGraph(inv_id)
    for n in nodes:
        graph.add(n)
    register_graph(inv_id, graph)
    return graph


def _created(client, **options):
    """An investigation whose state this test controls, and whose graph it owns.

    Deliberately NOT `POST /v1/investigations`: that route starts a real run
    loop on a background thread, against a repository path that does not exist
    here, so the investigation races to `failed` on its own. Terminal states are
    absorbing, so every later `update()` is refused — and a test asserting "a
    finished run shows no next" would then pass because the run happened to
    crash, not because the code under test did anything. Creating the record
    directly keeps the state a property of the test.
    """
    inv = client.manager.create(InvestigationRequest(
        repository_path="/tmp/test-repo",
        intent="investigate",
        targets=["architecture"],
        options=InvestigationOptions(**options),
    ))
    return inv.id


# ── `next` must be empty once the run is over ────────────────────────────────

def test_a_finished_run_advertises_no_next_node(client):
    """The node left waiting is real; calling it "next" is not.

    The loop stops when every goal is satisfied, so a queued node can survive a
    completed run. Reporting it under `next` contradicts the status the pane
    prints directly above it.
    """
    inv = _created(client)
    _graph(inv, [
        _node("n1", "read_file", "complete"),
        _node("n2", "browser_navigate", "waiting", url="http://127.0.0.1:8899/"),
    ])
    _set_state(client, inv, LifecycleState.completed)

    f = client.get(f"/v1/investigations/{inv}/frontier").json()
    assert f["status"] == "completed"
    assert f["next"] == [], "a finished run still claimed work was next"
    assert f["now"] is None


def test_a_finished_run_still_reports_the_work_it_never_did(client):
    """Emptied `next` must not become a cover-up.

    "Nothing left to do" and "the plan had work that was never needed" are
    different facts about a run, and only one of them is visible in `next` once
    it is emptied for honesty's sake.
    """
    inv = _created(client)
    _graph(inv, [
        _node("n1", "read_file", "complete"),
        _node("n2", "browser_navigate", "waiting", url="http://127.0.0.1:8899/"),
        _node("n3", "browser_snapshot", "waiting", depends_on=["n2"]),
    ])
    _set_state(client, inv, LifecycleState.completed)

    f = client.get(f"/v1/investigations/{inv}/frontier").json()
    assert f["counts"]["never_ran"] == 2
    assert [n["tool"] for n in f["never_ran"]] == ["browser_navigate", "browser_snapshot"]


def test_a_live_run_still_shows_what_is_next(client):
    """The guarantee for finished runs must not flatten the live view.

    Emptying `next` unconditionally would delete the feature the pane exists for.
    """
    inv = _created(client)
    _graph(inv, [
        _node("n1", "read_file", "running"),
        _node("n2", "browser_navigate", "waiting", url="http://127.0.0.1:8899/"),
    ])
    _set_state(client, inv, LifecycleState.investigation_loop)

    f = client.get(f"/v1/investigations/{inv}/frontier").json()
    assert f["now"]["tool"] == "read_file"
    assert [n["tool"] for n in f["next"]] == ["browser_navigate"]
    assert f["counts"]["never_ran"] == 0


@pytest.mark.parametrize("state", [
    LifecycleState.completed, LifecycleState.failed, LifecycleState.cancelled,
])
def test_every_terminal_state_empties_next(client, state):
    inv = _created(client)
    _graph(inv, [_node("n1", "browser_snapshot", "waiting")])
    _set_state(client, inv, state)
    f = client.get(f"/v1/investigations/{inv}/frontier").json()
    assert f["next"] == []


# ── Did a page actually open? ────────────────────────────────────────────────

def test_pages_opened_reports_the_url_the_agent_reached(client):
    """The evidence that separates the two blank panes.

    A run whose navigate node reached `complete` opened a page. Without this the
    pane can only guess, and one of the two guesses sends the user to debug a
    browser that worked.
    """
    inv = _created(client, browser_enabled=True)
    _graph(inv, [
        _node("n1", "browser_navigate", "complete", url="http://127.0.0.1:8899/"),
        _node("n2", "browser_extract", "complete"),
    ])
    _set_state(client, inv, LifecycleState.completed)

    f = client.get(f"/v1/investigations/{inv}/frontier").json()
    assert f["pages_opened"] == ["http://127.0.0.1:8899/"]


def test_pages_opened_is_empty_when_navigation_never_ran(client):
    inv = _created(client, browser_enabled=True)
    _graph(inv, [
        _node("n1", "read_file", "complete"),
        _node("n2", "browser_navigate", "waiting", url="http://127.0.0.1:8899/"),
    ])
    _set_state(client, inv, LifecycleState.completed)

    f = client.get(f"/v1/investigations/{inv}/frontier").json()
    assert f["pages_opened"] == []


def test_a_navigate_that_failed_is_not_evidence_of_a_page(client):
    """`failed` is not `complete`. A navigate that raised opened nothing."""
    inv = _created(client, browser_enabled=True)
    _graph(inv, [_node("n1", "browser_navigate", "failed", url="http://127.0.0.1:8899/")])
    _set_state(client, inv, LifecycleState.failed)

    f = client.get(f"/v1/investigations/{inv}/frontier").json()
    assert f["pages_opened"] == []


# ── The Engine's refusals must reach the user ────────────────────────────────

def test_docker_mode_without_a_daemon_is_refused_before_anything_starts(client, monkeypatch):
    """Fail at request time, with the reason — not minutes later inside the sandbox.

    The check itself is monkeypatched: this machine's docker daemon may be up or
    down, and the behaviour under test is what the Engine does with the answer,
    not what the answer currently is.
    """
    monkeypatch.setattr(
        "wizard_kernel.api.routes_investigations.docker_status",
        lambda *a, **k: (False, "failed to connect to the docker API at npipe:////./pipe/x"),
    )
    before = len(client.manager.all())

    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/test-repo",
        "intent": "investigate",
        "targets": ["architecture"],
        "options": {"sandbox_mode": "docker"},
    })

    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "npipe" in detail, "the Engine's own reason was dropped"
    assert "local_dev" in detail, "the refusal did not offer the way forward"
    assert len(client.manager.all()) == before, "a refused request left an investigation behind"


def test_docker_mode_with_a_daemon_is_accepted(client, monkeypatch):
    """The refusal must be about the machine, not about the mode."""
    monkeypatch.setattr(
        "wizard_kernel.api.routes_investigations.docker_status",
        lambda *a, **k: (True, "docker server 27.0.1"),
    )
    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/test-repo",
        "intent": "investigate",
        "targets": ["architecture"],
        "options": {"sandbox_mode": "docker"},
    })
    assert r.status_code == 201


def test_the_default_mode_is_never_checked_against_docker(client, monkeypatch):
    """local_dev must not so much as probe for Docker.

    Probing would make a run's success depend on a daemon it never uses.
    """
    def explode(*a, **k):
        raise AssertionError("the default sandbox mode probed for Docker")

    monkeypatch.setattr("wizard_kernel.api.routes_investigations.docker_status", explode)
    r = client.post("/v1/investigations", json={
        "repository_path": "/tmp/test-repo",
        "intent": "investigate",
        "targets": ["architecture"],
    })
    assert r.status_code == 201
