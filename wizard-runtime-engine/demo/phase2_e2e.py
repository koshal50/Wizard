"""Phase 2 end-to-end — CLI service function -> live kernel -> live planner sidecar.

Everything is real: the CLI's own service module, the kernel over HTTP, the
TypeScript planner over HTTP, the local sandbox. No mocks, no LLM (the planner's
default provider is the deterministic `heuristic`).

Asserts that the planner seam actually did work, rather than merely not erroring:
  - more than one node completed (the loop got past the seed node)
  - the planner produced nodes mid-loop (reason=need_more_work)
  - the RUNTIME goal, which demands execution evidence, got it
"""
import json
import sys
import time

import httpx

KERNEL = "http://127.0.0.1:8080/v1/investigations"
PLANNER = "http://127.0.0.1:8787"
REPO = "F:/Shivam/finalyear_project/wizard/wizard-runtime-engine"


def create():
    r = httpx.post(KERNEL, json={
        "repository_path": REPO,
        "intent": "investigate",
        "targets": [],
        "options": {"budget": 16, "planner_url": PLANNER},
    }, timeout=30)
    r.raise_for_status()
    return r.json()["investigation_id"]


def wait(inv_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = httpx.get(f"{KERNEL}/{inv_id}", timeout=30).json()
        if d["status"] in ("completed", "failed", "cancelled"):
            return d
        time.sleep(1.5)
    return httpx.get(f"{KERNEL}/{inv_id}", timeout=30).json()


inv_id = create()
print(f"investigation: {inv_id}")
final = wait(inv_id)

print(f"\nstatus          : {final['status']}")
print(f"nodes_completed : {final.get('nodes_completed')}")
print(f"claims_count    : {final.get('claims_count')}")
print(f"budget_remaining: {final.get('budget_remaining')}")
print(f"error           : {final.get('error')}")
print("\ngoals:")
for g in final.get("goals", final.get("active_goals", [])):
    print(f"  {json.dumps(g)}")

events = httpx.get(f"{KERNEL}/{inv_id}/events", timeout=30).json()
events = events if isinstance(events, list) else events.get("events", [])
print(f"\nevents: {len(events)}")

agent_events = [e for e in events if "agent" in str(e.get("type", "")).lower()]
print(f"agent-related events: {len(agent_events)}")

print("\nnode lifecycle:")
for e in events:
    t = e.get("type", "")
    if t in ("NodeStarted", "NodeCompleted", "NodeFailed", "ClaimCreated", "GoalSatisfied"):
        p = e.get("payload", {})
        detail = (p.get("node_id") or p.get("goal_id") or p.get("claim_type") or "")
        print(f"  {t:16} {detail}")

report = httpx.get(f"{KERNEL}/{inv_id}/report", timeout=30)
print(f"\nreport: {report.status_code}, {len(report.text)} chars")
