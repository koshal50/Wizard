"""Planner port — protocol + MockPlanner + HttpPlanner (Phase 6). Phase 3."""
from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from wizard_kernel.contracts.manifest import RepositoryManifest
from wizard_kernel.contracts.node import (
    ClaimTemplate, Hypothesis, HypothesisKind, InvestigationNode,
)
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.plan import GoalDefinition, TechnologyPlan, TechnologyEntry
from wizard_kernel.ports.goal_policy import (
    INSPECTED,
    MANIFEST,
    NAMED,
    NAMED_GOALS,
    OPERATING_FAMILIES,
    goal_evidence_for,
    goals_for_family,
    goals_named_by_command,
    names_operation_for,
)
from wizard_kernel.ports.interaction_script import interaction_script_for


@runtime_checkable
class PlannerPort(Protocol):
    def initial(
        self,
        manifest: RepositoryManifest,
        intent: str,
        targets: list[str],
        options: dict | None = None,
        question: str = "",
    ) -> TechnologyPlan: ...

    def next_nodes(self, context: dict) -> list[InvestigationNode]: ...

    def interpret(
        self, node: InvestigationNode, obs: Observation
    ) -> list[InvestigationNode]: ...


# ── Mock Planner ──────────────────────────────────────────────────────────────

class MockPlanner:
    """The built-in planner: deterministic, offline, and honest about the command.

    It was called Mock and ignored `intent`, `targets` and `question` entirely,
    which made it a planner that answers every question the same way: `wizard
    report`, `wizard verify runtime` and `wizard explain architecture` planned the
    same two goals for any Node repository and produced runs that differed in
    nothing a reader could see. Because it is the planner a run gets whenever
    `options.planner_url` is unset, that sameness was also invisible — the run
    looked like a working one, and only `seams.resolved` named the planner that
    had been asked.

    It is not a mock any more, and the name is kept only because every caller and
    every test knows it. What it does now is the same thing the TypeScript planner
    does, read from the same table: `ports/goal_policy.py`, whose mirror is
    `wizard-investigation-planner/src/planner/goalPolicy.ts`.

    It is still deliberately shallow — it reads key files and proposes no further
    nodes — and that shallowness is the honest part. A planner with no LLM and no
    repository beyond the manifest cannot decide which file answers "how does auth
    work", and inventing a plausible-looking node list would be worse than
    proposing the one node that provably does something.

    One exception, and it is not a guess either: when the plan declares an
    `Operate Web Surface` goal, the steps that satisfy it are written from the
    page's own controls in `next_nodes`, by the same decision table the
    TypeScript planner uses (`ports/interaction_script.py`). Without it the goal
    and the nodes that close it would be declared by different code, and a run
    with a goal nothing plans the steps for reports failing at something it was
    never given the means to do.
    """

    def __init__(self, max_next_calls: int = 0) -> None:
        self._next_calls = 0
        self._max_next_calls = max_next_calls

    def initial(
        self,
        manifest: RepositoryManifest,
        intent: str,
        targets: list[str],
        options: dict | None = None,
        question: str = "",
    ) -> TechnologyPlan:
        options = options or {}
        targets = [t for t in (targets or []) if t]
        question = question or ""
        signals = set(manifest.key_files)

        # ── What the repository proposes ──────────────────────────────────────
        # Each entry is a technology and the goals the *repository* suggests for
        # it. Which of them survive is decided further down, by the command family.
        techs: list[dict] = []

        if "package.json" in signals:
            techs.append({
                "name": "Node.js", "confidence": "high", "signals": ["package.json"],
                "goals": ["Verify Runtime", "Verify Dependencies"],
                "priority_files": ["package.json"],
            })

        if "requirements.txt" in signals or "pyproject.toml" in signals:
            python_file = "requirements.txt" if "requirements.txt" in signals else "pyproject.toml"
            techs.append({
                "name": "Python", "confidence": "high", "signals": [python_file],
                "goals": ["Verify Runtime", "Verify Dependencies"],
                "priority_files": [python_file],
            })

        if "Dockerfile" in signals:
            techs.append({
                "name": "Docker", "confidence": "high", "signals": ["Dockerfile"],
                # Named "Verify Containerization" and not "Verify Docker Build"
                # because it is the name the shared vocabulary routes. A request
                # that says "docker" or "deploy" names this goal, so a goal spelled
                # differently would be dropped by the family filter as one the user
                # never asked for — and `verify docker` would plan nothing at all.
                "goals": ["Verify Containerization"],
                "priority_files": ["Dockerfile"],
            })

        # A browser target is a target like any other. The Runtime owns whether a
        # browser plane exists (options.browser_enabled); the Planner owns what to
        # do with it. Without this branch an investigation that enabled a browser
        # and named a URL planned nothing at all for it — the plane started, the
        # page stayed blank, and no evidence was ever asked of it.
        web_urls = [t for t in targets if _looks_like_url(t)]
        if web_urls and options.get("browser_enabled"):
            # Reaching a page and operating it are two goals closed by two
            # different pieces of evidence — WEB by a navigate, INTERACTION by a
            # press — and a run that operates a page necessarily does both, so
            # both are proposed whenever the command operates and the family
            # filter is what decides which of them survives. `verify <url>` keeps
            # only the stronger one; `report` keeps only the reading one.
            #
            # Whether this command operates at all is read from the shared gate
            # and never re-decided: proposing "Operate Web Surface" while
            # planning only a navigate is the unsatisfiable goal this table
            # exists to prevent.
            web_goals = ["Verify Web Surface"]
            if names_operation_for(intent, targets, question):
                web_goals.append("Operate Web Surface")
            techs.append({
                "name": "Web", "confidence": "high", "signals": [f"target: {web_urls[0]}"],
                "goals": web_goals, "priority_files": [],
            })
        # The URL the browser nodes navigate to, kept here because whether those
        # nodes are added is decided below, by whether the Web goal survived the
        # family filter — the nodes and the goal are one decision.
        web_url = web_urls[0] if web_urls else ""

        if not techs:
            # Unknown repo — a discovery node with no required claim types.
            techs.append({
                "name": "Unknown", "confidence": "low", "signals": [],
                "goals": ["Investigate Repository"], "priority_files": [],
            })

        # ── Where each goal came from ─────────────────────────────────────────
        # Everything proposed so far came from the repository, and the map says so
        # before the user's own goals are attached and re-tag themselves. The
        # command family reads this: "Verify Runtime" is context when the manifest
        # suggests it for a Node repository, and the question itself when someone
        # runs `verify runtime`.
        origin: dict[str, str] = {}
        for tech in techs:
            for goal in tech["goals"]:
                origin[goal] = MANIFEST

        # The command, not just its text: `verify http://localhost:5173` is the
        # user choosing to prove a running app works, and the address is the
        # object rather than a word the vocabulary can match. Read from the same
        # gate the Web technology above reads, so the goals, the family filter
        # that keeps them, and the script in `next_nodes` are one decision seen
        # four times.
        named = goals_named_by_command(intent, targets, question)

        # A goal the request's own words name becomes the user's, even when the
        # repository had already suggested it — and it is re-tagged, not merely
        # added. `Verify Dependencies` is context in a Node repository and the
        # question in `explain dependencies`, and one map cannot say both: left as
        # MANIFEST, the explain branch reads it as repository context, finds
        # nothing the user asked for, and falls back to describing the whole
        # repository. The re-tag is what makes the two runs different.
        for goal in named:
            origin[goal] = NAMED

        # The user's own words, attached to the technology the run will actually
        # work on. Sorted so that one request plans the same way twice.
        host = techs[0]
        for goal in sorted(named):
            if goal not in {g for tech in techs for g in tech["goals"]}:
                host["goals"].append(goal)

        # A target the vocabulary does not know is a subject, not a probe: nobody
        # can run "architecture". It becomes a read-the-files goal named after the
        # user's own word, which is the only thing a plan can honestly do with it —
        # and the FILE_READ evidence it needs is evidence the repository's own
        # goals already go and get.
        for target in targets:
            if _looks_like_url(target) or _names_a_known_goal(target):
                continue
            inspected = f"Inspect {target}"
            if inspected in origin:
                continue
            origin[inspected] = INSPECTED
            host["goals"].append(inspected)

        # ── What the command family will pay for ──────────────────────────────
        # The last step and the only one that REMOVES a goal. Everything above
        # proposes and this decides; before it existed all four families inherited
        # the repository's whole set unconditionally and were one command.
        proposed = [(goal, origin[goal]) for tech in techs for goal in tech["goals"]]
        keep = set(goals_for_family(intent, proposed, named))

        technologies: list[TechnologyEntry] = []
        seed_nodes: list[InvestigationNode] = []
        for tech in techs:
            kept = [g for g in tech["goals"] if g in keep]
            if not kept:
                continue
            technologies.append(TechnologyEntry(
                name=tech["name"],
                confidence=tech["confidence"],
                signals=list(tech["signals"]),
                # Evidence is read from the shared table rather than written out
                # per goal here, so the built-in planner and the goal engine
                # cannot disagree about what closes a goal — which they did:
                # "Verify Runtime" was proposed with no execution requirement, so
                # this planner called it proven by reading package.json.
                initial_goals=[
                    GoalDefinition(
                        name=name,
                        required_claim_types=list(goal_evidence_for(name).required_claim_types),
                        requires_execution_evidence=goal_evidence_for(name).requires_execution_evidence,
                    )
                    for name in kept
                ],
                priority_files=list(tech["priority_files"]),
            ))
            if tech["priority_files"]:
                seed_nodes.append(_make_read_node(tech["priority_files"][0], "goal_0"))
            # The navigation chain is added only when the Web goal was kept. A
            # `report` keeps no goal that runs, and driving a browser to produce
            # one would be the same mistake the family filter exists to prevent —
            # the goal and the nodes that satisfy it are one decision.
            if tech["name"] == "Web" and web_url:
                seed_nodes.extend(_make_browser_nodes(web_url))

        if not seed_nodes:
            # A run with nothing to do still gets one look at the repository. Two
            # ways to arrive here and one rule for both: every goal was filtered
            # out (`wizard verify` on a repository with no key files at all), or
            # the goals that survived belong to a technology with no priority
            # file to read (`verify runtime` where there is no manifest to parse).
            # Neither is a reason for a run to end having done literally nothing,
            # and the scan is not a claim about the goals: it neither adds nor
            # substitutes one — it is what lets the report say what the
            # repository actually is when it says the question went unanswered.
            seed_nodes.append(_make_discover_node())

        return TechnologyPlan(technologies=technologies, seed_nodes=seed_nodes)

    def next_nodes(self, context: dict) -> list[InvestigationNode]:
        if self._next_calls >= self._max_next_calls:
            return []
        self._next_calls += 1
        return _interaction_nodes(context)

    def interpret(
        self, node: InvestigationNode, obs: Observation
    ) -> list[InvestigationNode]:
        # Unexpected result — nothing to add in mock
        return []


