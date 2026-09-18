"""What a goal is proven by, and what each command family will pay for.

**The source of truth for this table is `wizard-investigation-planner/src/
planner/goalPolicy.ts`**, and this is its mirror for the built-in planner. The
grep-able name of every rule is the same in both files; when one changes the
other is wrong until it is changed too.

Why a mirror exists at all: the Runtime's `MockPlanner` is the planner a run
gets when `options.planner_url` is unset, and it used to accept `intent`,
`targets` and `question` and ignore all three. It gave every repository the same
two goals — `Verify Runtime` and `Verify Dependencies` — so `wizard verify
runtime`, `wizard explain dependencies` and `wizard report` produced runs that
were identical in their goals, their nodes and their reports. A planner that
answers every question the same way is not a planner, and the fact that it is
the *fallback* planner is what made it silent: the run looked like a working
one, and only `seams.resolved` said which planner had been asked.

The alternative — deleting the built-in planner so the Runtime can only run
wired to the TypeScript one — would make every kernel unit test and every demo
in `demo/` need a Node process, which is a real cost paid for a table that is
sixty lines. So the table is carried here instead, and the two copies are held
to each other by `tests/test_goal_policy.py`, which asserts the rule set this
file encodes rather than trusting it to stay right by inspection.

Two facts about a goal decide everything, and both live in this file so they
cannot disagree:

  - Its EVIDENCE: which claim types the kernel's goal engine counts toward it,
    and whether it can only be closed by code that actually ran. A goal the plan
    believes a file closes, and the goal engine believes needs execution, can
    never be satisfied by anything — and it reads exactly like a goal the run
    failed to prove.
  - Its ORIGIN: whether the repository proposed it or the user's own words named
    it. `Verify Runtime` appears both ways — every Node repository suggests it,
    and `verify runtime` names it — and the two are not the same goal. One is
    context, the other is the question.
"""
from __future__ import annotations

import re

# ── Evidence routing ──────────────────────────────────────────────────────────

#: Claim types the kernel's extractors can actually produce. A goal naming a
#: type outside this set is unsatisfiable by construction.
FILE_READ = "FILE_READ"
INTERACTION = "INTERACTION"
WEB = "WEB"
RUNTIME = "RUNTIME"
PACKAGE = "PACKAGE"
DEPLOYMENT = "DEPLOYMENT"
TESTING = "TESTING"
FILESYSTEM = "FILESYSTEM"


class GoalEvidence:
    """How the kernel's goal engine counts a goal as satisfied."""

    __slots__ = ("required_claim_types", "requires_execution_evidence")

    def __init__(self, required_claim_types: list[str], requires_execution_evidence: bool) -> None:
        self.required_claim_types = required_claim_types
        self.requires_execution_evidence = requires_execution_evidence


#: A goal nothing routes: it exists to be reported on, not to be proven.
NO_EVIDENCE = GoalEvidence([], False)

#: How a goal name is routed. First match wins, and the order is the algorithm:
#: "Inspect runtime internals" is a read-the-files goal that happens to contain
#: the word "runtime", and only testing the `inspect` prefix first keeps it from
#: being routed as a runtime probe it cannot possibly satisfy. `operate` is
#: before `web` for the same reason — "Operate Web Surface" contains "Web", and
#: reaching a page and operating it are two goals closed by two different pieces
#: of evidence.
_ROUTES: list[tuple[re.Pattern[str], GoalEvidence]] = [
    (re.compile(r"^inspect\b"), GoalEvidence([FILE_READ], False)),
    (re.compile(r"^operate\b"), GoalEvidence([INTERACTION], True)),
    (re.compile(r"web|browser|http"), GoalEvidence([WEB], False)),
    (re.compile(r"runtime"), GoalEvidence([RUNTIME], True)),
    (re.compile(r"depend|package"), GoalEvidence([PACKAGE], False)),
    # No execution requirement: containerisation is *declared* by a file, and the
    # kernel's DEPLOYMENT claims come from reading a Dockerfile or a compose
    # file. Demanding execution evidence as well made the goal unsatisfiable by
    # construction — the evidence it asked for is not the kind that can exist.
    (re.compile(r"container|docker|deploy"), GoalEvidence([DEPLOYMENT], False)),
    # Tests are only really verified by running them. A file-tier TESTING claim
    # (a pytest section in pyproject.toml) says the suite is *configured*, which
    # is not what "verify the tests" asks.
    (re.compile(r"test|spec|coverage"), GoalEvidence([TESTING], True)),
    (re.compile(r"investigate|repository|filesystem"), GoalEvidence([FILESYSTEM], False)),
]


def goal_evidence_for(name: str) -> GoalEvidence:
    """The evidence a goal named `name` is closed by."""
    lowered = name.lower()
    for pattern, evidence in _ROUTES:
        if pattern.search(lowered):
            return evidence
    return NO_EVIDENCE


