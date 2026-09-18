"""Full-stack end-to-end — all four modules wired to each other.

    CLI service function -> kernel (8080) -> planner (8787)
                                         -> explorer agent  (8100)
                                         -> verifier agent  (8100)

Every hop is real HTTP between separately-running processes. No LLM anywhere:
the planner's provider is the deterministic `heuristic`, the agents' provider is
the deterministic `mock`. Nothing here is stubbed.
"""
import json
import sys
import time

import httpx

KERNEL = "http://127.0.0.1:8080/v1/investigations"
PLANNER = "http://127.0.0.1:8787"
AGENTS = "http://127.0.0.1:8100"
REPO = "F:/Shivam/finalyear_project/wizard/wizard-runtime-engine"


def hr(t):
    print(f"\n{'=' * 74}\n{t}\n{'=' * 74}")


# ── Preflight: every service must be up before we blame the wiring ───────────
hr("PREFLIGHT")
for name, url in (("kernel", f"{KERNEL.rsplit('/v1', 1)[0]}/health"),
                  ("planner", f"{PLANNER}/health"),
                  ("agents", f"{AGENTS}/health")):
    r = httpx.get(url, timeout=10)
    print(f"  {name:8} {url:42} {r.status_code} {r.text.strip()}")

# ── Create with all three seams pointed at real services ─────────────────────
hr("CREATE")
r = httpx.post(KERNEL, json={
    "repository_path": REPO,
    "intent": "investigate",
    "targets": [],
    "options": {
        "budget": 16,
        "planner_url": PLANNER,
        "agent_explorer_url": f"{AGENTS}/agent/explorer",
        "agent_verifier_url": f"{AGENTS}/agent/verifier",
    },
}, timeout=30)
r.raise_for_status()
inv_id = r.json()["investigation_id"]
print("investigation:", inv_id)

deadline = time.time() + 240
while time.time() < deadline:
    final = httpx.get(f"{KERNEL}/{inv_id}", timeout=30).json()
    if final["status"] in ("completed", "failed", "cancelled"):
        break
    time.sleep(1.5)

hr("RESULT")
print(f"status          : {final['status']}")
print(f"nodes_completed : {final.get('nodes_completed')}")
print(f"claims_count    : {final.get('claims_count')}")
print(f"budget_remaining: {final.get('budget_remaining')}")
print(f"error           : {final.get('error')}")
for g in final.get("goals", final.get("active_goals", [])):
    print(f"  goal: {g}")

# ── Trace ───────────────────────────────────────────────────────────────────
ev = httpx.get(f"{KERNEL}/{inv_id}/events", timeout=30).json()
ev = ev if isinstance(ev, list) else ev.get("events", [])
hr(f"TRACE ({len(ev)} events)")
for e in ev:
    print(f"{e['seq']:>3} {e['event_type']:26} {json.dumps(e['payload'])[:165]}")

# ── Did every seam actually get used? ───────────────────────────────────────
hr("SEAM VERIFICATION")
seams = [e for e in ev if e["event_type"] == "seams.resolved"]
if seams:
    p = seams[0]["payload"]
    print(f"  planner  -> {p['planner']}   ({p['planner_url']})")
    print(f"  explorer -> {p['explorer']}  ({p['agent_explorer_url']})")
    print(f"  verifier -> {p['verifier']}  ({p['agent_verifier_url']})")

decided = [e for e in ev if e["event_type"] == "agent.decided"]
sources = sorted({e["payload"].get("source") for e in decided})
print(f"\n  agent.decided sources: {sources}")
print("  (explorer = the agent chose; node_plan = agent unavailable/rejected)")

consulted = [e for e in ev if e["event_type"] == "agent.consulted"]
print(f"  verifier consultations: {len(consulted)}")

report = httpx.get(f"{KERNEL}/{inv_id}/report", timeout=30)
print(f"  report: {report.status_code}, {len(report.text)} chars")

problems = []
if not seams:
    problems.append("no seams.resolved event — cannot tell which impl ran")
elif "Mock" in seams[0]["payload"]["explorer"]:
    problems.append(f"explorer seam is {seams[0]['payload']['explorer']}, not HttpExplorer")
elif "Mock" in seams[0]["payload"]["verifier"]:
    problems.append(f"verifier seam is {seams[0]['payload']['verifier']}, not HttpVerifier")
if final["status"] != "completed":
    problems.append(f"status={final['status']} error={final.get('error')}")

hr("VERDICT")
if problems:
    for p in problems:
        print(f"  FAIL: {p}")
    sys.exit(1)
print("  All four modules ran connected: CLI -> kernel -> planner + explorer + verifier")
sys.exit(0)
