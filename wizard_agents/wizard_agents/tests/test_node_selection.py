import pytest
from app.contracts.explorer import ExplorerOutput
from app.llm.vllm_provider import _strict_explorer_schema
from app.validation.explorer_validation import validate_explorer_output, ExplorerValidationError
from app.prompts.explorer_prompts import build_explorer_user_prompt


def test_schema_binds_dispatch_ids(python_project_explorer_input):
    data = python_project_explorer_input
    schema = _strict_explorer_schema(ExplorerOutput.model_json_schema(), {'input': data.model_dump(mode='json')})
    assert schema['properties']['node_id']['enum'] == [data.current_node.node_id]
    assert schema['properties']['investigation_id']['enum'] == [data.investigation_id]
    assert 'node_id' in schema['required']
    assert schema['additionalProperties'] is False


def test_history_is_not_selectable(python_project_explorer_input):
    data = python_project_explorer_input
    data.plan = {'completed_nodes': [{'id': 'old-node'}], 'runnable_next_nodes': [{'id': 'future-node'}]}
    data.node_selection = {'valid_node_ids': [data.current_node.node_id]}
    prompt = build_explorer_user_prompt(data)
    assert 'valid_node_ids' in prompt and 'completed_nodes' in prompt
    for invalid in ['old-node', 'future-node', 'invented']:
        output = ExplorerOutput(investigation_id=data.investigation_id, node_id=invalid,
                                tool_request={'tool': 'read_file', 'parameters': {'path': 'README.md'}})
        with pytest.raises(ExplorerValidationError, match='node_id mismatch'):
            validate_explorer_output(data, output)


def test_verifier_strict_schema_does_not_require_explorer_node():
    from app.contracts.verification import VerificationOutput
    schema = _strict_explorer_schema(VerificationOutput.model_json_schema(), {})
    assert 'report_markdown' in schema['required']
    assert schema['additionalProperties'] is False
    assert 'node_id' not in schema['properties']