def is_proven(name: str) -> bool:
    """Whether closing this goal means running something.

    Derived from the routing rather than listed a second time: a goal that needs
    execution evidence and a goal that is worth executing for are the same goal,
    and a family policy built on a separate list would slowly stop agreeing with
    the goal engine about which ones those are.
    """
    return goal_evidence_for(name).requires_execution_evidence


def is_inspected(name: str) -> bool:
    """The read-the-files goals, which the user's own words produce."""
    return bool(re.match(r"^inspect\b", name, re.IGNORECASE))


# ── The vocabulary a target is read in ────────────────────────────────────────

#: Does the request ask for the application to be *operated*, rather than read?
#:
#: The one gate on the interaction script. Pressing a form's controls creates and
#: mutates real state in someone's running app, so it stays opt-in — but by the
#: two things the user actually states: the words they typed, and the command
#: they ran. Opting in by *question alone* meant the command could not ask for
#: anything, and every URL-shaped target in the product read "verify" as "look
#: at": a run pointed at a live application reached it and stopped there.
#:
#: The words are operations, not topics: "ui" and "frontend" name a surface the
#: user wants driven; "log in" and "submit" name an action. Generic verbs are
#: deliberately absent — a bare "use" made "which dependencies does this project
#: use" an instruction to type into a login form, and a false positive here does
#: not cost a step, it mutates someone's page.
ACTS_ON_PAGE = re.compile(
    r"\b(log ?in|log ?out|sign ?in|sign ?up|sign ?out|register|submit|checkout|"
    r"purchase|interact|operate|click|press|fill (?:in|out)|the (?:form|button|page|app|ui)|"
    r"ui|frontend|front[- ]end|end[- ]to[- ]end|e2e|walk ?through|go ?through|"
    r"drive the app|exercise the app)\b",
    re.IGNORECASE,
)

#: The families whose question cannot be answered by looking at the page.
#:
#: `verify <url>` is a request to prove an application works, and reading its
#: HTML proves nothing about it — a web app is a thing that responds to being
#: used. `investigate <url>` is the broad version of the same request. `report`
#: and `explain` are absent because they describe: a report that pressed a button
#: would be doing the work of another command.
OPERATING_FAMILIES = frozenset({"verify", "investigate"})

#: The goals a user's *request* can name, and the words that name them.
#:
#: Matched against the request's words — the command's targets and the sentence
#: the user typed — but never against the command family. `verify` and `explain`
#: are verbs, and a verb is not a subject; reading them as text is what produced
#: goals called "Inspect explain" and "Inspect report", which no repository can
#: answer and which the run then spent budget failing to.
NAMED_GOALS: list[tuple[str, re.Pattern[str]]] = [
    ("Verify Test Suite", re.compile(r"\b(tests?|testing|specs?|coverage|vitest|jest|pytest|mocha|ci)\b", re.I)),
    ("Verify Runtime", re.compile(r"\b(runtimes?|boot|serves?|served|start|builds?|install|version)\b", re.I)),
    ("Verify Containerization", re.compile(r"\b(deploy(?:ment)?s?|docker|compose|kubernetes|k8s|containers?|images?)\b", re.I)),
    ("Verify Dependencies", re.compile(r"\b(dependenc(?:y|ies)|packages?|librar(?:y|ies)|vulnerab\w*|outdated|audit)\b", re.I)),
    ("Operate Web Surface", ACTS_ON_PAGE),
]


def _is_address(target: str) -> bool:
    """A target that names a place rather than an action.

    The same test the Runtime uses to decide a target is a browser target at all
    (ports/planner.py `_looks_like_url`), so the two agree about which targets
    are addresses.
    """
    lowered = target.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def goals_named_by(words: list[str]) -> set[str]:
    """The goals these words name, in the vocabulary above."""
    named: set[str] = set()
    for word in words:
        for name, pattern in NAMED_GOALS:
            if pattern.search(word):
                named.add(name)
    return named


def names_operation_for(family: str, targets: list[str], question: str) -> bool:
    """Does this command ask for the application to be operated?

    Two ways in, and both are the user speaking. A sentence or a target naming an
    operation ("log in", "walk through the checkout", "ui") is the plain case. A
    family that means *prove this works*, aimed at an address rather than at a
    file, is the other: the address is the object, and proving a running
    application works means exercising it. The family test needs an address in
    the target list, so no amount of `verify package.json` becomes a click.
    """
    if "Operate Web Surface" in goals_named_by(_operation_words(targets, question)):
        return True
    return family in OPERATING_FAMILIES and any(_is_address(t) for t in targets)


def _operation_words(targets: list[str], question: str) -> list[str]:
    """The request's words, with addresses removed.

    An address is not an object — it is a location, and a location's own text is
    not the user asking for anything. `/register` in a target's path is the app's
    own name for one of its routes, and "register" is in the word list above, so
    a gate that read every target as a word turned "which routes does this client
    define", aimed at `http://localhost:5173/register`, into an instruction to
    submit a sign-up form. That is the false positive that mutates someone's
    page, produced by the target list alone with no sentence involved.
    """
    words = [t for t in targets if not _is_address(t)]
    if question.strip():
        words.append(question)
    return words


