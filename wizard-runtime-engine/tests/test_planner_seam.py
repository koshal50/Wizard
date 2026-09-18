"""Phase 2 seam — the Runtime <-> Planner contract.

These lock the two defects that made every planner-backed investigation stall:

  1. HttpPlanner joined "<origin>/plan" + "/plan/initial" into "/plan/plan/initial",
     so a correctly-configured planner returned 404 and run() failed the whole
     investigation.
  2. The /plan/next packet carried only kg_summary and prose missing_evidence.
     The planner's provider keys off structured fields (missing_requirements,
     goal_technology, priority_files, allow_execution, file_observation_ids), so
     it planned for "unknown" technology against no requirements and answered
     with an empty batch — the loop then broke out with goals still open.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.contracts.node import Hypothesis, HypothesisKind
from wizard_kernel.contracts.plan import GoalDefinition, TechnologyEntry, TechnologyPlan
from wizard_kernel.control import loop as kernel_loop
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.ports.planner import HttpPlanner
from wizard_kernel.reality.observations import ObservationStore
from wizard_kernel.session.budget import BudgetManager
from wizard_kernel.session.investigation import Investigation


# ── 1. URL joining ────────────────────────────────────────────────────────────

class _RecordingPlanner(BaseHTTPRequestHandler):
    """Records the path each POST arrives on so the test can assert the join."""
    paths: list[str] = []
    response: dict = {"technologies": [], "seed_nodes": []}

    # Close the connection with the response rather than holding it open: the
    # client is a one-shot httpx.post, so there is nothing to keep alive.
    protocol_version = "HTTP/1.0"

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler's naming
        # Drain the request body before answering. The client always sends one,
        # and a socket closed with unread bytes still in its receive buffer gets
        # an RST from Windows rather than a clean FIN — which the client, still
        # reading the response, reports as "WinError 10053: an established
        # connection was aborted". That is a race between the response and the
        # RST, so it showed up as an intermittent failure in whichever test
        # happened to lose it, and it looked like flakiness rather than a server
        # that never read what was sent to it.
        length = int(self.headers.get("content-length") or 0)
        if length:
            self.rfile.read(length)

        _RecordingPlanner.paths.append(self.path)
        body = json.dumps(_RecordingPlanner.response).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.send_header("connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.fixture
def recording_planner():
    _RecordingPlanner.paths = []
    # Threading, not the single-threaded HTTPServer: one request whose socket
    # lingers must not block the next test's request behind it.
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingPlanner)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.mark.parametrize("suffix", ["", "/plan", "/plan/"])
def test_planner_url_never_doubles_the_plan_segment(recording_planner, suffix):
    """Any of the three natural spellings must reach /plan/initial exactly once."""
    planner = HttpPlanner(recording_planner + suffix)
    planner.next_nodes({"investigation_id": "inv_test"})
    assert _RecordingPlanner.paths == ["/plan/next"]


# ── 2. The /plan/next packet ──────────────────────────────────────────────────

# Nodes are built by hand in the queue tests below; a read node's hypothesis is
# evaluated by the loop, but these tests only inspect the graph, so the simplest
# kind that always validates is the honest choice.
_ALWAYS = Hypothesis(kind=HypothesisKind.always_success)


def _fixture_plan() -> TechnologyPlan:
    return TechnologyPlan(technologies=[
        TechnologyEntry(
            name="Python", confidence="high", signals=["pyproject.toml"],
            priority_files=["pyproject.toml", "setup.cfg", "pyproject.toml"],
            initial_goals=[
                GoalDefinition(name="Verify Runtime", required_claim_types=["RUNTIME"],
                               requires_execution_evidence=True),
                GoalDefinition(name="Verify Dependencies", required_claim_types=["PACKAGE"]),
            ],
        ),
    ])


def _fixture_goals() -> GoalEngine:
    goals = GoalEngine("inv_test")
    for i, gd in enumerate(_fixture_plan().technologies[0].initial_goals):
        goals.add(Goal(id=f"goal_{i}", name=gd.name,
                       required_claim_types=list(gd.required_claim_types),
                       requires_execution_evidence=gd.requires_execution_evidence))
    return goals


def _context(goals=None, kg=None, obs_store=None, budget=None, graph=None,
             completed_ids=None):
    inv = Investigation(id="inv_test", repository_path="/repo",
                        intent="investigate", targets=[], options={})
    return kernel_loop._planner_next_context(
        inv,
        goals if goals is not None else _fixture_goals(),
        kg if kg is not None else KnowledgeGraph("inv_test"),
        _fixture_plan(),
        budget if budget is not None else BudgetManager(20),
        obs_store if obs_store is not None else ObservationStore("inv_test"),
        "need_more_work",
        graph=graph,
        completed_ids=completed_ids if completed_ids is not None else set(),
    )


def test_packet_carries_structured_requirements():
    """The provider reads claim_type as a field; prose alone left it empty."""
    ctx = _context()
    assert ctx["missing_requirements"] == [
        {"claim_type": "RUNTIME", "goal_id": "goal_0", "goal_name": "Verify Runtime",
         "expected_value": None, "description": "No claims of type 'RUNTIME' for goal 'Verify Runtime'"},
        {"claim_type": "PACKAGE", "goal_id": "goal_1", "goal_name": "Verify Dependencies",
         "expected_value": None, "description": "No claims of type 'PACKAGE' for goal 'Verify Dependencies'"},
    ]
    # The prose view must describe exactly the same gaps, in the same order.
    assert ctx["missing_evidence"] == [r["description"] for r in ctx["missing_requirements"]]


def test_packet_opts_into_execution_and_names_the_technology():
    ctx = _context()
    assert ctx["allow_execution"] is True
    assert ctx["goal_technology"] == "Python"
    assert ctx["budget_remaining"] == 20
    assert ctx["repo_root"] == "/repo"


def test_packet_priority_files_are_deduplicated_in_plan_order():
    assert _context()["priority_files"] == ["pyproject.toml", "setup.cfg"]


def test_packet_reports_files_already_read_and_parsed():
    """Without these the planner re-proposes reads the kernel then rejects as duplicates."""
    store = ObservationStore("inv_test")
    store.append(node_id="n1", source_tool="read_file", obs_type="file_content",
                 payload={"ok": True, "meta": {"path": "package.json"},
                          "data": {"path": "package.json", "parsed": {"name": "x"}}})
    store.append(node_id="n2", source_tool="read_file", obs_type="file_content",
                 payload={"ok": True, "meta": {"path": "README.md"},
                          "data": {"path": "README.md", "parsed": None}})
    # A failed read is not evidence the file was read.
    store.append(node_id="n3", source_tool="read_file", obs_type="file_content",
                 payload={"ok": False, "meta": {"path": "gone.txt"}, "data": None})

    ctx = _context(obs_store=store)
    read_ids = ctx["file_observation_ids"]
    assert set(read_ids) == {"package.json", "README.md"}
    # Only the JSON read produced a parse result — no parse tool exists in the kernel.
    assert set(ctx["parsed_observation_ids"]) == {"package.json"}


def test_packet_indexes_a_windows_path_the_way_the_planner_spells_it():
    """A nested file read on Windows must not look unread to a forward-slash planner.

    The planner holds the manifest's file list, which carries the platform's
    native separator ("client\\src\\app.js" on Windows), while this index is built
    from what the tool reported after ToolRequestValidator resolved the path.
    Comparing the two literally makes a file the Runtime just read look unread, so
    the planner proposes it again — and because the validator canonicalises before
    fingerprinting, that repeat is caught as a duplicate and the node *fails*,
    spending a budget slot on a question that was already answered.
    """
    store = ObservationStore("inv_test")
    store.append(node_id="n1", source_tool="read_file", obs_type="file_content",
                 payload={"ok": True, "meta": {"path": "client\\src\\app.js"},
                          "data": {"path": "client\\src\\app.js", "parsed": None}})

    ctx = _context(obs_store=store)
    # The key is the comparison form both sides agree on, so a planner holding
    # either spelling matches it. It is a key, not a path to hand to a tool.
    assert set(ctx["file_observation_ids"]) == {"client/src/app.js"}


def test_packet_reports_reads_that_are_queued_but_have_not_run_yet():
    """The index says what has run; the queue says what is already coming.

    Reporting only the first lets two /plan/next calls made against the same
    observation state return the same batch of reads. Both batches enter the
    graph, the first one reads the file, and the second one's requests are then
    refused as duplicates — a failed node and a spent budget slot per file, for
    evidence that was already on its way.
    """
    from wizard_kernel.control.investigation_graph import InvestigationGraph
    from wizard_kernel.contracts.node import InvestigationNode

    graph = InvestigationGraph("inv_test")
    graph.add(InvestigationNode(
        id="node_pending", type="read", goal_id="goal_0",
        action={"tool": "read_file", "params": {"path": "client\\src\\app.js"}},
        hypothesis=_ALWAYS))
    graph.add(InvestigationNode(
        id="node_other", type="read", goal_id="goal_0",
        action={"tool": "read_file", "params": {"path": "setup.cfg"}},
        hypothesis=_ALWAYS))
    # A node whose turn has been taken is no longer "coming": whatever it reads
    # is either in the observation index already or never will be.
    graph.add(InvestigationNode(
        id="node_done", type="read", goal_id="goal_0",
        action={"tool": "read_file", "params": {"path": "pyproject.toml"}},
        hypothesis=_ALWAYS))

    ctx = _context(graph=graph, completed_ids={"node_done"})
    # Canonical spelling, for the same reason the observation index uses it.
    assert set(ctx["queued_read_paths"]) == {"client/src/app.js", "setup.cfg"}


def test_packet_queues_nothing_when_there_is_no_graph():
    """The key is always present, so a planner never has to guess at its absence."""
    assert _context()["queued_read_paths"] == []


def test_a_planner_node_repeating_a_queued_action_is_not_added():
    """The kernel owns the graph; adding a node it will refuse wastes a slot."""
    from wizard_kernel.control.investigation_graph import InvestigationGraph
    from wizard_kernel.contracts.node import InvestigationNode

    graph = InvestigationGraph("inv_test")
    graph.add(InvestigationNode(
        id="node_pending", type="read", goal_id="goal_0",
        action={"tool": "read_file", "params": {"path": "package.json"}},
        hypothesis=_ALWAYS))

    same = InvestigationNode(
        id="node_repeat", type="read", goal_id="goal_0",
        action={"tool": "read_file", "params": {"path": "package.json"}},
        hypothesis=_ALWAYS)
    assert kernel_loop._already_scheduled(graph, set(), same)

    different = InvestigationNode(
        id="node_new", type="read", goal_id="goal_0",
        action={"tool": "read_file", "params": {"path": "server/package.json"}},
        hypothesis=_ALWAYS)
    assert not kernel_loop._already_scheduled(graph, set(), different)


def test_a_failed_action_is_not_proposed_again():
    """A failed node's action can never run a second time, so re-proposing it is waste.

    The validator dedupes on (tool, params) for the whole investigation, and a
    node reaches `failed` either by running (fingerprint registered) or by being
    refused as a duplicate (fingerprint already registered). Either way the next
    node carrying that action is certain to be refused — so letting it into the
    graph spends a budget slot to produce a rejection. A single failing command
    was re-proposed every round until the budget ran out, and the run ended
    having learned nothing after the first attempt.
    """
    from wizard_kernel.control.investigation_graph import InvestigationGraph
    from wizard_kernel.contracts.node import InvestigationNode

    graph = InvestigationGraph("inv_test")
    graph.add(InvestigationNode(
        id="node_failed", type="execute", goal_id="goal_0",
        action={"tool": "execute_command", "params": {"command": "npm test --silent"}},
        hypothesis=_ALWAYS))
    graph.mark_failed("node_failed")

    retry = InvestigationNode(
        id="node_retry", type="execute", goal_id="goal_0",
        action={"tool": "execute_command", "params": {"command": "npm test --silent"}},
        hypothesis=_ALWAYS)
    assert kernel_loop._already_scheduled(graph, set(), retry)


def test_a_browser_action_may_be_repeated():
    """The validator exempts browser tools, and this check has to agree with it.

    Identical parameters address a changed live page, so a repeat is a
    re-observation rather than a cycle. Skipping it here would silently remove
    work the validator was written to allow.
    """
    from wizard_kernel.control.investigation_graph import InvestigationGraph
    from wizard_kernel.contracts.node import InvestigationNode

    graph = InvestigationGraph("inv_test")
    graph.add(InvestigationNode(
        id="node_nav", type="browser", goal_id="goal_0",
        action={"tool": "browser_navigate", "params": {"url": "http://localhost:3000"}},
        hypothesis=_ALWAYS))

    again = InvestigationNode(
        id="node_nav2", type="browser", goal_id="goal_0",
        action={"tool": "browser_navigate", "params": {"url": "http://localhost:3000"}},
        hypothesis=_ALWAYS)
    assert not kernel_loop._already_scheduled(graph, set(), again)


def test_active_technology_follows_the_open_goal_not_the_plan_order():
    """Several technologies in a plan: pick the one with work left, not technologies[0]."""
    plan = TechnologyPlan(technologies=[
        TechnologyEntry(name="Docker", confidence="high", signals=[], priority_files=[],
                        initial_goals=[GoalDefinition(name="Verify Containerization",
                                                      required_claim_types=["DEPLOYMENT"])]),
        TechnologyEntry(name="Python", confidence="high", signals=[], priority_files=[],
                        initial_goals=[GoalDefinition(name="Verify Runtime",
                                                      required_claim_types=["RUNTIME"])]),
    ])
    goals = GoalEngine("inv_test")
    goals.add(Goal(id="g0", name="Verify Containerization", required_claim_types=["DEPLOYMENT"]))
    goals.add(Goal(id="g1", name="Verify Runtime", required_claim_types=["RUNTIME"]))
    goals.mark_satisfied("g0")

    assert kernel_loop._active_technology(plan, goals) == "Python"


def test_active_technology_falls_back_when_nothing_is_open():
    goals = _fixture_goals()
    for g in goals.all():
        goals.mark_satisfied(g.id)
    assert kernel_loop._active_technology(_fixture_plan(), goals) == "Python"
    assert kernel_loop._active_technology(TechnologyPlan(technologies=[]), goals) == "unknown"


def test_missing_requirements_requires_execution_evidence_for_execution_goals():
    """A satisfied-looking claim without execution-tier evidence is still a gap."""
    from wizard_kernel.belief.evidence import EvidenceEngine
    from wizard_kernel.reality.observations import ObservationStore as Store

    store = Store("inv_test")
    obs = store.append(node_id="n1", source_tool="read_file", obs_type="file_content",
                       payload={"ok": True, "data": {"content": "x"}})
    kg = KnowledgeGraph("inv_test")
    EvidenceEngine(kg).admit(inv_id="inv_test", claim_type="RUNTIME", key="language",
                             value="Python", obs_id=obs.id, support_type="support",
                             source_tier="config_parse", node_id="n1")

    ctx = _context(kg=kg)
    runtime = [r for r in ctx["missing_requirements"] if r["claim_type"] == "RUNTIME"]
    assert len(runtime) == 1
    assert "lacks execution evidence" in runtime[0]["description"]
    # PACKAGE has no claims at all, so it reports the absence instead.
    pkg = [r for r in ctx["missing_requirements"] if r["claim_type"] == "PACKAGE"]
    assert "No claims of type" in pkg[0]["description"]


# ── 3. What the page showed, not just that it was visited ─────────────────────

def _browser_obs(store, node_id: str, tool: str, data: dict):
    """Append a browser observation the way the ToolExecutor envelopes it."""
    return store.append(node_id=node_id, source_tool=tool, obs_type="page_content",
                        payload={"ok": True, "data": data})


def test_packet_carries_the_controls_of_the_last_page():
    """`visited_urls` names a page; only the observation names what is ON it.

    A script step addresses a control, and a control's role and accessible name
    exist in exactly one place — the observation of the page that offered it.
    Without this the planner can propose a navigate and nothing else.
    """
    store = ObservationStore("inv_test")
    _browser_obs(store, "n1", "browser_snapshot", {
        "url": "https://app.test/login",
        "controls": [{"role": "textbox", "name": "Email",
                      "selector": 'role=textbox[name="Email"]'}],
    })
    ctx = _context(obs_store=store)
    assert ctx["page_url"] == "https://app.test/login"
    assert [c["name"] for c in ctx["page_controls"]] == ["Email"]


def test_packet_reports_the_page_the_run_is_actually_on():
    """The LAST page wins: after a click the current page is the one it produced.

    Taking the first page-shaped observation would have the planner write a
    script against a page the run left several steps ago.
    """
    store = ObservationStore("inv_test")
    _browser_obs(store, "n1", "browser_snapshot",
                 {"url": "https://app.test/login", "controls": [{"role": "textbox", "name": "Email"}]})
    _browser_obs(store, "n2", "browser_snapshot",
                 {"url": "https://app.test/dashboard",
                  "controls": [{"role": "button", "name": "Sign out"}]})
    ctx = _context(obs_store=store)
    assert ctx["page_url"] == "https://app.test/dashboard"
    assert [c["name"] for c in ctx["page_controls"]] == ["Sign out"]


def test_a_navigate_updates_the_url_without_blanking_the_controls():
    """A navigate carries a url and no controls — it must not erase them.

    The snapshot that preceded it is still the only record of what is on the
    page, and a run that navigates to a URL it has already snapshotted would
    otherwise be handed an empty control list and stop being able to act.
    """
    store = ObservationStore("inv_test")
    _browser_obs(store, "n1", "browser_snapshot",
                 {"url": "https://app.test/login", "controls": [{"role": "textbox", "name": "Email"}]})
    store.append(node_id="n2", source_tool="browser_navigate", obs_type="browser_action",
                 payload={"ok": True, "data": {"url": "https://app.test/login", "status": 200}})
    ctx = _context(obs_store=store)
    assert ctx["page_url"] == "https://app.test/login"
    assert [c["name"] for c in ctx["page_controls"]] == ["Email"]


def test_no_browser_evidence_means_no_page_claims():
    """A repository-only run must not report a page it never opened."""
    ctx = _context()
    assert ctx["page_url"] == "" and ctx["page_controls"] == []
    assert ctx["page_fingerprint"] == ""
