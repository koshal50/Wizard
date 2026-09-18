"""The built-in planner reads the command, and agrees with the TypeScript one.

`MockPlanner` is the planner a run gets when `options.planner_url` is unset, so
these are the assertions that stop the four command families collapsing into one
again on that path. They were one command for the whole life of the project:
`initial` took `intent`, `targets` and `question` and read none of them, so
`wizard report`, `wizard verify runtime` and `wizard explain architecture` all
planned `Verify Runtime` + `Verify Dependencies` for any Node repository.

The expectations here are not invented. Each is the goal set the TypeScript
planner produces for the same request, recorded from a live `/plan/initial`
call — see `wizard-investigation-planner/src/planner/goalPolicy.ts`, which is the
source of truth this file's subject mirrors.
"""
from __future__ import annotations

import pytest

from wizard_kernel.contracts.manifest import RepositoryManifest
from wizard_kernel.ports.planner import MockPlanner


def _manifest(*key_files: str) -> RepositoryManifest:
    return RepositoryManifest(
        investigation_id="inv_plan",
        repository_path="/repo",
        root_path="/repo",
        size_bytes_approx=1,
        key_files=list(key_files),
        total_files=40,
        total_dirs=10,
        directory_tree=[],
        extensions={},
    )


def _goals(repo: RepositoryManifest, intent: str, targets: list[str],
            question: str = "", browser: bool = False) -> list[str]:
    plan = MockPlanner().initial(
        repo, intent, targets, {"browser_enabled": browser}, question=question
    )
    return [g.name for tech in plan.technologies for g in tech.initial_goals]


#: A repository that can propose every goal the vocabulary knows about.
_NODE_AND_DOCKER = _manifest("package.json", "Dockerfile")


# ── The four families are four commands ───────────────────────────────────────

def test_report_plans_nothing_that_runs():
    """A report says what the repository is; it does not prove anything.

    `Verify Runtime` and `Verify Test Suite` both require execution evidence, so
    neither may appear — running the test suite to produce a report is work the
    user asked for in a different command.
    """
    goals = _goals(_NODE_AND_DOCKER, "report", [])
    assert goals == ["Verify Dependencies", "Verify Containerization"]
    assert "Verify Runtime" not in goals


def test_verify_runtime_proves_the_runtime_and_abandons_the_rest():
    """Aimed at one thing, verify proves that thing — not the whole repository."""
    assert _goals(_NODE_AND_DOCKER, "verify", ["runtime"]) == ["Verify Runtime"]


def test_verify_testing_proves_the_suite():
    assert _goals(_NODE_AND_DOCKER, "verify", ["testing"]) == ["Verify Test Suite"]


def test_investigate_keeps_what_a_file_closes_and_what_was_aimed_at():
    """Understanding is broad: every read-only goal, plus the one named.

    `architecture` is a subject and not a probe, so it becomes a read-the-files
    goal named after the user's own word — and `Verify Runtime`, which the
    repository suggested and the user did not ask for, is dropped because
    investigating does not run things unless it was pointed at them.
    """
    goals = _goals(_NODE_AND_DOCKER, "investigate", ["architecture"])
    assert goals == ["Verify Dependencies", "Inspect architecture", "Verify Containerization"]
    assert "Verify Runtime" not in goals


def test_explain_answers_only_what_was_asked():
    """An explanation is not a request to also find out about the dependencies."""
    assert _goals(_NODE_AND_DOCKER, "explain", ["dependencies"]) == ["Verify Dependencies"]


def test_explain_of_a_word_the_vocabulary_does_not_know_still_says_something():
    """A target nothing answers to produces a goal, not an empty plan.

    Dropping it is how a run ends up reporting on a question nobody asked while
    the one that was asked leaves no trace.
    """
    assert _goals(_NODE_AND_DOCKER, "explain", ["architecture"]) == ["Inspect architecture"]


# ── The rules that are easy to get subtly wrong ───────────────────────────────

def test_a_goal_the_user_named_stops_being_repository_context():
    """The origin is re-tagged, not merely added.

    `Verify Dependencies` is context in a Node repository and the question in
    `explain dependencies`. Left tagged as the repository's, the explain branch
    reads it as context, finds nothing the user asked for, and falls back to
    describing the whole repository — so `explain dependencies` and `explain`
    would plan the same run, which is the collapse this whole file is about.
    """
    assert _goals(_NODE_AND_DOCKER, "explain", ["dependencies"]) == ["Verify Dependencies"]
    # The same goal, unnamed, is context a family may keep or drop.
    assert "Verify Dependencies" in _goals(_NODE_AND_DOCKER, "investigate", [])