# ── HTTP Planner (Phase 6) ────────────────────────────────────────────────────

class HttpPlanner:
    """Calls Yash's planner service via HTTP. Phase 6."""

    def __init__(self, base_url: str) -> None:
        self._url = base_url.rstrip("/")
        # The planner service mounts its three handlers at /plan/*, and _post()
        # appends the full "/plan/initial" path itself. A caller that configures
        # the base as "<origin>/plan" — the natural reading of "the planner's
        # URL" — would therefore post to "/plan/plan/initial" and get a 404,
        # which run() converts into a fatal investigation. Strip the redundant
        # suffix rather than making every caller know this internal detail.
        if self._url.endswith("/plan"):
            self._url = self._url[: -len("/plan")]

    def _post(self, path: str, payload: dict) -> dict:
        import httpx
        r = httpx.post(f"{self._url}{path}", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def initial(
        self,
        manifest: RepositoryManifest,
        intent: str,
        targets: list[str],
        options: dict | None = None,
        question: str = "",
    ) -> TechnologyPlan:
        # browser_enabled and allowed_domains ride along because the planner is what
        # decides whether to plan a browser phase, and it cannot plan for a plane it
        # has not been told about. These are facts about the Runtime's capabilities,
        # not trust or truth — the planner still cannot execute anything with them.
        #
        # `question` travels separately from `intent` because they are different
        # inputs: `intent` is the command family (one of four verbs), `question` is
        # the sentence the user typed. The Planner plans what was asked, and the
        # sentence is the only field that says what that was.
        opts = options or {}
        data = self._post("/plan/initial", {
            "manifest": manifest.model_dump(mode="json"),
            "intent": intent,
            "targets": targets,
            "question": question,
            "browser_enabled": bool(opts.get("browser_enabled")),
            "allowed_domains": list(opts.get("allowed_domains") or []),
        })
        return TechnologyPlan.model_validate(data)

    def next_nodes(self, context: dict) -> list[InvestigationNode]:
        data = self._post("/plan/next", context)
        return [InvestigationNode.model_validate(n) for n in data.get("new_nodes", [])]

    def interpret(
        self, node: InvestigationNode, obs: Observation
    ) -> list[InvestigationNode]:
        # mode="json" is required, not cosmetic: Observation.created_at is a datetime,
        # and httpx's json= encoder is stdlib json.dumps, which raises TypeError on it.
        # loop._run_loop calls planner.interpret() unguarded, so that TypeError would
        # propagate to run()'s handler and fail the whole investigation on the first
        # escalated node.
        data = self._post("/plan/interpret", {
            "node": node.model_dump(mode="json"),
            "observation": obs.model_dump(mode="json"),
        })
        return [InvestigationNode.model_validate(n) for n in data.get("new_nodes", [])]


# ── Factory ───────────────────────────────────────────────────────────────────

def get_planner(planner_url: str | None) -> PlannerPort:
    if planner_url:
        return HttpPlanner(planner_url)
    return MockPlanner()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _node_id() -> str:
    return f"node_{uuid.uuid4().hex[:6]}"


def _make_read_node(filename: str, goal_id: str) -> InvestigationNode:
    return InvestigationNode(
        id=_node_id(),
        type="read",
        action={"tool": "read_file", "params": {"path": filename, "max_bytes": 65536}},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success),
        on_success=ClaimTemplate(
            claim_type="FILE_READ", key=filename, value=True,
        ),
        goal_id=goal_id,
    )


