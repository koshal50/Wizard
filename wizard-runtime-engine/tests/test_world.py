"""Phase 2 tests — Scanner, LocalProcessRuntime, ToolExecutor, ObservationStore."""
import os
import tempfile
from pathlib import Path
import pytest

from wizard_kernel.world.scanner import scan
from wizard_kernel.world.sandbox.local import LocalProcessRuntime
from wizard_kernel.world.tools import ToolExecutor
from wizard_kernel.reality.observations import ObservationStore


# ── Scanner ───────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_repo(tmp_path):
    """Creates a small fake repo tree."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export default {}")
    (tmp_path / "package.json").write_text('{"name":"test","scripts":{"start":"node server.js"}}')
    (tmp_path / "Dockerfile").write_text("FROM node:18\nCOPY . .\n")
    (tmp_path / "README.md").write_text("# Test")
    (tmp_path / "node_modules").mkdir()  # should be pruned
    (tmp_path / "node_modules" / "secret.js").write_text("ignored")
    return tmp_path


def test_scanner_detects_key_files(sample_repo):
    manifest = scan(str(sample_repo), "inv_test")
    assert "package.json" in manifest.key_files
    assert "Dockerfile" in manifest.key_files


def test_scanner_prunes_node_modules(sample_repo):
    manifest = scan(str(sample_repo), "inv_test")
    assert not any("node_modules" in f for f in manifest.directory_tree)


def test_scanner_counts_files(sample_repo):
    manifest = scan(str(sample_repo), "inv_test")
    assert manifest.total_files >= 4  # package.json, Dockerfile, README.md, index.ts


def test_scanner_extension_counts(sample_repo):
    manifest = scan(str(sample_repo), "inv_test")
    assert "ts" in manifest.extensions
    assert manifest.extensions["ts"] >= 1


def test_scanner_never_reads_content(sample_repo):
    """Scanner must not store file contents."""
    manifest = scan(str(sample_repo), "inv_test")
    assert "export default" not in str(manifest.model_dump())


# ── LocalProcessRuntime ───────────────────────────────────────────────────────

@pytest.fixture
def sandbox(tmp_path):
    rt = LocalProcessRuntime()
    rt.start(str(tmp_path))
    yield rt
    rt.stop()


def test_local_sandbox_echo(sandbox, tmp_path):
    result = sandbox.exec("echo hello", ".", timeout_sec=10)
    assert result.ok
    assert "hello" in result.stdout


def test_local_sandbox_exit_code(sandbox):
    result = sandbox.exec("exit 42", ".", timeout_sec=5)
    assert result.exit_code == 42
    assert not result.ok


def test_local_sandbox_read_file(sandbox, tmp_path):
    (tmp_path / "test.txt").write_text("wizard rocks")
    data = sandbox.read_file("test.txt", max_bytes=1024)
    assert b"wizard rocks" in data


def test_local_sandbox_path_traversal(sandbox, tmp_path):
    """Path traversal attempt must raise, not succeed."""
    with pytest.raises((ValueError, AssertionError)):
        sandbox.read_file("../../etc/passwd", max_bytes=100)


def test_local_sandbox_timeout(sandbox):
    result = sandbox.exec("python -c \"import time; time.sleep(10)\"", ".", timeout_sec=1)
    assert not result.ok
    assert "timeout" in result.stderr


# ── ToolExecutor ──────────────────────────────────────────────────────────────

@pytest.fixture
def executor(tmp_path):
    (tmp_path / "data.json").write_text('{"key": "value"}')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')")
    rt = LocalProcessRuntime()
    rt.start(str(tmp_path))
    yield ToolExecutor(rt, str(tmp_path))
    rt.stop()


def test_tool_list_tree(executor):
    result = executor.execute({"tool": "list_tree", "params": {"max_depth": 3}})
    assert result["ok"]
    assert isinstance(result["data"]["tree"], list)


def test_tool_read_file(executor):
    result = executor.execute({"tool": "read_file", "params": {"path": "data.json"}})
    assert result["ok"]
    assert result["data"]["parsed"] == {"key": "value"}


def test_tool_execute_command(executor):
    result = executor.execute({"tool": "execute_command",
                               "params": {"command": "echo wizard", "cwd": "."}})
    assert result["ok"]
    assert "wizard" in result["stdout"]


def test_tool_path_exists_true(executor, tmp_path):
    result = executor.execute({"tool": "path_exists", "params": {"path": "data.json"}})
    assert result["data"]["exists"] is True


def test_tool_path_exists_false(executor):
    result = executor.execute({"tool": "path_exists", "params": {"path": "nope.txt"}})
    assert result["data"]["exists"] is False


def test_tool_unknown_returns_error(executor):
    result = executor.execute({"tool": "hack_system", "params": {}})
    assert not result["ok"]
    assert "unknown tool" in result["error"]


def test_tool_search_files(executor):
    result = executor.execute({"tool": "search_files",
                               "params": {"pattern": "*.py", "glob": "**/*.py"}})
    assert result["ok"]
    assert any("app.py" in m for m in result["data"]["matches"])


# ── ObservationStore ──────────────────────────────────────────────────────────

def test_observation_store_append_is_frozen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = ObservationStore("inv_test")
    obs = store.append(
        node_id="n_001", source_tool="read_file",
        obs_type="file_content", payload={"content": "hi"},
    )
    with pytest.raises(Exception):
        obs.id = "mutated"  # frozen=True


def test_observation_store_all(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = ObservationStore("inv_test2")
    store.append(node_id="n1", source_tool="read_file", obs_type="file_content", payload={})
    store.append(node_id="n2", source_tool="read_file", obs_type="file_content", payload={})
    assert store.count() == 2
    assert all(o.investigation_id == "inv_test2" for o in store.all())


def test_observation_store_unique_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = ObservationStore("inv_test3")
    obs_a = store.append(node_id="n1", source_tool="t", obs_type="file_content", payload={})
    obs_b = store.append(node_id="n2", source_tool="t", obs_type="file_content", payload={})
    assert obs_a.id != obs_b.id