def test_a_word_the_vocabulary_knows_does_not_also_get_an_inspect_goal():
    """`runtime` is answered by running the probe, not by also reading for it.

    Two goals under one word — `Verify Runtime` and `Inspect runtime` — would make
    the run look like it had two things to establish when the user named one.
    """
    goals = _goals(_NODE_AND_DOCKER, "investigate", ["runtime"])
    assert "Inspect runtime" not in goals
    assert "Verify Runtime" in goals


def test_an_address_does_not_name_goals_by_its_own_path():
    """`/register` in a URL is the app's route, not an instruction to sign up.

    The word list is read from the request's words because a question about tests
    should weigh the same as the target word "testing". A target that is an
    address is the exception: it is a location, and a location's own text is not
    the user asking for anything.

    `explain` is the family here because it describes and never operates, so the
    path's own word is the only thing that could name the goal — and it does not.
    """
    goals = _goals(_manifest(), "explain", ["http://localhost:5173/register"])
    assert "Operate Web Surface" not in goals


def test_a_proving_command_aimed_at_an_address_operates_the_page():
    """`verify http://localhost:5173` is the user asking for the app to be used.

    The gate used to be the request's words and nothing else, and words are the
    one thing a browser target is not: an address is filtered out of the word
    test, so every URL-shaped target in the product read "verify" as "look at".
    The run reached the live application and stopped there, which is what a
    reader sees as a browser that does nothing.

    Both halves are named, not just the stronger one: reaching a page and using
    it are two goals closed by two different pieces of evidence, and a run that
    operates a page navigates before it presses. Naming only the second would
    leave the run's own successful navigate closing nothing.
    """
    goals = _goals(_manifest(), "verify", ["http://localhost:5173"], browser=True)
    assert "Operate Web Surface" in goals
    assert "Verify Web Surface" in goals


def test_a_describing_command_aimed_at_an_address_only_reads_it():
    """A report runs nothing, and that includes not pressing the page's buttons.

    The other half of the gate, and the reason it is the family and not just the
    address: a report describing an application must not sign anything up.
    """
    goals = _goals(_manifest(), "report", ["http://localhost:5173"], browser=True)
    assert "Operate Web Surface" not in goals
    assert "Verify Web Surface" in goals


def test_a_question_that_asks_to_operate_the_page_plans_it():
    """The interaction script is opt-in by question, and the gate is shared.

    The decision that the run MAY act and the goal that requires it to are the
    same decision, read once — from the same table the TypeScript planner reads.
    """
    goals = _goals(_manifest(), "investigate", ["http://localhost:5173"],
                   question="log in and submit the form", browser=True)
    assert "Operate Web Surface" in goals
    assert "Verify Web Surface" in goals


def test_a_repository_the_vocabulary_cannot_read_still_gets_a_look():
    """A run with nothing to do takes one look at the repository.

    Not a claim about the goals: no goal is added or substituted. It is what lets
    the report say what the repository actually is when it says the question went
    unanswered — and it is the difference between an honest `incomplete` and a run
    that did literally nothing.
    """
    plan = MockPlanner().initial(_manifest(), "verify", ["runtime"], {})
    assert [g.name for tech in plan.technologies for g in tech.initial_goals] == ["Verify Runtime"]
    assert plan.seed_nodes, "a run with no steps cannot report on anything"


def test_operating_the_page_is_the_goal_a_repository_goal_never_forces():
    """The gate is on OPERATING the page, and it is the same gate both ways.

    Reaching a page and operating it are two goals closed by two different pieces
    of evidence, and the shared table says so: `Verify Web Surface` needs WEB,
    which a navigation produces, while `Operate Web Surface` needs INTERACTION,
    which only typing into a control and pressing it produces. So a run may be
    planned to *read* an address without being planned to act on it — and a
    command family that runs nothing keeps the first and drops the second.
    """
    read_only = MockPlanner().initial(
        _manifest(), "report", ["http://localhost:5173"], {"browser_enabled": True},
    )
    read_goals = [g.name for tech in read_only.technologies for g in tech.initial_goals]
    assert "Verify Web Surface" in read_goals
    assert "Operate Web Surface" not in read_goals, "a report may not be planned to act on a page"

    asked = MockPlanner().initial(
        _manifest(), "investigate", ["http://localhost:5173"],
        {"browser_enabled": True}, question="click the sign in button",
    )
    assert any(n.type == "browser" for n in asked.seed_nodes)
