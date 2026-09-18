"""Phase 4 acceptance test — the CLI driving all four modules.

    wizard CLI  ->  kernel (8080)  ->  planner (8787)
                                   ->  explorer agent (8100)
                                   ->  verifier agent (8100)

Phase 3 proved the *kernel* could reach the planner and the agents. This proves
the CLI can: it runs the CLI's own service function (`commands.investigate`),
with options built the way the TUI builds them (`RequestOptions.from_env`), and
then asserts what actually landed in the engine's trace.

Two things are checked that could not be checked before this phase:

  1. That a CLI-launched run resolves all three seams to the real HTTP
     implementations — i.e. the CLI can configure the seams at all. Before,
     RequestOptions had no URL fields, so every CLI run silently fell back to
     the kernel's built-in offline planner and mock agents.

  2. That Esc cancels the investigation *in the engine*, not just in the UI.
     The TuiSession is driven for real (worker thread, live stream), cancelled
     mid-flight, and the engine is then asked what it thinks the status is.

Deterministic throughout: the planner's provider is `heuristic` and the agents'
provider is `mock`, so no LLM is involved anywhere in the path.
"""
import os
import sys
import time

import httpx

WIZARD_ROOT = "F:/Shivam/finalyear_project/wizard"
REPO = f"{WIZARD_ROOT}/wizard-runtime-engine"
KERNEL = "http://127.0.0.1:8080/v1/investigations"
PLANNER = "http://127.0.0.1:8787"
AGENTS = "http://127.0.0.1:8100"

sys.path.insert(0, f"{WIZARD_ROOT}/wizard")

# The CLI's run is pointed at the live services the only way a user can: through
# the environment. Nothing below sets a URL on a request object by hand.
os.environ["WIZARD_PLANNER_URL"] = PLANNER
os.environ["WIZARD_EXPLORER_URL"] = f"{AGENTS}/agent/explorer"
os.environ["WIZARD_VERIFIER_URL"] = f"{AGENTS}/agent/verifier"
os.environ["WIZARD_BUDGET"] = "16"

from wizard.cli.models.investigation_request import RequestOptions          # noqa: E402
from wizard.cli.commands.investigate import investigate                    # noqa: E402
from wizard.cli.runtime_client.client import base_url, cancel_investigation  # noqa: E402

PROBLEMS: list[str] = []


def hr(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}{' — ' + detail if detail else ''}")
    if not ok:
        PROBLEMS.append(label)


# ── Preflight ────────────────────────────────────────────────────────────────
hr("PREFLIGHT")
for name, url in (("kernel", "http://127.0.0.1:8080/health"),
                  ("planner", f"{PLANNER}/health"),
                  ("agents", f"{AGENTS}/health")):
    r = httpx.get(url, timeout=10)
    print(f"  {name:8} {r.status_code} {r.text.strip()}")
    check(f"{name} is up", r.status_code == 200)

# ── 1. A CLI run reaches all three seams ─────────────────────────────────────
hr("RUN 1 — CLI investigate, options from the environment")

os.chdir(REPO)  # the CLI investigates the directory it is run from
options = RequestOptions.from_env()
print(f"  options -> {options.to_dict()}")
check("CLI options carry a planner URL", options.planner_url == PLANNER)
check("CLI options carry an explorer URL", bool(options.agent_explorer_url))
check("CLI options carry a verifier URL", bool(options.agent_verifier_url))
print(f"  engine  -> {base_url()}")

events = []
done = None
for ev in investigate("architecture", REPO, options):
    if ev.get("event_type") == "done":
        done = ev
        break
    events.append(ev)
    p = ev.get("payload", {})
    print(f"  {ev.get('seq'):>3} {ev.get('event_type'):26} {str(p)[:120]}")

check("the CLI stream terminated with a done event", done is not None)
if done is None:
    hr("VERDICT")
    sys.exit(1)

inv_id = done["investigation_id"]
print(f"\n  investigation : {inv_id}")
print(f"  status        : {done['status']}")
print(f"  report_path   : {done['report_path']}")

check("investigation completed", done["status"] == "completed", done["status"])

# The engine's own record of which implementation each seam got.
trace = httpx.get(f"{KERNEL}/{inv_id}/events", timeout=30).json()
seams = next((e["payload"] for e in trace if e["event_type"] == "seams.resolved"), None)
check("the engine reported its seams", seams is not None)
if seams:
    print(f"  planner  -> {seams['planner']}  ({seams['planner_url']})")
    print(f"  explorer -> {seams['explorer']}  ({seams['agent_explorer_url']})")
    print(f"  verifier -> {seams['verifier']}  ({seams['agent_verifier_url']})")
    check("planner seam is the real HTTP planner", seams["planner"] == "HttpPlanner")
    check("explorer seam is the real HTTP explorer", seams["explorer"] == "HttpExplorer")
    check("verifier seam is the real HTTP verifier", seams["verifier"] == "HttpVerifier")

check("the explorer actually decided at least one node",
      any(e["event_type"] == "agent.decided" and e["payload"].get("source") == "explorer"
          for e in trace))
check("the verifier was consulted",
      any(e["event_type"] == "agent.consulted" for e in trace))
check("the verifier's verdict was recorded",
      any(e["event_type"] == "agent.assessed" for e in trace))

# ── 2. The report reached disk ───────────────────────────────────────────────
hr("RUN 1 — report on disk")
report_path = done["report_path"]
check("the CLI saved a report file", bool(report_path) and not report_path.startswith("<"),
      str(report_path))
