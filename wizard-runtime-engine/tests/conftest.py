"""Test isolation for the whole kernel suite, in one place.

Two problems, both caused by tests running against real storage:

1. `fs_store.data_root()` falls back to `<cwd>/.wizard`, and pytest runs from the
   repository root — so the suite was writing every investigation it created into
   the repository's own data directory. It accumulated without bound, and a live
   Engine that calls `restore()` at startup reloads the lot and serves them to
   the user as if they were real investigations.

2. `InvestigationManager` keeps investigations in memory and `get_manager` is
   `lru_cache(maxsize=1)`, so the FIRST test to touch the app's default manager
   handed every later test the same manager, and with it the same store. A test
   could pass on an investigation an unrelated file happened to leave behind.

The root is isolated for the whole session rather than per test, and that is
deliberate: `POST /v1/investigations` starts the run loop on a background thread,
which outlives the test that started it and resolves the data root when it
writes — by which time a per-test override has already been torn down. Per-test
roots therefore protected nothing from exactly the writes that were escaping. A
root that lives as long as the process catches them all. Per-test *state*
isolation is the manager's, and is handled below.

Three test files had noticed problem 1 and worked around it by hand. This does it
for all of them.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _repo_safe_data_root(tmp_path_factory):
    """Point storage at a throwaway directory for the life of the test process.

    Set on the environment rather than through `monkeypatch` because the writers
    that matter — background run loops — read it after their test has finished.
    """
    previous = os.environ.get("WIZARD_DATA_DIR")
    root = tmp_path_factory.mktemp("wizard-data")
    os.environ["WIZARD_DATA_DIR"] = str(root)
    yield root
    if previous is None:
        os.environ.pop("WIZARD_DATA_DIR", None)
    else:
        os.environ["WIZARD_DATA_DIR"] = previous


@pytest.fixture(autouse=True)
def _private_manager():
    """No test inherits another test's investigations.

    Cleared before and after: before, so this test does not see the last one's
    store; after, so the manager this test built — now pointing at state another
    test may reuse — is not handed on.
    """
    # Imported defensively: this conftest also applies to tests that never touch
    # the API, and an import error here would fail collection for the whole suite.
    try:
        from wizard_kernel.api import deps
    except ImportError:  # pragma: no cover - the package is always importable here
        yield
        return
    deps.get_manager.cache_clear()
    yield
    deps.get_manager.cache_clear()