def goals_named_by_request(targets: list[str], question: str) -> set[str]:
    """The goals a whole request names from its own text: targets and sentence."""
    return goals_named_by(_operation_words(targets, question))


def goals_named_by_command(
    family: str, targets: list[str], question: str
) -> set[str]:
    """The goals a whole *command* names: the request's words and the command.

    `goals_named_by_request` reads the vocabulary and nothing else, and it is
    right to: families are verbs and a verb is not a subject. But a family is
    also the user choosing what kind of answer they want, and for the web goals
    that choice is the whole of what names them — `verify http://localhost:5173`
    asks for the application to be used without a word from the list above: the
    address is the object and `verify` is the demand.

    Both halves are named, not just the stronger one. Reaching a page and using
    it are two goals closed by two different pieces of evidence, and a run that
    operates a page necessarily does both — it navigates before it presses. Two
    goals, two honest answers; naming only the second would leave the run's own
    successful navigate closing nothing.

    Read from the same gate the script rule reads (`names_operation_for`), so the
    goals a plan declares and the steps that close them cannot come apart — a
    plan with an `Operate Web Surface` goal and no script to satisfy it reports
    failing at something it was never given the means to do.
    """
    named = goals_named_by_request(targets, question)
    if names_operation_for(family, targets, question):
        named.update({"Verify Web Surface", "Operate Web Surface"})
    return named


def names_operation(targets: list[str], question: str) -> bool:
    """Do these words ask for the application to be operated?"""
    return bool(goals_named_by(_operation_words(targets, question)))


# ── What each family wants ────────────────────────────────────────────────────

#: The families the Runtime understands, matching the `intent` Literal on
#: InvestigationRequest.
FAMILIES = ("investigate", "verify", "explain", "report")

#: A goal in the plan and where it came from.
#:
#:   manifest  — the repository suggests it. Context. Every family would get it.
#:   named     — a target or the question names it in the vocabulary above. This
#:               is the user's question, in the plan's own words.
#:   inspected — a target resolved to nothing and produced a read-the-files goal
#:               named after the user's word.
MANIFEST = "manifest"
NAMED = "named"
INSPECTED = "inspected"


def goals_for_family(
    family: str,
    proposed: list[tuple[str, str]],
    named: set[str],
) -> list[str]:
    """The goals a family keeps, given what the plan proposes and what was named.

    `proposed` is (name, origin) pairs in proposal order. Every branch below is
    the sentence that makes one command a different one from the others, and
    every branch is a restriction — a family may drop a goal the repository
    suggested and may never invent one, so no family can make the run claim more
    than the repository supports.

    Where a family and a target disagree, the target wins: `verify runtime` is
    narrower than verify, because the user said which part they meant.
    """
    # A family nobody stated is not a family that wants nothing. The Runtime
    # types this field as one of four and always sends one, but a caller that
    # omits it — a test driving the planner directly — must get the whole
    # proposal rather than an empty plan it would have no way to recognise as its
    # own mistake. Restricting is the exception here, so it has to be asked for.
    if family not in FAMILIES:
        return [name for name, _ in proposed]

    keep = lambda ok: [name for name, origin in proposed if ok(name, origin)]  # noqa: E731

    if family == "report":
        # A report says what the repository is. It runs nothing — a report is not
        # a proof, and running the test suite to produce one is work the user
        # asked for in a different command. It also does not hunt: `report` takes
        # no target, so a question about a named part of the repository is the
        # one thing it was never asked, and `Inspect …` goals are that question.
        return keep(lambda name, origin: not is_proven(name) and not is_inspected(name))

    if family == "explain":
        # Explaining answers the question that was asked, and nothing else. The
        # repository-wide goals are context an investigation needs and an
        # explanation does not: "explain the runtime" is not a request to also
        # find out about the dependencies.
        asked = keep(lambda name, origin: origin != MANIFEST)
        # A target the vocabulary does not know and no file answers to produces
        # no goal at all, and an explanation with nothing to explain would report
        # on an empty run. Falling back to what the repository can describe is
        # the honest answer to a question it cannot answer by name.
        return asked if asked else keep(lambda name, origin: not is_proven(name))

    if family == "verify":
        # Verifying proves. Aimed at one thing, it proves that thing and abandons
        # the rest — `verify containers` has no business running the test suite.
        # Aimed at something the vocabulary does not know, it proves what it can:
        # `ci` is a real target and not a goal, and reading it as "prove nothing"
        # would make the command silently do nothing at all.
        if named:
            return keep(lambda name, origin: name in named)
        return keep(lambda name, origin: is_proven(name))

    # investigate, and the default: understanding. Everything a file can close,
    # plus whatever the user named that has to be run to be answered — so an
    # investigation is broad by default and narrows to what was aimed at. A
    # target that names no provable goal (`architecture` is a subject, not a
    # probe) leaves a read-only run, which is what investigating architecture is.
    return keep(lambda name, origin: (not is_proven(name)) or (name in named))
