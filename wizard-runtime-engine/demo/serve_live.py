"""serve_live.py — start the kernel, open the dashboard, run the flow, print the report.

    python serve_live.py

That is the whole interface. It will:

  1. start the real Wizard kernel API (uvicorn, one worker) on 127.0.0.1:8090,
  2. mount the three deterministic agent services and the browse fixtures from
     see_agent_flow.py onto that same app,
  3. print a link and open it,
  4. wait until the dashboard is actually being watched, then create three real
     investigations over ``POST /v1/investigations`` — one with a browser plane,
     one without, and one that gets ``DELETE``d mid-flight,
  5. print the final verification report to this terminal.

The left pane of the dashboard is the agent stream: the Planner's gating
decisions, the Explorer's per-node rule evaluation, the Verifier's gap scan,
interleaved with the kernel's own authoritative event bus. The right pane is the
agent's Chromium, streamed frame by frame over CDP while it works.

Everything is real: real sandbox, real subprocesses, real Chromium, real HTTP.
There is no LLM anywhere in the loop — the three agents are rule engines, and
every rule they fire is written into the trace you are watching.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
# see_agent_flow.py lives alongside this file in the demo/ folder.  Inserting HERE
# guarantees the import resolves regardless of the working directory the caller used,
# and fixes the IDE's static-analysis lookup (its import root is src/, not demo/).
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
# The wizard_kernel package lives in wizard-runtime-engine/src/, one level above demo/.
# Insert it so the demo works both with and without `pip install -e .`.
SRC = HERE.parent / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# The kernel's report and the browse fixtures contain non-ASCII characters; a
# Windows console defaults to cp1252 and would raise on them.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — older/odd streams simply keep their encoding
        pass

import httpx  # noqa: E402
import uvicorn  # noqa: E402

import see_agent_flow as flow  # noqa: E402
from wizard_kernel.api.app import create_app  # noqa: E402

BANNER = r"""
 _      __ _____ ______  ___     ___    ___
