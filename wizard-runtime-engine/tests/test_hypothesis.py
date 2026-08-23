"""Hypothesis evaluator tests — all 7 kinds, deterministic, no LLM."""
from datetime import datetime, timezone
import pytest
from wizard_kernel.contracts.node import (
    Hypothesis, HypothesisKind, InvestigationNode,
)
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.control.hypothesis import evaluate


def _node(kind: HypothesisKind, **kw) -> InvestigationNode:
    return InvestigationNode(
        id="n_001", type="execute",
        action={"tool": "execute_command", "params": {}},
        hypothesis=Hypothesis(kind=kind, **kw),
    )


def _obs(payload: dict) -> Observation:
    return Observation(
        id="obs_001", investigation_id="inv_001", node_id="n_001",
        source_tool="execute_command", obs_type="command_result",
        payload=payload, created_at=datetime.now(timezone.utc),
    )


def test_exit_code_success():
    node = _node(HypothesisKind.exit_code_in, success_values=[0], failure_values=[1, 2])
    assert evaluate(node, _obs({"exit_code": 0})) == "expected_success"


def test_exit_code_failure():
    node = _node(HypothesisKind.exit_code_in, success_values=[0], failure_values=[1, 2])
    assert evaluate(node, _obs({"exit_code": 1})) == "expected_failure"


def test_exit_code_unexpected():
    node = _node(HypothesisKind.exit_code_in, success_values=[0], failure_values=[1])
    assert evaluate(node, _obs({"exit_code": 127})) == "unexpected"


def test_stdout_contains_success():
    node = _node(HypothesisKind.stdout_contains, pattern="added 47 packages")
    assert evaluate(node, _obs({"stdout": "added 47 packages", "exit_code": 0})) == "expected_success"


def test_stdout_contains_unexpected():
    node = _node(HypothesisKind.stdout_contains, pattern="added 47 packages")
    assert evaluate(node, _obs({"stdout": "error: ENOENT", "exit_code": 0})) == "unexpected"


def test_file_exists_success():
    node = _node(HypothesisKind.file_exists)
    assert evaluate(node, _obs({"exists": True})) == "expected_success"


def test_file_exists_failure():
    node = _node(HypothesisKind.file_exists)
    assert evaluate(node, _obs({"exists": False})) == "expected_failure"


def test_always_success():
    node = _node(HypothesisKind.always_success)
    assert evaluate(node, _obs({"anything": True})) == "expected_success"


def test_manual_escalate():
    node = _node(HypothesisKind.manual_escalate)
    assert evaluate(node, _obs({"anything": True})) == "unexpected"


def test_http_status_success():
    node = _node(HypothesisKind.http_status, success_values=[200, 201], failure_values=[404])
    assert evaluate(node, _obs({"status_code": 200})) == "expected_success"


def test_http_status_failure():
    node = _node(HypothesisKind.http_status, success_values=[200], failure_values=[404])
    assert evaluate(node, _obs({"status_code": 404})) == "expected_failure"
