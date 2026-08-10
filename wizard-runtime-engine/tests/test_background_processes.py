"""Background process tests — multiple terminals, non-blocking execution."""
import time
import pytest
from wizard_kernel.world.sandbox.local import LocalProcessRuntime
from wizard_kernel.world.tools import ToolExecutor


@pytest.fixture
def sandbox(tmp_path):
    rt = LocalProcessRuntime()
    rt.start(str(tmp_path))
    yield rt
    rt.stop()  # kills all background processes


@pytest.fixture
def executor(sandbox, tmp_path):
    return ToolExecutor(sandbox, str(tmp_path))


# ── Core background process tests ─────────────────────────────────────────────

def test_exec_background_returns_immediately(sandbox):
    """exec_background must not block — returns while process still runs."""
    t0 = time.monotonic()
    bg = sandbox.exec_background("python -c \"import time; time.sleep(30)\"")
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, "exec_background blocked — should return instantly"
    assert bg.handle_id.startswith("proc_")
    assert bg.is_running
    sandbox.kill_process(bg.handle_id)


def test_background_output_captured(sandbox):
    """Output from background process is readable without blocking."""
    bg = sandbox.exec_background("echo hello_from_bg")
    time.sleep(0.5)  # let it run
    snapshot = sandbox.read_process_output(bg.handle_id)
    assert "hello_from_bg" in snapshot.stdout_so_far


def test_multiple_background_processes(sandbox):
    """Multiple long-running processes run concurrently — no blocking."""
    bg1 = sandbox.exec_background("python -c \"import time; time.sleep(30)\"")
    bg2 = sandbox.exec_background("python -c \"import time; time.sleep(30)\"")
    bg3 = sandbox.exec_background("python -c \"import time; time.sleep(30)\"")

    procs = sandbox.list_processes()
    assert len(procs) >= 3
    assert all(p.is_running for p in procs)

    sandbox.kill_process(bg1.handle_id)
    sandbox.kill_process(bg2.handle_id)
    sandbox.kill_process(bg3.handle_id)


def test_kill_process_terminates(sandbox):
    """Killing a process makes it stop."""
    bg = sandbox.exec_background("python -c \"import time; time.sleep(30)\"")
    assert bg.is_running

    sandbox.kill_process(bg.handle_id)
    time.sleep(0.3)

    # After kill, handle is removed
    snapshot = sandbox.read_process_output(bg.handle_id)
    assert not snapshot.is_running


def test_process_completes_naturally(sandbox):
    """A short-lived background process completes on its own."""
    bg = sandbox.exec_background("echo done_naturally")
    time.sleep(1.0)
    snapshot = sandbox.read_process_output(bg.handle_id)
    assert not snapshot.is_running or "done_naturally" in snapshot.stdout_so_far


def test_stop_kills_all_background_processes(tmp_path):
    """sandbox.stop() must kill all background processes — no zombies."""
    rt = LocalProcessRuntime()
    rt.start(str(tmp_path))
    bg1 = rt.exec_background("python -c \"import time; time.sleep(30)\"")
    bg2 = rt.exec_background("python -c \"import time; time.sleep(30)\"")
    assert len(rt.list_processes()) == 2
    rt.stop()  # must kill all
    # After stop, list is empty
    assert rt.list_processes() == []


# ── Tool dispatcher tests ─────────────────────────────────────────────────────

def test_tool_start_process(executor):
    result = executor.execute({"tool": "start_process",
                               "params": {"command": "python -c \"import time; time.sleep(30)\""}})
    assert result["ok"]
    handle_id = result["data"]["handle_id"]
    assert handle_id.startswith("proc_")
    executor.execute({"tool": "kill_process", "params": {"handle_id": handle_id}})


def test_tool_read_process(executor):
    start = executor.execute({"tool": "start_process",
                              "params": {"command": "echo tool_bg_output"}})
    handle_id = start["data"]["handle_id"]
    time.sleep(0.5)
    result = executor.execute({"tool": "read_process", "params": {"handle_id": handle_id}})
    assert result["ok"]
    assert "tool_bg_output" in result["stdout"]


def test_tool_list_processes(executor):
    executor.execute({"tool": "start_process",
                      "params": {"command": "python -c \"import time; time.sleep(30)\""}})
    result = executor.execute({"tool": "list_processes", "params": {}})
    assert result["ok"]
    assert result["data"]["count"] >= 1


def test_blocking_while_background_runs(executor):
    """Critical: blocking exec() works while background process is running."""
    # Start a long background process
    executor.execute({"tool": "start_process",
                      "params": {"command": "python -c \"import time; time.sleep(30)\""}})
    # Blocking command in parallel must still work
    result = executor.execute({"tool": "execute_command",
                               "params": {"command": "echo blocking_works", "cwd": "."}})
    assert result["ok"]
    assert "blocking_works" in result["stdout"]
