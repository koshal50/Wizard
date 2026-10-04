import threading

from wizard.cli.tui.session import TuiSession


def test_concurrent_start_creates_one_worker():
    session = TuiSession(family="verify", target="runtime")
    count = 0
    count_lock = threading.Lock()
    barrier = threading.Barrier(3)

    def worker():
        nonlocal count
        with count_lock:
            count += 1

    session._run = worker
    callers = [threading.Thread(target=lambda: (barrier.wait(), session.start())) for _ in range(2)]
    for caller in callers:
        caller.start()
    barrier.wait()
    for caller in callers:
        caller.join()
    session._thread.join(timeout=2)
    assert count == 1
