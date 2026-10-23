import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.session.architecture import export_architecture
from wizard_kernel.storage import fs_store


def test_architecture_predicates_cannot_hide_multiline_content_with_control_characters():
    from wizard_kernel.contracts.verification import ArchitectureFinding
    with pytest.raises(ValidationError):
        ArchitectureFinding.model_validate({"area": "structure", "summary": "Workspace", "assertions": [{
            "source": "repository", "field": "content", "operator": "contains", "target": "package.json",
            "expected": '"workspaces": \x00"server"'}]})


def test_export_uses_observations_not_task_graph_and_preserves_proof_lines(tmp_path):
    inv = SimpleNamespace(id="inv_export", repository_path=str(tmp_path), state=LifecycleState.completed)
    fs_store.write_observation(inv.id, 1, {"id": "obs_api", "success": True, "source_tool": "read_file",
        "payload": {"data": {"path": str(tmp_path / "src" / "api.py"), "content": "# API\nfrom storage import save\n"}}})
    fs_store.write_observation(inv.id, 2, {"id": "obs_storage", "success": True, "source_tool": "read_file",
        "payload": {"data": {"path": "storage.py", "content": "def save(): pass"}}})
    fs_store.write_observation(inv.id, 3, {"id": "obs_failed", "success": False, "source_tool": "read_file",
        "payload": {"data": {"path": "secret.py", "content": "unusable"}}})
    fs_store.write(inv.id, "verification.json", {"results": {"check": {"assertions": [{
        "observation_id": "obs_api", "verdict": "passed", "assertion": {"field": "content", "operator": "contains", "expected": "from storage import save"}}]}},
        "architecture_diagram": {"components": [
            {"id": "api", "label": "API", "type": "service", "path": "src/", "description": "API entry", "observation_ids": ["obs_api"]},
            {"id": "storage", "label": "Storage", "type": "module", "path": "storage.py", "description": "Storage postgres://local:secret@database/app adapter", "observation_ids": ["obs_storage"]},
            {"id": "invented", "label": "Invented", "type": "module", "path": "secret.py", "description": "Unproven", "observation_ids": ["obs_failed"]}],
            "connections": [{"id": "uses", "source": "api", "target": "storage", "type": "USES", "description": "API imports storage", "observation_ids": ["obs_api"]},
                            {"id": "invalid", "source": "api", "target": "invented", "type": "USES", "description": "Unsupported", "observation_ids": ["obs_failed"]}]}})
    graph = export_architecture(inv)
    assert graph["status"] == "completed"
    assert len(graph["nodes"]) == 2 and len(graph["relationships"]) == 1
    assert graph["relationships"][0]["classification"] == "inferred"
    assert graph["evidence"][0]["line_start"] == 2
    assert str(tmp_path) not in json.dumps(graph) and "unusable" not in json.dumps(graph)
    assert "local:secret" not in json.dumps(graph)
    assert all(e["classification"] == "observed" for e in graph["evidence"])


def test_older_results_show_only_observed_files_without_invented_connections(tmp_path):
    inv = SimpleNamespace(id="inv_old_export", repository_path=str(tmp_path), state=LifecycleState.incomplete)
    fs_store.write_observation(inv.id, 1, {"id": "obs", "success": True, "source_tool": "read_file",
        "payload": {"data": {"path": "src/api.py", "content": "private source not uploaded"}}})
    fs_store.write(inv.id, "investigation_graph.json", [{"id": "task", "depends_on": ["scanner"]}])
    graph = export_architecture(inv)
    assert graph["nodes"][0]["path"] == "src/api.py"
    assert graph["relationships"] == [] and graph["status"] == "incomplete"
    assert "private source" not in json.dumps(graph)


def test_action_labels_do_not_claim_behavior_beyond_the_relation_kind():
    from wizard_kernel.session.architecture import action_label
    assert action_label('http','auth HTTP') == 'requests auth API'
    assert action_label('query','auth DB queries') == 'queries auth DB'
    assert action_label('imports','imports module') == 'imports module'
    assert action_label('unknown','shared contract') == 'shared contract'
