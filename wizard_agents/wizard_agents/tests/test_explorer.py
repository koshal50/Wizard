from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.common import ExecutionStep, ToolName
from app.contracts.explorer import ExplorerInput, ExplorerOutput, InvestigationNode, Route
from app.explorer.agent import ExplorerAgent, ExplorerAgentError
from app.llm.base import LLMError, LLMProvider
from app.llm.mock_provider import MockLLMProvider
from app.validation.explorer_validation import ExplorerValidationError, validate_explorer_output


def test_valid_node_produces_output(mock_llm, python_project_explorer_input):
    agent = ExplorerAgent(mock_llm)
    output = agent.investigate(python_project_explorer_input)
    assert output.investigation_id == python_project_explorer_input.investigation_id
    assert output.node_id == python_project_explorer_input.current_node.node_id
    assert output.selected_tool in python_project_explorer_input.available_tools
    assert len(output.execution_steps) >= 1


def test_multiple_nodes_context_does_not_break_output(mock_llm, python_project_explorer_input):
    assert len(python_project_explorer_input.nodes) == 2
    agent = ExplorerAgent(mock_llm)
    output = agent.investigate(python_project_explorer_input)
    assert output.node_id == "identify_application_entrypoint"


def test_route_handling_sets_next_node(mock_llm, python_project_explorer_input):
    agent = ExplorerAgent(mock_llm)
    output = agent.investigate(python_project_explorer_input)
    assert output.next_node == "inspect_dependencies"


def test_available_tool_selection_respects_restricted_list(mock_llm, nodejs_project_explorer_input):
    agent = ExplorerAgent(mock_llm)
    output = agent.investigate(nodejs_project_explorer_input)
    assert output.selected_tool in {ToolName.READ_FILE, ToolName.LIST_TREE}


def test_invalid_tool_in_output_is_rejected(python_project_explorer_input):
    bad_output = ExplorerOutput(
        investigation_id=python_project_explorer_input.investigation_id,
        node_id=python_project_explorer_input.current_node.node_id,
        purpose="p",
        reasoning="r",
        selected_tool=ToolName.EXECUTE_COMMAND,
        command="rm -rf /",
        execution_steps=[
            ExecutionStep(
                step_number=1, description="run", tool=ToolName.EXECUTE_COMMAND, parameters={}
            )
        ],
        expected_observation="e",
        success_condition="s",
        failure_condition="f",
    )
    # Restrict available_tools so execute_command is NOT allowed.
    restricted_input = python_project_explorer_input.model_copy(
        update={"available_tools": [ToolName.READ_FILE]}
    )
    with pytest.raises(ExplorerValidationError):
        validate_explorer_output(restricted_input, bad_output)


def test_malformed_llm_response_raises_agent_error(python_project_explorer_input):
    class BrokenProvider(LLMProvider):
        @property
        def name(self) -> str:
            return "broken"

        def generate_structured(self, *args, **kwargs):
            raise LLMError("simulated malformed response")

    agent = ExplorerAgent(BrokenProvider())
    with pytest.raises(ExplorerAgentError):
        agent.investigate(python_project_explorer_input)


def test_missing_required_fields_rejected_by_pydantic():
    with pytest.raises(ValidationError):
        ExplorerOutput(
            investigation_id="inv-1",
            node_id="n1",
            # purpose missing
            reasoning="r",
            selected_tool=ToolName.READ_FILE,
            execution_steps=[
                ExecutionStep(step_number=1, description="x", tool=ToolName.READ_FILE, parameters={})
            ],
            expected_observation="e",
            success_condition="s",
            failure_condition="f",
        )


def test_failed_previous_action_is_accepted_as_context(mock_llm, failed_previous_action_explorer_input):
    agent = ExplorerAgent(mock_llm)
    output = agent.investigate(failed_previous_action_explorer_input)
    assert output.node_id == "identify_application_entrypoint"


def test_next_node_generation_is_none_when_terminal(mock_llm):
    node = InvestigationNode(node_id="only_node", goal="terminal goal")
    route = Route(node_order=["only_node"], current_index=0)
    explorer_input = ExplorerInput(
        investigation_id="inv-terminal", current_node=node, route=route, nodes=[node]
    )
    agent = ExplorerAgent(mock_llm)
    output = agent.investigate(explorer_input)
    assert output.next_node is None


def test_output_validation_rejects_unknown_next_node(python_project_explorer_input):
    output = ExplorerOutput(
        investigation_id=python_project_explorer_input.investigation_id,
        node_id=python_project_explorer_input.current_node.node_id,
        purpose="p",
        reasoning="r",
        selected_tool=ToolName.READ_FILE,
        execution_steps=[
            ExecutionStep(step_number=1, description="x", tool=ToolName.READ_FILE, parameters={})
        ],
        expected_observation="e",
        success_condition="s",
        failure_condition="f",
        next_node="does_not_exist",
    )
    with pytest.raises(ExplorerValidationError):
        validate_explorer_output(python_project_explorer_input, output)


def test_output_validation_rejects_step_count_over_budget(python_project_explorer_input):
    steps = [
        ExecutionStep(step_number=i, description=f"step {i}", tool=ToolName.READ_FILE, parameters={})
        for i in range(1, 6)  # budget is max_steps=3
    ]
    output = ExplorerOutput(
        investigation_id=python_project_explorer_input.investigation_id,
        node_id=python_project_explorer_input.current_node.node_id,
        purpose="p",
        reasoning="r",
        selected_tool=ToolName.READ_FILE,
        execution_steps=steps,
        expected_observation="e",
        success_condition="s",
        failure_condition="f",
    )
    with pytest.raises(ExplorerValidationError):
        validate_explorer_output(python_project_explorer_input, output)


def test_explorer_never_produces_command_without_execute_tool():
    with pytest.raises(ValidationError):
        ExplorerOutput(
            investigation_id="inv-1",
            node_id="n1",
            purpose="p",
            reasoning="r",
            selected_tool=ToolName.READ_FILE,
            command="ls -la",
            execution_steps=[
                ExecutionStep(step_number=1, description="x", tool=ToolName.READ_FILE, parameters={})
            ],
            expected_observation="e",
            success_condition="s",
            failure_condition="f",
        )