def _make_discover_node() -> InvestigationNode:
    return InvestigationNode(
        id=_node_id(),
        type="discovery",
        action={"tool": "list_tree", "params": {"max_depth": 3}},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success),
        on_success=ClaimTemplate(
            claim_type="DISCOVERY", key="tree", value=True,
        ),
    )


def _looks_like_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def _names_a_known_goal(target: str) -> bool:
    """Whether the shared vocabulary already has a goal for this word.

    A target the vocabulary knows is a probe — `runtime`, `testing`, `docker` —
    and it already produced a goal above by name. One it does not know is a
    subject, and a subject is what `Inspect …` is for. Asking this rather than
    listing the words here is what keeps the two in step: a word added to
    NAMED_GOALS stops producing a second, contrarily-named goal on the next run.
    """
    return any(pattern.search(target) for _, pattern in NAMED_GOALS)



def _interaction_nodes(context: dict) -> list[InvestigationNode]:
    """The steps that operate the page the run is standing on, or none.

    The one thing the built-in planner proposes after its seed nodes, and the
    only place it reads something the initial plan could not know. A control's
    role and accessible name exist in exactly one place — the observation of the
    page that offered it — so a script can only be written once a page has been
    reached, which is what the ongoing phase is for.

    Four gates, all of them refusals, and every one of them is a check the
    TypeScript planner makes too:

      - the plane must exist (`browser_enabled`);
      - the page must offer controls at all;
      - the command must be one that operates (read from the shared gate, so the
        goal the plan declared and the steps that close it cannot come apart);
      - and the script itself will refuse every control it cannot justify.

    Returning [] is the ordinary answer and not a failure: `report`, `explain`,
    and any run whose goal was already satisfied reach the end of the plan with
    nothing to do, which is exactly what the loop reads as "done".
    """
    if not context.get("browser_enabled"):
        return []
    controls = context.get("page_controls") or []
    if not controls:
        return []
    if not names_operation_for(
        str(context.get("intent") or ""),
        list(context.get("targets") or []),
        str(context.get("question") or ""),
    ):
        return []

    steps = interaction_script_for(
        url=str(context.get("page_url") or ""),
        controls=controls,
        allowed_domains=list(context.get("allowed_domains") or []),
        acted=list(context.get("interacted_selectors") or []),
    )

    # Chained, because a script is ordered: filling a form after submitting it is
    # not the same operation, and the Runtime runs a node only once its
    # dependencies have. The chain is also what makes the script legible in the
    # trace — one step per line, in the order the page will receive them.
    #
    # No success_claim, deliberately, matching the TypeScript planner. A step's
    # evidence is what the kernel's own extractors read out of the observation —
    # `interacted:<selector>` and `effect:<selector>` — and a claim asserted here
    # would be about the planner's intention rather than the page's behaviour.
    # "I clicked Sign in" is not the same finding as "clicking Sign in changed
    # the page", and only the second one is evidence.
    nodes: list[InvestigationNode] = []
    previous: str | None = None
    for step in steps:
        node_id = _node_id()
        params = {"selector": step.selector}
        if step.tool == "type":
            params["text"] = step.text or ""
        nodes.append(InvestigationNode(
            id=node_id,
            type="browser",
            action={"tool": f"browser_{step.tool}", "params": params},
            hypothesis=Hypothesis(kind=HypothesisKind.always_success),
            depends_on=[previous] if previous else [],
            goal_id="goal_web",
        ))
        previous = node_id
    return nodes


def _make_browser_nodes(url: str) -> list[InvestigationNode]:
    """Navigate, then read the page as an accessibility tree, then pull its text.

    Three nodes rather than one because each answers a different question and
    produces different WEB claims: navigate proves the host answered at all
    (current_url / http_status:<url> / page_title), snapshot says what is ON the
    page (a11y_node_count), extract says what it SAYS (has_text_content). The
    kernel's browser tools are exempt from duplicate-request dedup precisely so
    this chain can observe the same URL three ways.

    All three carry `always_success`: a browser action always yields an
    observation, and the claims come from the extractors reading that observation,
    not from the node's own on_success template.
    """
    nav = InvestigationNode(
        id=_node_id(),
        type="browser",
        action={"tool": "browser_navigate", "params": {"url": url}},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success),
        goal_id="goal_web",
    )
    snap = InvestigationNode(
        id=_node_id(),
        type="browser",
        action={"tool": "browser_snapshot", "params": {}},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success),
        depends_on=[nav.id],
        goal_id="goal_web",
    )
    extract = InvestigationNode(
        id=_node_id(),
        type="browser",
        action={"tool": "browser_extract", "params": {}},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success),
        depends_on=[snap.id],
        goal_id="goal_web",
    )
    return [nav, snap, extract]

