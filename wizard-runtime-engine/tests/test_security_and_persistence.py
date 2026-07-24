"""Security and persistence regression tests.

1. Shell-injection guard — docker.py cwd path traversal rejected
2. Manager disk persistence — state survives process restart
"""
import pytest
from wizard_kernel.world.sandbox.docker import _safe_workdir


# ── Fix 1: Shell injection guard ─────────────────────────────────────────────

class TestSafeWorkdir:
    def test_dot_resolves_to_workspace(self):
        assert _safe_workdir(".") == "/workspace"

    def test_slash_resolves_to_workspace(self):
        assert _safe_workdir("/") == "/workspace"

    def test_normal_cwd_is_under_workspace(self):
        result = _safe_workdir("src")
        assert result == "/workspace/src"

    def test_nested_cwd(self):
        result = _safe_workdir("packages/api")
        assert result == "/workspace/packages/api"

    def test_path_traversal_rejected(self):
        """../../etc/passwd must not reach outside /workspace."""
        with pytest.raises(ValueError, match="escapes /workspace"):
            _safe_workdir("../../etc/passwd")

    def test_absolute_escape_rejected(self):
        with pytest.raises(ValueError, match="escapes /workspace"):
            _safe_workdir("/etc/shadow")

    def test_double_dot_in_subpath_rejected(self):
        with pytest.raises(ValueError, match="escapes /workspace"):
            _safe_workdir("src/../../etc")


# ── Fix 2: Manager disk persistence ──────────────────────────────────────────

def test_manager_persists_on_create(tmp_path, monkeypatch):
    """create() must write meta.json to disk immediately."""
    import os
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    from wizard_kernel.session.manager import InvestigationManager
    from wizard_kernel.contracts.request import InvestigationRequest, InvestigationOptions
    manager = InvestigationManager()
    req = InvestigationRequest(
        repository_path=str(tmp_path),
        intent="verify", targets=["runtime"],
        options=InvestigationOptions(budget=5),
    )
    inv = manager.create(req)
    # meta.json must exist on disk after create
    meta = tmp_path / "investigations" / inv.id / "meta.json"
    assert meta.exists(), "meta.json must be written on create"


def test_manager_restore_from_disk(tmp_path, monkeypatch):
    """After restart, restore() brings investigations back into memory."""
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    from wizard_kernel.session.manager import InvestigationManager
    from wizard_kernel.contracts.request import InvestigationRequest, InvestigationOptions

    # First process: create an investigation
    m1 = InvestigationManager()
    req = InvestigationRequest(
        repository_path=str(tmp_path),
        intent="verify", targets=["runtime"],
        options=InvestigationOptions(budget=5),
    )
    inv = m1.create(req)
    inv_id = inv.id

    # Simulate restart: new manager, call restore()
    m2 = InvestigationManager()
    assert m2.get(inv_id) is None, "new manager starts empty"
    restored = m2.restore()
    assert restored >= 1
    assert m2.get(inv_id) is not None, "restored manager must find the investigation"
    assert m2.get(inv_id).intent == "verify"


def test_manager_persists_on_terminal_state(tmp_path, monkeypatch):
    """update() with completed/failed state must re-persist to disk."""
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    from wizard_kernel.session.manager import InvestigationManager
    from wizard_kernel.session.investigation import Investigation
    from wizard_kernel.contracts.request import InvestigationRequest, InvestigationOptions
    from wizard_kernel.contracts.status import LifecycleState
    import json

    manager = InvestigationManager()
    req = InvestigationRequest(
        repository_path=str(tmp_path),
        intent="verify", targets=["runtime"],
        options=InvestigationOptions(budget=5),
    )
    inv = manager.create(req)

    # Update to completed state — must re-persist
    manager.update(inv.id, state=LifecycleState.completed, last_event="done")
    meta = tmp_path / "investigations" / inv.id / "meta.json"
    data = json.loads(meta.read_text())
    assert data["state"] == LifecycleState.completed


def test_restore_skips_corrupt_dirs(tmp_path, monkeypatch):
    """restore() must not crash on corrupt/incomplete investigation dirs."""
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    from wizard_kernel.session.manager import InvestigationManager
    # Create a broken dir with no meta.json
    broken = tmp_path / "investigations" / "inv_broken"
    broken.mkdir(parents=True)
    (broken / "random.txt").write_text("junk")
    # Should not raise — returns 0 or skips silently
    m = InvestigationManager()
    count = m.restore()
    assert isinstance(count, int)