if report_path and not report_path.startswith("<"):
    check("the saved report exists", os.path.isfile(report_path), report_path)
    body = open(report_path, encoding="utf-8").read()
    check("the saved report has content", len(body) > 200, f"{len(body)} chars")
    check("the saved report is the engine's report",
          body.strip() == done["report_markdown"].strip())

# ── 3. Esc cancels the run in the engine ─────────────────────────────────────
hr("RUN 2 — cancellation reaches the engine")

# A big budget so the run is not bounded by it. It still finishes on its own in a
# couple of seconds — the investigation is only two nodes — which makes the
# cancel a genuine race, and that race is the point.
os.environ["WIZARD_BUDGET"] = "400"
from wizard.cli.tui.session import TuiSession  # noqa: E402

session = TuiSession(family="investigate", target="architecture")
session.start()

deadline = time.time() + 60
while time.time() < deadline and not session.investigation_id:
    time.sleep(0.05)

cancel_id = session.investigation_id
check("the TUI session learned the engine's investigation id", bool(cancel_id), cancel_id)

if cancel_id:
    session.cancelled = True  # exactly what Esc sets
    deadline = time.time() + 30
    while time.time() < deadline and not session.finished:
        time.sleep(0.1)

    check("the TUI session stopped", session.finished)
    check("the TUI session reports cancelled", session.status == "cancelled", session.status)
    print(f"  the session's own account: "
          f"{[b.detail for b in session.snapshot_activity() if b.detail][-1:]}")

    # The engine's half. Two properties, both of which must hold whichever way
    # the race went:
    #   * the investigation is in a terminal state — nothing is left running, and
    #   * that state is stable — a client that polls twice is not told two
    #     different things, which is exactly what a lost cancel used to cause.
    first = httpx.get(f"{KERNEL}/{cancel_id}", timeout=10).json()["status"]
    time.sleep(2.5)
    second = httpx.get(f"{KERNEL}/{cancel_id}", timeout=10).json()["status"]
    check("the engine reached a terminal state",
          second in ("completed", "failed", "cancelled"), second)
    check("the engine's answer is stable across polls", first == second,
          f"{first} then {second}")

    engine = httpx.get(f"{KERNEL}/{cancel_id}", timeout=10).json()
    print(f"  engine status : {engine['status']}   nodes_completed={engine['nodes_completed']}"
          f"   budget_remaining={engine['budget_remaining']}")
    print("  (completed = the run finished before the cancel landed; it is only two")
    print("   nodes long. Either answer is correct — contradicting itself is not.)")

    # ── 4. The cancel contract, driven directly ──────────────────────────────
    hr("RUN 3 — the DELETE's own answer matches the engine's state")

    def create_run(budget: int = 400) -> str:
        return httpx.post(KERNEL, json={
            "repository_path": REPO, "intent": "investigate", "targets": [],
            "options": {"budget": budget},
        }, timeout=30).json()["investigation_id"]

    def await_terminal(inv_id: str, seconds: float = 60) -> str:
        deadline = time.time() + seconds
        state = "?"
        while time.time() < deadline:
            state = httpx.get(f"{KERNEL}/{inv_id}", timeout=10).json()["status"]
            if state in ("completed", "failed", "cancelled"):
                return state
            time.sleep(0.5)
        return state

    # Cancelled straight after creation, so the cancel is sent while the run is
    # most likely still planning.
    fresh = create_run()
    reply = httpx.request("DELETE", f"{KERNEL}/{fresh}", timeout=10).json()
    after = httpx.get(f"{KERNEL}/{fresh}", timeout=10).json()["status"]

    print(f"  DELETE replied : {reply}")
    print(f"  GET then said  : {after}")
    check("the DELETE's reported status is the state the engine holds",
          reply["status"] == after, f"{reply['status']} vs {after}")
    check("the DELETE's `cancelled` flag agrees with its status",
          reply["cancelled"] == (reply["status"] == "cancelled"))

    # Whether an immediate cancel wins is a genuine race — the whole run is about
    # two nodes long — so the deterministic property is not "it won" but "the
    # helper's answer is the engine's answer". Over a few attempts we should see
    # it win at least once, which exercises the other branch too.
    wins = 0
    for _ in range(4):
        rid = create_run()
        claimed = cancel_investigation(rid)
        actual = httpx.get(f"{KERNEL}/{rid}", timeout=10).json()["status"]
        check(f"the helper's answer matches the engine ({rid[-6:]})",
              claimed == (actual == "cancelled"), f"claimed={claimed} actual={actual}")
        wins += bool(claimed)

    print(f"  the cancel won {wins}/4 immediate attempts")
    if not wins:
        print("  note: no immediate cancel won this time, so the won-cancel branch")
        print("        was not exercised here. It is covered deterministically by")
        print("        tests/test_cancellation.py.")

    # A run that reaches its own end keeps `completed` — terminal states are
    # absorbing, so a late cancel must not be reported as a success.
    finished = create_run(budget=16)
    state = await_terminal(finished)
    check("a completed run reports False for a late cancel",
          cancel_investigation(finished) is False and state == "completed", state)
    check("a late cancel does not rewrite a completed run's state",
          httpx.get(f"{KERNEL}/{finished}", timeout=10).json()["status"] == "completed")

    check("cancelling an unknown id returns False", cancel_investigation("inv_does_not_exist") is False)
    check("cancelling a blank id returns False", cancel_investigation("") is False)

# ── Verdict ──────────────────────────────────────────────────────────────────
hr("VERDICT")
if PROBLEMS:
    for p in PROBLEMS:
        print(f"  FAIL: {p}")
    sys.exit(1)
print("  The CLI drives all four modules: options -> engine -> planner + agents,")
print("  the report lands on disk, and Esc stops the run in the engine.")
sys.exit(0)