| | /| / //  _//_  __/ /  _ | / _ \ / _ \
| |/ |/ / _/ /   / /   / /_| |/ , _// // /
|__/|__/ /___/  /_/   /_/  |_/_/|_|/____/     runtime kernel · live agent flow
"""


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) != 0


def _wait_for_health(base: str, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base}/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except Exception:  # noqa: BLE001 — server is still binding
            pass
        time.sleep(0.25)
    return False


def _playwright_available() -> tuple[bool, str]:
    try:
        from importlib.metadata import version
        return True, f"playwright {version('playwright')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"playwright not importable ({exc})"


def _print_report(text: str) -> None:
    sys.stdout.write("\n" + text.rstrip() + "\n")
    sys.stdout.flush()


def conductor(args: argparse.Namespace, base: str, shutdown: threading.Event) -> None:
    """Runs alongside uvicorn: waits for the server, drives the run, prints the report."""
    if not _wait_for_health(base):
        print(f"\n[serve_live] kernel never became healthy at {base}/health — aborting.\n")
        shutdown.set()
        return

    dash = f"{base}/flow"
    print(BANNER)
    print(f"  kernel        {base}          (GET /health, /docs)")
    print(f"  repository    {flow.CFG.repo_path}")
    ok_pw, pw_note = _playwright_available()
    print(f"  browser       {pw_note}"
          f"{'' if ok_pw else '  -> the browser session will report tool errors, not crash'}")
    print(f"  agents        planner + explorer + verifier = deterministic rule engines "
          f"(no LLM)")
    print()
    print("  " + "=" * 74)
    print(f"  >>>  OPEN THIS:   {dash}")
    print("  " + "=" * 74)
    print()
    print("  Left pane  = agent reasoning (Planner gates, Explorer rules, Verifier gaps)")
    print("               interleaved with the kernel's authoritative event bus.")
    print("  Right pane = the agent's live Chromium, streamed over CDP while it acts.")
    print()

    if not args.no_open:
        try:
            webbrowser.open(dash)
        except Exception as exc:  # noqa: BLE001
            print(f"  (could not auto-open a browser: {exc} — open the link above)")

    # Hold until someone is actually watching. /flow/trace polling is the heartbeat.
    # Bounded: if nobody shows up, run anyway and say so.
    print(f"  waiting up to {args.wait}s for the dashboard to connect…", flush=True)
    deadline = time.time() + args.wait
    while time.time() < deadline and not shutdown.is_set():
        if flow.TRACE.viewer_seen_at > 0:
            print("  dashboard connected — starting the investigations.\n", flush=True)
            break
        time.sleep(0.3)
    else:
        if not shutdown.is_set():
            print("  no dashboard connected — running headless; "
                  "the report will still be printed here.\n", flush=True)

    if shutdown.is_set():
        return

    flow.RUN.start()

    # Progress ticks so the terminal is not silent while the kernel works. The hard
    # ceiling is the flow's own poll timeout plus a margin for report generation.
    last = ""
    hard_deadline = time.time() + args.timeout + 60
    while not flow.RUN.finished.wait(timeout=2.0):
        if shutdown.is_set():
            print("\n[serve_live] shutting down before the run finished.\n")
            return
        if time.time() > hard_deadline:
            print(f"\n[serve_live] run exceeded {args.timeout + 60}s — "
                  f"printing what has been verified so far.\n")
            break
        if flow.RUN.phase != last:
            last = flow.RUN.phase
            print(f"  [{time.time() - flow.RUN.started_at:>6.1f}s] {last}", flush=True)

    _print_report(flow.RUN.terminal_report
                  or f"[serve_live] no report was built (state={flow.RUN.state})")

    if args.exit_when_done:
        print("\n[serve_live] --exit-when-done: stopping the server.\n")
        shutdown.set()
    else:
        print(f"\n  The dashboard is still live at {dash} — Ctrl+C here to stop.\n",
              flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the Wizard kernel and the live agent flow.")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--repo", default=str(HERE.parent),
                    help="repository the investigations will examine "
                         "(default: wizard-runtime-engine/, the parent of demo/)")
    ap.add_argument("--wait", type=int, default=45,
                    help="seconds to wait for the dashboard before running headless")
    ap.add_argument("--think-ms", type=int, default=260,
                    help="pacing between agent decisions so the stream is readable")
    ap.add_argument("--timeout", type=int, default=420,
                    help="hard ceiling on the whole run, in seconds")
    ap.add_argument("--no-open", action="store_true", help="do not auto-open a browser")
    ap.add_argument("--exit-when-done", action="store_true",
                    help="stop the server once the report has printed")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"[serve_live] --repo {repo} is not a directory.")
        return 2

    if not _port_free(args.host, args.port):
        print(f"[serve_live] {args.host}:{args.port} is already in use. "
              f"Stop the other process or pass --port.")
        return 2

    flow.configure(host=args.host, port=args.port, repo_path=str(repo),
                   think_ms=args.think_ms, poll_timeout_s=args.timeout)

    # The kernel app, unmodified, plus the agent services it will call back into.
    app = create_app()
    app.include_router(flow.planner_router)     # /plan/initial|next|interpret
    app.include_router(flow.explorer_router)    # /agent/explorer, /agent/verifier
    app.include_router(flow.fixtures_router)    # /flow/fixtures/*
    app.include_router(flow.flow_router)        # /flow, /flow/start|state|trace|report

    base = flow.CFG.base
    shutdown = threading.Event()

    config = uvicorn.Config(
        app, host=args.host, port=args.port,
        log_level="warning",   # the flow's own output is the signal; keep uvicorn quiet
        access_log=False,      # the dashboard polls several times a second
        workers=1,             # kernel state is in-process (see app.lifespan warning)
    )
    server = uvicorn.Server(config)

    t = threading.Thread(target=conductor, args=(args, base, shutdown),
                         name="flow-conductor", daemon=True)
    t.start()

    stopper = threading.Thread(
        target=lambda: (shutdown.wait(), setattr(server, "should_exit", True)),
        name="flow-stopper", daemon=True)
    stopper.start()

    try:
        server.run()      # blocks; Ctrl+C raises inside uvicorn and returns cleanly
    except KeyboardInterrupt:
        pass
    finally:
        shutdown.set()
        # If Ctrl+C landed mid-run, still show whatever the flow managed to verify.
        if flow.RUN.terminal_report:
            _print_report(flow.RUN.terminal_report)
        elif flow.RUN.started:
            print(f"\n[serve_live] interrupted during: {flow.RUN.phase}")
            for s in flow.RUN.sessions:
                st = s.status or {}
                print(f"  {s.role:<10} {s.inv_id or '(none)':<22} "
                      f"{s.final_state or '?':<11} "
                      f"{st.get('nodes_completed', '–')} nodes / "
                      f"{st.get('claims_count', '–')} claims")
            print()

    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    raise SystemExit(main())
